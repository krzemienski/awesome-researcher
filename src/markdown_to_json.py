"""Convert an Awesome README into structured JSON format."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Regex patterns
TITLE_PATTERN = re.compile(r'^# Awesome (.*?)(?:\s+|$)')
SECTION_PATTERN = re.compile(r'^#{2,3}\s+(.+)$', re.MULTILINE)
ITEM_PATTERN = re.compile(r'^\s*\*\s+\[([^\]]+)\]\(([^)]+)\)(?: - (.+))?$', re.MULTILINE)
CONTRIBUTING_PATTERN = re.compile(r'^#{2,3}\s+Contributing', re.IGNORECASE | re.MULTILINE)

class MarkdownToJson:
    """Convert Awesome List README.md to structured JSON."""

    def __init__(self, logger: logging.Logger, output_dir: str):
        """Initialize the markdown to JSON converter.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
        """
        self.logger = logger
        self.output_dir = output_dir

    def convert_file(self, markdown_path: str) -> Dict[str, Any]:
        """Convert a markdown file to structured JSON.

        Args:
            markdown_path: Path to the markdown file

        Returns:
            Dictionary containing structured data
        """
        # Read markdown file
        with open(markdown_path, 'r', encoding='utf-8') as f:
            markdown = f.read()

        return self.convert_string(markdown)

    def convert_string(self, markdown: str) -> Dict[str, Any]:
        """Convert a markdown string to structured JSON.

        Args:
            markdown: Markdown string

        Returns:
            Dictionary containing structured data
        """
        self.logger.info("Converting markdown to JSON")

        # Extract title
        title_match = TITLE_PATTERN.search(markdown)
        if not title_match:
            self.logger.warning("Could not find title in markdown")
            title = "Unknown"
        else:
            title = title_match.group(1).strip()

        # Extract tagline
        lines = markdown.split('\n')
        tagline = ""
        for i, line in enumerate(lines):
            if TITLE_PATTERN.match(line):
                if i + 1 < len(lines) and not lines[i + 1].startswith('#') and lines[i + 1].strip():
                    tagline = lines[i + 1].strip()
                break

        # Extract sections
        sections = []
        current_section = None

        for line in lines:
            section_match = SECTION_PATTERN.match(line)

            if section_match:
                section_name = section_match.group(1).strip()

                # Skip Contributing section
                if re.match(r'contributing', section_name, re.IGNORECASE):
                    current_section = None
                    continue

                current_section = {
                    "name": section_name,
                    "items": []
                }
                sections.append(current_section)

            elif current_section is not None:
                item_match = ITEM_PATTERN.match(line)

                if item_match:
                    name = item_match.group(1).strip()
                    url = item_match.group(2).strip()
                    description = item_match.group(3).strip() if item_match.group(3) else ""

                    item = {
                        "name": name,
                        "url": url,
                        "description": description
                    }

                    current_section["items"].append(item)

        # Assemble the result
        result = {
            "title": title,
            "tagline": tagline,
            "sections": sections
        }

        self.logger.info(f"Converted {sum(len(section['items']) for section in sections)} items across {len(sections)} sections")

        return result

    def save_json(self, data: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """Save the JSON data to a file.

        Args:
            data: JSON data
            output_path: Path to save the JSON file (optional)

        Returns:
            Path to the saved JSON file
        """
        if output_path is None:
            output_path = os.path.join(self.output_dir, "awesome.json")

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved JSON data to {output_path}")

        return output_path

    def validate_against_schema(self, data: Dict[str, Any], schema_path: str) -> bool:
        """Validate JSON data against a schema.

        Args:
            data: JSON data
            schema_path: Path to the JSON schema file

        Returns:
            True if validation passes, False otherwise
        """
        try:
            import jsonschema

            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)

            jsonschema.validate(data, schema)
            self.logger.info("JSON data validated successfully against schema")
            return True

        except Exception as e:
            self.logger.error(f"JSON schema validation failed: {str(e)}")
            return False
