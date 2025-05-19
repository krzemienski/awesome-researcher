"""
Planner agent for generating research queries.
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from openai import OpenAI

from awesome_list_researcher.awesome_parser import AwesomeCategory, AwesomeLink, AwesomeList
from awesome_list_researcher.utils.cost_guard import CostGuard
from awesome_list_researcher.utils.logging import APICallLogRecord


@dataclass
class ResearchQuery:
    """
    A research query for a category or subcategory.
    """
    category: str
    subcategory: Optional[str]
    query: str

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "category": self.category,
            "subcategory": self.subcategory,
            "query": self.query
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResearchQuery':
        """Create from dictionary."""
        return cls(
            category=data["category"],
            subcategory=data.get("subcategory"),
            query=data["query"]
        )


@dataclass
class ResearchPlan:
    """
    A research plan containing queries for categories and subcategories.
    """
    awesome_list_title: str
    queries: List[ResearchQuery] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "awesome_list_title": self.awesome_list_title,
            "queries": [query.to_dict() for query in self.queries]
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResearchPlan':
        """Create from dictionary."""
        plan = cls(awesome_list_title=data["awesome_list_title"])
        plan.queries = [
            ResearchQuery.from_dict(query_data)
            for query_data in data.get("queries", [])
        ]
        return plan

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> 'ResearchPlan':
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class PlannerAgent:
    """
    Agent for planning research queries.
    """

    def __init__(
        self,
        model: str,
        api_client: OpenAI,
        cost_guard: CostGuard,
        logger: logging.Logger,
        seed: Optional[int] = None
    ):
        """
        Initialize the planner agent.

        Args:
            model: OpenAI model to use
            api_client: OpenAI client
            cost_guard: Cost guard instance
            logger: Logger instance
            seed: Random seed for deterministic generation
        """
        self.model = model
        self.api_client = api_client
        self.cost_guard = cost_guard
        self.logger = logger
        self.seed = seed

        # Set random seed if provided
        if self.seed is not None:
            random.seed(self.seed)
            self.logger.info(f"Set random seed to {self.seed}")

    def _generate_category_queries(
        self,
        category: AwesomeCategory,
        num_queries: int = 3
    ) -> List[ResearchQuery]:
        """
        Generate research queries for a category.

        Args:
            category: AwesomeCategory instance
            num_queries: Number of queries to generate per category/subcategory

        Returns:
            List of ResearchQuery instances
        """
        queries = []

        # Prepare the system prompt
        system_prompt = f"""
You are a research planner helping to find new resources for an Awesome List about {category.name}.
Your task is to formulate {num_queries} diverse search queries that would help discover new, high-quality resources in this category.

Here are the existing resources already in the list:
"""

        # Add existing links
        existing_links = []
        for link in category.links:
            existing_links.append(f"- {link.name}: {link.description}")

        existing_links_text = "\n".join(existing_links)

        # Prepare the user prompt
        user_prompt = f"""
Category: {category.name}

Existing resources:
{existing_links_text}

Please generate {num_queries} different search queries that would help discover NEW resources for this category.
Each query should:
1. Focus on finding high-quality resources not already in the list
2. Be specific enough to yield relevant results
3. Include synonyms or alternative terms where appropriate
4. Be diverse compared to other queries

Respond with a JSON array of queries only, no explanation. Example:
[
  "best open source python data visualization libraries 2023",
  "modern javascript frameworks for building web applications comparison",
  "rust memory safety tools for systems programming"
]
"""

        # Check if the cost would exceed the ceiling
        estimated_tokens = len(system_prompt.split()) + len(user_prompt.split()) + 500
        if self.cost_guard.would_exceed_ceiling(self.model, estimated_tokens, estimated_tokens // 2):
            self.logger.warning(f"Cost ceiling would be exceeded for category {category.name}, skipping")
            return []

        # Make the API call
        start_time = time.time()

        try:
            completion = self.api_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            # Update cost
            self.cost_guard.update_from_completion(completion, self.model)

            # Log full prompt and completion
            latency = time.time() - start_time
            api_log = APICallLogRecord(
                agent_id="planner",
                model=self.model,
                prompt=f"System: {system_prompt}\nUser: {user_prompt}",
                completion=completion.choices[0].message.content,
                tokens=completion.usage.total_tokens,
                cost_usd=self.cost_guard.total_cost_usd,
                latency=latency
            )

            self.logger.info(f"API call log: {api_log.to_json()}")

            # Parse the response
            try:
                response_json = json.loads(completion.choices[0].message.content)
                generated_queries = response_json.get("queries", [])

                # If the response has a queries field, use it, otherwise assume the whole response is the array
                if not generated_queries and isinstance(response_json, list):
                    generated_queries = response_json

                if not generated_queries:
                    self.logger.warning(f"No queries generated for category {category.name}")
                    return []

                # Create ResearchQuery objects
                for query in generated_queries:
                    queries.append(ResearchQuery(
                        category=category.name,
                        subcategory=None,
                        query=query
                    ))

                self.logger.info(f"Generated {len(queries)} queries for category {category.name}")

            except (json.JSONDecodeError, KeyError) as e:
                self.logger.error(f"Error parsing response for category {category.name}: {str(e)}")

        except Exception as e:
            self.logger.error(f"API call failed for category {category.name}: {str(e)}")

        return queries

    def _generate_subcategory_queries(
        self,
        category: AwesomeCategory,
        subcategory: str,
        links: List[AwesomeLink],
        num_queries: int = 2
    ) -> List[ResearchQuery]:
        """
        Generate research queries for a subcategory.

        Args:
            category: AwesomeCategory instance
            subcategory: Subcategory name
            links: List of AwesomeLink instances in the subcategory
            num_queries: Number of queries to generate per subcategory

        Returns:
            List of ResearchQuery instances
        """
        queries = []

        # Prepare the system prompt
        system_prompt = f"""
You are a research planner helping to find new resources for an Awesome List about {category.name}, specifically in the subcategory {subcategory}.
Your task is to formulate {num_queries} diverse search queries that would help discover new, high-quality resources in this subcategory.

Here are the existing resources already in the list:
"""

        # Add existing links
        existing_links = []
        for link in links:
            existing_links.append(f"- {link.name}: {link.description}")

        existing_links_text = "\n".join(existing_links)

        # Prepare the user prompt
        user_prompt = f"""
Category: {category.name}
Subcategory: {subcategory}

Existing resources:
{existing_links_text}

Please generate {num_queries} different search queries that would help discover NEW resources for this subcategory.
Each query should:
1. Focus on finding high-quality resources not already in the list
2. Be specific enough to yield relevant results
3. Include synonyms or alternative terms where appropriate
4. Be diverse compared to other queries

Respond with a JSON array of queries only, no explanation. Example:
[
  "best open source python data visualization libraries 2023",
  "modern javascript frameworks for building web applications comparison"
]
"""

        # Check if the cost would exceed the ceiling
        estimated_tokens = len(system_prompt.split()) + len(user_prompt.split()) + 500
        if self.cost_guard.would_exceed_ceiling(self.model, estimated_tokens, estimated_tokens // 2):
            self.logger.warning(f"Cost ceiling would be exceeded for subcategory {subcategory}, skipping")
            return []

        # Make the API call
        start_time = time.time()

        try:
            completion = self.api_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500,
                response_format={"type": "json_object"}
            )

            # Update cost
            self.cost_guard.update_from_completion(completion, self.model)

            # Log full prompt and completion
            latency = time.time() - start_time
            api_log = APICallLogRecord(
                agent_id="planner",
                model=self.model,
                prompt=f"System: {system_prompt}\nUser: {user_prompt}",
                completion=completion.choices[0].message.content,
                tokens=completion.usage.total_tokens,
                cost_usd=self.cost_guard.total_cost_usd,
                latency=latency
            )

            self.logger.info(f"API call log: {api_log.to_json()}")

            # Parse the response
            try:
                response_json = json.loads(completion.choices[0].message.content)
                generated_queries = response_json.get("queries", [])

                # If the response has a queries field, use it, otherwise assume the whole response is the array
                if not generated_queries and isinstance(response_json, list):
                    generated_queries = response_json

                if not generated_queries:
                    self.logger.warning(f"No queries generated for subcategory {subcategory}")
                    return []

                # Create ResearchQuery objects
                for query in generated_queries:
                    queries.append(ResearchQuery(
                        category=category.name,
                        subcategory=subcategory,
                        query=query
                    ))

                self.logger.info(f"Generated {len(queries)} queries for subcategory {subcategory}")

            except (json.JSONDecodeError, KeyError) as e:
                self.logger.error(f"Error parsing response for subcategory {subcategory}: {str(e)}")

        except Exception as e:
            self.logger.error(f"API call failed for subcategory {subcategory}: {str(e)}")

        return queries

    def generate_plan(self, awesome_list: AwesomeList) -> ResearchPlan:
        """
        Generate a research plan for an Awesome List.

        Args:
            awesome_list: AwesomeList instance

        Returns:
            ResearchPlan instance
        """
        self.logger.info(f"Generating research plan for {awesome_list.title}")

        research_plan = ResearchPlan(awesome_list_title=awesome_list.title)

        # Process each category
        for category in awesome_list.categories:
            # Skip categories like "Contributing" or "License"
            if category.name.lower() in {"contributing", "license", "contents", "table of contents"}:
                self.logger.info(f"Skipping category {category.name}")
                continue

            # Generate queries for the category
            category_queries = self._generate_category_queries(category)
            research_plan.queries.extend(category_queries)

            # Generate queries for each subcategory
            for subcategory, links in category.subcategories.items():
                subcategory_queries = self._generate_subcategory_queries(
                    category, subcategory, links
                )
                research_plan.queries.extend(subcategory_queries)

        # Shuffle queries to ensure diversity in case we hit the cost ceiling
        if research_plan.queries:
            random.shuffle(research_plan.queries)

        self.logger.info(f"Generated {len(research_plan.queries)} queries in total")

        return research_plan
