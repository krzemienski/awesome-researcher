"""
Validator for candidate resources.
"""

import json
import logging
import re
import time
from typing import Dict, List, Any, Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from awesome_list_researcher.category_agent import ResearchCandidate
from awesome_list_researcher.utils import mcp_handler


class Validator:
    """
    Validator for candidate resources.

    This implementation uses MCP tools to maintain chain-of-thought reasoning.
    """

    def __init__(self, candidates: List[Dict], min_stars: int = 100):
        """
        Initialize the validator.

        Args:
            candidates: List of candidate dictionaries to validate
            min_stars: Minimum number of GitHub stars for a repository
        """
        self.logger = logging.getLogger(__name__)
        self.candidates = [ResearchCandidate.from_dict(candidate) for candidate in candidates]
        self.min_stars = min_stars
        self.validated = []
        self.rejected = []
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Awesome-List-Researcher/0.1.0"
        })

        # Continue sequence thinking with MCP
        mcp_handler.sequence_thinking(
            thought=f"Validating {len(self.candidates)} candidate resources",
            thought_number=1,
            total_thoughts=3
        )

    @retry(
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _check_url_accessibility(self, url: str, timeout: int = 3) -> bool:
        """
        Check if a URL is accessible.

        Args:
            url: URL to check
            timeout: Timeout in seconds

        Returns:
            True if the URL is accessible, False otherwise
        """
        try:
            response = self.session.head(url, timeout=timeout, allow_redirects=True)

            if response.status_code == 200:
                self.logger.info(f"URL {url} is accessible")
                return True

            self.logger.warning(f"URL {url} returned status code {response.status_code}")
            return False

        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Error checking URL {url}: {str(e)}")
            raise

    def _is_github_repo(self, url: str) -> bool:
        """
        Check if a URL is a GitHub repository.

        Args:
            url: URL to check

        Returns:
            True if the URL is a GitHub repository, False otherwise
        """
        return re.match(r"https://github\.com/[^/]+/[^/]+/?$", url) is not None

    def _normalize_description(self, description: str) -> str:
        """
        Normalize a resource description.

        Args:
            description: Description to normalize

        Returns:
            Normalized description
        """
        # Remove quotes and periods at the end
        description = description.strip('"\'')
        description = description.rstrip(".")

        # Limit to 100 characters
        if len(description) > 100:
            description = description[:97] + "..."

        return description

    def validate(self) -> List[Dict]:
        """
        Validate all candidates.

        Returns:
            List of validated candidate dictionaries
        """
        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Checking resource URLs and descriptions",
            thought_number=2,
            total_thoughts=3
        )

        for i, candidate in enumerate(self.candidates):
            self.logger.info(f"Validating candidate {i+1}/{len(self.candidates)}: {candidate.name}")

            # Check if the URL is accessible
            try:
                url_accessible = self._check_url_accessibility(candidate.url)
                if not url_accessible:
                    self.logger.warning(f"URL {candidate.url} is not accessible, rejected")
                    self.rejected.append(candidate)
                    continue
            except Exception as e:
                self.logger.error(f"Error checking URL {candidate.url}: {str(e)}")
                self.rejected.append(candidate)
                continue

            # Normalize the description
            cleaned_description = self._normalize_description(candidate.description)

            # Create a new candidate with the cleaned description
            cleaned_candidate = ResearchCandidate(
                name=candidate.name,
                url=candidate.url,
                description=cleaned_description,
                category=candidate.category,
                subcategory=candidate.subcategory,
                source_query=candidate.source_query
            )

            self.validated.append(cleaned_candidate)

        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought=f"Validated {len(self.candidates)} candidates: {len(self.validated)} valid, {len(self.rejected)} rejected",
            thought_number=3,
            total_thoughts=3
        )

        self.logger.info(
            f"Validated {len(self.candidates)} candidates: "
            f"{len(self.validated)} valid, {len(self.rejected)} rejected"
        )

        # Convert to dictionaries
        return [candidate.to_dict() for candidate in self.validated]

    def get_cost(self) -> float:
        """Mock method to maintain API compatibility with main.py."""
        return 0.0

    def estimate_cost(self) -> float:
        """Mock method to maintain API compatibility with main.py."""
        return len(self.candidates) * 0.01
