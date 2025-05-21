"""
Planner agent for generating research queries.
"""

import json
import logging
import random
from typing import Dict, List, Any, Optional

from awesome_list_researcher.utils import mcp_handler


class ResearchQuery:
    """
    A research query for a category.
    """

    def __init__(self, category: str, query: str, subcategory: Optional[str] = None):
        """
        Initialize a research query.

        Args:
            category: Category name
            query: Search query
            subcategory: Optional subcategory name
        """
        self.category = category
        self.query = query
        self.subcategory = subcategory

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dictionary representation
        """
        result = {
            "category": self.category,
            "query": self.query
        }

        if self.subcategory:
            result["subcategory"] = self.subcategory

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchQuery':
        """
        Create from dictionary.

        Args:
            data: Dictionary data

        Returns:
            ResearchQuery instance
        """
        return cls(
            category=data["category"],
            query=data["query"],
            subcategory=data.get("subcategory")
        )


class PlannerAgent:
    """
    Agent for planning research queries.

    This implementation uses MCP tools to maintain chain-of-thought reasoning.
"""

    def __init__(
        self,
        categories: List[Dict],
        queries_per_category: int = 3,
        seed: Optional[int] = None
    ):
        """
        Initialize the planner agent.

        Args:
            categories: List of category dictionaries
            queries_per_category: Number of queries per category
            seed: Random seed for deterministic generation
        """
        self.logger = logging.getLogger(__name__)
        self.categories = categories
        self.queries_per_category = queries_per_category

        # Set random seed if provided
        if seed is not None:
            random.seed(seed)
            self.logger.info(f"Set random seed to {seed}")

        # Continue sequence thinking with MCP
        mcp_handler.sequence_thinking(
            thought=f"Planning research queries for {len(categories)} categories",
            thought_number=1,
            total_thoughts=3
        )

    def generate_queries(self) -> List[Dict]:
        """
        Generate research queries for all categories.

        Returns:
            List of query dictionaries
        """
        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought="Generating specific research queries",
            thought_number=2,
            total_thoughts=3
        )

        all_queries = []

        for category in self.categories:
            category_name = category.get("name", "")

            # Skip categories like "Contributing" or "License"
            if category_name.lower() in {"contributing", "license", "contents", "table of contents"}:
                self.logger.info(f"Skipping category {category_name}")
                continue

            # Generate queries for this category
            category_queries = self._generate_category_queries(category)
            all_queries.extend(category_queries)

        # Shuffle queries for diversity
        random.shuffle(all_queries)

        # Continue sequence thinking
        mcp_handler.sequence_thinking(
            thought=f"Generated {len(all_queries)} total research queries",
            thought_number=3,
            total_thoughts=3
        )

        self.logger.info(f"Generated {len(all_queries)} total research queries")

        # Convert to dictionaries
        return [query.to_dict() for query in all_queries]

    def _generate_category_queries(self, category: Dict) -> List[ResearchQuery]:
        """
        Generate research queries for a category.

        Args:
            category: Category dictionary

        Returns:
            List of ResearchQuery instances
        """
        category_name = category.get("name", "")
        self.logger.info(f"Generating queries for category: {category_name}")

        queries = []

        # For demonstration purposes, we'll generate simple queries based on the category name
        for i in range(self.queries_per_category):
            query_text = f"best {category_name.lower()} libraries and tools {2023 + i}"
            queries.append(ResearchQuery(
                category=category_name,
                query=query_text
            ))

        self.logger.info(f"Generated {len(queries)} queries for category {category_name}")

        # In a real implementation, we would call the LLM here like the previous version

        return queries
