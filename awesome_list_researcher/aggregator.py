"""
Aggregator for combining research results from multiple agents.
"""

import json
import logging
from typing import Dict, List, Optional, Set

from awesome_list_researcher.category_agent import ResearchCandidate, ResearchResult


class Aggregator:
    """
    Aggregates research results from multiple category agents.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize the aggregator.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.results: List[ResearchResult] = []

    def add_result(self, result: ResearchResult) -> None:
        """
        Add a research result to the aggregator.

        Args:
            result: ResearchResult to add
        """
        self.results.append(result)
        self.logger.info(
            f"Added research result for query '{result.query.query}' "
            f"with {len(result.candidates)} candidates"
        )

    def get_all_candidates(self) -> List[ResearchCandidate]:
        """
        Get all candidate resources from all research results.

        Returns:
            List of all candidate resources
        """
        all_candidates = []

        for result in self.results:
            all_candidates.extend(result.candidates)

        self.logger.info(f"Aggregated {len(all_candidates)} total candidates")

        return all_candidates

    def get_candidates_by_category(self) -> Dict[str, List[ResearchCandidate]]:
        """
        Get candidate resources grouped by category.

        Returns:
            Dictionary mapping category names to lists of candidates
        """
        candidates_by_category = {}

        for result in self.results:
            for candidate in result.candidates:
                category = candidate.category

                if category not in candidates_by_category:
                    candidates_by_category[category] = []

                candidates_by_category[category].append(candidate)

        return candidates_by_category

    def get_candidates_for_category(self, category: str) -> List[ResearchCandidate]:
        """
        Get candidate resources for a specific category.

        Args:
            category: Category name

        Returns:
            List of candidates for the category
        """
        return [
            candidate
            for result in self.results
            for candidate in result.candidates
            if candidate.category == category
        ]

    def save_aggregated_results(self, output_path: str) -> None:
        """
        Save aggregated results to a JSON file.

        Args:
            output_path: Path to save the results to
        """
        aggregated_data = {
            "total_results": len(self.results),
            "total_candidates": len(self.get_all_candidates()),
            "results": [result.to_dict() for result in self.results]
        }

        with open(output_path, 'w') as f:
            json.dump(aggregated_data, f, indent=2)

        self.logger.info(f"Saved aggregated results to {output_path}")

    def generate_research_report(self, output_path: str) -> None:
        """
        Generate a Markdown report of the research results.

        Args:
            output_path: Path to save the report to
        """
        report_lines = ["# Research Report\n"]

        # Summary
        report_lines.append("## Summary\n")
        report_lines.append(f"- Total queries executed: {len(self.results)}")
        report_lines.append(f"- Total candidates found: {len(self.get_all_candidates())}")
        report_lines.append("")

        # Results by category
        report_lines.append("## Results by Category\n")

        candidates_by_category = self.get_candidates_by_category()

        for category, candidates in sorted(candidates_by_category.items()):
            report_lines.append(f"### {category}\n")
            report_lines.append(f"Found {len(candidates)} candidates:\n")

            # Group by subcategory if present
            subcategories = {}
            no_subcategory = []

            for candidate in candidates:
                if candidate.subcategory:
                    if candidate.subcategory not in subcategories:
                        subcategories[candidate.subcategory] = []
                    subcategories[candidate.subcategory].append(candidate)
                else:
                    no_subcategory.append(candidate)

            # Add candidates without subcategory
            if no_subcategory:
                for candidate in no_subcategory:
                    report_lines.append(
                        f"- [{candidate.name}]({candidate.url}) - {candidate.description}"
                    )
                report_lines.append("")

            # Add candidates by subcategory
            for subcategory, subcat_candidates in sorted(subcategories.items()):
                report_lines.append(f"#### {subcategory}\n")
                for candidate in subcat_candidates:
                    report_lines.append(
                        f"- [{candidate.name}]({candidate.url}) - {candidate.description}"
                    )
                report_lines.append("")

        # Queries executed
        report_lines.append("## Queries Executed\n")

        for i, result in enumerate(self.results, 1):
            query = result.query
            category_info = f"Category: {query.category}"
            if query.subcategory:
                category_info += f", Subcategory: {query.subcategory}"

            report_lines.append(f"### Query {i}: {query.query}\n")
            report_lines.append(f"{category_info}\n")
            report_lines.append(f"Found {len(result.candidates)} candidates\n")

        # Write the report
        with open(output_path, 'w') as f:
            f.write('\n'.join(report_lines))

        self.logger.info(f"Generated research report at {output_path}")
