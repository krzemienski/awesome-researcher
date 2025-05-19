"""
Parser for Awesome-style Markdown lists.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

import mistletoe
from mistletoe.ast_renderer import ASTRenderer
from rapidfuzz import fuzz


@dataclass
class AwesomeLink:
    """
    Represents a link in an Awesome list.
    """
    name: str
    url: str
    description: str
    category: str
    subcategory: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "category": self.category,
            "subcategory": self.subcategory
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'AwesomeLink':
        """Create from dictionary."""
        return cls(
            name=data["name"],
            url=data["url"],
            description=data["description"],
            category=data["category"],
            subcategory=data.get("subcategory")
        )

    def to_markdown(self) -> str:
        """Convert to Markdown format."""
        return f"* [{self.name}]({self.url}) - {self.description}"


@dataclass
class AwesomeCategory:
    """
    Represents a category in an Awesome list.
    """
    name: str
    links: List[AwesomeLink] = field(default_factory=list)
    subcategories: Dict[str, List[AwesomeLink]] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "links": [link.to_dict() for link in self.links],
        }

        if self.subcategories:
            result["subcategories"] = {
                subcat: [link.to_dict() for link in links]
                for subcat, links in self.subcategories.items()
            }

        return result

    @classmethod
    def from_dict(cls, data: Dict) -> 'AwesomeCategory':
        """Create from dictionary."""
        category = cls(name=data["name"])

        category.links = [
            AwesomeLink.from_dict(link_data)
            for link_data in data.get("links", [])
        ]

        for subcat_name, subcat_links in data.get("subcategories", {}).items():
            category.subcategories[subcat_name] = [
                AwesomeLink.from_dict(link_data)
                for link_data in subcat_links
            ]

        return category


@dataclass
class AwesomeList:
    """
    Represents a parsed Awesome list.
    """
    title: str
    description: str
    categories: List[AwesomeCategory] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "description": self.description,
            "categories": [cat.to_dict() for cat in self.categories]
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'AwesomeList':
        """Create from dictionary."""
        awesome_list = cls(
            title=data["title"],
            description=data["description"]
        )

        awesome_list.categories = [
            AwesomeCategory.from_dict(cat_data)
            for cat_data in data.get("categories", [])
        ]

        return awesome_list

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> 'AwesomeList':
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class MarkdownParser:
    """
    Parser for Awesome-style Markdown lists.
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize the Markdown parser.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.ast_renderer = ASTRenderer()

    def _extract_title_description(self, ast: Dict) -> Tuple[str, str]:
        """
        Extract title and description from AST.

        Args:
            ast: Markdown AST

        Returns:
            Tuple of (title, description)
        """
        title = ""
        description = ""

        # Extract title (first h1)
        for child in ast.get("children", []):
            if child.get("type") == "Heading" and child.get("level") == 1:
                heading_children = child.get("children", [])
                if heading_children:
                    title = heading_children[0].get("content", "")
                break

        # Extract description (first paragraph after h1)
        found_h1 = False
        for child in ast.get("children", []):
            if found_h1 and child.get("type") == "Paragraph":
                para_text = []
                for para_child in child.get("children", []):
                    if "content" in para_child:
                        para_text.append(para_child.get("content", ""))
                description = " ".join(para_text)
                break

            if child.get("type") == "Heading" and child.get("level") == 1:
                found_h1 = True

        return title, description

    def _parse_link(
        self,
        link_item: Dict,
        category: str,
        subcategory: Optional[str] = None
    ) -> Optional[AwesomeLink]:
        """
        Parse a link from an AST list item.

        Args:
            link_item: List item AST
            category: Category name
            subcategory: Subcategory name (optional)

        Returns:
            AwesomeLink or None if not a valid link
        """
        # Check if item has children
        children = link_item.get("children", [])
        if not children:
            return None

        # Check if first child is a paragraph with link
        first_child = children[0]
        if first_child.get("type") != "Paragraph":
            return None

        paragraph_children = first_child.get("children", [])
        if not paragraph_children:
            return None

        # Find the link element
        link_element = None
        for child in paragraph_children:
            if child.get("type") == "Link":
                link_element = child
                break

        if not link_element:
            return None

        # Extract link name and URL
        link_name = ""
        for name_child in link_element.get("children", []):
            if "content" in name_child:
                link_name += name_child.get("content", "")

        link_url = link_element.get("target", "")

        # Extract description (text after the link)
        description = ""
        description_started = False

        for child in paragraph_children:
            if description_started and "content" in child:
                description += child.get("content", "")

            if child is link_element:
                description_started = True

        # Clean up description (remove leading dash/hyphen and whitespace)
        description = re.sub(r'^[\s\-–—]+', '', description).strip()

        # Create and return the link
        return AwesomeLink(
            name=link_name,
            url=link_url,
            description=description,
            category=category,
            subcategory=subcategory
        )

    def _process_list(
        self,
        list_node: Dict,
        category: str,
        subcategory: Optional[str] = None
    ) -> List[AwesomeLink]:
        """
        Process a list of links from AST.

        Args:
            list_node: List AST
            category: Category name
            subcategory: Subcategory name (optional)

        Returns:
            List of AwesomeLink objects
        """
        links = []

        for item in list_node.get("children", []):
            if item.get("type") != "ListItem":
                continue

            link = self._parse_link(item, category, subcategory)
            if link:
                links.append(link)

        return links

    def parse_markdown(self, markdown: str) -> AwesomeList:
        """
        Parse Markdown content into an AwesomeList object.

        Args:
            markdown: Markdown content

        Returns:
            AwesomeList object
        """
        # Parse markdown to AST
        ast = json.loads(self.ast_renderer.render(mistletoe.Document(markdown)))

        # Extract title and description
        title, description = self._extract_title_description(ast)

        awesome_list = AwesomeList(title=title, description=description)

        # Track current category and subcategory
        current_category = None
        current_subcategory = None

        # Iterate through children
        for child in ast.get("children", []):
            # Handle ## headings (categories)
            if child.get("type") == "Heading" and child.get("level") == 2:
                heading_text = ""
                for heading_child in child.get("children", []):
                    if "content" in heading_child:
                        heading_text += heading_child.get("content", "")

                current_category = AwesomeCategory(name=heading_text)
                awesome_list.categories.append(current_category)
                current_subcategory = None

            # Handle ### headings (subcategories)
            elif child.get("type") == "Heading" and child.get("level") == 3:
                heading_text = ""
                for heading_child in child.get("children", []):
                    if "content" in heading_child:
                        heading_text += heading_child.get("content", "")

                current_subcategory = heading_text
                if current_category and current_subcategory not in current_category.subcategories:
                    current_category.subcategories[current_subcategory] = []

            # Handle lists
            elif child.get("type") == "List" and current_category:
                category_name = current_category.name

                links = self._process_list(child, category_name, current_subcategory)

                if current_subcategory:
                    if current_subcategory not in current_category.subcategories:
                        current_category.subcategories[current_subcategory] = []
                    current_category.subcategories[current_subcategory].extend(links)
                else:
                    current_category.links.extend(links)

        self.logger.info(
            f"Parsed Markdown: {len(awesome_list.categories)} categories, "
            f"{sum(len(c.links) for c in awesome_list.categories)} links, "
            f"{sum(len(sc) for c in awesome_list.categories for sc in c.subcategories.values())} "
            f"subcategory links"
        )

        return awesome_list


class DuplicateDetector:
    """
    Detect duplicates between Awesome list entries.
    """

    def __init__(
        self,
        similarity_threshold: float = 80.0,
        url_exact_match: bool = True
    ):
        """
        Initialize the duplicate detector.

        Args:
            similarity_threshold: Fuzzy matching threshold (0-100)
            url_exact_match: Whether to consider URLs for exact matching
        """
        self.similarity_threshold = similarity_threshold
        self.url_exact_match = url_exact_match
        self.urls: Set[str] = set()
        self.names: Set[str] = set()

    def add_existing_links(self, links: List[AwesomeLink]) -> None:
        """
        Add existing links to the detector.

        Args:
            links: List of existing AwesomeLink objects
        """
        for link in links:
            self.urls.add(link.url.lower())
            self.names.add(link.name.lower())

    def is_duplicate(self, link: AwesomeLink) -> bool:
        """
        Check if a link is a duplicate.

        Args:
            link: AwesomeLink to check

        Returns:
            True if the link is a duplicate
        """
        # Exact URL match
        if self.url_exact_match and link.url.lower() in self.urls:
            return True

        # Exact name match
        if link.name.lower() in self.names:
            return True

        # Fuzzy name matching
        for existing_name in self.names:
            similarity = fuzz.ratio(link.name.lower(), existing_name)
            if similarity >= self.similarity_threshold:
                return True

        return False

    def add_link(self, link: AwesomeLink) -> None:
        """
        Add a link to the detector.

        Args:
            link: AwesomeLink to add
        """
        self.urls.add(link.url.lower())
        self.names.add(link.name.lower())
