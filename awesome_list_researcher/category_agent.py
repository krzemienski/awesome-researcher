"""
Category research agent for finding new resources.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Union

from openai import OpenAI

from awesome_list_researcher.awesome_parser import AwesomeLink
from awesome_list_researcher.planner_agent import ResearchQuery
from awesome_list_researcher.utils.cost_guard import CostGuard
from awesome_list_researcher.utils.logging import APICallLogRecord


@dataclass
class ResearchCandidate:
    """
    A candidate resource discovered during research.
    """
    name: str
    url: str
    description: str
    category: str
    subcategory: Optional[str] = None
    source_query: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "category": self.category,
        }

        if self.subcategory:
            result["subcategory"] = self.subcategory

        if self.source_query:
            result["source_query"] = self.source_query

        return result

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResearchCandidate':
        """Create from dictionary."""
        return cls(
            name=data["name"],
            url=data["url"],
            description=data["description"],
            category=data["category"],
            subcategory=data.get("subcategory"),
            source_query=data.get("source_query")
        )

    def to_awesome_link(self) -> AwesomeLink:
        """Convert to AwesomeLink."""
        return AwesomeLink(
            name=self.name,
            url=self.url,
            description=self.description,
            category=self.category,
            subcategory=self.subcategory
        )


@dataclass
class ResearchResult:
    """
    Results of researching a query.
    """
    query: str
    category: str
    subcategory: Optional[str]
    candidates: List[ResearchCandidate] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "category": self.category,
            "subcategory": self.subcategory,
            "candidates": [c.to_dict() for c in self.candidates],
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResearchResult':
        """Create from dictionary."""
        result = cls(
            query=data["query"],
            category=data["category"],
            subcategory=data.get("subcategory"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )

        result.candidates = [
            ResearchCandidate.from_dict(c)
            for c in data.get("candidates", [])
        ]

        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> 'ResearchResult':
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class CategoryResearchAgent:
    """
    Agent for researching new resources for a category.
    """

    def __init__(
        self,
        model: str,
        api_client: OpenAI,
        cost_guard: CostGuard,
        logger: logging.Logger
    ):
        """
        Initialize the category research agent.

        Args:
            model: OpenAI model to use
            api_client: OpenAI client
            cost_guard: Cost guard for tracking API costs
            logger: Logger instance
        """
        self.model = model
        self.api_client = api_client
        self.cost_guard = cost_guard
        self.logger = logger

    def research_query(self, query: ResearchQuery) -> ResearchResult:
        """
        Research a query to find new resources.

        Args:
            query: ResearchQuery instance

        Returns:
            ResearchResult instance with candidate resources
        """
        self.logger.info(
            f"Researching query: '{query.query}' for category: {query.category}"
            + (f", subcategory: {query.subcategory}" if query.subcategory else "")
        )

        # Initialize result
        result = ResearchResult(
            query=query.query,
            category=query.category,
            subcategory=query.subcategory
        )

        # Perform web search using the query
        search_results = self._perform_web_search(query.query)

        if not search_results:
            self.logger.warning(f"No search results found for query: {query.query}")
            return result

        # For each search result, browse the page and extract information
        for search_item in search_results[:5]:  # Limit to top 5 results
            url = search_item.get("url")
            title = search_item.get("title", "")

            if not url:
                continue

            # Check if the URL starts with https
            if not url.startswith("https"):
                self.logger.info(f"Skipping non-HTTPS URL: {url}")
                continue

            try:
                # Visit the page with the browser tool
                self.logger.info(f"Browsing URL: {url}")
                page_content = self._browse_page(url)

                if not page_content:
                    self.logger.warning(f"Failed to browse page: {url}")
                    continue

                # Extract candidates from the page
                candidates = self._extract_candidates(
                    url=url,
                    title=title,
                    page_content=page_content,
                    category=query.category,
                    subcategory=query.subcategory,
                    source_query=query.query
                )

                result.candidates.extend(candidates)
                self.logger.info(f"Found {len(candidates)} candidates from {url}")

            except Exception as e:
                self.logger.error(f"Error processing URL {url}: {str(e)}")

        # Log the total number of candidates found
        self.logger.info(
            f"Found {len(result.candidates)} candidates for query: {query.query}"
        )

        return result

    def _perform_web_search(self, query: str) -> List[Dict]:
        """
        Perform a web search using the provided query.

        Args:
            query: Search query

        Returns:
            List of search results (dicts with url, title, snippet)
        """
        self.logger.info(f"Performing web search for: {query}")

        # This function should use the BrowserTool to perform a search
        # For now, simulate a search with a sample implementation
        try:
            # Here we would use the BrowserTool in a real implementation
            # For example with OpenAI Agents SDK:
            # results = browser_tool.search(query)

            # For this implementation, we'll use the web_search function
            self.logger.info("Using web_search function")

            search_results = self._web_search(query)

            if not search_results:
                self.logger.warning(f"No results from web search for query: {query}")
                return []

            formatted_results = []

            for result in search_results:
                formatted_results.append({
                    "url": result.get("url", ""),
                    "title": result.get("title", ""),
                    "snippet": result.get("snippet", "")
                })

            self.logger.info(f"Found {len(formatted_results)} search results")
            return formatted_results

        except Exception as e:
            self.logger.error(f"Error performing web search: {str(e)}")
            return []

    def _web_search(self, query: str) -> List[Dict]:
        """
        Perform a web search using the web_search function.

        Args:
            query: Search query

        Returns:
            List of search results
        """
        from antml.functions import web_search  # Import here to avoid circular imports

        try:
            search_response = web_search(
                search_term=query,
                explanation="Searching for resources to add to awesome list"
            )

            if not search_response:
                return []

            results = []
            for result in search_response.get("results", []):
                results.append({
                    "url": result.get("url", ""),
                    "title": result.get("title", ""),
                    "snippet": result.get("snippet", ""),
                })

            return results

        except Exception as e:
            self.logger.error(f"Error using web_search: {str(e)}")
            return []

    def _browse_page(self, url: str) -> Optional[str]:
        """
        Browse a page using the BrowserTool.

        Args:
            url: URL to browse

        Returns:
            Page content (or None if failed)
        """
        self.logger.info(f"Browsing page: {url}")

        try:
            # Here we would use the BrowserTool in a real implementation
            # For example with OpenAI Agents SDK:
            # page_content = browser_tool.navigate(url)

            # For this implementation, we'll use the firecrawl_scrape function
            from antml.functions import mcp_firecrawl_mcp_firecrawl_scrape

            result = mcp_firecrawl_mcp_firecrawl_scrape(
                url=url,
                formats=["markdown"],
                onlyMainContent=True,
                timeout=10000  # 10 seconds timeout
            )

            if not result or not result.get("data"):
                self.logger.warning(f"Failed to scrape page: {url}")
                return None

            content = result.get("data", {}).get("markdown", "")

            if not content:
                self.logger.warning(f"No content retrieved from page: {url}")
                return None

            self.logger.info(f"Successfully browsed page: {url} ({len(content)} chars)")
            return content

        except Exception as e:
            self.logger.error(f"Error browsing page: {url} - {str(e)}")
            return None

    def _extract_candidates(
        self,
        url: str,
        title: str,
        page_content: str,
        category: str,
        subcategory: Optional[str],
        source_query: str
    ) -> List[ResearchCandidate]:
        """
        Extract candidate resources from a page.

        Args:
            url: URL of the page
            title: Title of the page
            page_content: Content of the page
            category: Category
            subcategory: Subcategory (optional)
            source_query: Source query

        Returns:
            List of ResearchCandidate instances
        """
        self.logger.info(f"Extracting candidates from page: {url}")

        system_prompt = f"""
You are a resource extraction agent that identifies valuable GitHub repositories, tools, libraries,
frameworks, and other resources from web content.

You need to find resources relevant to the category '{category}'{f", specifically the subcategory '{subcategory}'" if subcategory else ""}.

For each valuable resource you find in the provided content, extract:
1. Name - The name of the tool/library/framework/resource
2. URL - The direct URL to the resource (must be HTTPS and properly formatted)
3. Description - A concise description (under 100 characters) in sentence case without a period

Only return resources that:
- Are high-quality and valuable to developers
- Directly relate to the specified category/subcategory
- Have a valid HTTPS URL
- Have not been abandoned (are still maintained)
- Are well-documented and have community support
"""

        user_prompt = f"""
Please analyze the following content from the search result "{title}" and extract relevant resources for the category '{category}'{f", subcategory '{subcategory}'" if subcategory else ""}.

The search query was: "{source_query}"

PAGE CONTENT:
{page_content[:4000]}  # Limit content to avoid token limits

FORMAT YOUR RESPONSE AS JSON with an array of resources, each with "name", "url", and "description" fields. Example:
```json
{{
  "resources": [
    {{
      "name": "Resource Name",
      "url": "https://example.com/resource",
      "description": "A concise description of what it does"
    }},
    ...
  ]
}}
```

If you find no relevant resources, return an empty resources array: {"resources": []}
"""

        # Check if the API call would exceed the cost ceiling
        estimated_tokens = len(system_prompt.split()) + len(user_prompt.split()) + 500
        if self.cost_guard.would_exceed_ceiling(self.model, estimated_tokens, estimated_tokens // 2):
            self.logger.warning(f"Cost ceiling would be exceeded for extracting candidates from {url}, skipping")
            return []

        # Make the API call
        start_time = time.time()

        try:
            completion = self.api_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )

            # Update cost
            self.cost_guard.update_from_completion(completion, self.model)

            # Log full prompt and completion
            latency = time.time() - start_time
            api_log = APICallLogRecord(
                agent_id="category_researcher",
                model=self.model,
                prompt=f"System: {system_prompt}\nUser: {user_prompt}",
                completion=completion.choices[0].message.content,
                tokens=completion.usage.total_tokens,
                cost_usd=self.cost_guard.total_cost_usd,
                latency=latency
            )

            self.logger.info(f"API call log: {api_log.to_json()}")

            # Parse the response
            try:
                response_json = json.loads(completion.choices[0].message.content)
                resources = response_json.get("resources", [])

                if not resources:
                    self.logger.info(f"No resources found on page: {url}")
                    return []

                # Create ResearchCandidate objects
                candidates = []
                for resource in resources:
                    # Basic validation
                    name = resource.get("name", "").strip()
                    resource_url = resource.get("url", "").strip()
                    description = resource.get("description", "").strip()

                    if not name or not resource_url or not description:
                        continue

                    # Ensure URL is HTTPS
                    if not resource_url.startswith("https://"):
                        continue

                    # Create candidate
                    candidate = ResearchCandidate(
                        name=name,
                        url=resource_url,
                        description=description,
                        category=category,
                        subcategory=subcategory,
                        source_query=source_query
                    )

                    candidates.append(candidate)

                self.logger.info(f"Extracted {len(candidates)} candidates from page: {url}")
                return candidates

            except (json.JSONDecodeError, KeyError) as e:
                self.logger.error(f"Error parsing response for page {url}: {str(e)}")
                return []

        except Exception as e:
            self.logger.error(f"API call failed for page {url}: {str(e)}")
            return []
