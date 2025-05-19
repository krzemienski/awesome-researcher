"""
Aggregator for combining and analyzing research results.
"""

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from awesome_list_researcher.category_agent import ResearchCandidate, ResearchResult


class Aggregator:
    """
    Aggregator for combining and analyzing research results.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize the aggregator.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.results: List[ResearchResult] = []
        self.all_candidates: List[ResearchCandidate] = []
        self.categories_count: Dict[str, int] = defaultdict(int)
        self.subcategories_count: Dict[str, int] = defaultdict(int)

    def add_result(self, result: ResearchResult) -> None:
        """
        Add a research result to the aggregator.

        Args:
            result: Research result to add
        """
        self.results.append(result)
        self.all_candidates.extend(result.candidates)

        # Update category and subcategory counts
        category = result.category
        subcategory = result.subcategory

        # Count candidates per category and subcategory
        for candidate in result.candidates:
            self.categories_count[category] += 1
            if subcategory:
                self.subcategories_count[f"{category}/{subcategory}"] += 1

        self.logger.info(
            f"Added result with {len(result.candidates)} candidates for query '{result.query}'"
        )

    def get_all_candidates(self) -> List[ResearchCandidate]:
        """
        Get all candidates from all results.

        Returns:
            List of all candidates
        """
        return self.all_candidates

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
            "total_queries": len(self.results),
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
            f"\n- **Total queries executed**: {len(self.results)}",
            f"- **Total candidates found**: {len(self.all_candidates)}",
            f"- **Categories researched**: {len(self.categories_count)}",
            f"- **Subcategories researched**: {len(self.subcategories_count)}",
            f"\n## Research Queries",
            "\nThe following queries were executed during research:"
        ]

        # Add queries
        for i, result in enumerate(self.results, 1):
            cat_info = f"*{result.category}*"
            if result.subcategory:
                cat_info += f" / *{result.subcategory}*"
            report.append(f"\n{i}. **Query**: \"{result.query}\" ({cat_info})")
            report.append(f"   - Found {len(result.candidates)} candidates")

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
