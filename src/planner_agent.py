import json
import logging
import os
import random
from typing import Dict, List, Set, Any, Tuple

from openai import OpenAI

from src.utils.cost_tracker import CostTracker, estimate_tokens_from_string
from src.utils.timer import timeout


class PlannerAgent:
    """Agent for planning category-specific research strategies."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        cost_tracker: CostTracker,
        original_data: Dict,
        model: str = "gpt-4.1",
        seed: int = None,
    ):
        """Initialize the planner agent.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            cost_tracker: Cost tracker instance
            original_data: Original awesome-list data
            model: Model to use for planning
            seed: Random seed for deterministic shuffling
        """
        self.logger = logger
        self.output_dir = output_dir
        self.cost_tracker = cost_tracker
        self.original_data = original_data
        self.model = model
        self.client = OpenAI()

        # Initialize random seed if provided
        if seed is not None:
            random.seed(seed)
            self.logger.info(f"Using random seed: {seed}")

    def create_research_plan(
        self, expanded_queries: Dict[str, List[str]], queries_per_category: int = 3
    ) -> Dict[str, Dict]:
        """Create a research plan for each category.

        Args:
            expanded_queries: Dictionary mapping category names to expanded query terms
            queries_per_category: Maximum number of queries to use per category

        Returns:
            Dictionary mapping category names to research plans
        """
        research_plan = {}
        all_original_urls = self._extract_all_original_urls()

        self.logger.info(f"Creating research plans for {len(expanded_queries)} categories")

        for category, terms in expanded_queries.items():
            self.logger.info(f"Planning research for category: {category}")

            # Get category-specific original URLs
            category_original_urls = self._extract_category_urls(category)

            # Create a negative prompt with all original URLs
            negative_urls_list = "\n".join(all_original_urls)

            # Shuffle and limit terms
            shuffled_terms = terms.copy()
            random.shuffle(shuffled_terms)
            selected_terms = shuffled_terms[:queries_per_category]

            # Create the plan for this category
            plan = {
                "category": category,
                "search_terms": selected_terms,
                "exclude_urls": all_original_urls,
                "original_item_count": len(category_original_urls)
            }

            # Add to research plan
            research_plan[category] = plan

        # Optimize the plan by refining search terms with AI assistance
        self._refine_search_terms(research_plan)

        # Save the research plan to a file
        self._save_research_plan(research_plan)

        return research_plan

    def _extract_all_original_urls(self) -> List[str]:
        """Extract all URLs from the original data.

        Returns:
            List of all URLs in the original data
        """
        all_urls = []

        for section in self.original_data.get("sections", []):
            for item in section.get("items", []):
                url = item.get("url")
                if url:
                    all_urls.append(url)

        self.logger.info(f"Extracted {len(all_urls)} URLs from original data")
        return all_urls

    def _extract_category_urls(self, category: str) -> List[str]:
        """Extract URLs from a specific category in the original data.

        Args:
            category: Category name

        Returns:
            List of URLs in the specified category
        """
        category_urls = []

        for section in self.original_data.get("sections", []):
            if section.get("name") == category:
                for item in section.get("items", []):
                    url = item.get("url")
                    if url:
                        category_urls.append(url)
                break

        return category_urls

    def _refine_search_terms(self, research_plan: Dict[str, Dict]) -> None:
        """Refine search terms using AI assistant.

        Args:
            research_plan: Research plan dictionary
        """
        # Prepare batches of categories to process together
        batch_size = 5  # Process multiple categories in one API call
        categories_with_terms = [(category, plan) for category, plan in research_plan.items()
                                if plan.get("search_terms")]

        for i in range(0, len(categories_with_terms), batch_size):
            batch = categories_with_terms[i:i+batch_size]
            if not batch:
                continue

            self.logger.info(f"Refining search terms for batch of {len(batch)} categories")

            # Prepare the system message for the batch
            system_message = (
                "You are a search query optimization assistant. "
                "Your task is to refine the provided search terms for multiple categories "
                "to maximize the discovery of new, high-quality resources."
            )

            # Prepare the user message with all categories in this batch
            user_message = "I need to refine search terms for multiple categories. For each category, please improve the terms to make them more specific and effective at finding new, high-quality resources.\n\n"

            for category, plan in batch:
                user_message += f"CATEGORY: {category}\n"
                user_message += f"TERMS: {', '.join(plan['search_terms'])}\n\n"

            user_message += "For each category, return the improved terms in this format:\n"
            user_message += "CATEGORY: [category name]\n"
            user_message += "REFINED_TERMS:\n- [term 1]\n- [term 2]\n- [term 3]\n\n"

            # Estimate tokens for cost ceiling check
            estimated_tokens = estimate_tokens_from_string(system_message + user_message) * 2

            if self.cost_tracker.would_exceed_ceiling(self.model, estimated_tokens):
                self.logger.warning(f"Skipping term refinement for batch due to cost ceiling")
                continue

            try:
                # Use timeout to prevent hanging
                with timeout(60):  # Increased timeout for batch processing
                    # Prepare API parameters
                    api_params = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_message}
                        ],
                    }

                    # Only add temperature for non-gpt-4o models
                    if "gpt-4o" not in self.model:
                        api_params["temperature"] = 0.5

                    # Make the API call
                    response = self.client.chat.completions.create(**api_params)

                    # Log the API call
                    from src.utils.logger import log_api_call
                    log_api_call(
                        logger=self.logger,
                        agent="planner",
                        event="refine_search_terms_batch",
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

                    # Parse the response for each category
                    content = response.choices[0].message.content.strip()
                    self._process_batch_response(content, research_plan, [c for c, _ in batch])

            except Exception as e:
                self.logger.error(f"Error refining search terms for batch: {str(e)}")
                # Keep the original terms on error

    def _process_batch_response(self, content: str, research_plan: Dict[str, Dict], batch_categories: List[str]) -> None:
        """Process the batched response and update the research plan.

        Args:
            content: The response content from the API
            research_plan: The research plan to update
            batch_categories: List of categories in this batch
        """
        current_category = None
        refined_terms = []

        # Parse the response line by line
        for line in content.split('\n'):
            line = line.strip()

            if line.startswith("CATEGORY:"):
                # If we were processing a category, save its terms
                if current_category and refined_terms and current_category in research_plan:
                    max_terms = len(research_plan[current_category]["search_terms"])
                    research_plan[current_category]["search_terms"] = refined_terms[:max_terms]
                    self.logger.info(f"Updated search terms for '{current_category}': {research_plan[current_category]['search_terms']}")

                # Start a new category
                category_part = line.split("CATEGORY:")[1].strip()
                current_category = category_part
                refined_terms = []

            elif line.startswith("-") or line.startswith("*") and current_category:
                # This is a term
                term = line.lstrip("- *").strip()
                if term:
                    refined_terms.append(term)

        # Don't forget to save the last category
        if current_category and refined_terms and current_category in research_plan:
            max_terms = len(research_plan[current_category]["search_terms"])
            research_plan[current_category]["search_terms"] = refined_terms[:max_terms]
            self.logger.info(f"Updated search terms for '{current_category}': {research_plan[current_category]['search_terms']}")

    def _save_research_plan(self, research_plan: Dict[str, Dict]) -> str:
        """Save the research plan to a JSON file.

        Args:
            research_plan: Research plan dictionary

        Returns:
            Path to the saved JSON file
        """
        output_path = os.path.join(self.output_dir, "plan.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(research_plan, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved research plan to {output_path}")
        return output_path
