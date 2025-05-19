"""
Duplicate detection and filtering for Awesome List candidates.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz
from rapidfuzz import process as fuzz_process

from awesome_list_researcher.awesome_parser import AwesomeLink
from awesome_list_researcher.category_agent import ResearchCandidate


class DuplicateFilter:
    """
    Filter out duplicate resources from research results.
    """

    def __init__(self, logger: logging.Logger, similarity_threshold: float = 80.0):
        """
        Initialize the duplicate filter.

        Args:
            logger: Logger instance
            similarity_threshold: Threshold for fuzzy matching (0-100)
        """
        self.logger = logger
        self.similarity_threshold = similarity_threshold
        self.existing_urls: Set[str] = set()
        self.existing_names: Set[str] = set()

    def add_existing_links(self, links: List[AwesomeLink]) -> None:
        """
        Add existing links to the filter.

        Args:
            links: List of existing links
        """
        for link in links:
            self.existing_urls.add(link.url.lower())
            self.existing_names.add(link.name.lower())

        self.logger.info(f"Added {len(links)} existing links to the duplicate filter")

    def _is_duplicate_url(self, url: str) -> bool:
        """
        Check if a URL is a duplicate.

        Args:
            url: URL to check

        Returns:
            True if the URL is a duplicate
        """
        # Normalize URL
        norm_url = url.lower().rstrip("/")

        # Check exact matches
        if norm_url in self.existing_urls:
            return True

        # Add common variations (with/without www, http/https)
        if norm_url.startswith("https://www."):
            alt_url = norm_url.replace("https://www.", "https://")
            if alt_url in self.existing_urls:
                return True
        elif norm_url.startswith("https://"):
            alt_url = norm_url.replace("https://", "https://www.")
            if alt_url in self.existing_urls:
                return True

        return False

    def _is_duplicate_name(self, name: str) -> bool:
        """
        Check if a name is a duplicate using fuzzy matching.

        Args:
            name: Name to check

        Returns:
            True if the name is a duplicate
        """
        norm_name = name.lower()

        # Check exact matches
        if norm_name in self.existing_names:
            return True

        # Check fuzzy matches
        if self.existing_names:
            matches = fuzz_process.extract(
                norm_name,
                self.existing_names,
                scorer=fuzz.ratio,
                limit=5
            )

            for match, score, _ in matches:
                if score >= self.similarity_threshold:
                    self.logger.info(f"Fuzzy match: '{name}' matches '{match}' with score {score}")
                    return True

        return False

    def is_duplicate(self, candidate: ResearchCandidate) -> bool:
        """
        Check if a candidate is a duplicate.

        Args:
            candidate: Candidate to check

        Returns:
            True if the candidate is a duplicate
        """
        # Check URL
        if self._is_duplicate_url(candidate.url):
            self.logger.info(f"Duplicate URL: {candidate.url}")
            return True

        # Check name
        if self._is_duplicate_name(candidate.name):
            self.logger.info(f"Duplicate name: {candidate.name}")
            return True

        return False

    def filter_duplicates(
        self,
        candidates: List[ResearchCandidate]
    ) -> Tuple[List[ResearchCandidate], List[ResearchCandidate]]:
        """
        Filter out duplicates from a list of candidates.

        Args:
            candidates: List of candidates to filter

        Returns:
            Tuple of (unique candidates, duplicate candidates)
        """
        unique_candidates = []
        duplicate_candidates = []

        for candidate in candidates:
            if self.is_duplicate(candidate):
                duplicate_candidates.append(candidate)
            else:
                unique_candidates.append(candidate)
                # Add to existing URLs and names to avoid future duplicates
                self.existing_urls.add(candidate.url.lower().rstrip("/"))
                self.existing_names.add(candidate.name.lower())

        duplicate_rate = len(duplicate_candidates) / len(candidates) if candidates else 0

        self.logger.info(
            f"Filtered {len(duplicate_candidates)} duplicates out of {len(candidates)} candidates "
            f"({duplicate_rate:.2%} duplicate rate)"
        )

        # Warn if the duplicate rate is > 30%
        if duplicate_rate > 0.3:
            self.logger.warning(
                f"High duplicate rate ({duplicate_rate:.2%}). Consider refining search queries."
            )

        return unique_candidates, duplicate_candidates

    def filter_duplicates_among_candidates(
        self,
        candidates: List[ResearchCandidate]
    ) -> List[ResearchCandidate]:
        """
        Filter out duplicates among candidates themselves.

        Args:
            candidates: List of candidates to filter

        Returns:
            List of unique candidates
        """
        unique_candidates = []
        seen_urls = set()
        seen_names = set()

        for candidate in candidates:
            # Check for URL duplicates
            norm_url = candidate.url.lower().rstrip("/")
            if norm_url in seen_urls:
                self.logger.info(f"Duplicate URL among candidates: {candidate.url}")
                continue

            # Check for name duplicates
            is_duplicate = False

            for existing_name in seen_names:
                similarity = fuzz.ratio(candidate.name.lower(), existing_name)
                if similarity >= self.similarity_threshold:
                    self.logger.info(
                        f"Duplicate name among candidates: '{candidate.name}' matches '{existing_name}' "
                        f"with score {similarity}"
                    )
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            # Add candidate to unique list and update seen sets
            unique_candidates.append(candidate)
            seen_urls.add(norm_url)
            seen_names.add(candidate.name.lower())

        self.logger.info(
            f"Filtered {len(candidates) - len(unique_candidates)} duplicates among candidates"
        )

        return unique_candidates
