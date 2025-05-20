"""
Renderer for generating updated Markdown files from the original list and new links.
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Any

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
            total_thoughts=3
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
            total_thoughts=3
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

        # TODO: Add table of contents if needed

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
            total_thoughts=3
        )

        # Render the updated list as Markdown
        markdown = self._render_markdown(updated_data)

        self.logger.info(f"Rendered updated Awesome List with {len(self.new_links)} new links")

        return markdown
