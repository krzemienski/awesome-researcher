"""
Category research agent for discovering new resources in specific categories.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

from openai import OpenAI

from awesome_list_researcher.awesome_parser import AwesomeLink
from awesome_list_researcher.planner_agent import ResearchQuery
from awesome_list_researcher.utils.cost_guard import CostGuard


@dataclass
class ResearchCandidate:
    """
    A candidate resource discovered by the research agent.
    """
    name: str
    url: str
    description: str
    category: str
    subcategory: Optional[str] = None
    stars: Optional[int] = None
    validated: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "category": self.category,
            "validated": self.validated,
        }

        if self.subcategory:
            result["subcategory"] = self.subcategory

        if self.stars is not None:
            result["stars"] = self.stars

        return result

    def to_awesome_link(self) -> AwesomeLink:
        """Convert to AwesomeLink."""
        return AwesomeLink(
            name=self.name,
            url=self.url,
            description=self.description,
            category=self.category,
            subcategory=self.subcategory
        )

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResearchCandidate':
        """Create from dictionary."""
        return cls(
            name=data["name"],
            url=data["url"],
            description=data["description"],
            category=data["category"],
            subcategory=data.get("subcategory"),
            stars=data.get("stars"),
            validated=data.get("validated", False)
        )


@dataclass
class ResearchResult:
    """
    The result of a category research operation.
    """
    query: ResearchQuery
    candidates: List[ResearchCandidate] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "query": self.query.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates]
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ResearchResult':
        """Create from dictionary."""
        query = ResearchQuery(
            query=data["query"]["query"],
            category=data["query"]["category"],
            subcategory=data["query"].get("subcategory")
        )

        result = cls(query=query)

        for candidate_data in data.get("candidates", []):
            result.candidates.append(ResearchCandidate.from_dict(candidate_data))

        return result

    @classmethod
    def from_json(cls, json_str: str) -> 'ResearchResult':
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class CategoryResearchAgent:
    """
    Agent for researching a specific category in an Awesome list.
    """

    SYSTEM_PROMPT = """You are a research assistant specializing in finding high-quality resources for Awesome Lists.

Your task is to search for and identify high-quality resources for a specific category that are NOT already in the list.

ACCEPTANCE CRITERIA for resources:
1. Must be relevant to the specified category/subcategory
2. Must be high quality (well-maintained, documented, useful)
3. Should have significant popularity if it's a GitHub repository (ideally 100+ stars)
4. Must have HTTPS links and be accessible
5. Must provide a clear, concise description (<100 characters)
6. Must NOT be already in the original list (avoid duplicates)

FORMAT YOUR FINDINGS as a JSON array of objects with this format:
{
  "name": "Resource Name",
  "url": "https://example.com",
  "description": "Clear, concise description of the resource",
  "category": "Category Name",
  "subcategory": "Subcategory Name" // Optional, only if provided in the query
}

Aim to find 3-5 high-quality resources that meet all criteria.
"""

    def __init__(
        self,
        model: str,
        api_client: OpenAI,
        cost_guard: CostGuard,
        logger: logging.Logger
    ):
        """
        Initialize the category research agent.

        Args:
            model: OpenAI model to use
            api_client: OpenAI API client
            cost_guard: Cost guard for tracking API usage
            logger: Logger instance
        """
        self.model = model
        self.api_client = api_client
        self.cost_guard = cost_guard
        self.logger = logger

    def research_query(self, query: ResearchQuery) -> ResearchResult:
        """
        Research a specific query to find new resources.

        Args:
            query: ResearchQuery to research

        Returns:
            ResearchResult with candidate resources
        """
        self.logger.info(
            f"Researching query: '{query.query}' for category '{query.category}'"
            + (f", subcategory '{query.subcategory}'" if query.subcategory else "")
        )

        # Prepare the prompt
        category_info = f"category '{query.category}'"
        if query.subcategory:
            category_info += f", subcategory '{query.subcategory}'"

        prompt = (
            f"Please research this query and find high-quality resources for {category_info}:\n\n"
            f"Query: {query.query}\n\n"
            f"Find 3-5 excellent resources that are not already in popular Awesome Lists.\n\n"
            f"Make sure to check if GitHub repositories have at least 100 stars, and verify all URLs use HTTPS and are accessible.\n\n"
            f"Return your findings as a JSON array of resource objects."
        )

        # Check if the API call would exceed the cost ceiling
        input_tokens = len(prompt.split()) * 1.5  # Rough estimate
        if self.cost_guard.would_exceed_ceiling(self.model, int(input_tokens)):
            self.logger.error("Cost ceiling would be exceeded by category agent call")
            raise ValueError("Cost ceiling would be exceeded")

        # Make the API call
        try:
            response = self.api_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )

            # Track usage
            usage = response.usage
            self.cost_guard.update_usage(
                model=self.model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                event=f"category_agent_call_{query.category}"
            )

            # Parse the response
            response_content = response.choices[0].message.content

            # Parse the results
            candidates = []

            try:
                # Try to extract JSON from the text
                json_match = self._extract_json(response_content)

                if json_match:
                    candidates_data = json.loads(json_match)

                    # Handle both array and object formats
                    if isinstance(candidates_data, dict):
                        if "resources" in candidates_data:
                            candidates_data = candidates_data["resources"]
                        else:
                            candidates_data = [candidates_data]

                    for candidate_data in candidates_data:
                        # Ensure required fields are present
                        if all(k in candidate_data for k in ["name", "url", "description", "category"]):
                            candidate = ResearchCandidate(
                                name=candidate_data["name"],
                                url=candidate_data["url"],
                                description=candidate_data["description"],
                                category=candidate_data["category"],
                                subcategory=candidate_data.get("subcategory")
                            )
                            candidates.append(candidate)
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse JSON from response: {response_content}")

            self.logger.info(f"Found {len(candidates)} candidate resources for query '{query.query}'")

            # Create and return the result
            return ResearchResult(query=query, candidates=candidates)

        except Exception as e:
            self.logger.error(f"Error calling category agent: {str(e)}")
            raise

    def _extract_json(self, text: str) -> Optional[str]:
        """
        Extract JSON from text.

        Args:
            text: Text to extract JSON from

        Returns:
            JSON string or None
        """
        # Look for JSON array or object
        json_start = text.find('[') if '[' in text else text.find('{')
        json_end = text.rfind(']') if ']' in text else text.rfind('}')

        if json_start != -1 and json_end != -1 and json_end > json_start:
            return text[json_start:json_end + 1]

        return None
