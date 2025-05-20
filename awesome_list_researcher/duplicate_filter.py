"""
Duplicate detection and filtering for Awesome List candidates.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz
from rapidfuzz import process as fuzz_process

from awesome_list_researcher.awesome_parser import AwesomeLink
from awesome_list_researcher.category_agent import ResearchCandidate
from awesome_list_researcher.utils import mcp_handler


class DuplicateFilter:
    """
    Filter out duplicate resources from research results.
    """

    def __init__(self, new_candidates: List[Dict], original_data: Dict):
        """
        Initialize the duplicate filter.

        Args:
            new_candidates: List of candidate dictionaries to filter
            original_data: Original data from the awesome list
        """
        self.logger = logging.getLogger(__name__)
        self.similarity_threshold = 80.0
        self.existing_urls: Set[str] = set()
        self.existing_names: Set[str] = set()
        self.new_candidates = [
            ResearchCandidate.from_dict(candidate) for candidate in new_candidates
        ]
        self.duplicate_count = 0
        self.total_count = len(self.new_candidates)

        # Continue sequence thinking with MCP
        mcp_handler.sequence_thinking(
            thought="Filtering duplicate resources",
            thought_number=1,
            total_thoughts=3
        )

        # Extract existing links from original data
        self._extract_existing_links(original_data)

    def _extract_existing_links(self, original_data: Dict) -> None:
        """
        Extract existing links from original data.

        Args:
            original_data: Original data dictionary
        """
        self.logger.info("Extracting existing links from original data")

        # Process all categories
        for category_data in original_data.get("categories", []):
            category_name = category_data.get("name", "")

            # Process main category links
            for link_data in category_data.get("links", []):
                self._add_link_to_existing(link_data)

            # Process subcategory links
            for subcat_name, subcat_links in category_data.get("subcategories", {}).items():
                for link_data in subcat_links:
                    self._add_link_to_existing(link_data)

        self.logger.info(f"Extracted {len(self.existing_urls)} existing URLs and {len(self.existing_names)} existing names")

    def _add_link_to_existing(self, link_data: Dict) -> None:
        """
        Add a link to the existing links sets.

        Args:
            link_data: Link data dictionary
        """
        url = link_data.get("url", "").lower().rstrip("/")
        name = link_data.get("name", "").lower()

        if url:
            self.existing_urls.add(url)

        if name:
            self.existing_names.add(name)

    def _is_duplicate(self, candidate: ResearchCandidate) -> bool:
        """
        Check if a candidate is a duplicate.

        Args:
            candidate: Candidate to check

        Returns:
            True if the candidate is a duplicate
        """
        # Check URL
        norm_url = candidate.url.lower().rstrip("/")
        if norm_url in self.existing_urls:
            return True

        # Check name with fuzzy matching
        norm_name = candidate.name.lower()
        if norm_name in self.existing_names:
            return True

        # Use fuzzy matching for names
        if self.existing_names:
            matches = fuzz_process.extract(
                norm_name,
                self.existing_names,
                scorer=fuzz.ratio,
                limit=5
            )

            for match, score, _ in matches:
                if score >= self.similarity_threshold:
                    self.logger.info(f"Fuzzy match: '{candidate.name}' matches '{match}' with score {score}")
                    return True

        return False

    def filter(self) -> List[Dict]:
        """
        Filter out duplicates from candidates.

        Returns:
            List of non-duplicate candidate dictionaries
        """
        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Applying deduplication filters",
            thought_number=2,
            total_thoughts=3
        )

        filtered_candidates = []

        for candidate in self.new_candidates:
            if not self._is_duplicate(candidate):
                filtered_candidates.append(candidate)

                # Add to sets to avoid duplicates within the new candidates
                self.existing_urls.add(candidate.url.lower().rstrip("/"))
                self.existing_names.add(candidate.name.lower())
            else:
                self.duplicate_count += 1

        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought=f"Found {self.duplicate_count} duplicates out of {self.total_count} candidates",
            thought_number=3,
            total_thoughts=3
        )

        self.logger.info(f"Filtered out {self.duplicate_count} duplicates from {self.total_count} candidates")

        # Convert back to dictionary representation
        return [candidate.to_dict() for candidate in filtered_candidates]

    def get_duplicate_ratio(self) -> float:
        """
        Get the ratio of duplicates to total candidates.

        Returns:
            Duplicate ratio as a percentage
        """
        if self.total_count == 0:
            return 0.0

        return (self.duplicate_count / self.total_count) * 100.0
