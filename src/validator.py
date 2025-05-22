import json
import logging
import os
import re
import time
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from openai import OpenAI

from src.utils.cost_tracker import CostTracker, estimate_tokens_from_string
from src.utils.timer import timeout


class ValidatorAgent:
    """Agent for validating and refining discovered resources."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        cost_tracker: CostTracker,
        model: str = "gpt-4o",
    ):
        """Initialize the validator agent.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            cost_tracker: Cost tracker instance
            model: Model to use for validation
        """
        self.logger = logger
        self.output_dir = output_dir
        self.cost_tracker = cost_tracker
        self.model = model
        self.client = OpenAI()

    def validate_resources(self, resources: List[Dict]) -> List[Dict]:
        """Validate and refine discovered resources.

        Args:
            resources: List of resources to validate

        Returns:
            List of validated and refined resources
        """
        self.logger.info(f"Starting validation of {len(resources)} resources")

        # Track validation statistics
        valid_count = 0
        invalid_count = 0
        trimmed_count = 0

        # Process each resource
        validated_resources = []

        for idx, resource in enumerate(resources):
            self.logger.info(f"Validating resource [{idx+1}/{len(resources)}]: {resource.get('name', 'Unknown')}")

            # Check if the URL is accessible
            url = resource.get("url", "")
            is_valid = self._validate_url(url)

            if is_valid:
                # Trim description if necessary
                description = resource.get("description", "")

                if len(description) > 100:
                    trimmed_description = self._trim_description(resource.get("name", ""), description)
                    resource["description"] = trimmed_description
                    trimmed_count += 1

                validated_resources.append(resource)
                valid_count += 1
            else:
                invalid_count += 1
                self.logger.warning(f"Invalid URL: {url}")

        # Log validation results
        self.logger.info(
            f"Validation complete: {valid_count} valid, {invalid_count} invalid, "
            f"{trimmed_count} descriptions trimmed"
        )

        # Save validated resources
        self._save_validated_resources(validated_resources)

        return validated_resources

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
        return output_path
