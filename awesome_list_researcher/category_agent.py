"""
Category research agent for finding new resources.
"""

import json
import logging
import time
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Union, Any

from awesome_list_researcher.awesome_parser import AwesomeLink
from awesome_list_researcher.utils import mcp_handler, context_store

# Import browser tools for actual web searching
import httpx
from bs4 import BeautifulSoup

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


class BrowserTool:
    """
    Browser tool implementation for web searching and browsing.
    """

    def __init__(self):
        """Initialize the browser tool."""
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        self.logger = logging.getLogger(__name__)

    def search(self, query: str, num_results: int = 10) -> List[Dict[str, str]]:
        """
        Perform a web search.

        Args:
            query: Search query
            num_results: Number of results to return

        Returns:
            List of search result dictionaries
        """
        self.logger.info(f"Performing web search: {query}")

        # Encode query for URL
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded_query}&num={num_results}"

        try:
            response = self.client.get(search_url)
            soup = BeautifulSoup(response.text, "html.parser")

            # Extract search results
            results = []

            # Find the main search result divs
            for result in soup.select("div.g"):
                try:
                    # Extract title and URL
                    title_element = result.select_one("h3")
                    link_element = result.select_one("a")
                    snippet_element = result.select_one("div.VwiC3b")

                    if title_element and link_element and "href" in link_element.attrs:
                        title = title_element.get_text()
                        url = link_element["href"]

                        # Clean URL (remove Google redirect)
                        if url.startswith("/url?"):
                            url = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]

                        # Get snippet if available
                        snippet = ""
                        if snippet_element:
                            snippet = snippet_element.get_text()

                        results.append({
                            "title": title,
                            "url": url,
                            "snippet": snippet
                        })
                except Exception as e:
                    self.logger.warning(f"Error parsing search result: {str(e)}")

            self.logger.info(f"Found {len(results)} search results")
            return results

        except Exception as e:
            self.logger.error(f"Search failed: {str(e)}")
            return []

    def browse(self, url: str) -> Optional[str]:
        """
        Browse a web page and get its content.

        Args:
            url: URL to browse

        Returns:
            Page content or None if failed
        """
        self.logger.info(f"Browsing URL: {url}")

        try:
            response = self.client.get(url)

            if response.status_code == 200:
                return response.text
            else:
                self.logger.warning(f"Failed to browse {url}: Status code {response.status_code}")
                return None

        except Exception as e:
            self.logger.error(f"Error browsing {url}: {str(e)}")
            return None

    def extract_resource_info(self, url: str, category: str) -> Optional[Dict[str, str]]:
        """
        Extract resource information from a URL.

        Args:
            url: URL to extract information from
            category: Resource category

        Returns:
            Dictionary with resource information or None if failed
        """
        self.logger.info(f"Extracting resource info from {url}")

        try:
            content = self.browse(url)
            if not content:
                return None

            soup = BeautifulSoup(content, "html.parser")

            # Extract title (prefer og:title or Twitter card)
            title = None
            og_title = soup.select_one("meta[property='og:title']")
            if og_title and "content" in og_title.attrs:
                title = og_title["content"]
            else:
                twitter_title = soup.select_one("meta[name='twitter:title']")
                if twitter_title and "content" in twitter_title.attrs:
                    title = twitter_title["content"]
                else:
                    title_tag = soup.select_one("title")
                    if title_tag:
                        title = title_tag.get_text()

            # If still no title, use URL parts
            if not title:
                parsed_url = urllib.parse.urlparse(url)
                title = parsed_url.netloc
                if parsed_url.path and parsed_url.path != "/":
                    path_parts = parsed_url.path.strip("/").split("/")
                    if path_parts:
                        title = path_parts[-1].replace("-", " ").replace("_", " ").title()

            # Extract description
            description = None
            og_desc = soup.select_one("meta[property='og:description']")
            if og_desc and "content" in og_desc.attrs:
                description = og_desc["content"]
            else:
                meta_desc = soup.select_one("meta[name='description']")
                if meta_desc and "content" in meta_desc.attrs:
                    description = meta_desc["content"]
                else:
                    # Try to get first paragraph
                    first_p = soup.select_one("p")
                    if first_p:
                        description = first_p.get_text()

            # Fallback description
            if not description:
                description = f"A tool or resource for {category}"

            # Clean and truncate description
            if description:
                # Remove extra whitespace
                description = re.sub(r'\s+', ' ', description).strip()
                # Truncate to 100 chars as per Awesome list spec
                if len(description) > 100:
                    description = description[:97] + "..."

            return {
                "title": title,
                "url": url,
                "description": description
            }

        except Exception as e:
            self.logger.error(f"Error extracting resource info from {url}: {str(e)}")
            return None


class CategoryResearchAgent:
    """
    Agent for researching new resources for a category.
    Uses BrowserTool to perform real web searches.
    """

    def __init__(
        self,
        category: str,
        queries: List[str],
        model_name: str = "o3",
        cost_ceiling: float = 10.0
    ):
        """
        Initialize the category research agent.

        Args:
            category: Category to research
            queries: List of search queries
            model_name: OpenAI model to use
            cost_ceiling: Maximum cost in USD
        """
        self.category = category
        self.queries = queries
        self.model_name = model_name
        self.cost_ceiling = cost_ceiling
        self.logger = logging.getLogger(__name__)
        self.browser_tool = BrowserTool()
        self.total_cost = 0.0

        # Continue sequence thinking with MCP
        mcp_handler.sequence_thinking(
            thought=f"Researching category: {category} with {len(queries)} queries using BrowserTool",
            thought_number=1,
            total_thoughts=3
        )

    def estimate_cost(self) -> float:
        """
        Estimate the cost of the operation.

        Returns:
            Estimated cost in USD
        """
        # Rough estimate based on number of queries and model
        cost_per_query = 0.05 if self.model_name == "o3" else 0.1
        return len(self.queries) * cost_per_query

    def get_cost(self) -> float:
        """
        Get the current total cost.

        Returns:
            Total cost in USD
        """
        return self.total_cost

    def research(self) -> Dict:
        """
        Research the category using the provided queries and BrowserTool.

        Returns:
            Dictionary mapping queries to results
        """
        self.logger.info(f"Researching category: {self.category} with {len(self.queries)} queries")

        mcp_handler.sequence_thinking(
            thought=f"Searching for resources using BrowserTool",
            thought_number=2,
            total_thoughts=3
        )

        results = {}
        for i, query in enumerate(self.queries):
            query_with_category = f"{query} {self.category}"
            self.logger.info(f"Processing query {i+1}/{len(self.queries)}: {query_with_category}")

            # Use BrowserTool to perform search
            search_results = self.browser_tool.search(query_with_category)

            # Filter results to filter out potentially irrelevant ones
            relevant_results = self._filter_relevant_results(search_results)

            # Extract resource information
            candidates = []
            for result in relevant_results[:5]:  # Limit to top 5 per query
                url = result["url"]

                # Skip if the URL has any obvious issues
                if not self._is_valid_url(url):
                    self.logger.info(f"Skipping invalid URL: {url}")
                    continue

                # Extract resource information
                resource_info = self.browser_tool.extract_resource_info(url, self.category)

                if resource_info:
                    candidate = ResearchCandidate(
                        name=resource_info["title"],
                        url=url,
                        description=resource_info["description"],
                        category=self.category,
                        source_query=query
                    )
                    candidates.append(candidate)
                    self.logger.info(f"Added candidate: {candidate.name}")

            results[query] = candidates

            # Update cost
            query_cost = 0.02  # Cost per query
            self.total_cost += query_cost
            self.logger.info(f"Query cost: ${query_cost:.4f}, total cost: ${self.total_cost:.4f}")

            # Check cost ceiling
            if self.total_cost >= self.cost_ceiling:
                self.logger.warning(f"Cost ceiling of ${self.cost_ceiling:.2f} reached, stopping research")
                break

        mcp_handler.sequence_thinking(
            thought=f"Found {sum(len(c) for c in results.values())} candidates across {len(results)} queries",
            thought_number=3,
            total_thoughts=3
        )

        # Convert to dictionary format
        result_dict = {}
        for query, candidates in results.items():
            result_dict[query] = [c.to_dict() for c in candidates]

        return result_dict

    def _is_valid_url(self, url: str) -> bool:
        """
        Check if a URL is valid and relevant.

        Args:
            url: URL to check

        Returns:
            True if the URL is valid and relevant
        """
        # Check for empty URL
        if not url:
            return False

        # Check URL format
        try:
            parsed = urllib.parse.urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False
        except:
            return False

        # Skip URLs that don't look like resources
        if any(domain in url.lower() for domain in [
            "google.com/search", "youtube.com/watch", "wikipedia.org",
            "instagram.com", "facebook.com", "twitter.com", "tiktok.com"
        ]):
            return False

        return True

    def _filter_relevant_results(self, search_results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Filter search results by relevance.

        Args:
            search_results: List of search results

        Returns:
            Filtered list of search results
        """
        # Filter by relevance to the category
        relevant_results = []

        for result in search_results:
            relevance_score = 0

            # Check title for category or related terms
            if self.category.lower() in result["title"].lower():
                relevance_score += 3

            # Check snippet for category or related terms
            if self.category.lower() in result["snippet"].lower():
                relevance_score += 2

            # Check for GitHub repositories (often high-quality resources)
            if "github.com" in result["url"].lower():
                relevance_score += 2

            # Check for documentation, tools, libraries
            if any(term in result["title"].lower() or term in result["snippet"].lower()
                  for term in ["library", "framework", "tool", "package", "documentation"]):
                relevance_score += 1

            # Include if relevant enough
            if relevance_score >= 2:
                relevant_results.append(result)

        return relevant_results
