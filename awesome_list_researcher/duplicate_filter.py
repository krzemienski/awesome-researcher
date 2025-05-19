"""
Duplicate filtering for candidate resources.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz

from awesome_list_researcher.awesome_parser import AwesomeLink, DuplicateDetector
from awesome_list_researcher.category_agent import ResearchCandidate


class DuplicateFilter:
    """
    Filters duplicate resources from candidate lists.
    """

    def __init__(
        self,
        logger: logging.Logger,
        similarity_threshold: float = 80.0,
        url_exact_match: bool = True
    ):
        """
        Initialize the duplicate filter.

        Args:
            logger: Logger instance
            similarity_threshold: Threshold for fuzzy matching (0-100)
            url_exact_match: Whether to match URLs exactly
        """
        self.logger = logger
        self.detector = DuplicateDetector(
            similarity_threshold=similarity_threshold,
            url_exact_match=url_exact_match
        )

    def add_existing_links(self, links: List[AwesomeLink]) -> None:
        """
        Add existing links to the filter.

        Args:
            links: List of existing links to filter against
        """
        self.detector.add_existing_links(links)
        self.logger.info(f"Added {len(links)} existing links to duplicate filter")

    def extract_all_links(self, awesome_list_dict: Dict) -> List[AwesomeLink]:
        """
        Extract all links from an awesome list dictionary.

        Args:
            awesome_list_dict: Dictionary representation of an awesome list

        Returns:
            List of AwesomeLink objects
        """
        links = []

        for category_data in awesome_list_dict.get("categories", []):
            category_name = category_data.get("name", "")

            # Add links from the category
            for link_data in category_data.get("links", []):
                links.append(AwesomeLink(
                    name=link_data.get("name", ""),
                    url=link_data.get("url", ""),
                    description=link_data.get("description", ""),
                    category=category_name
                ))

            # Add links from subcategories
            for subcat_name, subcat_links in category_data.get("subcategories", {}).items():
                for link_data in subcat_links:
                    links.append(AwesomeLink(
                        name=link_data.get("name", ""),
                        url=link_data.get("url", ""),
                        description=link_data.get("description", ""),
                        category=category_name,
                        subcategory=subcat_name
                    ))

        return links

    def filter_duplicates(
        self,
        candidates: List[ResearchCandidate]
    ) -> Tuple[List[ResearchCandidate], List[ResearchCandidate]]:
        """
        Filter duplicate resources from a list of candidates.

        Args:
            candidates: List of candidate resources

        Returns:
            Tuple of (unique candidates, duplicate candidates)
        """
        unique_candidates = []
        duplicate_candidates = []

        # Add candidates to their respective lists
        for candidate in candidates:
            link = candidate.to_awesome_link()

            if self.detector.is_duplicate(link):
                duplicate_candidates.append(candidate)
            else:
                unique_candidates.append(candidate)
                self.detector.add_link(link)

        self.logger.info(
            f"Filtered {len(duplicate_candidates)} duplicates from {len(candidates)} candidates"
        )

        return unique_candidates, duplicate_candidates

    def filter_duplicates_among_candidates(
        self,
        candidates: List[ResearchCandidate]
    ) -> List[ResearchCandidate]:
        """
        Filter duplicates among candidate resources (without considering existing links).

        Args:
            candidates: List of candidate resources

        Returns:
            List of unique candidate resources
        """
        temp_detector = DuplicateDetector(
            similarity_threshold=self.detector.similarity_threshold,
            url_exact_match=self.detector.url_exact_match
        )

        unique_candidates = []

        for candidate in candidates:
            link = candidate.to_awesome_link()

            if not temp_detector.is_duplicate(link):
                unique_candidates.append(candidate)
                temp_detector.add_link(link)

        self.logger.info(
            f"Filtered {len(candidates) - len(unique_candidates)} "
            f"duplicates among {len(candidates)} candidates"
        )

        return unique_candidates
