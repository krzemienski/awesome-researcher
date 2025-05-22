import json
import logging
import os
import random
from typing import Dict, List, Set, Any, Tuple, Optional
from pathlib import Path
import time

from openai import OpenAI

from src.utils.cost_tracker import CostTracker, estimate_tokens_from_string
from src.utils.timer import timeout
import src.logger as log


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
        taxonomy_file: Optional[str] = None,
    ):
        """Initialize the planner agent.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            cost_tracker: Cost tracker instance
            original_data: Original awesome-list data
            model: Model to use for planning
            seed: Random seed for deterministic shuffling
            taxonomy_file: Path to external taxonomy file (JSON)
        """
        self.logger = logger
        self.output_dir = output_dir
        self.cost_tracker = cost_tracker
        self.original_data = original_data
        self.model = model
        self.client = OpenAI()
        self.taxonomy_data = None
        self.category_synonyms = {}
        self.cost_timer = log.CostTimer()
        self.run_dir = Path(output_dir).parent

        # Load external taxonomy if provided
        if taxonomy_file:
            self._load_taxonomy(taxonomy_file)

        # Initialize random seed if provided
        if seed is not None:
            random.seed(seed)
            self.logger.info(f"Using random seed: {seed}")

    def _load_taxonomy(self, taxonomy_file: str) -> None:
        """Load external taxonomy file.

        Args:
            taxonomy_file: Path to taxonomy file (JSON)
        """
        try:
            with open(taxonomy_file, 'r', encoding='utf-8') as f:
                self.taxonomy_data = json.load(f)

            self.logger.info(f"Loaded taxonomy file: {taxonomy_file}")

            # Extract category synonyms
            if self.taxonomy_data and "categories" in self.taxonomy_data:
                for category in self.taxonomy_data["categories"]:
                    name = category.get("name", "")
                    synonyms = category.get("synonyms", [])
                    if name and synonyms:
                        self.category_synonyms[name] = synonyms

                self.logger.info(f"Extracted synonyms for {len(self.category_synonyms)} categories")

                # Log taxonomy information
                log._LOGGER.info(json.dumps({
                    "phase": "load_taxonomy",
                    "taxonomy_file": taxonomy_file,
                    "categories": list(self.category_synonyms.keys()),
                    "synonym_count": sum(len(synonyms) for synonyms in self.category_synonyms.values())
                }))
        except Exception as e:
            self.logger.error(f"Error loading taxonomy file: {str(e)}")

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
        with log.log_phase("planning", self.run_dir, self.cost_timer):
            research_plan = {}
            all_original_urls = self._extract_all_original_urls()

            # Get video categories from taxonomy if available
            video_categories = set(self.category_synonyms.keys())

            self.logger.info(f"Creating research plans for {len(expanded_queries)} categories")
            log._LOGGER.info(json.dumps({
                "phase": "planning_start",
                "category_count": len(expanded_queries),
                "video_categories": list(video_categories) if video_categories else []
            }))

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

                # Add synonyms from taxonomy if available
                if category in self.category_synonyms:
                    synonyms = self.category_synonyms[category]
                    self.logger.info(f"Adding {len(synonyms)} synonyms for category '{category}': {synonyms}")
                    selected_terms.extend(synonyms)
                    # Ensure we don't exceed the queries_per_category limit
                    selected_terms = selected_terms[:queries_per_category]

                # Create the plan for this category
                plan = {
                    "category": category,
                    "search_terms": selected_terms,
                    "exclude_urls": all_original_urls,
                    "original_item_count": len(category_original_urls)
                }

                # Add synonyms if available
                if category in self.category_synonyms:
                    plan["synonyms"] = self.category_synonyms[category]
                    # Log synonym enrichment
                    log._LOGGER.info(json.dumps({
                        "phase": "synonym_enrichment",
                        "category": category,
                        "synonyms": self.category_synonyms[category]
                    }))

                # Add to research plan
                research_plan[category] = plan

            # Optimize the plan by refining search terms with AI assistance
            self._refine_search_terms(research_plan)

            # Save the research plan to a file
            self._save_research_plan(research_plan)

            # Log planning completion
            log._LOGGER.info(json.dumps({
                "phase": "planning_complete",
                "categories": list(research_plan.keys()),
                "total_search_terms": sum(len(plan["search_terms"]) for plan in research_plan.values())
            }))

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
                user_message += f"TERMS: {', '.join(plan['search_terms'])}\n"

                # Include synonyms if available
                if "synonyms" in plan:
                    user_message += f"SYNONYMS: {', '.join(plan['synonyms'])}\n"

                user_message += "\n"

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

                    # Measure response time
                    start_time = time.perf_counter()

                    # Make the API call
                    response = self.client.chat.completions.create(**api_params)

                    # Calculate latency and add tokens to cost timer
                    latency_ms = round((time.perf_counter() - start_time) * 1000)
                    self.cost_timer.add_tokens(response.usage.total_tokens)

                    # Log the API call with structured data
                    log._LOGGER.info(json.dumps({
                        "phase": "query_refinement",
                        "batch_size": len(batch),
                        "categories": [c for c, _ in batch],
                        "prompt_excerpt": system_message[:200],
                        "completion_excerpt": response.choices[0].message.content[:200],
                        "latency_ms": latency_ms,
                        "tokens": response.usage.total_tokens,
                        "cost_usd": self.cost_tracker.get_cost_for_tokens(self.model, response.usage.total_tokens)
                    }))

                    # Log the API call to regular logger
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

                    # Log term refinement
                    log._LOGGER.info(json.dumps({
                        "phase": "term_refinement",
                        "category": current_category,
                        "original_terms": research_plan[current_category].get("original_terms", []),
                        "refined_terms": refined_terms[:max_terms]
                    }))

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
            # Save original terms for logging
            if "original_terms" not in research_plan[current_category]:
                research_plan[current_category]["original_terms"] = research_plan[current_category]["search_terms"].copy()

            max_terms = len(research_plan[current_category]["search_terms"])
            research_plan[current_category]["search_terms"] = refined_terms[:max_terms]
            self.logger.info(f"Updated search terms for '{current_category}': {research_plan[current_category]['search_terms']}")

            # Log term refinement
            log._LOGGER.info(json.dumps({
                "phase": "term_refinement",
                "category": current_category,
                "original_terms": research_plan[current_category].get("original_terms", []),
                "refined_terms": refined_terms[:max_terms]
            }))

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
