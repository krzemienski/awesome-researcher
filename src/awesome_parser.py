import json
import logging
import os
import re
from typing import Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pybloom_live import BloomFilter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# GitHub raw content URLs
RAW_URL_TEMPLATES = [
    "https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/master/README.md",
    "https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/main/README.md",
    "https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
]

# Regex patterns
TITLE_PATTERN = re.compile(r'^# Awesome (.*?)(?:\s+|$)')
SECTION_PATTERN = re.compile(r'^#{2,3}\s+(.+)$', re.MULTILINE)
ITEM_PATTERN = re.compile(r'^\s*\*\s+\[([^\]]+)\]\(([^)]+)\)(?: - (.+))?$', re.MULTILINE)
CONTRIBUTING_PATTERN = re.compile(r'^#{2,3}\s+Contributing', re.IGNORECASE | re.MULTILINE)


class AwesomeParser:
    """Parser for Awesome lists on GitHub."""

    def __init__(self, logger: logging.Logger, output_dir: str):
        """Initialize the parser.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
        """
        self.logger = logger
        self.output_dir = output_dir
        self.bloom_filter = BloomFilter(capacity=10000, error_rate=0.001)
        self.original_urls: Set[str] = set()

    @retry(
        retry=retry_if_exception_type((requests.exceptions.RequestException)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30)
    )
    def fetch_raw_markdown(self, repo_url: str) -> str:
        """Fetch raw markdown content from GitHub repository.

        Args:
            repo_url: URL of the GitHub repository

        Returns:
            Raw markdown content

        Raises:
            ValueError: If all fetch attempts fail
        """
        # Parse repository URL to extract owner and repo name
        parsed_url = urlparse(repo_url)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) < 2 or "github.com" not in parsed_url.netloc:
            raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

        owner, repo = path_parts[0], path_parts[1]

        # Try each URL template
        last_exception = None
        for template in RAW_URL_TEMPLATES:
            raw_url = template.format(owner=owner, repo=repo)

            try:
                self.logger.info(f"Attempting to fetch README from {raw_url}")
                response = requests.get(raw_url, timeout=10)
                response.raise_for_status()
                self.logger.info(f"Successfully fetched README from {raw_url}")
                return response.text
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Failed to fetch from {raw_url}: {str(e)}")
                last_exception = e

        # If all attempts fail, raise an exception
        raise ValueError(f"Failed to fetch README from all URL templates: {last_exception}")

    def parse_markdown(self, markdown: str) -> Dict:
        """Parse markdown content into structured data.

        Args:
            markdown: Raw markdown content

        Returns:
            Dictionary containing parsed data
        """
        self.logger.info("Parsing markdown content")

        # Extract title
        title_match = TITLE_PATTERN.search(markdown)
        if not title_match:
            self.logger.warning("Could not find title in README.md")
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

                    # Add URL to original URLs set and bloom filter
                    self.original_urls.add(url)
                    self.bloom_filter.add(url)

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

        self.logger.info(f"Parsed {sum(len(section['items']) for section in sections)} items across {len(sections)} sections")
        return result

    def save_original_json(self, data: Dict) -> str:
        """Save the original parsed data to a JSON file.

        Args:
            data: Parsed data dictionary

        Returns:
            Path to the saved JSON file
        """
        output_path = os.path.join(self.output_dir, "original.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved original data to {output_path}")
        return output_path

    def url_exists_in_original(self, url: str) -> bool:
        """Check if a URL exists in the original list.

        Args:
            url: URL to check

        Returns:
            True if URL exists in original list, False otherwise
        """
        # First check bloom filter for quick negative results
        if url not in self.bloom_filter:
            return False

        # Double check in the original URLs set for accuracy
        return url in self.original_urls

    def extract_exemplar_titles(self, data: Dict) -> Dict[str, List[str]]:
        """Extract category names and exemplar titles for term expansion.

        Args:
            data: Parsed data dictionary

        Returns:
            Dictionary mapping category names to exemplar titles
        """
        exemplars = {}

        for section in data["sections"]:
            # Skip very short sections
            if len(section["items"]) < 2:
                continue

            # Take up to 5 item names as exemplars
            exemplars[section["name"]] = [
                item["name"] for item in section["items"][:5]
            ]

        return exemplars

    def run_awesome_lint(self, output_path: str) -> bool:
        """Run awesome-lint on a markdown file.

        Args:
            output_path: Path to the markdown file

        Returns:
            True if lint passes, False otherwise
        """
        # Import here to avoid circular imports
        from src.utils.timer import timeout

        try:
            # Use timeout to prevent hanging
            with timeout(30):
                result = os.system(f"awesome-lint {output_path}")
                success = result == 0

                if success:
                    self.logger.info(f"awesome-lint passed for {output_path}")
                else:
                    self.logger.warning(f"awesome-lint failed for {output_path}")

                return success
        except Exception as e:
            self.logger.error(f"Error running awesome-lint: {str(e)}")
            return False


def fetch_and_parse(repo_url: str, logger: logging.Logger, output_dir: str) -> Tuple[AwesomeParser, Dict]:
    """Fetch and parse an awesome list.

    Args:
        repo_url: URL of the GitHub repository
        logger: Logger instance
        output_dir: Directory to store output files

    Returns:
        Tuple of (AwesomeParser instance, parsed data dictionary)
    """
    parser = AwesomeParser(logger, output_dir)

    # Fetch raw markdown
    markdown = parser.fetch_raw_markdown(repo_url)

    # Parse the markdown
    data = parser.parse_markdown(markdown)

    # Save to JSON
    parser.save_original_json(data)

    return parser, data
