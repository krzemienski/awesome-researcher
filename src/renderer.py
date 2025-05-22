import json
import logging
import os
import re
from typing import Dict, List, Any, Tuple, Set

from src.awesome_parser import AwesomeParser


class Renderer:
    """Renderer for generating the updated awesome list markdown."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        awesome_parser: AwesomeParser,
    ):
        """Initialize the renderer.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            awesome_parser: AwesomeParser instance
        """
        self.logger = logger
        self.output_dir = output_dir
        self.awesome_parser = awesome_parser

    def render_updated_list(self, original_data: Dict, new_links: List[Dict]) -> str:
        """Render the updated awesome list with new links.

        Args:
            original_data: Original awesome list data
            new_links: New links to add

        Returns:
            Path to the rendered markdown file
        """
        self.logger.info(f"Rendering updated awesome list with {len(new_links)} new links")

        # Create a copy of the original data to modify
        updated_data = self._deep_copy_data(original_data)

        # Categorize new links
        categorized_links = self._categorize_links(updated_data, new_links)

        # Add new links to sections in alphabetical order
        self._add_links_to_sections(updated_data, categorized_links)

        # Render the markdown
        markdown = self._render_markdown(updated_data)

        # Save the markdown to a file
        output_path = os.path.join(self.output_dir, "updated_list.md")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        self.logger.info(f"Saved updated awesome list to {output_path}")

        # Validate with awesome-lint
        self._ensure_lint_passes(output_path)

        return output_path

    def _deep_copy_data(self, data: Dict) -> Dict:
        """Create a deep copy of the data.

        Args:
            data: Data to copy

        Returns:
            Deep copy of the data
        """
        # Use json to create a deep copy
        return json.loads(json.dumps(data))

    def _categorize_links(self, original_data: Dict, new_links: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize new links into sections.

        Args:
            original_data: Original awesome list data
            new_links: New links to categorize

        Returns:
            Dictionary mapping section names to lists of links
        """
        categorized = {}
        uncategorized = []

        # Extract section names
        section_names = [section["name"] for section in original_data.get("sections", [])]

        # Try to match each link to a section
        for link in new_links:
            # Check if the link already has a category assigned
            if "category" in link and link["category"] in section_names:
                # Add to the specified category
                category = link["category"]
                if category not in categorized:
                    categorized[category] = []

                categorized[category].append(link)
                continue

            # If no category is assigned, try to guess based on name or description
            name = link.get("name", "").lower()
            description = link.get("description", "").lower()

            assigned = False
            for section in original_data.get("sections", []):
                section_name = section["name"]
                section_name_lower = section_name.lower()

                # Check if the section name appears in the link name or description
                if (section_name_lower in name or section_name_lower in description):
                    if section_name not in categorized:
                        categorized[section_name] = []

                    categorized[section_name].append(link)
                    assigned = True
                    break

            # If no match was found, add to uncategorized
            if not assigned:
                uncategorized.append(link)

        # Log categorization results
        self.logger.info(
            f"Categorized {sum(len(links) for links in categorized.values())} links into "
            f"{len(categorized)} sections, with {len(uncategorized)} uncategorized"
        )

        # Handle uncategorized links
        if uncategorized:
            # Try to find the most appropriate section for each link
            for link in uncategorized:
                best_section = self._find_best_section(link, original_data)

                if best_section not in categorized:
                    categorized[best_section] = []

                categorized[best_section].append(link)

            self.logger.info(f"Assigned {len(uncategorized)} uncategorized links to best-matching sections")

        return categorized

    def _find_best_section(self, link: Dict, original_data: Dict) -> str:
        """Find the best section for an uncategorized link.

        Args:
            link: Link to categorize
            original_data: Original awesome list data

        Returns:
            Name of the best matching section
        """
        sections = original_data.get("sections", [])

        if not sections:
            return "Miscellaneous"

        # Default to the first section
        best_section = sections[0]["name"]

        # If there's a "Miscellaneous" or "Other" section, use that
        for section in sections:
            if section["name"] in ["Miscellaneous", "Other", "Resources"]:
                return section["name"]

        # Find the section with the most items (as a fallback)
        max_items = 0
        for section in sections:
            if len(section.get("items", [])) > max_items:
                max_items = len(section.get("items", []))
                best_section = section["name"]

        return best_section

    def _add_links_to_sections(self, data: Dict, categorized_links: Dict[str, List[Dict]]) -> None:
        """Add new links to sections in alphabetical order.

        Args:
            data: Data to update
            categorized_links: Dictionary mapping section names to lists of links
        """
        # Process each section
        for section in data.get("sections", []):
            section_name = section["name"]

            # Skip if there are no new links for this section
            if section_name not in categorized_links:
                continue

            # Get new links for this section
            new_section_links = categorized_links[section_name]

            # Extend the items list with new links
            section["items"].extend(new_section_links)

            # Sort items alphabetically (ignoring A/An/The at the beginning)
            section["items"].sort(key=lambda x: self._get_sort_key(x.get("name", "")))

            self.logger.info(f"Added {len(new_section_links)} new links to section '{section_name}'")

    def _get_sort_key(self, title: str) -> str:
        """Get the sorting key for a title, ignoring A/An/The.

        Args:
            title: Title to get the sorting key for

        Returns:
            Sorting key
        """
        # Convert to lowercase for case-insensitive sorting
        title_lower = title.lower()

        # Remove "A ", "An ", or "The " from the beginning
        if title_lower.startswith("a "):
            return title_lower[2:]
        elif title_lower.startswith("an "):
            return title_lower[3:]
        elif title_lower.startswith("the "):
            return title_lower[4:]

        return title_lower

    def _render_markdown(self, data: Dict) -> str:
        """Render the data as markdown.

        Args:
            data: Data to render

        Returns:
            Rendered markdown
        """
        lines = []

        # Add title
        lines.append(f"# Awesome {data.get('title', '')}")

        # Add tagline
        if data.get("tagline"):
            lines.append("")
            lines.append(data.get("tagline"))

        # Add TOC if there are more than 40 items
        total_items = sum(len(section.get("items", [])) for section in data.get("sections", []))
        if total_items > 40:
            lines.append("")
            lines.append("## Contents")
            lines.append("")

            for section in data.get("sections", []):
                section_name = section["name"]
                # Create a link-friendly version of the section name
                section_link = section_name.lower().replace(" ", "-")
                lines.append(f"- [{section_name}](#{section_link})")

        # Add each section
        for section in data.get("sections", []):
            section_name = section["name"]

            lines.append("")
            lines.append(f"## {section_name}")
            lines.append("")

            for item in section.get("items", []):
                name = item.get("name", "")
                url = item.get("url", "")
                description = item.get("description", "")

                if description:
                    lines.append(f"* [{name}]({url}) - {description}")
                else:
                    lines.append(f"* [{name}]({url})")

        # Add Contributing section if not present
        has_contributing = False
        for section in data.get("sections", []):
            if section["name"].lower() == "contributing":
                has_contributing = True
                break

        if not has_contributing:
            lines.append("")
            lines.append("## Contributing")
            lines.append("")
            lines.append("Contributions welcome! Read the [contribution guidelines](contributing.md) first.")

        # Join lines with newlines
        return "\n".join(lines)

    def _ensure_lint_passes(self, markdown_path: str) -> None:
        """Ensure the markdown passes awesome-lint.

        Args:
            markdown_path: Path to the markdown file
        """
        # Try running awesome-lint
        lint_passes = self.awesome_parser.run_awesome_lint(markdown_path)

        # If lint fails, try to fix common issues
        if not lint_passes:
            self.logger.warning("awesome-lint failed, attempting to fix common issues")

            # Read the markdown file
            with open(markdown_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Fix common issues
            # 1. Ensure trailing newline
            if not content.endswith("\n"):
                content += "\n"

            # 2. Ensure consistent list markers (using * instead of - for lists)
            content = re.sub(r"^- ", "* ", content, flags=re.MULTILINE)

            # 3. Fix description formatting
            content = re.sub(
                r"^\* \[([^\]]+)\]\(([^)]+)\) ([^-])",
                r"* [\1](\2) - \3",
                content,
                flags=re.MULTILINE
            )

            # Write the fixed content
            with open(markdown_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Try running awesome-lint again
            lint_passes = self.awesome_parser.run_awesome_lint(markdown_path)

            if lint_passes:
                self.logger.info("Fixed issues, awesome-lint now passes")
            else:
                self.logger.warning("awesome-lint still fails after fixing common issues")

    def create_research_report(self, categorized_links: Dict[str, List[Dict]]) -> str:
        """Create a research report summarizing the new links.

        Args:
            categorized_links: Dictionary mapping section names to lists of links

        Returns:
            Path to the rendered markdown report
        """
        lines = []

        # Add title
        lines.append("# Awesome List Research Report")
        lines.append("")

        # Add summary
        total_links = sum(len(links) for links in categorized_links.values())
        total_sections = len(categorized_links)

        lines.append("## Summary")
        lines.append("")
        lines.append(f"* **Total new links:** {total_links}")
        lines.append(f"* **Categories with new links:** {total_sections}")
        lines.append("")

        # Add section-by-section breakdown
        lines.append("## Categories")
        lines.append("")

        for section_name, links in sorted(categorized_links.items()):
            lines.append(f"### {section_name}")
            lines.append("")
            lines.append(f"**Added {len(links)} new links:**")
            lines.append("")

            for link in links:
                name = link.get("name", "")
                url = link.get("url", "")
                description = link.get("description", "")

                if description:
                    lines.append(f"* [{name}]({url}) - {description}")
                else:
                    lines.append(f"* [{name}]({url})")

            lines.append("")

        # Join lines with newlines
        markdown = "\n".join(lines)

        # Save the markdown to a file
        output_path = os.path.join(self.output_dir, "research_report.md")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        self.logger.info(f"Saved research report to {output_path}")

        return output_path
