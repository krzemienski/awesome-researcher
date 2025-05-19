"""
Validator for candidate resources.
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set

import requests
from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from awesome_list_researcher.category_agent import ResearchCandidate
from awesome_list_researcher.utils.cost_guard import CostGuard
from awesome_list_researcher.utils.logging import APICallLogRecord


class Validator:
    """
    Validator for candidate resources.
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
            model: OpenAI model to use
            api_client: OpenAI client
            cost_guard: Cost guard for tracking API costs
            logger: Logger instance
            min_stars: Minimum number of GitHub stars for a repository
        """
        self.model = model
        self.api_client = api_client
        self.cost_guard = cost_guard
        self.logger = logger
        self.min_stars = min_stars
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Awesome-List-Researcher/0.1.0"
        })

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

    def _cleanup_description(
        self,
        candidate: ResearchCandidate
    ) -> Tuple[str, int]:
        """
        Clean up and normalize the description of a candidate resource.

        Args:
            candidate: Candidate resource to clean up

        Returns:
            Tuple of (cleaned description, tokens used)
        """
        name = candidate.name
        description = candidate.description
        category = candidate.category
        subcategory = candidate.subcategory or ""

        # Check if the description needs cleanup
        if (
            len(description) <= 100 and
            description[0].isupper() and
            not description.endswith(".")
        ):
            # No cleanup needed
            return description, 0

        system_prompt = """
You are a description cleaner for the Awesome List project. Your task is to reformat and improve
resource descriptions following these rules:

1. Make the description clear, concise, and informative
2. Use sentence case (capitalize the first letter only)
3. Keep it under 100 characters (shorter is better)
4. Don't include a period at the end
5. Avoid promotional language or value claims (like "best" or "amazing")
6. Focus on what the resource DOES, not why it's good
7. Use present tense
"""

        user_prompt = f"""
Resource: {name}
Category: {category}{f", Subcategory: {subcategory}" if subcategory else ""}
Current description: "{description}"

Please rewrite this description following the rules. Return ONLY the cleaned-up description text.
"""

        # Check if the API call would exceed the cost ceiling
        estimated_tokens = len(system_prompt.split()) + len(user_prompt.split()) + 50
        if self.cost_guard.would_exceed_ceiling(self.model, estimated_tokens, estimated_tokens // 4):
            self.logger.warning(f"Cost ceiling would be exceeded for cleaning description, skipping")
            return description, 0

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
                max_tokens=100
            )

            # Update cost
            self.cost_guard.update_from_completion(completion, self.model)

            # Log full prompt and completion
            latency = time.time() - start_time
            api_log = APICallLogRecord(
                agent_id="validator",
                model=self.model,
                prompt=f"System: {system_prompt}\nUser: {user_prompt}",
                completion=completion.choices[0].message.content,
                tokens=completion.usage.total_tokens,
                cost_usd=self.cost_guard.total_cost_usd,
                latency=latency
            )

            self.logger.info(f"API call log: {api_log.to_json()}")

            # Get the cleaned description
            cleaned_description = completion.choices[0].message.content.strip()

            # Remove any quotes or period at the end
            cleaned_description = cleaned_description.strip('"\'')
            cleaned_description = cleaned_description.rstrip(".")

            self.logger.info(f"Original description: '{description}'")
            self.logger.info(f"Cleaned description: '{cleaned_description}'")

            return cleaned_description, completion.usage.total_tokens

        except Exception as e:
            self.logger.error(f"Error cleaning description: {str(e)}")
            return description, 0

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

        for i, candidate in enumerate(candidates):
            self.logger.info(f"Validating candidate {i+1}/{len(candidates)}: {candidate.name}")

            # Check if the URL is accessible
            try:
                url_accessible = self._check_url_accessibility(candidate.url)
                if not url_accessible:
                    self.logger.warning(f"URL {candidate.url} is not accessible, skipping")
                    invalid_candidates.append(candidate)
                    continue
            except Exception as e:
                self.logger.error(f"Error checking URL {candidate.url}: {str(e)}")
                invalid_candidates.append(candidate)
                continue

            # Clean up the description
            cleaned_description, tokens_used = self._cleanup_description(candidate)

            # Create a new candidate with the cleaned description
            cleaned_candidate = ResearchCandidate(
                name=candidate.name,
                url=candidate.url,
                description=cleaned_description,
                category=candidate.category,
                subcategory=candidate.subcategory,
                source_query=candidate.source_query
            )

            valid_candidates.append(cleaned_candidate)

        self.logger.info(
            f"Validated {len(candidates)} candidates: "
            f"{len(valid_candidates)} valid, {len(invalid_candidates)} invalid"
        )

        return valid_candidates, invalid_candidates

    def save_validated_candidates(self, candidates: List[ResearchCandidate], output_path: str) -> None:
        """
        Save validated candidates to a JSON file.

        Args:
            candidates: List of validated candidates
            output_path: Path to save the candidates
        """
        # Convert to list of dictionaries
        candidates_data = [c.to_dict() for c in candidates]

        # Write the file
        with open(output_path, "w") as f:
            json.dump(candidates_data, f, indent=2)

        self.logger.info(f"Saved {len(candidates)} validated candidates to {output_path}")
