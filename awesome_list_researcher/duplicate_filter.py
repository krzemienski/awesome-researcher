"""
Duplicate detection and filtering for Awesome List candidates.
"""

import logging
import re
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
        self.new_candidates = new_candidates
        self.original_data = original_data

        # Continue sequence thinking with MCP
        mcp_handler.sequence_thinking(
            thought=f"Extracting existing links from original data",
            thought_number=1,
            total_thoughts=3
        )

        # Extract existing URLs and names
        self.existing_urls = set()
        self.existing_names = set()

        self._extract_existing_urls_and_names()

        self.logger.info(f"Extracted {len(self.existing_urls)} existing URLs and {len(self.existing_names)} existing names")

    def _normalize_url(self, url: str) -> str:
        """
        Normalize a URL to make comparison more robust.

        This removes protocol differences (http vs https), trailing slashes,
        and normalizes to lowercase.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL
        """
        # Remove protocol (http:// or https://)
        normalized = re.sub(r'^https?://', '', url)

        # Remove trailing slash if present
        normalized = normalized.rstrip('/')

        # Convert to lowercase
        normalized = normalized.lower()

        return normalized

    def _extract_existing_urls_and_names(self):
        """Extract URLs and names from the original data."""
        for category in self.original_data.get("categories", []):
            category_name = category.get("name", "")

            # Process links in the category
            for link in category.get("links", []):
                if url := link.get("url"):
                    self.existing_urls.add(self._normalize_url(url))

                if name := link.get("name"):
                    self.existing_names.add(name.lower())

            # Process subcategories
            for subcategory in category.get("subcategories", []):
                subcategory_name = subcategory.get("name", "")

                for link in subcategory.get("links", []):
                    if url := link.get("url"):
                        self.existing_urls.add(self._normalize_url(url))

                    if name := link.get("name"):
                        self.existing_names.add(name.lower())

    def filter_duplicates(self) -> List[Dict]:
        """
        Filter out duplicate resources from candidate list.

        Returns:
            List of non-duplicate candidate dictionaries
        """
        mcp_handler.sequence_thinking(
            thought=f"Filtering {len(self.new_candidates)} candidates for duplicates",
            thought_number=2,
            total_thoughts=3
        )

        filtered_candidates = []
        duplicates = []

        for candidate in self.new_candidates:
            # Check if URL already exists
            normalized_url = self._normalize_url(candidate["url"])
            if normalized_url in self.existing_urls:
                self.logger.info(f"Candidate URL duplicate: {candidate['url']}")
                duplicates.append(candidate)
                continue

            # Check if name is too similar
            candidate_name_lower = candidate["name"].lower()
            if candidate_name_lower in self.existing_names:
                self.logger.info(f"Candidate name duplicate: {candidate['name']}")
                duplicates.append(candidate)
                continue

            # Check for fuzzy name matches
            best_match, score, _ = fuzz_process.extractOne(
                candidate_name_lower,
                self.existing_names,
                scorer=fuzz.ratio
            ) if self.existing_names else (None, 0, None)

            if score > 90:  # 90% similarity threshold
                self.logger.info(f"Candidate name fuzzy duplicate: {candidate['name']} -> {best_match} ({score}%)")
                duplicates.append(candidate)
                continue

            # Not a duplicate, add to filtered list
            filtered_candidates.append(candidate)

            # Update existing data with this candidate to avoid duplicates in the same batch
            self.existing_urls.add(normalized_url)
            self.existing_names.add(candidate_name_lower)

        mcp_handler.sequence_thinking(
            thought=f"Filtered out {len(duplicates)} duplicates from {len(self.new_candidates)} candidates",
            thought_number=3,
            total_thoughts=3
        )

        self.logger.info(f"Filtered out {len(duplicates)} duplicates from {len(self.new_candidates)} candidates")

        return filtered_candidates

    def get_duplicate_ratio(self) -> float:
        """
        Get the ratio of duplicates to total candidates.

        Returns:
            Duplicate ratio as a percentage
        """
        if len(self.new_candidates) == 0:
            return 0.0

        # Count duplicates as total candidates minus filtered candidates
        num_duplicates = len(self.new_candidates) - len(self.filter_duplicates())
        return (num_duplicates / len(self.new_candidates)) * 100.0
