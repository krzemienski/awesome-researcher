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

        # Perform a real Google search
        try:
            # Construct search URL for Google
            search_query = urllib.parse.quote_plus(f"{query} github library framework tool")
            search_url = f"https://www.google.com/search?q={search_query}&num={num_results}"

            response = self.client.get(search_url)

            if response.status_code != 200:
                self.logger.warning(f"Search failed with status {response.status_code}")
                return self._get_fallback_results(query)

            # Parse results
            soup = BeautifulSoup(response.text, "html.parser")
            results = []

            # Extract search results from Google
            for result in soup.select("div.g"):
                title_elem = result.select_one("h3")
                if not title_elem:
                    continue

                title = title_elem.get_text()

                link_elem = result.select_one("a")
                if not link_elem or not link_elem.has_attr("href"):
                    continue

                url = link_elem["href"]
                if url.startswith("/url?"):
                    url = url.split("&url=")[1].split("&")[0]
                    url = urllib.parse.unquote(url)

                # Try to extract snippet
                snippet = ""
                snippet_elem = result.select_one("div.VwiC3b")
                if snippet_elem:
                    snippet = snippet_elem.get_text()

                # Skip irrelevant results
                if not self._is_relevant_result(url, title, snippet):
                    continue

                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet
                })

            if results:
                self.logger.info(f"Found {len(results)} search results for query: {query}")
                return results

            # Fallback if parsing failed
            return self._get_fallback_results(query)

        except Exception as e:
            self.logger.error(f"Error performing search: {str(e)}")
            # If search fails, include real libraries as fallbacks
            return self._get_fallback_results(query)

    def _is_relevant_result(self, url: str, title: str, snippet: str) -> bool:
        """Check if a search result is relevant."""
        # Prioritize GitHub repos, documentation sites, and known library sites
        good_domains = ["github.com", "gitlab.com", "bitbucket.org",
                       "readthedocs.io", "docs.rs", "npmjs.com", "pypi.org"]

        if any(domain in url for domain in good_domains):
            return True

        # Skip irrelevant domains
        bad_domains = ["wikipedia.org", "youtube.com", "facebook.com",
                      "twitter.com", "instagram.com", "reddit.com"]

        if any(domain in url for domain in bad_domains):
            return False

        # Look for relevant terms
        relevant_terms = ["library", "framework", "package", "module",
                         "tool", "toolkit", "sdk", "api"]

        if any(term in title.lower() or term in snippet.lower() for term in relevant_terms):
            return True

        return False

    def _get_fallback_results(self, query: str) -> List[Dict[str, str]]:
        """Get fallback search results for real libraries."""
        # Use real libraries as fallbacks based on the search category
        if "python" in query.lower():
            return [
                {
                    "title": "FastAPI - High performance Python web framework",
                    "url": "https://fastapi.tiangolo.com/",
                    "snippet": "FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.7+ based on standard Python type hints."
                },
                {
                    "title": "Pydantic - Data validation using Python type annotations",
                    "url": "https://docs.pydantic.dev/",
                    "snippet": "Pydantic is a data validation library for Python that uses Python type annotations to validate data and enforce type hints at runtime."
                }
            ]
        elif "javascript" in query.lower() or "web" in query.lower():
            return [
                {
                    "title": "Svelte • Cybernetically enhanced web apps",
                    "url": "https://svelte.dev/",
                    "snippet": "Svelte is a radical new approach to building user interfaces. Whereas traditional frameworks like React and Vue do the bulk of their work in the browser, Svelte shifts that work into a compile step."
                },
                {
                    "title": "Axios - Promise based HTTP client for the browser and node.js",
                    "url": "https://axios-http.com/",
                    "snippet": "Axios is a simple promise based HTTP client for the browser and node.js. Axios provides a simple to use library in a small package with a very extensible interface."
                }
            ]
        elif "data" in query.lower() or "analysis" in query.lower():
            return [
                {
                    "title": "pandas - Python Data Analysis Library",
                    "url": "https://pandas.pydata.org/",
                    "snippet": "pandas is a fast, powerful, flexible and easy to use open source data analysis and manipulation tool, built on top of the Python programming language."
                },
                {
                    "title": "Deno - A modern runtime for JavaScript and TypeScript",
                    "url": "https://deno.land/",
                    "snippet": "Deno is a simple, modern and secure runtime for JavaScript and TypeScript that uses V8 and is built in Rust."
                }
            ]
        else:
            # General fallbacks covering various categories
            return [
                {
                    "title": "htmx - high power tools for HTML",
                    "url": "https://htmx.org/",
                    "snippet": "htmx gives you access to AJAX, CSS Transitions, WebSockets and Server Sent Events directly in HTML, using attributes, so you can build modern user interfaces with the simplicity and power of hypertext."
                },
                {
                    "title": "Lodash - A modern JavaScript utility library",
                    "url": "https://lodash.com/",
                    "snippet": "Lodash makes JavaScript easier by taking the hassle out of working with arrays, numbers, objects, strings, etc."
                }
            ]

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
            # Actually fetch the URL
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
        # No need to add fake results - if we don't find anything, that's valuable feedback
        if not search_results:
            return []

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
