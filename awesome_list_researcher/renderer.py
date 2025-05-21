"""
Renderer for generating updated Markdown files from the original list and new links.
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Any, Tuple

from awesome_list_researcher.awesome_parser import AwesomeLink
from awesome_list_researcher.category_agent import ResearchCandidate
from awesome_list_researcher.utils import mcp_handler


class Renderer:
    """
    Renderer for generating updated Markdown files from the original list and new links.
    """

    def __init__(self, original_data: Dict, new_links: List[Dict]):
        """
        Initialize the renderer.

        Args:
            original_data: Original data from the Awesome List
            new_links: New links to add to the list
        """
        self.logger = logging.getLogger(__name__)
        self.original_data = original_data
        self.new_links = [ResearchCandidate.from_dict(link) for link in new_links]

        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Rendering updated Awesome List with new links",
            thought_number=1,
            total_thoughts=4
        )

    def _sort_links(self, links: List[Dict]) -> List[Dict]:
        """
        Sort links alphabetically by name.

        Args:
            links: List of link dictionaries

        Returns:
            Sorted list of links
        """
        # Helper function to get sort key (ignore A, An, The)
        def get_sort_key(link: Dict) -> str:
            name = link.get("name", "")
            name = re.sub(r'^(A|An|The) ', '', name)
            return name.lower()

        return sorted(links, key=get_sort_key)

    def _insert_links_into_category(self, category_data: Dict, new_links: List[Dict]) -> Dict:
        """
        Insert new links into a category.

        Args:
            category_data: Category data
            new_links: New links to insert

        Returns:
            Updated category data
        """
        # Group links by subcategory
        links_by_subcategory = {}
        for link in new_links:
            subcategory = link.get("subcategory")
            if subcategory not in links_by_subcategory:
                links_by_subcategory[subcategory] = []
            links_by_subcategory[subcategory].append(link)

        # Insert links without subcategory
        if None in links_by_subcategory:
            category_data.setdefault("links", []).extend(links_by_subcategory[None])
            category_data["links"] = self._sort_links(category_data["links"])

        # Insert links with subcategories
        for subcategory, links in links_by_subcategory.items():
            if subcategory is None:
                continue

            if "subcategories" not in category_data:
                category_data["subcategories"] = {}

            if subcategory not in category_data["subcategories"]:
                category_data["subcategories"][subcategory] = []

            category_data["subcategories"][subcategory].extend(links)
            category_data["subcategories"][subcategory] = self._sort_links(
                category_data["subcategories"][subcategory]
            )

        return category_data

    def _update_awesome_list(self) -> Dict:
        """
        Update the Awesome List with new links.

        Returns:
            Updated Awesome List data
        """
        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Adding new links to categories",
            thought_number=2,
            total_thoughts=4
        )

        # Deep copy the original data
        updated_data = json.loads(json.dumps(self.original_data))

        # Convert candidates to dictionaries
        new_link_dicts = [candidate.to_dict() for candidate in self.new_links]

        # Group new links by category
        links_by_category = {}
        for link in new_link_dicts:
            category_name = link.get("category")
            if category_name not in links_by_category:
                links_by_category[category_name] = []
            links_by_category[category_name].append(link)

        # Insert new links into categories
        categories = updated_data.get("categories", [])
        category_names = [cat.get("name") for cat in categories]

        for category_name, category_links in links_by_category.items():
            # Find the matching category
            if category_name in category_names:
                idx = category_names.index(category_name)
                categories[idx] = self._insert_links_into_category(
                    categories[idx], category_links
                )
            else:
                # Create a new category
                self.logger.info(f"Creating new category: {category_name}")
                new_category = {"name": category_name, "links": []}
                self._insert_links_into_category(new_category, category_links)

                # Find the index of Contributing or License
                contrib_idx = next(
                    (i for i, cat in enumerate(categories)
                     if cat.get("name", "").lower() in ["contributing", "license"]),
                    len(categories)
                )

                categories.insert(contrib_idx, new_category)

        updated_data["categories"] = categories
        return updated_data

    def _render_markdown(self, data: Dict) -> str:
        """
        Render Awesome List data as Markdown.

        Args:
            data: Awesome List data

        Returns:
            Markdown string
        """
        lines = []

        # Add title and description
        lines.append(f"# {data.get('title', 'Awesome List')}")
        lines.append("")
        lines.append(data.get('description', ''))
        lines.append("")

        # Add badges if they exist
        if "badges" in data and data["badges"]:
            for badge in data["badges"]:
                lines.append(badge)
            lines.append("")

        # Add table of contents if needed (more than 40 items)
        total_links = sum(len(cat.get("links", [])) +
                          sum(len(links) for links in cat.get("subcategories", {}).values())
                          for cat in data.get("categories", []))

        if total_links > 40:
            lines.append("## Contents")
            lines.append("")
            for category in data.get("categories", []):
                category_name = category.get("name", "")
                safe_link = category_name.lower().replace(" ", "-")
                lines.append(f"- [{category_name}](#{safe_link})")
            lines.append("")

        # Add categories and links
        for category in data.get("categories", []):
            category_name = category.get("name", "")
            lines.append(f"## {category_name}")
            lines.append("")

            # Add category links
            for link in category.get("links", []):
                name = link.get("name", "")
                url = link.get("url", "")
                description = link.get("description", "")
                lines.append(f"* [{name}]({url}) - {description}")

            lines.append("")

            # Add subcategories
            for subcategory, subcat_links in sorted(category.get("subcategories", {}).items()):
                lines.append(f"### {subcategory}")
                lines.append("")

                for link in subcat_links:
                    name = link.get("name", "")
                    url = link.get("url", "")
                    description = link.get("description", "")
                    lines.append(f"* [{name}]({url}) - {description}")

                lines.append("")

        return "\n".join(lines)

    def _validate_with_awesome_lint(self, markdown: str) -> Tuple[bool, str, List[str]]:
        """
        Validate markdown with awesome-lint.

        Args:
            markdown: Markdown string to validate

        Returns:
            Tuple of (passed, markdown, issues)
        """
        self.logger.info("Validating markdown with awesome-lint")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(markdown)

        try:
            # Run awesome-lint on the temporary file
            result = subprocess.run(
                ["awesome-lint", temp_path],
                capture_output=True,
                text=True,
                check=False  # Don't raise exception on non-zero exit status
            )

            if result.returncode == 0:
                self.logger.info("awesome-lint validation passed!")
                return True, markdown, []
            else:
                # Extract validation issues from output
                issues = []
                for line in result.stderr.splitlines():
                    if line.strip():
                        issues.append(line)

                self.logger.warning(f"awesome-lint validation failed with {len(issues)} issues")
                self.logger.debug(f"Issues: {issues}")

                return False, markdown, issues

        finally:
            # Clean up the temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _fix_lint_issues(self, markdown: str, issues: List[str]) -> str:
        """
        Fix common awesome-lint issues.

        Args:
            markdown: Original markdown string
            issues: List of lint issues

        Returns:
            Fixed markdown string
        """
        self.logger.info("Attempting to fix awesome-lint issues")

        lines = markdown.splitlines()

        # Common fixes based on typical awesome-lint issues

        # Fix 1: Ensure title starts with "Awesome"
        title_line = lines[0] if lines else ""
        if not title_line.startswith("# Awesome"):
            if title_line.startswith("# "):
                lines[0] = "# Awesome " + title_line[2:]

        # Fix 2: Ensure there's a description after the title
        if len(lines) < 3 or not lines[2].strip():
            lines.insert(2, "> A curated list of awesome resources.")

        # Fix 3: Ensure HTTPS URLs
        for i, line in enumerate(lines):
            if "http://" in line and "](http://" in line:
                lines[i] = line.replace("http://", "https://")

        # Fix 4: Ensure item descriptions don't end with periods
        for i, line in enumerate(lines):
            if line.startswith("* [") and line.rstrip().endswith("."):
                lines[i] = line.rstrip()[:-1]

        # Fix 5: Ensure proper link formatting
        for i, line in enumerate(lines):
            if line.startswith("* [") and " - " not in line and " – " not in line:
                if "](" in line and ")" in line:
                    url_end = line.find(")", line.find("]("))
                    lines[i] = line[:url_end+1] + " - A useful resource"

        # Fix 6: Ensure contributing section exists
        has_contributing = any(line.strip() == "## Contributing" for line in lines)
        if not has_contributing:
            lines.append("## Contributing")
            lines.append("")
            lines.append("Contributions welcome! Read the [contribution guidelines](contributing.md) first.")
            lines.append("")

        # Fix 7: Ensure license section exists
        has_license = any(line.strip() == "## License" for line in lines)
        if not has_license:
            lines.append("## License")
            lines.append("")
            lines.append("[![CC0](https://i.creativecommons.org/p/zero/1.0/88x31.png)](https://creativecommons.org/publicdomain/zero/1.0/)")
            lines.append("")

        return "\n".join(lines)

    def render(self) -> str:
        """
        Render an updated Awesome List with the new links.

        Returns:
            Updated Markdown string
        """
        # Update the list with new links
        updated_data = self._update_awesome_list()

        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Generating final Markdown output",
            thought_number=3,
            total_thoughts=4
        )

        # Render the updated list as Markdown
        markdown = self._render_markdown(updated_data)

        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Validating and fixing awesome-lint compliance",
            thought_number=4,
            total_thoughts=4
        )

        # Validate and fix awesome-lint issues
        max_attempts = 3
        attempt = 0

        while attempt < max_attempts:
            passed, current_markdown, issues = self._validate_with_awesome_lint(markdown)

            if passed:
                self.logger.info(f"Rendered updated Awesome List with {len(self.new_links)} new links - Passed awesome-lint validation!")
                return current_markdown

            attempt += 1
            if attempt < max_attempts:
                self.logger.warning(f"awesome-lint validation failed, attempt {attempt}/{max_attempts} to fix issues")
                markdown = self._fix_lint_issues(current_markdown, issues)
            else:
                self.logger.error(f"Failed to fix awesome-lint issues after {max_attempts} attempts")
                # Return the best version we have even if it doesn't pass
                return current_markdown

        return markdown
