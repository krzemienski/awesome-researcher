"""
Renderer for generating updated Markdown files from the original list and new links.
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from awesome_list_researcher.awesome_parser import (
    AwesomeCategory,
    AwesomeLink,
    AwesomeList,
    MarkdownParser
)
from awesome_list_researcher.category_agent import ResearchCandidate


@dataclass
class Renderer:
    """
    Renders an updated Markdown file with new links.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize the renderer.

        Args:
            logger: Logger instance
        """
        self.logger = logger

    def render_updated_list(
        self,
        original_list: AwesomeList,
        new_links: List[ResearchCandidate],
        output_path: str
    ) -> bool:
        """
        Render an updated Markdown file with new links.

        Args:
            original_list: Original awesome list
            new_links: New links to add
            output_path: Path to save the updated Markdown file

        Returns:
            True if the file passes awesome-lint
        """
        self.logger.info(
            f"Rendering updated list with {len(new_links)} new links"
        )

        # Convert candidates to AwesomeLink objects
        awesome_links = [candidate.to_awesome_link() for candidate in new_links]

        # Group links by category and subcategory
        links_by_category = {}

        for link in awesome_links:
            category_name = link.category
            subcategory_name = link.subcategory

            if category_name not in links_by_category:
                links_by_category[category_name] = {None: []}

            if subcategory_name is not None:
                if subcategory_name not in links_by_category[category_name]:
                    links_by_category[category_name][subcategory_name] = []
                links_by_category[category_name][subcategory_name].append(link)
            else:
                links_by_category[category_name][None].append(link)

        # Create a deep copy of the original list
        updated_list = AwesomeList(
            title=original_list.title,
            description=original_list.description,
            categories=[]
        )

        # Add categories from the original list
        for category in original_list.categories:
            new_category = AwesomeCategory(
                name=category.name,
                links=category.links.copy(),
                subcategories={k: v.copy() for k, v in category.subcategories.items()}
            )
            updated_list.categories.append(new_category)

        # Add new links to the updated list
        for category in updated_list.categories:
            category_name = category.name

            if category_name in links_by_category:
                # Add links with no subcategory
                if None in links_by_category[category_name]:
                    category.links.extend(links_by_category[category_name][None])
                    # Sort alphabetically
                    category.links.sort(key=lambda x: x.name.lower())

                # Add links with subcategories
                for subcategory_name, subcategory_links in links_by_category[category_name].items():
                    if subcategory_name is not None:
                        if subcategory_name not in category.subcategories:
                            category.subcategories[subcategory_name] = []

                        category.subcategories[subcategory_name].extend(subcategory_links)
                        # Sort alphabetically
                        category.subcategories[subcategory_name].sort(key=lambda x: x.name.lower())

        # Render the Markdown
        markdown = self._render_markdown(updated_list)

        # Save the Markdown to the output file
        with open(output_path, 'w') as f:
            f.write(markdown)

        self.logger.info(f"Saved updated Markdown to {output_path}")

        # Validate with awesome-lint
        lint_result = self._validate_with_awesome_lint(output_path)

        if not lint_result:
            self.logger.warning(f"Generated Markdown failed awesome-lint validation")
        else:
            self.logger.info(f"Generated Markdown passed awesome-lint validation")

        return lint_result

    def _render_markdown(self, awesome_list: AwesomeList) -> str:
        """
        Render an AwesomeList object as Markdown.

        Args:
            awesome_list: AwesomeList to render

        Returns:
            Markdown string
        """
        lines = []

        # Title
        lines.append(f"# {awesome_list.title}")
        lines.append("")

        # Description
        lines.append(awesome_list.description)
        lines.append("")

        # Categories
        for category in awesome_list.categories:
            lines.append(f"## {category.name}")
            lines.append("")

            # Links in the category
            for link in category.links:
                lines.append(link.to_markdown())

            lines.append("")

            # Subcategories
            for subcategory_name, subcategory_links in sorted(category.subcategories.items()):
                if subcategory_links:
                    lines.append(f"### {subcategory_name}")
                    lines.append("")

                    for link in subcategory_links:
                        lines.append(link.to_markdown())

                    lines.append("")

        # Ensure the file ends with a newline
        if lines[-1] != "":
            lines.append("")

        return "\n".join(lines)

    def _validate_with_awesome_lint(self, markdown_path: str) -> bool:
        """
        Validate a Markdown file with awesome-lint.

        Args:
            markdown_path: Path to the Markdown file

        Returns:
            True if the file passes awesome-lint
        """
        try:
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Create a temporary file
                temp_file = os.path.join(temp_dir, "README.md")

                # Copy the contents of the Markdown file to the temporary file
                with open(markdown_path, 'r') as src_file, open(temp_file, 'w') as dest_file:
                    dest_file.write(src_file.read())

                # Run awesome-lint in the temporary directory
                result = subprocess.run(
                    ["awesome-lint", temp_file],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=temp_dir
                )

                # Check the result
                if result.returncode == 0:
                    return True
                else:
                    self.logger.warning(f"awesome-lint output: {result.stderr}")
                    return False

        except Exception as e:
            self.logger.error(f"Error validating with awesome-lint: {str(e)}")
            return False

    def load_candidates_from_json(self, json_path: str) -> List[ResearchCandidate]:
        """
        Load candidate resources from a JSON file.

        Args:
            json_path: Path to the JSON file

        Returns:
            List of ResearchCandidate objects
        """
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            if isinstance(data, list):
                return [ResearchCandidate.from_dict(item) for item in data]
            else:
                self.logger.error(f"Invalid JSON structure in {json_path}")
                return []

        except Exception as e:
            self.logger.error(f"Error loading candidates from {json_path}: {str(e)}")
            return []
