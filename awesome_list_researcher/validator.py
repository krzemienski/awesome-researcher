"""
Validator for candidate resources.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

import httpx
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential
)

from awesome_list_researcher.category_agent import ResearchCandidate
from awesome_list_researcher.utils.cost_guard import CostGuard
from awesome_list_researcher.utils.github import GitHubAPI, is_github_url, parse_github_url


class Validator:
    """
    Validates candidate resources against quality criteria.
    """

    DESCRIPTION_PROMPT = """
You are a description formatter for resources in an Awesome List.
Your task is to refine resource descriptions to match the Awesome List style guide:

1. Begin with a capital letter
2. Do not end with a period
3. Keep to under 100 characters
4. Be concise but informative
5. Avoid promotional language ('best', 'amazing', etc.)
6. Focus on what the resource does/provides

Original description: "{description}"

Give only the improved description, nothing else.
"""

    def __init__(
        self,
        model: str,
        api_client: OpenAI,
        cost_guard: CostGuard,
        logger: logging.Logger,
        min_stars: int = 100
    ):
        """
        Initialize the validator.

        Args:
            model: OpenAI model to use for validation
            api_client: OpenAI API client
            cost_guard: Cost guard for tracking API usage
            logger: Logger instance
            min_stars: Minimum GitHub stars required for repositories
        """
        self.model = model
        self.api_client = api_client
        self.cost_guard = cost_guard
        self.logger = logger
        self.min_stars = min_stars

        self.http_client = httpx.Client(follow_redirects=True, timeout=10.0)
        self.github_api = GitHubAPI(logger)

    def validate_candidates(
        self,
        candidates: List[ResearchCandidate]
    ) -> Tuple[List[ResearchCandidate], List[ResearchCandidate]]:
        """
        Validate a list of candidate resources.

        Args:
            candidates: List of candidate resources to validate

        Returns:
            Tuple of (valid candidates, invalid candidates)
        """
        valid_candidates = []
        invalid_candidates = []

        for candidate in candidates:
            try:
                # Validate URL
                if not self._validate_url(candidate.url):
                    self.logger.info(f"Invalid URL: {candidate.url}")
                    invalid_candidates.append(candidate)
                    continue

                # Validate GitHub stars if it's a GitHub repository
                if is_github_url(candidate.url) and not self._validate_github_stars(candidate):
                    self.logger.info(
                        f"Insufficient GitHub stars for {candidate.url} "
                        f"(required: {self.min_stars})"
                    )
                    invalid_candidates.append(candidate)
                    continue

                # Clean up description
                cleaned_description = self._clean_description(candidate.description)

                # If needed, use the LLM to improve the description
                if len(cleaned_description) > 100 or self._needs_description_improvement(cleaned_description):
                    improved_description = self._improve_description(cleaned_description)
                    candidate.description = improved_description
                else:
                    candidate.description = cleaned_description

                # Mark as validated and add to valid candidates
                candidate.validated = True
                valid_candidates.append(candidate)

            except Exception as e:
                self.logger.error(f"Error validating candidate {candidate.name}: {str(e)}")
                invalid_candidates.append(candidate)

        self.logger.info(
            f"Validated {len(valid_candidates)} candidates, "
            f"rejected {len(invalid_candidates)} candidates"
        )

        return valid_candidates, invalid_candidates

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3)
    )
    def _validate_url(self, url: str) -> bool:
        """
        Validate a URL by checking that it:
        1. Uses HTTPS
        2. Is accessible (200 OK)

        Args:
            url: URL to validate

        Returns:
            True if the URL is valid
        """
        # Check HTTPS
        if not url.startswith("https://"):
            return False

        try:
            # Check accessibility with HEAD request
            response = self.http_client.head(url)
            return response.status_code == 200
        except Exception:
            return False

    def _validate_github_stars(self, candidate: ResearchCandidate) -> bool:
        """
        Validate that a GitHub repository has enough stars.

        Args:
            candidate: Candidate to validate

        Returns:
            True if the repository has enough stars
        """
        try:
            # Parse the GitHub URL
            owner, repo = parse_github_url(candidate.url)

            # Get the star count
            stars = self.github_api.get_repo_stars(owner, repo)

            # Update the candidate with the star count
            candidate.stars = stars

            return stars >= self.min_stars

        except Exception as e:
            self.logger.warning(f"Error checking GitHub stars: {str(e)}")
            return False

    def _clean_description(self, description: str) -> str:
        """
        Clean up a description by:
        1. Removing leading/trailing whitespace
        2. Capitalizing the first letter
        3. Removing trailing periods

        Args:
            description: Description to clean

        Returns:
            Cleaned description
        """
        # Remove leading/trailing whitespace
        description = description.strip()

        # Capitalize first letter
        if description and len(description) > 0:
            description = description[0].upper() + description[1:]

        # Remove trailing periods
        description = description.rstrip(".")

        return description

    def _needs_description_improvement(self, description: str) -> bool:
        """
        Check if a description needs improvement.

        Args:
            description: Description to check

        Returns:
            True if the description needs improvement
        """
        # Check for promotional language
        promotional_words = [
            "best", "amazing", "awesome", "incredible", "excellent",
            "outstanding", "superior", "fantastic", "greatest",
            "perfect", "ultimate", "unbelievable", "magnificent"
        ]

        # Convert description to lowercase for case-insensitive matching
        lower_desc = description.lower()

        for word in promotional_words:
            if f" {word} " in f" {lower_desc} ":
                return True

        # Check for exclamation marks
        if "!" in description:
            return True

        return False

    def _improve_description(self, description: str) -> str:
        """
        Improve a description using the language model.

        Args:
            description: Description to improve

        Returns:
            Improved description
        """
        # Prepare the prompt
        prompt = self.DESCRIPTION_PROMPT.format(description=description)

        # Check if the API call would exceed the cost ceiling
        input_tokens = len(prompt.split()) * 1.5  # Rough estimate
        if self.cost_guard.would_exceed_ceiling(self.model, int(input_tokens)):
            self.logger.warning("Cost ceiling would be exceeded, skipping description improvement")
            return description

        try:
            # Call the OpenAI API
            response = self.api_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150
            )

            # Track usage
            usage = response.usage
            self.cost_guard.update_usage(
                model=self.model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                event="improve_description"
            )

            # Get the improved description
            improved_description = response.choices[0].message.content.strip()

            # If the improved description is too long, truncate it
            if len(improved_description) > 100:
                improved_description = improved_description[:97] + "..."

            return improved_description

        except Exception as e:
            self.logger.error(f"Error improving description: {str(e)}")
            return description

    def save_validated_candidates(self, candidates: List[ResearchCandidate], output_path: str) -> None:
        """
        Save validated candidates to a JSON file.

        Args:
            candidates: List of validated candidates
            output_path: Path to save the candidates to
        """
        candidates_data = [candidate.to_dict() for candidate in candidates]

        with open(output_path, 'w') as f:
            json.dump(candidates_data, f, indent=2)

        self.logger.info(f"Saved {len(candidates)} validated candidates to {output_path}")
