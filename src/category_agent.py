import json
import logging
import os
import re
import time
import asyncio
from typing import Dict, List, Any, Set, Tuple, Optional
from urllib.parse import urlparse
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.utils.cost_tracker import CostTracker, estimate_tokens_from_string
from src.utils.timer import timeout, WallTimeTracker
import src.logger as log


class CategoryResearchAgent:
    """Agent for researching a specific category using OpenAI's Agents API."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        cost_tracker: CostTracker,
        wall_time_tracker: WallTimeTracker,
        model: str = "gpt-4o",
        list_title: str = "",
        max_retries: int = 3,
    ):
        """Initialize the category research agent.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            cost_tracker: Cost tracker instance
            wall_time_tracker: Wall time tracker instance
            model: Model to use for research
            list_title: Title of the awesome list
            max_retries: Maximum number of retries for failed operations
        """
        self.logger = logger
        self.output_dir = output_dir
        self.cost_tracker = cost_tracker
        self.wall_time_tracker = wall_time_tracker
        self.model = model
        self.client = OpenAI()
        self._logged_step_ids = set()
        self.list_title = list_title
        self.category_examples = {}  # Will store examples of resources for each category
        self.max_retries = max_retries
        self.cost_timer = log.CostTimer()
        self.run_dir = Path(output_dir)

    def set_category_examples(self, category_examples: Dict[str, List[Dict]]):
        """Set examples of existing resources for each category.

        Args:
            category_examples: Dictionary mapping category names to lists of example resources
        """
        self.category_examples = category_examples
        self.logger.info(f"Loaded examples for {len(category_examples)} categories")

    async def research_category_async(
        self, category: str, search_terms: List[str], exclude_urls: List[str]
    ) -> List[Dict]:
        """Research a category asynchronously using the provided search terms.

        Args:
            category: Category name
            search_terms: List of search terms
            exclude_urls: List of URLs to exclude from results

        Returns:
            List of discovered resources
        """
        with log.log_phase("research_category", self.run_dir, self.cost_timer, {"category": category}):
            self.logger.info(f"Starting async research for category: {category}")
            self.logger.info(f"Using search terms: {search_terms}")

            # Create a clean set of URLs to exclude
            exclude_urls_set = set(exclude_urls)

            # Warn if exclude_urls is empty
            if not exclude_urls_set:
                self.logger.warning(f"No URLs provided to exclude for category: {category}. This may result in rediscovering existing resources.")

            # Get examples for this category if available
            category_examples_str = self._prepare_category_examples(category, exclude_urls_set)

            # Create tasks for each search term
            tasks = []
            for term_idx, term in enumerate(search_terms):
                if self.wall_time_tracker.is_expired():
                    self.logger.warning(f"Wall time limit reached. Stopping research for category: {category}")
                    break

                if self.cost_tracker.would_exceed_ceiling(self.model, 2000):  # Conservative estimate
                    self.logger.warning(f"Cost ceiling would be exceeded. Stopping research for category: {category}")
                    break

                # Add list title to search terms if available
                contextualized_term = term
                if self.list_title and not self.list_title.lower() in term.lower():
                    contextualized_term = f"{term} {self.list_title}"

                # Create a task for this term
                task = self._research_term_with_retry(
                    category=category,
                    term=contextualized_term,
                    term_idx=term_idx,
                    total_terms=len(search_terms),
                    category_examples_str=category_examples_str
                )
                tasks.append(task)

            # Execute all tasks concurrently and gather results
            results = await asyncio.gather(*tasks)

            # Flatten the results and filter out None values
            all_resources = [resource for sublist in results if sublist for resource in sublist]

            # Filter out resources with URLs in the exclude list
            filtered_resources = [
                resource for resource in all_resources
                if resource.get("url", "") and resource.get("url", "") not in exclude_urls_set
            ]

            # Add category information to resources
            for resource in filtered_resources:
                resource["category"] = category

            # Save the results to a file
            self._save_results(category, filtered_resources)

            return filtered_resources

    def research_category(
        self, category: str, search_terms: List[str], exclude_urls: List[str]
    ) -> List[Dict]:
        """Research a category using the provided search terms.

        Args:
            category: Category name
            search_terms: List of search terms
            exclude_urls: List of URLs to exclude from results

        Returns:
            List of discovered resources
        """
        # Use asyncio.run to execute the async method
        return asyncio.run(self.research_category_async(category, search_terms, exclude_urls))

    def research_categories(
        self, research_plan: Dict[str, Dict]
    ) -> Dict[str, List[Dict]]:
        """Research multiple categories concurrently.

        Args:
            research_plan: Dictionary mapping category names to research plans

        Returns:
            Dictionary mapping category names to discovered resources
        """
        with log.log_phase("research_all_categories", self.run_dir, self.cost_timer):
            self.logger.info(f"Starting research for {len(research_plan)} categories")

            async def _research_all_categories():
                tasks = []
                for category, plan in research_plan.items():
                    if self.wall_time_tracker.is_expired():
                        self.logger.warning(f"Wall time limit reached. Stopping research for remaining categories")
                        break

                    if self.cost_tracker.would_exceed_ceiling(self.model, 5000):  # Conservative estimate
                        self.logger.warning(f"Cost ceiling would be exceeded. Stopping research for remaining categories")
                        break

                    task = self.research_category_async(
                        category=category,
                        search_terms=plan["search_terms"],
                        exclude_urls=plan.get("exclude_urls", [])
                    )
                    tasks.append((category, task))

                # Execute all tasks concurrently
                results = {}
                for category, task in tasks:
                    try:
                        results[category] = await task
                    except Exception as e:
                        self.logger.error(f"Error researching category '{category}': {str(e)}")
                        results[category] = []

                return results

            # Use asyncio.run to execute the async method
            return asyncio.run(_research_all_categories())

    def _prepare_category_examples(self, category: str, exclude_urls_set: Set[str]) -> str:
        """Prepare examples string for a category and update exclude URLs.

        Args:
            category: Category name
            exclude_urls_set: Set of URLs to exclude (updated in-place)

        Returns:
            String with category examples
        """
        category_examples_str = ""
        if category in self.category_examples and self.category_examples[category]:
            examples = self.category_examples[category]
            example_items = []

            # Add example URLs to exclude_urls_set to prevent rediscovery
            for example in examples:
                example_url = example.get("url", "")
                if example_url and self._is_valid_url(example_url):
                    exclude_urls_set.add(example_url)

            for i, example in enumerate(examples[:3]):  # Limit to 3 examples to avoid token overload
                name = example.get("name", "")
                url = example.get("url", "")
                desc = example.get("description", "")
                if name and url:
                    example_items.append(f"{i+1}. {name}: {desc} - {url}")

            if example_items:
                category_examples_str = (
                    "Here are examples of existing resources in this category:\n" +
                    "\n".join(example_items) +
                    "\n\nFind similar high-quality resources that are not already in the list."
                )

            self.logger.info(f"Added {len(examples)} example URLs to exclude list for category: {category}")

        return category_examples_str

    async def _research_term_with_retry(
        self,
        category: str,
        term: str,
        term_idx: int,
        total_terms: int,
        category_examples_str: str,
    ) -> List[Dict]:
        """Research a term with retry logic.

        Args:
            category: Category name
            term: Search term
            term_idx: Index of the term in the search terms list
            total_terms: Total number of search terms
            category_examples_str: Category examples string

        Returns:
            List of discovered resources
        """
        self.logger.info(f"Researching term [{term_idx+1}/{total_terms}]: '{term}'")

        retries = 0
        last_error = None

        while retries < self.max_retries:
            try:
                resources = await self._research_term(
                    category=category,
                    term=term,
                    term_idx=term_idx,
                    retries=retries,
                    category_examples_str=category_examples_str
                )

                # Log the successful result
                self.logger.info(
                    f"Term '{term}' research complete after {retries} retries: {len(resources)} resources found."
                )

                # Log completion via research logger
                log._LOGGER.info(json.dumps({
                    "phase": "query_complete",
                    "category": category,
                    "term_idx": term_idx,
                    "retry_idx": retries,
                    "results_count": len(resources)
                }))

                return resources

            except Exception as e:
                retries += 1
                last_error = e
                wait_time = 2 ** retries  # Exponential back-off

                self.logger.warning(
                    f"Error researching term '{term}' (attempt {retries}/{self.max_retries}): {str(e)}. "
                    f"Retrying in {wait_time} seconds..."
                )

                # Log retry via research logger
                log._LOGGER.info(json.dumps({
                    "phase": "query_retry",
                    "category": category,
                    "term_idx": term_idx,
                    "retry_idx": retries,
                    "error": str(e),
                    "wait_time": wait_time
                }))

                await asyncio.sleep(wait_time)

        # If we get here, all retries failed
        self.logger.error(f"Failed to research term '{term}' after {self.max_retries} attempts: {str(last_error)}")

        # Log failure via research logger
        log._LOGGER.info(json.dumps({
            "phase": "query_failed",
            "category": category,
            "term_idx": term_idx,
            "retry_idx": self.max_retries,
            "error": str(last_error)
        }))

        return []

    async def _research_term(
        self,
        category: str,
        term: str,
        term_idx: int,
        retries: int,
        category_examples_str: str,
    ) -> List[Dict]:
        """Research a single term.

        Args:
            category: Category name
            term: Search term
            term_idx: Term index
            retries: Number of retries so far
            category_examples_str: Category examples string

        Returns:
            List of discovered resources
        """
        # Prepare system message
        system_message = (
            f"You are a research assistant specializing in finding high-quality resources related to {category} "
            f"in the context of {self.list_title or 'programming and technology'}. "
            f"Your task is to discover new, valuable resources (libraries, tools, frameworks, articles, etc.) "
            f"that would make excellent additions to an Awesome List. "
            f"\n\n"
            f"Requirements for discovered resources:"
            f"\n1. Must be high-quality, well-maintained, and relevant to {category} within the domain of {self.list_title or 'technology'}"
            f"\n2. Should have an informative title and URL"
            f"\n3. Must include a concise description (max 100 characters)"
            f"\n4. Must be presented in a consistent format for each resource"
            f"\n\n"
            f"For each resource, provide:"
            f"\n- Title: The name of the resource"
            f"\n- URL: The direct link to the resource"
            f"\n- Description: A brief description (max 100 characters)"
        )

        # Prepare user message
        user_message = (
            f"Research the term '{term}' in the context of '{category}'. "
            f"Find high-quality resources, tools, libraries, frameworks, articles, or projects that are "
            f"relevant to this topic and would be valuable additions to an awesome list. "
        )

        # Add examples if available
        if category_examples_str:
            user_message += f"\n\n{category_examples_str}\n\n"

        user_message += (
            f"For each resource, provide the title, URL, and a concise description (maximum 100 characters). "
            f"Return the results in a structured format with Title, URL, and Description for each resource."
        )

        # Estimate tokens
        estimated_tokens = estimate_tokens_from_string(system_message + user_message) * 2

        if self.cost_tracker.would_exceed_ceiling(self.model, estimated_tokens):
            self.logger.warning(f"Cost ceiling would be exceeded. Skipping term '{term}'")
            return []

        # Make the API call
        # Don't use temperature parameter for gpt-4o model
        api_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
        }

        # Only add temperature for non-gpt-4o models
        if "gpt-4o" not in self.model:
            api_params["temperature"] = 0.7

        # Timing start
        start_time = time.perf_counter()

        # Make the API call with timeout
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.chat.completions.create(**api_params)
        )

        # Calculate latency and add tokens to cost timer
        latency_ms = round((time.perf_counter() - start_time) * 1000)
        self.cost_timer.add_tokens(response.usage.total_tokens)

        # Log the API call with detailed info for research logger
        log._LOGGER.info(json.dumps({
            "phase": "query",
            "category": category,
            "term_idx": term_idx,
            "retry_idx": retries,
            "query": term,
            "prompt_excerpt": system_message[:200],
            "completion_excerpt": response.choices[0].message.content[:200],
            "latency_ms": latency_ms,
            "tokens": response.usage.total_tokens,
            "cost_usd": self.cost_tracker.get_cost_for_tokens(self.model, response.usage.total_tokens)
        }))

        # Log the API call for regular logger
        from src.utils.logger import log_api_call
        log_api_call(
            logger=self.logger,
            agent=f"category_agent:{category.lower()}",
            event=f"research_term",
            model=self.model,
            tokens=response.usage.total_tokens,
            cost_usd=self.cost_tracker.add_usage(
                self.model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            ),
            prompt={
                "system": system_message,
                "user": user_message
            },
            completion=response.choices[0].message.content
        )

        # Parse the results
        content = response.choices[0].message.content
        resources = self._parse_results_from_content(content)

        return resources

    def _parse_results_from_content(self, content: str) -> List[Dict]:
        """Parse the results from the content.

        Args:
            content: The content to parse

        Returns:
            List of discovered resources
        """
        resources = []

        try:
            # First attempt: Try to parse as JSON if content appears to be JSON
            json_resources = self._try_parse_json(content)
            if json_resources:
                self.logger.info(f"Successfully parsed content as JSON, found {len(json_resources)} resources")
                return json_resources

            # Second attempt: Try to parse using regex patterns for different formats
            regex_resources = self._try_parse_with_regex(content)
            if regex_resources:
                self.logger.info(f"Successfully parsed content with regex, found {len(regex_resources)} resources")
                return regex_resources

            # Third attempt: Fall back to line-by-line parsing (original method)
            resources = self._parse_line_by_line(content)

        except Exception as e:
            self.logger.error(f"Error parsing results: {str(e)}")

        self.logger.info(f"Parsed {len(resources)} resources from response")
        return resources

    def _try_parse_json(self, content: str) -> List[Dict]:
        """Try to parse the content as JSON.

        Args:
            content: The content to parse

        Returns:
            List of resources if successful, empty list otherwise
        """
        resources = []
        # Look for JSON-like content (anything between [ ] or { })
        json_pattern = r'(\[[\s\S]*\]|\{[\s\S]*\})'
        json_matches = re.findall(json_pattern, content)

        for json_str in json_matches:
            try:
                data = json.loads(json_str)

                # Handle different JSON structures
                if isinstance(data, list):
                    for item in data:
                        resource = self._normalize_resource_dict(item)
                        if resource:
                            resources.append(resource)
                elif isinstance(data, dict):
                    # Check if this is a single resource or a container
                    if any(key.lower() in ['name', 'title', 'url'] for key in data.keys()):
                        resource = self._normalize_resource_dict(data)
                        if resource:
                            resources.append(resource)
                    else:
                        # Might be a container with multiple resources
                        for key, value in data.items():
                            if isinstance(value, dict):
                                resource = self._normalize_resource_dict(value)
                                if resource:
                                    resources.append(resource)
                            elif isinstance(value, list):
                                for item in value:
                                    if isinstance(item, dict):
                                        resource = self._normalize_resource_dict(item)
                                        if resource:
                                            resources.append(resource)
            except json.JSONDecodeError:
                continue  # Not valid JSON, move to next match

            # If we found resources, return them
            if resources:
                return resources

        return []

    def _try_parse_with_regex(self, content: str) -> List[Dict]:
        """Try to parse content using various regex patterns.

        Args:
            content: The content to parse

        Returns:
            List of resources if successful, empty list otherwise
        """
        resources = []

        # Pattern to match multi-line resources with various prefixes
        # This handles numbered lists, bullet points, etc.
        resource_pattern = r'(?:^|\n)(?:\d+\.|\*|\-|\+)?\s*(?:[Tt]itle|[Nn]ame)\s*:(.+?)(?:\n|\r\n?)(?:\d+\.|\*|\-|\+)?\s*(?:[Uu][Rr][Ll])\s*:(.+?)(?:\n|\r\n?)(?:\d+\.|\*|\-|\+)?\s*(?:[Dd]escription)\s*:(.+?)(?:\n\n|\n(?=\d+\.|\*|\-|\+|\Z)|$)'

        # Alternative pattern for bulleted list items
        bulleted_pattern = r'(?:^|\n)(?:\d+\.|\*|\-|\+)?\s*\[([^\]]+)\]\(([^)]+)\)(?:\s*[-–]\s*|\s*:\s*)(.+?)(?=\n(?:\d+\.|\*|\-|\+)|\n\n|\Z)'

        # Alternative pattern for resource blocks with no specific prefix/format
        block_pattern = r'(?:^|\n)((?:[A-Z][A-Za-z0-9\s]+){1,4})(?:\s*[-–:]\s*)(.+?)(?:\n|\r\n?)(?:(?:https?:\/\/|www\.)[^\s]+)(?:\s*[-–:]\s*)(.+?)(?=\n\n|\Z)'

        # Try the main pattern first
        matches = re.finditer(resource_pattern, content, re.DOTALL)
        for match in matches:
            name = match.group(1).strip()
            url = match.group(2).strip()
            description = match.group(3).strip()

            if name and url:
                resources.append({
                    "name": name,
                    "url": url,
                    "description": description[:100] if description else ""
                })

        # If no matches, try the bulleted pattern
        if not resources:
            matches = re.finditer(bulleted_pattern, content, re.DOTALL)
            for match in matches:
                name = match.group(1).strip()
                url = match.group(2).strip()
                description = match.group(3).strip()

                if name and url:
                    resources.append({
                        "name": name,
                        "url": url,
                        "description": description[:100] if description else ""
                    })

        # If still no matches, try the block pattern
        if not resources:
            matches = re.finditer(block_pattern, content, re.DOTALL)
            for match in matches:
                name = match.group(1).strip()
                url_desc = match.group(2).strip()
                extra = match.group(3).strip()

                # Try to extract URL from the second group using regex
                url_match = re.search(r'(https?://\S+)', url_desc)
                url = url_match.group(1) if url_match else ""

                # If no URL found in second group, try the third group
                if not url:
                    url_match = re.search(r'(https?://\S+)', extra)
                    url = url_match.group(1) if url_match else ""

                # Set description based on which group contained the URL
                description = extra if url_match and url_match.group(1) in url_desc else url_desc

                if name and url:
                    resources.append({
                        "name": name,
                        "url": url,
                        "description": description[:100] if description else ""
                    })

        return resources

    def _parse_line_by_line(self, content: str) -> List[Dict]:
        """Parse content line by line (original method).

        Args:
            content: The content to parse

        Returns:
            List of resources
        """
        resources = []
        lines = content.split('\n')
        current_resource = {}

        # Common prefixes that might appear before title/url/description
        prefixes = ['', '- ', '* ', '+ ', '1. ', '2. ', '3. ', '4. ', '5. ', '6. ', '7. ', '8. ', '9. ', '10. ']

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for title/name in various formats
            title_match = False
            for prefix in prefixes:
                for title_key in ['Title:', 'Name:']:
                    if line.startswith(f"{prefix}{title_key}"):
                        # Save previous resource if complete
                        if current_resource.get("name") and current_resource.get("url"):
                            if "description" not in current_resource:
                                current_resource["description"] = ""
                            resources.append(current_resource.copy())

                        # Start new resource
                        title_value = line[len(prefix)+len(title_key):].strip()
                        current_resource = {"name": title_value}
                        title_match = True
                        break
                if title_match:
                    break

            # If not a title, check for URL
            if not title_match:
                url_match = False
                for prefix in prefixes:
                    if line.startswith(f"{prefix}URL:"):
                        if current_resource:  # Only if we have a current resource
                            current_resource["url"] = line[len(prefix)+4:].strip()
                            url_match = True
                            break

                # If not a URL, check for description
                if not url_match:
                    for prefix in prefixes:
                        if line.startswith(f"{prefix}Description:"):
                            if current_resource:  # Only if we have a current resource
                                description = line[len(prefix)+12:].strip()
                                # Truncate description to max 100 characters
                                current_resource["description"] = description[:100]
                                break

        # Add the last resource if it's complete
        if current_resource.get("name") and current_resource.get("url"):
            if "description" not in current_resource:
                current_resource["description"] = ""
            resources.append(current_resource)

        return resources

    def _normalize_resource_dict(self, data: Dict) -> Dict:
        """Normalize resource dictionary keys to standard format.

        Args:
            data: Dictionary containing resource data

        Returns:
            Normalized resource dictionary or None if invalid
        """
        if not isinstance(data, dict):
            return None

        # Map common key variations to our standard keys
        key_mappings = {
            'name': ['name', 'title', 'resource', 'tool'],
            'url': ['url', 'link', 'href'],
            'description': ['description', 'desc', 'summary', 'about']
        }

        result = {}

        # Process each of our standard keys
        for std_key, possible_keys in key_mappings.items():
            # Look for matching keys in data (case-insensitive)
            for key in data:
                if key.lower() in possible_keys:
                    result[std_key] = data[key]
                    break

        # Ensure we have at least name and url
        if 'name' not in result or 'url' not in result:
            return None

        # Ensure we have a description (even if empty)
        if 'description' not in result:
            result['description'] = ""

        # Truncate description to 100 characters
        result['description'] = result['description'][:100]

        return result

    def _save_results(self, category: str, resources: List[Dict]) -> str:
        """Save research results to a JSON file.

        Args:
            category: Category name
            resources: List of discovered resources

        Returns:
            Path to the saved JSON file
        """
        # Sanitize category name for filename
        category_filename = re.sub(r'[^a-zA-Z0-9_-]', '_', category.lower())
        output_path = os.path.join(self.output_dir, f"candidate_{category_filename}.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(resources, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved {len(resources)} resources for category '{category}' to {output_path}")
        return output_path

    def _is_valid_url(self, url: str) -> bool:
        """Check if a URL is valid.

        Args:
            url: URL to check

        Returns:
            True if URL is valid, False otherwise
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
