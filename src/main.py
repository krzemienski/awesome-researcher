import argparse
import logging
import os
import signal
import sys
import time
from typing import Dict, List, Set, Any

from openai import OpenAI

from src.awesome_parser import AwesomeParser, fetch_and_parse
from src.term_expander_agent import TermExpanderAgent
from src.planner_agent import PlannerAgent
from src.category_agent import CategoryResearchAgent
from src.dedup_engine import DedupEngine
from src.validator import ValidatorAgent
from src.renderer import Renderer

from src.utils.logger import setup_logger
from src.utils.cost_tracker import CostTracker
from src.utils.timer import WallTimeTracker, setup_wall_time_limit


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Awesome-List Researcher")

    # Required arguments
    parser.add_argument("--repo_url", required=True, help="URL of the GitHub repository")

    # Optional arguments with defaults
    parser.add_argument("--wall_time", type=int, default=600, help="Maximum wall time in seconds (default: 600)")
    parser.add_argument("--cost_ceiling", type=float, default=10.0, help="Maximum cost in USD (default: 10.0)")
    parser.add_argument("--output_dir", default="runs", help="Output directory (default: runs)")
    parser.add_argument("--seed", type=int, help="Random seed for deterministic behavior")
    parser.add_argument("--model_planner", default="gpt-4.1", help="Model to use for planner agent (default: gpt-4.1)")
    parser.add_argument("--model_researcher", default="gpt-4o", help="Model to use for researcher agent (default: gpt-4o)")
    parser.add_argument("--model_validator", default="gpt-4o", help="Model to use for validator agent (default: gpt-4o)")

    return parser.parse_args()


def handle_timeout(logger):
    """Handle wall time limit expiration."""
    logger.error("Wall time limit reached. Exiting.")
    sys.exit(1)


def check_openai_api_key():
    """Check if OPENAI_API_KEY is set."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable is not set.")
        sys.exit(1)

    # Test the API key
    try:
        client = OpenAI()
        client.models.list()
    except Exception as e:
        print(f"Error: Invalid OPENAI_API_KEY: {str(e)}")
        sys.exit(1)


def extract_category_examples(original_data: Dict) -> Dict[str, List[Dict]]:
    """Extract examples of resources from each category in the original data.

    Args:
        original_data: Original parsed awesome list data

    Returns:
        Dictionary mapping category names to lists of example resources
    """
    category_examples = {}

    for section in original_data.get("sections", []):
        category = section.get("name")
        if not category:
            continue

        items = section.get("items", [])
        if not items:
            continue

        # Store all items for this category
        category_examples[category] = items

    return category_examples


def main():
    """Main entry point."""
    # Parse arguments
    args = parse_arguments()

    # Check if OPENAI_API_KEY is set
    check_openai_api_key()

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Set up logger
    logger = setup_logger(args.output_dir)

    # Log startup information
    logger.info(f"Starting Awesome-List Researcher")
    logger.info(f"Repository URL: {args.repo_url}")
    logger.info(f"Wall time limit: {args.wall_time} seconds")
    logger.info(f"Cost ceiling: ${args.cost_ceiling}")
    logger.info(f"Output directory: {args.output_dir}")
    if args.seed is not None:
        logger.info(f"Random seed: {args.seed}")
    logger.info(f"Model (planner): {args.model_planner}")
    logger.info(f"Model (researcher): {args.model_researcher}")
    logger.info(f"Model (validator): {args.model_validator}")

    # Set up wall time tracking
    wall_time_tracker = WallTimeTracker(args.wall_time)

    # Set up wall time limit
    setup_wall_time_limit(args.wall_time, lambda: handle_timeout(logger))

    # Set up cost tracking
    cost_tracker = CostTracker(args.cost_ceiling, logger)

    try:
        # STEP 1: Parse the awesome list
        logger.info("STEP 1: Parsing awesome list")
        parser, original_data = fetch_and_parse(args.repo_url, logger, args.output_dir)

        # Extract list title and other metadata
        list_title = original_data.get('title', 'Unknown')
        list_tagline = original_data.get('tagline', '')

        # Extract exemplar titles for term expansion
        exemplars = parser.extract_exemplar_titles(original_data)

        # Extract examples of resources for each category
        category_examples = extract_category_examples(original_data)
        logger.info(f"Extracted examples for {len(category_examples)} categories")

        # Log information about the parsed list
        logger.info(f"Title: {list_title}")
        logger.info(f"Tagline: {list_tagline}")
        logger.info(f"Sections: {len(original_data.get('sections', []))}")
        logger.info(f"Categories for expansion: {len(exemplars)}")

        # STEP 2: Expand search terms
        logger.info("STEP 2: Expanding search terms")
        term_expander = TermExpanderAgent(
            logger=logger,
            output_dir=args.output_dir,
            cost_tracker=cost_tracker,
            model=args.model_planner,
        )
        expanded_queries = term_expander.expand_queries(
            exemplars=exemplars,
            max_per_category=5,
            original_data=original_data
        )

        # STEP 3: Create research plan
        logger.info("STEP 3: Creating research plan")
        planner = PlannerAgent(
            logger=logger,
            output_dir=args.output_dir,
            cost_tracker=cost_tracker,
            original_data=original_data,
            model=args.model_planner,
            seed=args.seed,
        )
        research_plan = planner.create_research_plan(expanded_queries)

        # STEP 4: Research categories
        logger.info("STEP 4: Researching categories")
        category_agent = CategoryResearchAgent(
            logger=logger,
            output_dir=args.output_dir,
            cost_tracker=cost_tracker,
            wall_time_tracker=wall_time_tracker,
            model=args.model_researcher,
            list_title=list_title,
        )

        # Provide examples of resources for each category
        category_agent.set_category_examples(category_examples)

        all_candidate_resources = []

        for category, plan in research_plan.items():
            if wall_time_tracker.is_expired() or cost_tracker.would_exceed_ceiling(args.model_researcher, 5000):
                logger.warning(f"Skipping research for remaining categories due to resource limits")
                break

            logger.info(f"Researching category: {category}")
            resources = category_agent.research_category(
                category=category,
                search_terms=plan["search_terms"],
                exclude_urls=plan["exclude_urls"],
            )

            # Add category information to resources
            for resource in resources:
                resource["category"] = category

            all_candidate_resources.extend(resources)

            logger.info(f"Found {len(resources)} resources for category: {category}")
            logger.info(f"Total resources so far: {len(all_candidate_resources)}")

        # STEP 5: Deduplicate resources
        logger.info("STEP 5: Deduplicating resources")
        dedup_engine = DedupEngine(
            logger=logger,
            output_dir=args.output_dir,
            cost_tracker=cost_tracker,
            original_urls=parser.original_urls,
        )
        deduplicated_resources = dedup_engine.deduplicate_resources(all_candidate_resources)

        # STEP 6: Validate resources
        logger.info("STEP 6: Validating resources")
        validator = ValidatorAgent(
            logger=logger,
            output_dir=args.output_dir,
            cost_tracker=cost_tracker,
            model=args.model_validator,
        )
        validated_resources = validator.validate_resources(deduplicated_resources)

        # STEP 7: Render updated list
        logger.info("STEP 7: Rendering updated list")
        renderer = Renderer(
            logger=logger,
            output_dir=args.output_dir,
            awesome_parser=parser,
        )

        # Create categorized links dictionary for the research report
        categorized_links = {}
        for resource in validated_resources:
            category = resource.get("category", "Uncategorized")
            if category not in categorized_links:
                categorized_links[category] = []

            categorized_links[category].append(resource)

        # Render the updated list
        updated_list_path = renderer.render_updated_list(original_data, validated_resources)

        # Create a research report
        research_report_path = renderer.create_research_report(categorized_links)

        # STEP 8: Report completion
        logger.info("STEP 8: Process complete")

        # Check if we found at least 10 new links
        if len(validated_resources) >= 10:
            logger.info(f"SUCCESS: Found {len(validated_resources)} new links")
        else:
            logger.warning(
                f"WARNING: Found only {len(validated_resources)} new links, "
                f"which is less than the required minimum of 10"
            )

        # Print cost report
        cost_report = cost_tracker.generate_cost_report()
        logger.info(f"Cost report: {cost_report}")

        # Print paths to output files
        logger.info(f"Updated list: {updated_list_path}")
        logger.info(f"Research report: {research_report_path}")

        # Print elapsed time
        elapsed_time = wall_time_tracker.elapsed()
        logger.info(f"Total elapsed time: {elapsed_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
