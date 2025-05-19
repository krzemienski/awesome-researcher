"""
GitHub utilities for interacting with repositories and README files.
"""

import logging
import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential
)


class GitHubAPI:
    """
    Utility class for interacting with GitHub repositories.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize the GitHub API utility.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.client = httpx.Client(timeout=30.0)
        self.common_branches = ["main", "master"]

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5)
    )
    def get_raw_readme(self, owner: str, repo: str, branch: Optional[str] = None) -> str:
        """
        Get the raw README.md content from a GitHub repository.
        Tries common branch names and file name variations if branch is not specified.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch name (optional)

        Returns:
            Raw README.md content
        """
        if branch:
            branches_to_try = [branch]
        else:
            branches_to_try = self.common_branches

        readme_formats = [
            # Standard formats with branch name
            lambda b: f"https://raw.githubusercontent.com/{owner}/{repo}/{b}/README.md",
            lambda b: f"https://raw.githubusercontent.com/{owner}/{repo}/{b}/readme.md",
            # Using refs/heads format
            lambda b: f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{b}/README.md",
            lambda b: f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{b}/readme.md",
        ]

        readme_content = None
        last_error = None

        for try_branch in branches_to_try:
            for format_func in readme_formats:
                raw_url = format_func(try_branch)

                self.logger.info(f"Fetching README from {raw_url}")

                try:
                    response = self.client.get(raw_url)
                    response.raise_for_status()
                    readme_content = response.text
                    self.logger.info(f"Successfully fetched README.md ({len(readme_content)} bytes)")
                    return readme_content
                except Exception as e:
                    last_error = e
                    self.logger.warning(f"Failed to fetch README from {raw_url}: {str(e)}")

        # If we get here, all attempts failed
        if last_error:
            raise last_error
        else:
            raise ValueError(f"Could not fetch README for {owner}/{repo}")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5)
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

        response = self.client.get(url)
        response.raise_for_status()

        data = response.json()
        stars = data.get("stargazers_count", 0)

        return stars


def parse_github_url(url: str) -> Tuple[str, str]:
    """
    Parse a GitHub URL to extract owner and repository name.

    Args:
        url: GitHub repository URL

    Returns:
        Tuple of (owner, repo)

    Raises:
        ValueError: If the URL is not a valid GitHub repository URL
    """
    parsed = urlparse(url)

    if parsed.netloc != "github.com":
        raise ValueError(f"Not a GitHub URL: {url}")

    path_parts = [p for p in parsed.path.split("/") if p]

    if len(path_parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {url}")

    owner = path_parts[0]
    repo = path_parts[1]

    return owner, repo


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
