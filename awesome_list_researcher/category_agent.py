"""
Category research agent for finding new resources.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Union

from awesome_list_researcher.awesome_parser import AwesomeLink
from awesome_list_researcher.utils import mcp_handler

@dataclass
class ResearchCandidate:
    """
    A candidate resource discovered during research.
    """
    name: str
    url: str
    description: str
    category: str
    subcategory: Optional[str] = None
    source_query: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "category": self.category,
        }

        if self.subcategory:
            result["subcategory"] = self.subcategory

        if self.source_query:
            result["source_query"] = self.source_query

        return result

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResearchCandidate':
        """Create from dictionary."""
        return cls(
            name=data["name"],
            url=data["url"],
            description=data["description"],
            category=data["category"],
            subcategory=data.get("subcategory"),
            source_query=data.get("source_query")
        )

    def to_awesome_link(self) -> AwesomeLink:
        """Convert to AwesomeLink."""
        return AwesomeLink(
            name=self.name,
            url=self.url,
            description=self.description,
            category=self.category,
            subcategory=self.subcategory
        )


class CategoryResearchAgent:
    """
    Agent for researching new resources for a category.

    This implementation uses the MCP tools to maintain chain-of-thought reasoning.
    """

    def __init__(
        self,
        category: str,
        queries: List[str],
        model_name: str = "o3",
        cost_ceiling: float = 10.0
    ):
        """
        Initialize the category research agent.

        Args:
            category: Category to research
            queries: List of search queries
            model_name: OpenAI model to use
            cost_ceiling: Maximum cost in USD
        """
        self.category = category
        self.queries = queries
        self.model_name = model_name
        self.cost_ceiling = cost_ceiling
        self.logger = logging.getLogger(__name__)
        self.total_cost = 0.0

        # Continue sequence thinking with MCP
        mcp_handler.sequence_thinking(
            thought=f"Researching category: {category} with {len(queries)} queries",
            thought_number=1,
            total_thoughts=3
        )

    def estimate_cost(self) -> float:
        """
        Estimate the cost of the operation.

        Returns:
            Estimated cost in USD
        """
        # Rough estimate based on number of queries and model
        cost_per_query = 0.05 if self.model_name == "o3" else 0.1
        return len(self.queries) * cost_per_query

    def get_cost(self) -> float:
        """
        Get the current total cost.

        Returns:
            Total cost in USD
        """
        return self.total_cost

    def research(self) -> Dict:
        """
        Research the category using the provided queries.

        Returns:
            Dictionary mapping queries to results
        """
        self.logger.info(f"Researching category: {self.category} with {len(self.queries)} queries")

        mcp_handler.sequence_thinking(
            thought=f"Searching for resources across multiple sources",
            thought_number=2,
            total_thoughts=3
        )

        results = {}
        for i, query in enumerate(self.queries):
            self.logger.info(f"Processing query {i+1}/{len(self.queries)}: {query}")

            # In a real implementation, we would use the BrowserTool
            # For demo purposes, we'll simulate research results
            candidates = self._simulate_research_results(query)

            results[query] = candidates

            # Update cost
            query_cost = 0.02  # Simulated cost
            self.total_cost += query_cost
            self.logger.info(f"Query cost: ${query_cost:.4f}, total cost: ${self.total_cost:.4f}")

            # Check cost ceiling
            if self.total_cost >= self.cost_ceiling:
                self.logger.warning(f"Cost ceiling of ${self.cost_ceiling:.2f} reached, stopping research")
                break

        mcp_handler.sequence_thinking(
            thought=f"Found {sum(len(c) for c in results.values())} candidates across {len(results)} queries",
            thought_number=3,
            total_thoughts=3
        )

        # Convert to dictionary format
        result_dict = {}
        for query, candidates in results.items():
            result_dict[query] = [c.to_dict() for c in candidates]

        return result_dict

    def _simulate_research_results(self, query: str) -> List[ResearchCandidate]:
        """
        Simulate research results for demonstration purposes.

        Args:
            query: Search query

        Returns:
            List of simulated research candidates
        """
        # Create a couple of simulated results
        return [
            ResearchCandidate(
                name=f"Resource for {self.category} - {i}",
                url=f"https://example.com/{self.category.lower().replace(' ', '-')}-resource-{i}",
                description=f"A great {self.category} resource found with query: {query[:30]}",
                category=self.category,
                source_query=query
            )
            for i in range(1, 4)  # 3 results per query
        ]
