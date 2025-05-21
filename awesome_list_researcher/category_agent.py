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

        try:
            # Construct search URL for Google
            search_query = urllib.parse.quote_plus(f"{query} github library framework tool")
            search_url = f"https://www.google.com/search?q={search_query}&num={num_results}"

            response = self.client.get(search_url)

            if response.status_code != 200:
                self.logger.warning(f"Search failed with status {response.status_code}")
                return []

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

            # If no results are found or parsing failed, return empty list
            self.logger.warning(f"No search results found for query: {query}")
            return []

        except Exception as e:
            self.logger.error(f"Error performing search: {str(e)}")
            return []

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
            # For GitHub repositories, use a specialized extraction method
            if "github.com" in url:
                return self._extract_github_repo_info(url, category)

            # For PyPI packages, use specialized extraction
            if "pypi.org" in url:
                return self._extract_pypi_package_info(url, category)

            # General extraction for other URLs
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

    def _extract_github_repo_info(self, url: str, category: str) -> Optional[Dict[str, str]]:
        """Extract information from a GitHub repository."""
        try:
            content = self.browse(url)
            if not content:
                return None

            soup = BeautifulSoup(content, "html.parser")

            # Get the repo name
            title_elem = soup.select_one("h1 strong a") or soup.select_one("h1.d-inline a")
            if not title_elem:
                # Try alternative selectors
                title_elem = soup.select_one("h1") or soup.select_one("title")

            title = title_elem.get_text().strip() if title_elem else None

            # If we couldn't find the title, extract from URL
            if not title:
                path_parts = urllib.parse.urlparse(url).path.strip("/").split("/")
                if len(path_parts) >= 2:
                    title = path_parts[1].replace("-", " ").replace("_", " ").title()

            # Get the description
            desc_elem = soup.select_one(".f4.my-3") or soup.select_one(".repository-content .f4") or soup.select_one("p.f4")
            description = None
            if desc_elem:
                description = desc_elem.get_text().strip()

            # If no description found, check for og:description
            if not description:
                og_desc = soup.select_one("meta[property='og:description']")
                if og_desc and "content" in og_desc.attrs:
                    description = og_desc["content"]

            # Fallback
            if not description:
                readme_elem = soup.select_one("#readme")
                if readme_elem:
                    first_p = readme_elem.select_one("p")
                    if first_p:
                        description = first_p.get_text().strip()

            # Final fallback description
            if not description:
                description = f"A {category} library or tool"

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
            self.logger.error(f"Error extracting GitHub repo info from {url}: {str(e)}")
            return None

    def _extract_pypi_package_info(self, url: str, category: str) -> Optional[Dict[str, str]]:
        """Extract information from a PyPI package page."""
        try:
            content = self.browse(url)
            if not content:
                return None

            soup = BeautifulSoup(content, "html.parser")

            # Get package name
            title_elem = soup.select_one("h1.package-header__name")
            title = title_elem.get_text().strip() if title_elem else None

            # If we couldn't find the title, extract from URL
            if not title:
                path_parts = urllib.parse.urlparse(url).path.strip("/").split("/")
                if path_parts:
                    title = path_parts[-1].replace("-", " ").replace("_", " ").title()

            # Get the description
            desc_elem = soup.select_one(".package-description__summary")
            description = None
            if desc_elem:
                description = desc_elem.get_text().strip()

            # If no description found, try other elements
            if not description:
                project_description = soup.select_one("#description")
                if project_description:
                    first_p = project_description.select_one("p")
                    if first_p:
                        description = first_p.get_text().strip()

            # Fallback description
            if not description:
                description = f"A {category} Python package"

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
            self.logger.error(f"Error extracting PyPI package info from {url}: {str(e)}")
            return None

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

        # Filter by relevance to the category and focus on GitHub repos
        relevant_results = []

        for result in search_results:
            relevance_score = 0
            url = result.get("url", "")

            # Strong preference for GitHub/GitLab/PyPI results
            if "github.com" in url:
                relevance_score += 5
            elif "gitlab.com" in url:
                relevance_score += 4
            elif "pypi.org" in url:
                relevance_score += 4
            elif "readthedocs.io" in url or "docs.rs" in url:
                relevance_score += 3

            # Check for code snippets or documentation sites
            if ".io" in url or ".dev" in url:
                relevance_score += 1

            # Avoid general review sites and non-relevant domains
            if any(domain in url for domain in [
                "google.com", "youtube.com", "wikipedia.org",
                "facebook.com", "twitter.com", "instagram.com",
                "reddit.com", "medium.com", "stackoverflow.com",
                "quora.com", "pinterest.com"
            ]):
                relevance_score -= 3

            # Check title for keywords suggesting it's a library
            title = result.get("title", "").lower()
            if any(term in title for term in [
                "library", "framework", "package", "module", "toolkit",
                "api", "sdk", "tool", "utility", "plugin", "extension",
                "github", "gitlab", "repo", "python"
            ]):
                relevance_score += 2

            # Check snippet for keywords
            snippet = result.get("snippet", "").lower()
            if any(term in snippet for term in [
                "library", "framework", "package", "module", "install",
                "pip", "import", "from", "github", "open source", "documentation"
            ]):
                relevance_score += 2

            # Relevant enough to include?
            if relevance_score >= 3:
                relevant_results.append(result)

        return relevant_results


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
            relevant_results = self.browser_tool._filter_relevant_results(search_results)

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
