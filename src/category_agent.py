import json
import logging
import os
import time
from typing import Dict, List, Any, Set, Tuple

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.utils.cost_tracker import CostTracker, estimate_tokens_from_string
from src.utils.timer import timeout, WallTimeTracker


class CategoryResearchAgent:
    """Agent for researching a specific category using OpenAI's Agents API."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        cost_tracker: CostTracker,
        wall_time_tracker: WallTimeTracker,
        model: str = "o3",
        list_title: str = "",
    ):
        """Initialize the category research agent.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            cost_tracker: Cost tracker instance
            wall_time_tracker: Wall time tracker instance
            model: Model to use for research
            list_title: Title of the awesome list
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

    def set_category_examples(self, category_examples: Dict[str, List[Dict]]):
        """Set examples of existing resources for each category.

        Args:
            category_examples: Dictionary mapping category names to lists of example resources
        """
        self.category_examples = category_examples
        self.logger.info(f"Loaded examples for {len(category_examples)} categories")

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
        self.logger.info(f"Starting research for category: {category}")
        self.logger.info(f"Using search terms: {search_terms}")

        # Create a clean set of URLs to exclude
        exclude_urls_set = set(exclude_urls)

        # Store all discovered resources
        all_resources = []

        # Get examples for this category if available
        category_examples_str = ""
        if category in self.category_examples and self.category_examples[category]:
            examples = self.category_examples[category]
            example_items = []
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

        # Process each search term
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

            self.logger.info(f"Researching term [{term_idx+1}/{len(search_terms)}]: '{contextualized_term}'")

            try:
                # Use chat completions instead of assistants API
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

                user_message = (
                    f"Research the term '{contextualized_term}' in the context of '{category}'. "
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
                    continue

                # Make the API call
                # Don't use temperature parameter for o3 model
                api_params = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message}
                    ],
                }

                # Only add temperature for non-o3 models
                if self.model != "o3":
                    api_params["temperature"] = 0.7

                response = self.client.chat.completions.create(**api_params)

                # Log the API call
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

                # Add discovered resources to the list
                for resource in resources:
                    # Skip resources with URLs in the exclude list
                    if resource.get("url") in exclude_urls_set:
                        continue

                    # Add to the exclude set to avoid duplicates in future terms
                    exclude_urls_set.add(resource.get("url"))

                    # Add the resource to the results
                    all_resources.append(resource)

                # Log progress
                self.logger.info(
                    f"Term '{term}' research complete: {len(resources)} resources found, "
                    f"{len(all_resources)} total unique resources so far."
                )

            except Exception as e:
                self.logger.error(f"Error researching term '{term}': {str(e)}")

        # Save the results to a file
        self._save_results(category, all_resources)

        return all_resources

    def _parse_results_from_content(self, content: str) -> List[Dict]:
        """Parse the results from the content.

        Args:
            content: The content to parse

        Returns:
            List of discovered resources
        """
        resources = []

        try:
            # Look for patterns like "Title: X\nURL: Y\nDescription: Z"
            lines = content.split('\n')
            current_resource = {}

            for line in lines:
                line = line.strip()

                if line.startswith("Title:") or line.startswith("- Title:"):
                    # Save the previous resource if we have a complete one
                    if current_resource.get("name") and current_resource.get("url"):
                        # Ensure we have a description
                        if "description" not in current_resource:
                            current_resource["description"] = ""

                        resources.append(current_resource)

                    # Start a new resource
                    current_resource = {"name": line.split(":", 1)[1].strip()}

                elif line.startswith("URL:") or line.startswith("- URL:"):
                    if current_resource:  # Only if we have a current resource
                        current_resource["url"] = line.split(":", 1)[1].strip()

                elif line.startswith("Description:") or line.startswith("- Description:"):
                    if current_resource:  # Only if we have a current resource
                        description = line.split(":", 1)[1].strip()
                        # Truncate description to max 100 characters
                        current_resource["description"] = description[:100]

            # Add the last resource if it's complete
            if current_resource.get("name") and current_resource.get("url"):
                # Ensure we have a description
                if "description" not in current_resource:
                    current_resource["description"] = ""

                resources.append(current_resource)

        except Exception as e:
            self.logger.error(f"Error parsing results: {str(e)}")

        self.logger.info(f"Parsed {len(resources)} resources from response")
        return resources

    def _save_results(self, category: str, resources: List[Dict]) -> str:
        """Save the research results to a JSON file.

        Args:
            category: Category name
            resources: List of discovered resources

        Returns:
            Path to the saved JSON file
        """
        # Create a safe filename
        safe_category = "".join(c if c.isalnum() else "_" for c in category.lower())
        output_path = os.path.join(self.output_dir, f"candidate_{safe_category}.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(resources, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved {len(resources)} resources for '{category}' to {output_path}")
        return output_path
