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

    def _sort_links(self, links: List[AwesomeLink]) -> List[AwesomeLink]:
        """
        Sort links alphabetically by name, ignoring "A", "An", "The".

        Args:
            links: List of links to sort

        Returns:
            Sorted list of links
        """
        def get_sort_key(link: AwesomeLink) -> str:
            # Remove leading articles for sorting
            name = link.name
            name = re.sub(r'^(A|An|The) ', '', name)
            return name.lower()

        return sorted(links, key=get_sort_key)

    def _insert_links_into_category(
        self,
        category: AwesomeCategory,
        new_links: List[AwesomeLink]
    ) -> None:
        """
        Insert new links into a category, maintaining alphabetical order.

        Args:
            category: Category to insert links into
            new_links: New links to insert
        """
        # Group new links by subcategory
        links_by_subcategory = {}
        for link in new_links:
            subcategory = link.subcategory
            if subcategory not in links_by_subcategory:
                links_by_subcategory[subcategory] = []
            links_by_subcategory[subcategory].append(link)

        # Insert links without subcategory
        if None in links_by_subcategory:
            category.links.extend(links_by_subcategory[None])
            category.links = self._sort_links(category.links)

        # Insert links with subcategories
        for subcategory, links in links_by_subcategory.items():
            if subcategory is None:
                continue

            if subcategory not in category.subcategories:
                category.subcategories[subcategory] = []

            category.subcategories[subcategory].extend(links)
            category.subcategories[subcategory] = self._sort_links(
                category.subcategories[subcategory]
            )

    def _update_awesome_list(
        self,
        awesome_list: AwesomeList,
        new_links: List[ResearchCandidate]
    ) -> AwesomeList:
        """
        Update an Awesome List with new links.

        Args:
            awesome_list: Original Awesome List
            new_links: New links to add

        Returns:
            Updated Awesome List
        """
        # Create a copy of the original list
        updated_list = AwesomeList(
            title=awesome_list.title,
            description=awesome_list.description,
            categories=[
                AwesomeCategory(
                    name=category.name,
                    links=category.links.copy(),
                    subcategories={
                        subcat: links.copy()
                        for subcat, links in category.subcategories.items()
                    }
                )
                for category in awesome_list.categories
            ]
        )

        # Convert candidates to AwesomeLink objects
        new_awesome_links = [candidate.to_awesome_link() for candidate in new_links]

        # Group new links by category
        links_by_category = {}
        for link in new_awesome_links:
            category_name = link.category
            if category_name not in links_by_category:
                links_by_category[category_name] = []
            links_by_category[category_name].append(link)

        # Insert new links into categories
        for category_name, category_links in links_by_category.items():
            # Find the matching category
            matching_categories = [
                category for category in updated_list.categories
                if category.name == category_name
            ]

            if matching_categories:
                category = matching_categories[0]
                self._insert_links_into_category(category, category_links)
            else:
                # If the category doesn't exist, create it
                self.logger.info(f"Creating new category: {category_name}")
                new_category = AwesomeCategory(name=category_name)
                self._insert_links_into_category(new_category, category_links)

                # Add the new category at the end, before any Contributing or License sections
                # Find the index of Contributing or License
                contrib_index = next(
                    (i for i, cat in enumerate(updated_list.categories)
                     if cat.name.lower() in ["contributing", "license"]),
                    len(updated_list.categories)
                )

                updated_list.categories.insert(contrib_index, new_category)

        return updated_list

    def _generate_toc(self, awesome_list: AwesomeList) -> str:
        """
        Generate a table of contents for an Awesome List.

        Args:
            awesome_list: Awesome List to generate TOC for

        Returns:
            Markdown string with the table of contents
        """
        # Count the total number of links
        total_links = sum(
            len(category.links) + sum(len(links) for links in category.subcategories.values())
            for category in awesome_list.categories
        )

        # Only generate a TOC if there are more than 40 links
        if total_links <= 40:
            return ""

        toc_lines = ["## Contents\n"]

        for category in awesome_list.categories:
            category_name = category.name

            # Skip certain categories in the TOC
            if category_name.lower() in ["contents", "table of contents"]:
                continue

            # Create a link-friendly ID
            category_id = category_name.lower().replace(" ", "-")
            category_id = re.sub(r'[^\w\-]', '', category_id)

            toc_lines.append(f"- [{category_name}](#{category_id})")

            # Add subcategories if any
            if category.subcategories:
                for subcategory in sorted(category.subcategories.keys()):
                    # Create a link-friendly ID for the subcategory
                    subcategory_id = f"{category_id}-{subcategory.lower().replace(' ', '-')}"
                    subcategory_id = re.sub(r'[^\w\-]', '', subcategory_id)

                    toc_lines.append(f"  - [{subcategory}](#{subcategory_id})")

        return "\n".join(toc_lines) + "\n"

    def _generate_contributing_section(self) -> str:
        """
        Generate a Contributing section for an Awesome List.

        Returns:
            Markdown string with the Contributing section
        """
        # Check if CONTRIBUTING_TEMPLATE.md exists
        if os.path.exists("CONTRIBUTING_TEMPLATE.md"):
            with open("CONTRIBUTING_TEMPLATE.md", "r") as f:
                return f.read()
        else:
            # Generate a basic Contributing section
            return """
## Contributing

Your contributions are always welcome! Please take a look at the [contribution guidelines](CONTRIBUTING.md) first.

- To add, remove, or update an item, please submit a pull request
- All contributors will be added to this document
- Make sure to follow the [Awesome List Guidelines](https://github.com/sindresorhus/awesome/blob/main/pull_request_template.md)

Thank you to all contributors!
"""

    def _render_markdown(self, awesome_list: AwesomeList) -> str:
        """
        Render an Awesome List as Markdown.

        Args:
            awesome_list: Awesome List to render

        Returns:
            Markdown string
        """
        lines = []

        # Add title and description
        lines.append(f"# {awesome_list.title}")
        lines.append("")
        lines.append(awesome_list.description)
        lines.append("")

        # Add table of contents if needed
        toc = self._generate_toc(awesome_list)
        if toc:
            lines.append(toc)

        # Add categories and links
        for category in awesome_list.categories:
            lines.append(f"## {category.name}")
            lines.append("")

            # Add category links
            for link in category.links:
                lines.append(link.to_markdown())

            lines.append("")

            # Add subcategories
            for subcategory, subcat_links in sorted(category.subcategories.items()):
                lines.append(f"### {subcategory}")
                lines.append("")

                for link in subcat_links:
                    lines.append(link.to_markdown())

                lines.append("")

        return "\n".join(lines)

    def render_updated_list(
        self,
        awesome_list: AwesomeList,
        new_links: List[ResearchCandidate],
        output_path: str
    ) -> bool:
        """
        Render an updated Awesome List with new links and save it to a file.

        Args:
            awesome_list: Original Awesome List
            new_links: New links to add
            output_path: Path to save the updated list

        Returns:
            True if the rendering was successful and passes validation
        """
        self.logger.info(f"Rendering updated list with {len(new_links)} new links")

        # Update the list with new links
        updated_list = self._update_awesome_list(awesome_list, new_links)

        # Render the updated list as Markdown
        markdown = self._render_markdown(updated_list)

        # Save the Markdown to the output file
        with open(output_path, "w") as f:
            f.write(markdown)

        self.logger.info(f"Saved updated list to {output_path}")

        # Validate the updated list with awesome-lint
        validation_result = self._validate_with_awesome_lint(output_path)

        return validation_result

    def _validate_with_awesome_lint(self, markdown_path: str) -> bool:
        """
        Validate a Markdown file with awesome-lint.

        Args:
            markdown_path: Path to the Markdown file

        Returns:
            True if the validation succeeded, False otherwise
        """
        self.logger.info(f"Validating {markdown_path} with awesome-lint")

        # Create a temporary directory for validation
        # (awesome-lint requires the file to be named README.md)
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy the file to the temporary directory as README.md
            readme_path = os.path.join(temp_dir, "README.md")
            with open(markdown_path, "r") as src_file:
                with open(readme_path, "w") as dest_file:
                    dest_file.write(src_file.read())

            # Run awesome-lint on the temporary README.md
            try:
                result = subprocess.run(
                    ["awesome-lint", readme_path],
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode == 0:
                    self.logger.info("awesome-lint validation passed")
                    return True
                else:
                    self.logger.error(f"awesome-lint validation failed: {result.stderr}")
                    # Try to fix common issues and revalidate
                    fixed = self._fix_common_lint_issues(markdown_path)
                    if fixed:
                        return self._validate_with_awesome_lint(markdown_path)
                    return False

            except Exception as e:
                self.logger.error(f"Error running awesome-lint: {str(e)}")
                return False

    def _fix_common_lint_issues(self, markdown_path: str) -> bool:
        """
        Fix common lint issues in a Markdown file.

        Args:
            markdown_path: Path to the Markdown file

        Returns:
            True if fixes were applied, False otherwise
        """
        self.logger.info(f"Attempting to fix common lint issues in {markdown_path}")

        with open(markdown_path, "r") as f:
            content = f.read()

        # Fix issue: Missing newline at end of file
        if not content.endswith("\n"):
            content += "\n"

        # Fix issue: Multiple consecutive blank lines
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Fix issue: Trailing whitespace
        content = re.sub(r'[ \t]+\n', '\n', content)

        # Fix issue: Links ending with periods
        content = re.sub(r'\) - ([^.]+)\.(\s)', r') - \1\2', content)

        # Fix issue: Description length > 100 characters
        def shorten_description(match):
            desc = match.group(2)
            if len(desc) > 100:
                desc = desc[:97] + "..."
            return match.group(1) + desc + match.group(3)

        content = re.sub(r'(\) - )([^"\n]{101,})(\s)', shorten_description, content)

        with open(markdown_path, "w") as f:
            f.write(content)

        return True

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
