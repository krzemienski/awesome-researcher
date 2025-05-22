import json
import logging
import os
import re
from typing import Dict, List, Optional, Any

from openai import OpenAI

from src.utils.cost_tracker import CostTracker, estimate_tokens_from_string
from src.utils.timer import timeout


class TermExpanderAgent:
    """Agent for expanding search terms using OpenAI's API."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        cost_tracker: CostTracker,
        model: str = "gpt-4.1",
    ):
        """Initialize the term expander agent.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            cost_tracker: Cost tracker instance
            model: Model to use for term expansion
        """
        self.logger = logger
        self.output_dir = output_dir
        self.cost_tracker = cost_tracker
        self.model = model
        self.client = OpenAI()

    def expand_queries(
        self, exemplars: Dict[str, List[str]], max_per_category: int = 5, original_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[str]]:
        """Expand category-specific queries using Responses API.

        Args:
            exemplars: Dictionary mapping category names to exemplar titles
            max_per_category: Maximum number of expanded terms per category
            original_data: Original parsed data dictionary

        Returns:
            Dictionary mapping category names to expanded query terms
        """
        expanded_queries = {}
        self.logger.info(f"Expanding queries for {len(exemplars)} categories")

        # Extract list title and some global context
        list_title = "Unknown"
        list_tagline = ""
        if original_data:
            list_title = original_data.get("title", "Unknown")
            list_tagline = original_data.get("tagline", "")

        # Prepare a global list context message
        list_context = f"This is an 'Awesome List' about {list_title}."
        if list_tagline:
            list_context += f" {list_tagline}"

        # Extract general information about the list's categories
        categories_overview = "The list contains the following categories: " + ", ".join(exemplars.keys())

        # Generate a short description of all sections to provide as context
        sections_context = []
        if original_data and "sections" in original_data:
            for section in original_data["sections"]:
                section_name = section.get("name", "")
                if section_name and "items" in section and section_name in exemplars:
                    item_count = len(section.get("items", []))
                    sample_items = ", ".join([item.get("name", "") for item in section.get("items", [])[:3]])
                    sections_context.append(f"- {section_name} ({item_count} items): Examples include {sample_items}")

        all_sections_context = "\n".join(sections_context)

        for category, examples in exemplars.items():
            self.logger.info(f"Expanding terms for category: {category}")

            # Get category-specific items from the original data
            category_items = []
            if original_data and "sections" in original_data:
                for section in original_data["sections"]:
                    if section.get("name") == category:
                        for item in section.get("items", []):
                            name = item.get("name", "")
                            desc = item.get("description", "")
                            if name and desc:
                                category_items.append(f"{name}: {desc}")
                            elif name:
                                category_items.append(name)

            category_examples = "\n".join(category_items[:5])  # Limit to avoid excessive tokens

            # Prepare the system message with more context
            system_message = (
                f"You are a term expansion assistant for research in the '{category}' category of an Awesome {list_title} list. "
                f"{list_context}\n\n"
                f"Categories in this list: {categories_overview}\n\n"
                f"Your task is to generate alternative search terms and adjacent topics that can be used to "
                f"discover new resources in the '{category}' category that would be valuable additions to this list. "
                f"Focus on generating specific, technical terms related to {list_title} rather than generic descriptions."
            )

            # Prepare the user message with examples and context
            user_message = (
                f"I need to expand my search terms for researching '{category}' in the context of {list_title}. "
                f"Here are some examples of existing items in this category:\n\n{category_examples}\n\n"
                f"Please suggest {max_per_category} additional search terms or adjacent topics that could help "
                "discover new, high-quality resources for this category. Each term should be specific enough "
                "to yield focused results, relevant to the topic of the list, and directly related to this category. "
                "Return just the list of terms, each on a separate line, without numbering or explanation."
            )

            # Estimate tokens for cost ceiling check
            estimated_tokens = estimate_tokens_from_string(system_message + user_message) * 2

            if self.cost_tracker.would_exceed_ceiling(self.model, estimated_tokens):
                self.logger.warning(f"Skipping expansion for '{category}' due to cost ceiling")
                continue

            try:
                # Use timeout to prevent hanging
                with timeout(30):
                    # Prepare API parameters
                    api_params = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_message}
                        ]
                    }

                    # Only add temperature for non-o3 models
                    if "o3" not in self.model:
                        api_params["temperature"] = 0.7

                    # Make the API call
                    response = self.client.chat.completions.create(**api_params)

                    # Log the API call
                    from src.utils.logger import log_api_call
                    log_api_call(
                        logger=self.logger,
                        agent="term_expander",
                        event="expand_queries",
                        model=self.model,
                        tokens=response.usage.total_tokens,
                        cost_usd=self.cost_tracker.add_usage(
                            self.model,
                            response.usage.prompt_tokens,
                            response.usage.completion_tokens
                        ),
                        prompt={
                            "system": system_message,
                            "user": user_message
                        },
                        completion=response.choices[0].message.content
                    )

                    # Parse the response
                    content = response.choices[0].message.content.strip()
                    terms = [term.strip() for term in content.split('\n') if term.strip()]

                    # Limit the number of terms
                    terms = terms[:max_per_category]

                    expanded_queries[category] = terms
                    self.logger.info(f"Generated {len(terms)} expanded terms for '{category}'")

            except Exception as e:
                self.logger.error(f"Error expanding terms for '{category}': {str(e)}")
                # Use the original category name as a fallback
                expanded_queries[category] = [category]

        # Save the expanded queries to a file
        self._save_expanded_queries(expanded_queries)

        return expanded_queries

    def _save_expanded_queries(self, expanded_queries: Dict[str, List[str]]) -> str:
        """Save expanded queries to a JSON file.

        Args:
            expanded_queries: Dictionary mapping category names to expanded query terms

        Returns:
            Path to the saved JSON file
        """
        output_path = os.path.join(self.output_dir, "expanded_queries.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(expanded_queries, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved expanded queries to {output_path}")
        return output_path
