"""
Main orchestrator for the Awesome-List Researcher.
"""

import argparse
import datetime
import json
import logging
import os
import random
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import dotenv
import httpx
from openai import OpenAI

from awesome_list_researcher.aggregator import Aggregator
from awesome_list_researcher.awesome_parser import AwesomeList, MarkdownParser
from awesome_list_researcher.category_agent import CategoryResearchAgent
from awesome_list_researcher.duplicate_filter import DuplicateFilter
from awesome_list_researcher.planner_agent import PlannerAgent
from awesome_list_researcher.renderer import Renderer
from awesome_list_researcher.utils.cost_guard import CostGuard
from awesome_list_researcher.utils.github import GitHubAPI, parse_github_url
from awesome_list_researcher.utils.logging import setup_logger
from awesome_list_researcher.validator import Validator


class TimeoutError(Exception):
    """Exception raised when the wall-time limit is reached."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for the wall-time limit."""
    raise TimeoutError("Wall-time limit reached")


@dataclass
class AppConfig:
    """Configuration for the Awesome-List Researcher."""
    repo_url: str
    wall_time: int = 600
    cost_ceiling: float = 10.0
    output_dir: str = "runs"
    seed: Optional[int] = None
    model_planner: str = "gpt-4.1"
    model_researcher: str = "o3"
    model_validator: str = "o3"


def parse_args() -> AppConfig:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Awesome-List Researcher")

    parser.add_argument(
        "--repo_url",
        type=str,
        required=True,
        help="GitHub URL of the Awesome List repository"
    )

    parser.add_argument(
        "--wall_time",
        type=int,
        default=600,
        help="Maximum execution time in seconds (default: 600)"
    )

    parser.add_argument(
        "--cost_ceiling",
        type=float,
        default=10.0,
        help="Maximum OpenAI API cost in USD (default: 10.0)"
    )

    parser.add_argument(
        "--output_dir",
        type=str,
        default="runs",
        help="Directory for output artifacts (default: runs)"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for deterministic behavior (default: random)"
    )

    parser.add_argument(
        "--model_planner",
        type=str,
        default="gpt-4.1",
        help="Model for planning research queries (default: gpt-4.1)"
    )

    parser.add_argument(
        "--model_researcher",
        type=str,
        default="o3",
        help="Model for researching new resources (default: o3)"
    )

    parser.add_argument(
        "--model_validator",
        type=str,
        default="o3",
        help="Model for validating new resources (default: o3)"
    )

    args = parser.parse_args()

    return AppConfig(
        repo_url=args.repo_url,
        wall_time=args.wall_time,
        cost_ceiling=args.cost_ceiling,
        output_dir=args.output_dir,
        seed=args.seed,
        model_planner=args.model_planner,
        model_researcher=args.model_researcher,
        model_validator=args.model_validator
    )


def setup_output_directory(output_dir: str) -> str:
    """Set up the output directory with a timestamp subdirectory."""
    # Create a timestamp for the run
    timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')

    # Create the output directory
    run_dir = os.path.join(output_dir, timestamp)
    os.makedirs(run_dir, exist_ok=True)

    return run_dir


def main():
    """Main entry point."""
    # Load environment variables
    dotenv.load_dotenv()

    # Parse command-line arguments
    config = parse_args()

    # Set up the output directory
    run_dir = setup_output_directory(config.output_dir)

    # Set up logging
    log_file = os.path.join(run_dir, "agent.log")
    logger = setup_logger("awesome_researcher", log_file)

    # Log the configuration
    logger.info(f"Starting Awesome-List Researcher with configuration:")
    logger.info(f"  Repo URL: {config.repo_url}")
    logger.info(f"  Wall time: {config.wall_time} seconds")
    logger.info(f"  Cost ceiling: ${config.cost_ceiling}")
    logger.info(f"  Output directory: {run_dir}")
    logger.info(f"  Seed: {config.seed or 'random'}")
    logger.info(f"  Model (planner): {config.model_planner}")
    logger.info(f"  Model (researcher): {config.model_researcher}")
    logger.info(f"  Model (validator): {config.model_validator}")

    # Check for OpenAI API key
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        logger.error("OPENAI_API_KEY environment variable not set")
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    # Set up the wall-time limit
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(config.wall_time)

    # Set random seed if provided
    if config.seed is not None:
        random.seed(config.seed)

    try:
        # Initialize the OpenAI client with custom timeout settings
        logger.info("Initializing OpenAI client with custom timeout settings")
        http_client = httpx.Client(
            timeout=httpx.Timeout(
                connect=10.0,  # connection timeout
                read=180.0,    # read timeout
                write=10.0,    # write timeout
                pool=5.0       # pool timeout
            ),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5
            )
        )

        client = OpenAI(
            api_key=openai_api_key,
            http_client=http_client
        )
        logger.info("OpenAI client initialized successfully")

        # Initialize the cost guard
        cost_guard = CostGuard(
            cost_ceiling=config.cost_ceiling,
            logger=logger
        )
        logger.info(f"Cost guard initialized with ceiling ${config.cost_ceiling}")

        # Initialize the GitHub API
        github_api = GitHubAPI(logger)

        # Step 1: Parse the GitHub URL and get the raw README
        logger.info(f"Fetching README from {config.repo_url}")
        owner, repo = parse_github_url(config.repo_url)
        readme_content = github_api.get_raw_readme(owner, repo)
        logger.info(f"Successfully fetched README.md ({len(readme_content)} bytes)")

        # Save the raw README
        readme_path = os.path.join(run_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write(readme_content)
        logger.info(f"Saved README.md to {readme_path}")

        # Step 2: Parse the README to JSON
        logger.info("Parsing README to structured format")
        markdown_parser = MarkdownParser(logger)
        awesome_list = markdown_parser.parse_markdown(readme_content)
        logger.info(f"Parsed {len(awesome_list.categories)} categories from README")

        # Save the original list as JSON
        original_json_path = os.path.join(run_dir, "original.json")
        with open(original_json_path, "w") as f:
            f.write(awesome_list.to_json())
        logger.info(f"Saved original list as JSON to {original_json_path}")

        # Step 3: Generate a research plan
        logger.info("Generating research plan")
        planner_agent = PlannerAgent(
            model=config.model_planner,
            api_client=client,
            cost_guard=cost_guard,
            logger=logger,
            seed=config.seed
        )

        research_plan = planner_agent.generate_plan(awesome_list)
        logger.info(f"Generated research plan with {len(research_plan.queries)} queries")

        # Save the research plan
        plan_path = os.path.join(run_dir, "plan.json")
        with open(plan_path, "w") as f:
            f.write(research_plan.to_json())
        logger.info(f"Saved research plan to {plan_path}")

        # Step 4: Execute the research plan with parallel agents
        logger.info(f"Executing research plan with {len(research_plan.queries)} queries")
        category_agent = CategoryResearchAgent(
            model=config.model_researcher,
            api_client=client,
            cost_guard=cost_guard,
            logger=logger
        )

        aggregator = Aggregator(logger)

        # Execute queries in parallel
        logger.info(f"Starting parallel execution with max 5 workers")
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_query = {
                executor.submit(category_agent.research_query, query): query
                for query in research_plan.queries
            }

            completed = 0
            total = len(future_to_query)

            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    result = future.result()
                    aggregator.add_result(result)
                    completed += 1
                    logger.info(f"Completed query {completed}/{total}: '{query.query}'")

                    # Save the result
                    result_path = os.path.join(
                        run_dir,
                        f"candidate_{query.category.lower().replace(' ', '_')}.json"
                    )
                    with open(result_path, "w") as f:
                        f.write(result.to_json())
                    logger.info(f"Saved query result to {result_path}")

                except Exception as e:
                    logger.error(f"Error researching query '{query.query}': {str(e)}")
                    import traceback
                    logger.error(f"Query error details: {traceback.format_exc()}")

        # Save the aggregated results
        aggregated_path = os.path.join(run_dir, "aggregated_results.json")
        aggregator.save_aggregated_results(aggregated_path)
        logger.info(f"Saved aggregated results to {aggregated_path}")

        # Generate a research report
        report_path = os.path.join(run_dir, "research_report.md")
        aggregator.generate_research_report(report_path)
        logger.info(f"Generated research report at {report_path}")

        # Step 5: Filter duplicates
        logger.info("Filtering duplicates")
        duplicate_filter = DuplicateFilter(logger)

        # Extract all links from the original list
        all_links = []
        for category in awesome_list.categories:
            all_links.extend(category.links)
            for subcategory_links in category.subcategories.values():
                all_links.extend(subcategory_links)

        # Add existing links to the filter
        duplicate_filter.add_existing_links(all_links)

        # Filter duplicates among candidates
        candidates = aggregator.get_all_candidates()
        candidates = duplicate_filter.filter_duplicates_among_candidates(candidates)

        # Filter duplicates against the original list
        unique_candidates, duplicate_candidates = duplicate_filter.filter_duplicates(candidates)

        # Step 6: Validate the candidates
        logger.info(f"Validating {len(unique_candidates)} candidates")
        validator = Validator(
            model=config.model_validator,
            api_client=client,
            cost_guard=cost_guard,
            logger=logger
        )

        valid_candidates, invalid_candidates = validator.validate_candidates(unique_candidates)

        # Save the valid candidates
        new_links_path = os.path.join(run_dir, "new_links.json")
        validator.save_validated_candidates(valid_candidates, new_links_path)

        # Step 7: Render the updated list
        logger.info(f"Rendering updated list with {len(valid_candidates)} new links")
        renderer = Renderer(logger)

        updated_list_path = os.path.join(run_dir, "updated_list.md")
        lint_result = renderer.render_updated_list(
            awesome_list,
            valid_candidates,
            updated_list_path
        )

        # Cancel the wall-time alarm
        signal.alarm(0)

        # Log the results
        logger.info("=== Results ===")
        logger.info(f"Total queries: {len(research_plan.queries)}")
        logger.info(f"Total candidates: {len(candidates)}")
        logger.info(f"Unique candidates: {len(unique_candidates)}")
        logger.info(f"Validated candidates: {len(valid_candidates)}")
        logger.info(f"New links added: {len(valid_candidates)}")
        logger.info(f"Total API cost: ${cost_guard.total_cost_usd:.2f}")
        logger.info(f"awesome-lint validation: {'Passed' if lint_result else 'Failed'}")
        logger.info("==============")

        # Print the results to the console
        print(f"\n=== Results ===")
        print(f"Total queries: {len(research_plan.queries)}")
        print(f"Total candidates: {len(candidates)}")
        print(f"New links added: {len(valid_candidates)}")
        print(f"Total API cost: ${cost_guard.total_cost_usd:.2f}")
        print(f"awesome-lint validation: {'Passed' if lint_result else 'Failed'}")
        print(f"Output directory: {run_dir}")
        print("==============")

    except TimeoutError:
        logger.error(f"Wall-time limit of {config.wall_time} seconds reached")
        print(f"\nError: Wall-time limit of {config.wall_time} seconds reached")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        import traceback
        logger.error(f"Error details: {traceback.format_exc()}")
        print(f"\nError: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
