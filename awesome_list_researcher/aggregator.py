"""
Aggregator for combining and analyzing research results.
"""

import json
import logging
import os
from collections import defaultdict
from typing import Dict, List, Any

from awesome_list_researcher.category_agent import ResearchCandidate
from awesome_list_researcher.utils import mcp_handler


class Aggregator:
    """
    Aggregator for combining and analyzing research results.
    """

    def __init__(self, category_results: Dict[str, Dict[str, List[Dict]]]):
        """
        Initialize the aggregator.

        Args:
            category_results: Results from category research
                Dictionary mapping categories to query results
        """
        self.logger = logging.getLogger(__name__)
        self.category_results = category_results
        self.all_candidates: List[ResearchCandidate] = []

        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Aggregating and analyzing research results",
            thought_number=1,
            total_thoughts=2
        )

        self._process_results()

    def _process_results(self):
        """Process the input results and extract candidates."""
        self.logger.info(f"Processing results from {len(self.category_results)} categories")

        for category, query_results in self.category_results.items():
            self.logger.info(f"Processing category: {category} with {len(query_results)} queries")

            for query, candidate_dicts in query_results.items():
                # Convert dicts to ResearchCandidate objects
                candidates = [
                    ResearchCandidate.from_dict(candidate_dict)
                    for candidate_dict in candidate_dicts
                ]

                self.all_candidates.extend(candidates)
                self.logger.info(f"Added {len(candidates)} candidates from query '{query}'")

        self.logger.info(f"Total candidates after aggregation: {len(self.all_candidates)}")

    def aggregate(self) -> List[Dict]:
        """
        Aggregate the results and return a list of candidate dicts.

        Returns:
            List of candidate dictionaries
        """
        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Finalizing aggregated candidates",
            thought_number=2,
            total_thoughts=2
        )

        self.logger.info(f"Returning {len(self.all_candidates)} aggregated candidates")

        # Convert all candidates to dicts
        return [candidate.to_dict() for candidate in self.all_candidates]

    def save_aggregated_results(self, output_path: str) -> None:
        """
        Save aggregated results to a JSON file.

        Args:
            output_path: Path to save the results
        """
        # Create the aggregated data structure
        aggregated_data = {
            "timestamp": datetime.now().isoformat(),
            "total_candidates": len(self.all_candidates),
            "total_queries": len(self.category_results),
            "categories": dict(self.categories_count),
            "subcategories": dict(self.subcategories_count),
            "results": [result.to_dict() for result in self.results],
            "candidates": [candidate.to_dict() for candidate in self.all_candidates]
        }

        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Save the data
        with open(output_path, "w") as f:
            json.dump(aggregated_data, f, indent=2)

        self.logger.info(f"Saved aggregated results to {output_path}")

    def generate_research_report(self, output_path: str) -> None:
        """
        Generate a Markdown research report.

        Args:
            output_path: Path to save the report
        """
        # Create the report content
        report = [
            "# Awesome List Research Report",
            f"\nGenerated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"\n## Summary",
            f"\n- **Total queries executed**: {len(self.category_results)}",
            f"- **Total candidates found**: {len(self.all_candidates)}",
            f"- **Categories researched**: {len(self.categories_count)}",
            f"- **Subcategories researched**: {len(self.subcategories_count)}",
            f"\n## Research Queries",
            "\nThe following queries were executed during research:"
        ]

        # Add queries
        for i, (category, query_results) in enumerate(self.category_results.items(), 1):
            cat_info = f"*{category}*"
            report.append(f"\n{i}. **Category**: {cat_info}")
            report.append(f"   - Found {len(query_results)} queries")

        # Add candidate statistics by category
        report.append(f"\n## Candidate Resources by Category")

        for category, count in sorted(self.categories_count.items(), key=lambda x: x[1], reverse=True):
            report.append(f"\n### {category} ({count} candidates)")

            # Add subcategories for this category
            subcats = {
                subcat.split("/")[1]: count
                for subcat, count in self.subcategories_count.items()
                if subcat.startswith(f"{category}/")
            }

            if subcats:
                for subcat, subcount in sorted(subcats.items(), key=lambda x: x[1], reverse=True):
                    report.append(f"- *{subcat}*: {subcount} candidates")

        # Add sample candidates
        report.append(f"\n## Sample Candidates")

        # Get a maximum of 20 candidates, distributed across categories
        samples_per_category = 3
        sample_candidates = []

        # Group candidates by category
        candidates_by_category = defaultdict(list)
        for candidate in self.all_candidates:
            candidates_by_category[candidate.category].append(candidate)

        # Take samples from each category
        for category, candidates in candidates_by_category.items():
            for candidate in candidates[:samples_per_category]:
                sample_candidates.append(candidate)

        # Add to report
        for candidate in sample_candidates[:20]:
            report.append(f"\n### {candidate.name}")
            report.append(f"- **URL**: {candidate.url}")
            report.append(f"- **Description**: {candidate.description}")
            report.append(f"- **Category**: {candidate.category}")
            if candidate.subcategory:
                report.append(f"- **Subcategory**: {candidate.subcategory}")

        # Write the report
        with open(output_path, "w") as f:
            f.write("\n".join(report))

        self.logger.info(f"Generated research report at {output_path}")
