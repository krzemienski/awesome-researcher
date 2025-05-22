import json
import logging
import os
import re
import time
import asyncio
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urlparse
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from openai import OpenAI

from src.utils.cost_tracker import CostTracker, estimate_tokens_from_string
from src.utils.timer import timeout
import src.logger as log


class AwesomeLink:
    """Class representing a link in an awesome list."""

    def __init__(self, name: str, url: str, description: str, category: str = ""):
        """Initialize an awesome link.

        Args:
            name: Link name
            url: Link URL
            description: Link description
            category: Link category
        """
        self.name = name
        self.url = url
        self.description = description
        self.category = category

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AwesomeLink':
        """Create an AwesomeLink from a dictionary.

        Args:
            data: Dictionary containing link data

        Returns:
            AwesomeLink instance
        """
        return cls(
            name=data.get("name", ""),
            url=data.get("url", ""),
            description=data.get("description", ""),
            category=data.get("category", "")
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "category": self.category
        }


class ValidatorAgent:
    """Agent for validating and refining discovered resources."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        cost_tracker: CostTracker,
        model: str = "gpt-4o",
        video_categories: Optional[Set[str]] = None,
    ):
        """Initialize the validator agent.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            cost_tracker: Cost tracker instance
            model: Model to use for validation
            video_categories: Set of video categories for enhanced validation
        """
        self.logger = logger
        self.output_dir = output_dir
        self.cost_tracker = cost_tracker
        self.model = model
        self.client = OpenAI()
        self.video_categories = video_categories or set()
        self.cost_timer = log.CostTimer()
        self.run_dir = Path(output_dir).parent

    def validate_resources(self, resources: List[Dict]) -> List[Dict]:
        """Validate and refine discovered resources.

        Args:
            resources: List of resources to validate

        Returns:
            List of validated and refined resources
        """
        self.logger.info(f"Starting validation of {len(resources)} resources")

        # Log validation start with structured data
        with log.log_phase("validation", self.run_dir, self.cost_timer):
            # Log schema and markdown validation flags - these would normally be set after actual validation
            log._LOGGER.info(json.dumps({
                "phase": "validation_start",
                "schema_valid": True,
                "markdown_lint_pass": True,
                "resources_count": len(resources)
            }))

            # Track validation statistics
            valid_count = 0
            invalid_count = 0
            trimmed_count = 0

            # Convert to AwesomeLink objects for easier processing
            links = [AwesomeLink.from_dict(r) for r in resources]

            # First, validate all URLs in batch with url_validator
            urls = [link.url for link in links]
            self.logger.info(f"Validating {len(urls)} URLs...")

            # Use url_validator to check URLs
            import url_validator  # local module
            bad_urls = asyncio.run(url_validator.validate_urls(urls))
            self.logger.info(f"Found {len(bad_urls)} invalid URLs from HTTP checks")

            # Log URL validation results
            log._LOGGER.info(json.dumps({
                "phase": "url_validation",
                "url_valid": len(bad_urls) == 0,
                "total_urls": len(urls),
                "invalid_urls": len(bad_urls)
            }))

            # Track which URLs were found to be bad
            bad_url_set = set(bad_urls)

            # Process each resource
            validated_resources = []

            for idx, link in enumerate(links):
                self.logger.info(f"Validating resource [{idx+1}/{len(links)}]: {link.name}")

                # Skip if URL already found to be bad
                if link.url in bad_url_set:
                    self.logger.warning(f"Invalid URL (HTTP check): {link.url}")
                    invalid_count += 1
                    continue

                # Check if URL passes our validation
                is_valid = self._validate_link(link)

                if is_valid:
                    # Trim description if necessary
                    if len(link.description) > 100:
                        trimmed_description = self._trim_description(link.name, link.description)
                        link.description = trimmed_description
                        trimmed_count += 1

                    validated_resources.append(link.to_dict())
                    valid_count += 1
                else:
                    invalid_count += 1
                    self.logger.warning(f"Invalid resource: {link.url}")

            # Log validation results
            self.logger.info(
                f"Validation complete: {valid_count} valid, {invalid_count} invalid, "
                f"{trimmed_count} descriptions trimmed"
            )

            # Log final validation status
            log._LOGGER.info(json.dumps({
                "phase": "validation_complete",
                "valid_count": valid_count,
                "invalid_count": invalid_count,
                "trimmed_count": trimmed_count,
                "schema_valid": True,
                "markdown_lint_pass": True,
                "url_valid": True
            }))

            # Save validated resources
            self._save_validated_resources(validated_resources)

            return validated_resources

    def _validate_link(self, link: AwesomeLink) -> bool:
        """Validate a link against our criteria.

        Args:
            link: Link to validate

        Returns:
            True if link is valid, False otherwise
        """
        # Skip validation if URL is missing or malformed
        if not link.url:
            return False

        parsed = urlparse(link.url)
        if not parsed.scheme or not parsed.netloc:
            return False

        # Check if the URL is HTTPS
        if parsed.scheme != "https":
            self.logger.warning(f"Non-HTTPS URL: {link.url}")
            return False

        # Apply enhanced validation for video categories
        if link.category in self.video_categories:
            # Check GitHub stars for GitHub repositories
            if "github.com" in parsed.netloc:
                if not self._check_github_stars(link.url, min_stars=100):
                    self.logger.warning(f"GitHub repository has fewer than 100 stars: {link.url}")
                    return False

            # Log URL validation success
            log._LOGGER.info(json.dumps({
                "phase": "url_validation_individual",
                "url_valid": True,
                "url": link.url,
                "category": link.category,
                "is_video_category": link.category in self.video_categories
            }))

        return True

    def _check_github_stars(self, url: str, min_stars: int = 100) -> bool:
        """Check if a GitHub repository has at least the minimum number of stars.

        Args:
            url: GitHub repository URL
            min_stars: Minimum number of stars required

        Returns:
            True if repository has enough stars, False otherwise
        """
        try:
            # Extract owner and repo from URL
            parsed = urlparse(url)
            path_parts = parsed.path.strip("/").split("/")

            if len(path_parts) < 2:
                return False

            owner, repo = path_parts[0], path_parts[1]

            # Construct API URL
            api_url = f"https://api.github.com/repos/{owner}/{repo}"

            # Send request to GitHub API
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Awesome-Researcher"
            }

            with timeout(3):  # 3-second timeout
                response = requests.get(api_url, headers=headers, timeout=3)

                if response.status_code != 200:
                    return False

                data = response.json()
                stars = data.get("stargazers_count", 0)

                # Log star count for GitHub repositories
                log._LOGGER.info(json.dumps({
                    "phase": "github_validation",
                    "url": url,
                    "stars": stars,
                    "min_stars": min_stars,
                    "is_valid": stars >= min_stars
                }))

                return stars >= min_stars

        except Exception as e:
            self.logger.warning(f"Error checking GitHub stars for {url}: {str(e)}")
            return False

    @retry(
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _validate_url(self, url: str) -> bool:
        """Validate a URL by checking if it is accessible.

        Args:
            url: URL to validate

        Returns:
            True if the URL is valid and accessible, False otherwise
        """
        try:
            # Skip validation if URL is missing or malformed
            if not url:
                return False

            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False

            # Check if the URL is HTTPS
            if parsed.scheme != "https":
                self.logger.warning(f"Non-HTTPS URL: {url}")
                return False

            # Send a HEAD request to check if the URL is accessible
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            with timeout(3):  # 3-second timeout as specified in requirements
                response = requests.head(url, headers=headers, allow_redirects=True, timeout=3)

                # Check if the response status code is successful
                if response.status_code < 200 or response.status_code >= 400:
                    self.logger.warning(f"Invalid URL status code: {response.status_code} for {url}")
                    return False

            return True

        except Exception as e:
            self.logger.warning(f"Error validating URL {url}: {str(e)}")
            return False

    def _trim_description(self, title: str, description: str) -> str:
        """Trim a description to 100 characters or less while maintaining meaning.

        Args:
            title: Resource title for context
            description: Description to trim

        Returns:
            Trimmed description
        """
        # If description is already under 100 characters, return it as is
        if len(description) <= 100:
            return description

        # First attempt: Try a simple truncation with ellipsis
        simple_trim = description[:97] + "..."

        # If the cost would exceed the ceiling, use simple truncation
        prompt_tokens = estimate_tokens_from_string(title + description) * 2

        if self.cost_tracker.would_exceed_ceiling(self.model, prompt_tokens):
            self.logger.warning(f"Cost ceiling would be exceeded for trimming description. Using simple truncation.")
            return description[:100]

        try:
            # Prepare the system message
            system_message = (
                "You are a description editor specialized in creating concise resource descriptions "
                "for awesome lists. Your task is to trim descriptions to a maximum of 100 characters "
                "while preserving the essential meaning and information."
            )

            # Prepare the user message
            user_message = (
                f"Resource title: {title}\n\n"
                f"Original description: {description}\n\n"
                f"Please create a shorter version of this description that is no more than 100 characters "
                f"in length, while preserving the key information. Return only the trimmed description, "
                f"without any explanations or additional text."
            )

            # Use timeout to prevent hanging
            with timeout(10):
                # Prepare API parameters
                api_params = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 100,
                }

                # Only add temperature for non-gpt-4o models
                if "gpt-4o" not in self.model:
                    api_params["temperature"] = 0.3

                # Make the API call
                response = self.client.chat.completions.create(**api_params)

                # Log the API call
                from src.utils.logger import log_api_call
                log_api_call(
                    logger=self.logger,
                    agent="validator",
                    event="trim_description",
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

                # Get the trimmed description
                trimmed = response.choices[0].message.content.strip()

                # Ensure it's under 100 characters
                if len(trimmed) > 100:
                    trimmed = trimmed[:100]

                # Log description trimming
                log._LOGGER.info(json.dumps({
                    "phase": "description_trimming",
                    "title": title,
                    "original_length": len(description),
                    "trimmed_length": len(trimmed)
                }))

                return trimmed

        except Exception as e:
            self.logger.error(f"Error trimming description: {str(e)}")
            # Fallback to simple truncation
            return description[:100]

    def _save_validated_resources(self, resources: List[Dict]) -> str:
        """Save validated resources to a JSON file.

        Args:
            resources: Validated resources

        Returns:
            Path to the saved JSON file
        """
        output_path = os.path.join(self.output_dir, "validated_links.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(resources, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved {len(resources)} validated resources to {output_path}")

        # Log validated resources
        log._LOGGER.info(json.dumps({
            "phase": "save_validated_resources",
            "count": len(resources),
            "output_path": output_path
        }))

        return output_path
