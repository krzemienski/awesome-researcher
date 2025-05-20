"""
GitHub utilities for fetching content without using the GitHub API.
"""

import logging
import re
import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)


def parse_github_url(url: str) -> Tuple[str, str]:
    """
    Parse a GitHub repository URL into owner and repo name.

    Args:
        url: GitHub repository URL

    Returns:
        Tuple of (owner, repo)

    Raises:
        ValueError: If the URL is not a valid GitHub repository URL
    """
    # Remove trailing slashes
    url = url.rstrip('/')

    # Try parsing as a github.com URL
    parsed = urlparse(url)
    if parsed.netloc == 'github.com':
        path_parts = [p for p in parsed.path.split('/') if p]
        if len(path_parts) >= 2:
            return path_parts[0], path_parts[1]

    # Try parsing as a format like "owner/repo"
    if '/' in url and ' ' not in url:
        parts = url.split('/')
        if len(parts) == 2:
            return parts[0], parts[1]

    raise ValueError(
        f"Invalid GitHub repository URL: {url}. "
        f"Expected format: https://github.com/owner/repo"
)


class GitHubAPI:
    """
    Utility for interacting with GitHub repositories without using the API.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize the GitHub API client.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Awesome-List-Researcher/0.1.0"
        })

    @retry(
        retry=retry_if_exception_type((requests.exceptions.RequestException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        before_sleep=lambda retry_state: None  # No callback needed
    )
    def _make_request(self, url: str) -> Optional[str]:
        """
        Make a request with retries and backoff.

        Args:
            url: URL to request

        Returns:
            Response text if successful, None otherwise
        """
        try:
            response = self.session.get(url, timeout=10)

            # Log rate limits if present in headers
            if 'X-RateLimit-Remaining' in response.headers:
                remaining = response.headers.get('X-RateLimit-Remaining')
                limit = response.headers.get('X-RateLimit-Limit')
                reset = response.headers.get('X-RateLimit-Reset')
                self.logger.debug(
                    f"GitHub rate limits: {remaining}/{limit}, "
                    f"resets at {time.ctime(int(reset) if reset else 0)}"
                )

            # Handle rate limiting
            if response.status_code == 429:
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(1, reset_time - int(time.time()))
                self.logger.warning(
                    f"GitHub rate limit exceeded. Waiting {wait_time} seconds."
                )
                time.sleep(wait_time)
                return None

            # Handle other errors
            if response.status_code >= 400:
                self.logger.warning(
                    f"GitHub request failed: {response.status_code} for {url}"
                )
                return None

            return response.text

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error: {str(e)}")
            raise

    def get_raw_readme(self, owner: str, repo: str) -> str:
        """
        Get the raw README.md content from a GitHub repository.

        Tries different branches in order: master, main, HEAD.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Raw README.md content

        Raises:
            ValueError: If README.md cannot be found
        """
        urls = [
            f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md",
            f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md",
            f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md",
        ]

        for url in urls:
            self.logger.info(f"Trying to fetch README from {url}")
            content = self._make_request(url)
            if content:
                self.logger.info(f"Successfully fetched README from {url}")
                return content

        raise ValueError(
            f"Could not find README.md in {owner}/{repo} repository. "
            f"Tried branches: master, main, HEAD."
        )

    @retry(
        retry=retry_if_exception_type((requests.exceptions.RequestException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        before_sleep=lambda retry_state: None  # No callback needed
    )
    def get_repo_stars(self, owner: str, repo: str) -> int:
        """
        Get the number of stars for a GitHub repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Number of stars
        """
        url = f"https://api.github.com/repos/{owner}/{repo}"

        response = self.session.get(url)
        response.raise_for_status()

        data = response.json()
        stars = data.get("stargazers_count", 0)

        return stars


def is_github_url(url: str) -> bool:
    """
    Check if a URL is a GitHub URL.

    Args:
        url: URL to check

    Returns:
        True if the URL is a GitHub URL
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc == "github.com"
    except:
        return False
