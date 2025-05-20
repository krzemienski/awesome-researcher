"""
Main module for the Awesome-List Researcher.

This module serves as the entry point for the application, orchestrating the
various components to find new resources for an Awesome-List repository.
"""

import os
import sys
import signal
import logging
import argparse
import json
import time
import datetime
from typing import Dict, List, Any, Optional, Tuple

# Import MCP tools
from awesome_list_researcher.utils import (
    load_mcp_tools,
    mcp_handler,
    memory_store,
    context_store,
    create_dependency_graph,
    create_file_graph
)

# Import core components
from awesome_list_researcher.awesome_parser import AwesomeParser
from awesome_list_researcher.planner_agent import PlannerAgent
from awesome_list_researcher.category_agent import CategoryResearchAgent
from awesome_list_researcher.aggregator import Aggregator
from awesome_list_researcher.duplicate_filter import DuplicateFilter
from awesome_list_researcher.validator import Validator
from awesome_list_researcher.renderer import Renderer

# Create logger
logger = logging.getLogger(__name__)

class AwesomeListResearcher:
    """
    Main class for the Awesome-List Researcher application.

    This class orchestrates the workflow for researching and finding
    new resources for an Awesome-List repository.
    """

    def __init__(self, args: argparse.Namespace):
        """
        Initialize the Awesome-List Researcher.

        Args:
            args: Command-line arguments
        """
        self.args = args
        self.start_time = time.time()
        self.total_cost = 0.0
        self.run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        # Create output directory
        self.output_dir = os.path.join(args.output_dir, self.run_id)
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize MCP tools
        self._init_mcp_tools()

        # Setup logging
        self._setup_logging()

        # Setup wall-time guard
        if args.wall_time > 0:
            signal.signal(signal.SIGALRM, self._wall_time_handler)
            signal.alarm(args.wall_time)

        # Log initialization
        logger.info(f"Initialized Awesome-List Researcher with run ID: {self.run_id}")
        logger.info(f"Arguments: {args}")

    def _init_mcp_tools(self):
        """Initialize MCP tools as required by Cursor Rules."""
        # Load all MCP tools
        mcp_data = load_mcp_tools()

        # Store in context
        context_store.set("repo_tree", mcp_data["repo_tree"])
        context_store.set("code_map", mcp_data["code_map"])
        context_store.set("openai_context", mcp_data["context"])

        # Create and store dependency graph
        dependency_graph = create_dependency_graph()
        context_store.set("dependency_graph", dependency_graph.to_dict())

        # Create and store file graph
        file_graph = create_file_graph()
        context_store.set("file_graph", file_graph.to_dict())

        # Store the run configuration in memory
        memory_store.put("run_config", vars(self.args))

        # Initialize sequence thinking in MCP handler
        mcp_handler.sequence_thinking(
            thought="Initializing Awesome-List Researcher workflow",
            thought_number=1,
            total_thoughts=7
        )

    def _setup_logging(self):
        """Set up logging configuration."""
        log_file = os.path.join(self.output_dir, "agent.log")

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )

        logger.info(f"Logging to {log_file}")

    def _wall_time_handler(self, signum, frame):
        """Handle wall-time exceeded signal."""
        elapsed = time.time() - self.start_time
        logger.warning(f"Wall-time limit of {self.args.wall_time}s exceeded after {elapsed:.2f}s")

        # Create a summary report
        self._create_summary_report(aborted=True)

        # Exit with non-zero status
        sys.exit(1)

    def _check_cost_ceiling(self, estimated_cost: float) -> bool:
        """
        Check if an operation would exceed the cost ceiling.

        Args:
            estimated_cost: Estimated cost of the operation

        Returns:
            True if the operation is allowed, False if it would exceed the ceiling
        """
        if self.args.cost_ceiling <= 0:
            return True

        if self.total_cost + estimated_cost >= self.args.cost_ceiling:
            logger.warning(f"Cost ceiling of ${self.args.cost_ceiling:.2f} would be exceeded: "
                          f"current ${self.total_cost:.4f} + estimated ${estimated_cost:.4f}")
            return False

        return True

    def _update_cost(self, cost: float):
        """
        Update the total cost.

        Args:
            cost: Cost to add
        """
        self.total_cost += cost
        logger.info(f"Added cost: ${cost:.4f}, new total: ${self.total_cost:.4f}")

        # Store in memory for persistence
        memory_store.put("total_cost", self.total_cost)

    def _create_summary_report(self, aborted: bool = False):
        """
        Create a summary report of the run.

        Args:
            aborted: Whether the run was aborted
        """
        elapsed = time.time() - self.start_time

        summary = {
            "run_id": self.run_id,
            "args": vars(self.args),
            "elapsed_seconds": elapsed,
            "total_cost_usd": self.total_cost,
            "aborted": aborted,
            "timestamp": datetime.datetime.now().isoformat()
        }

        # Add additional stats if available
        if context_store.has("stats"):
            summary["stats"] = context_store.get("stats")

        # Write to file
        report_file = os.path.join(self.output_dir, "research_report.md")
        with open(report_file, "w") as f:
            f.write(f"# Awesome-List Research Report\n\n")
            f.write(f"**Run ID:** {self.run_id}\n")
            f.write(f"**Timestamp:** {summary['timestamp']}\n")
            f.write(f"**Elapsed time:** {elapsed:.2f}s\n")
            f.write(f"**Total cost:** ${self.total_cost:.4f}\n")
            f.write(f"**Repository URL:** {self.args.repo_url}\n")

            if aborted:
                f.write(f"\n**ABORTED:** The run was aborted due to exceeding limits.\n")

            # Add stats section if available
            if "stats" in summary:
                f.write(f"\n## Statistics\n\n")
                for key, value in summary["stats"].items():
                    f.write(f"- **{key}:** {value}\n")

            # Add categories section if available
            if context_store.has("categories"):
                categories = context_store.get("categories")
                f.write(f"\n## Categories Researched\n\n")
                for category in categories:
                    f.write(f"- {category}\n")

        logger.info(f"Summary report written to {report_file}")
        return summary

    def run(self):
        """
        Run the Awesome-List Researcher workflow.
        """
        try:
            # Continue sequence thinking
            mcp_handler.sequence_thinking(
                thought="Parsing the Awesome-List README",
                thought_number=2,
                total_thoughts=7
            )

            # 1. Parse the README
            parser = AwesomeParser(self.args.repo_url)
            original_data = parser.parse()
            original_json_path = os.path.join(self.output_dir, "original.json")
            with open(original_json_path, "w") as f:
                json.dump(original_data, f, indent=2)
            logger.info(f"Original data saved to {original_json_path}")

            # Store in context
            context_store.set("original_data", original_data)
            context_store.set("categories", parser.get_categories())

            # Continue sequence thinking
            mcp_handler.sequence_thinking(
                thought="Planning research queries",
                thought_number=3,
                total_thoughts=7
            )

            # 2. Generate research plan
            planner = PlannerAgent(
                categories=original_data.get("categories", []),
                queries_per_category=3,
                seed=self.args.seed
            )

            # Generate plan
            plan_data = {}
            plan_queries = planner.generate_queries()

            # Group queries by category
            for query in plan_queries:
                category = query.get("category")
                if category not in plan_data:
                    plan_data[category] = []
                plan_data[category].append(query.get("query"))

            # Save plan
            plan_json_path = os.path.join(self.output_dir, "plan.json")
            with open(plan_json_path, "w") as f:
                json.dump(plan_data, f, indent=2)
            logger.info(f"Research plan saved to {plan_json_path}")

            # Store in context
            context_store.set("plan_data", plan_data)

            # Continue sequence thinking
            mcp_handler.sequence_thinking(
                thought="Researching new resources for each category",
                thought_number=4,
                total_thoughts=7
            )

            # 3. Research categories
            candidates = {}
            for category, queries in plan_data.items():
                # Create a category agent
                category_agent = CategoryResearchAgent(
                    category=category,
                    queries=queries,
                    model_name=self.args.model_researcher,
                    cost_ceiling=self.args.cost_ceiling - self.total_cost
                )

                # Check cost ceiling
                estimated_cost = category_agent.estimate_cost()
                if not self._check_cost_ceiling(estimated_cost):
                    logger.warning(f"Skipping category {category} due to cost ceiling")
                    continue

                # Research the category
                category_results = category_agent.research()
                self._update_cost(category_agent.get_cost())

                # Save category results
                category_json_path = os.path.join(self.output_dir, f"candidate_{category.lower().replace(' ', '_')}.json")
                with open(category_json_path, "w") as f:
                    json.dump(category_results, f, indent=2)
                logger.info(f"Category results saved to {category_json_path}")

                # Add to candidates
                candidates[category] = category_results

            # Store in context
            context_store.set("candidates", candidates)

            # Continue sequence thinking
            mcp_handler.sequence_thinking(
                thought="Aggregating and filtering candidates",
                thought_number=5,
                total_thoughts=7
            )

            # 4. Aggregate results
            aggregator = Aggregator(candidates)
            aggregated_results = aggregator.aggregate()

            # 5. Filter duplicates
            duplicate_filter = DuplicateFilter(aggregated_results, original_data)
            filtered_results = duplicate_filter.filter()

            # Check duplicate ratio
            dupe_ratio = duplicate_filter.get_duplicate_ratio()
            context_store.set("stats", {
                "total_candidates": len(aggregated_results),
                "duplicates_found": len(aggregated_results) - len(filtered_results),
                "duplicate_ratio": f"{dupe_ratio:.2f}%",
                "new_links_found": len(filtered_results)
            })

            # Save new links
            new_links_path = os.path.join(self.output_dir, "new_links.json")
            with open(new_links_path, "w") as f:
                json.dump(filtered_results, f, indent=2)
            logger.info(f"New links saved to {new_links_path}")

            # Continue sequence thinking
            mcp_handler.sequence_thinking(
                thought="Validating candidate resources",
                thought_number=6,
                total_thoughts=7
            )

            # 6. Validate new links
            validator = Validator(
                filtered_results,
                model_name=self.args.model_validator,
                cost_ceiling=self.args.cost_ceiling - self.total_cost
            )

            # Check cost ceiling
            estimated_cost = validator.estimate_cost()
            if not self._check_cost_ceiling(estimated_cost):
                logger.error("Cannot proceed with validation due to cost ceiling")
                self._create_summary_report(aborted=True)
                return 1

            validated_results = validator.validate()
            self._update_cost(validator.get_cost())

            # Save validated links
            validated_links_path = os.path.join(self.output_dir, "validated_links.json")
            with open(validated_links_path, "w") as f:
                json.dump(validated_results, f, indent=2)
            logger.info(f"Validated links saved to {validated_links_path}")

            # Continue sequence thinking
            mcp_handler.sequence_thinking(
                thought="Rendering updated Awesome-List",
                thought_number=7,
                total_thoughts=7
            )

            # 7. Render updated list
            renderer = Renderer(original_data, validated_results)
            updated_list = renderer.render()

            # Save updated list
            updated_list_path = os.path.join(self.output_dir, "updated_list.md")
            with open(updated_list_path, "w") as f:
                f.write(updated_list)
            logger.info(f"Updated list saved to {updated_list_path}")

            # Create summary report
            self._create_summary_report()

            logger.info(f"Awesome-List Researcher completed successfully in {time.time() - self.start_time:.2f}s")
            return 0

        except Exception as e:
            logger.exception(f"Error running Awesome-List Researcher: {e}")
            self._create_summary_report(aborted=True)
            return 1
        finally:
            # Cancel the wall-time alarm if set
            if self.args.wall_time > 0:
                signal.alarm(0)

def parse_args():
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(description="Awesome-List Researcher")

    parser.add_argument(
        "--repo_url",
        type=str,
        required=True,
        help="GitHub URL of the Awesome-List repository"
    )

    parser.add_argument(
        "--wall_time",
        type=int,
        default=600,
        help="Wall-time limit in seconds (default: 600)"
    )

    parser.add_argument(
        "--cost_ceiling",
        type=float,
        default=10.0,
        help="Cost ceiling in USD (default: 10.0)"
    )

    parser.add_argument(
        "--output_dir",
        type=str,
        default="runs",
        help="Output directory for results (default: runs)"
    )

    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducibility"
    )

    parser.add_argument(
        "--model_planner",
        type=str,
        default="gpt-4.1",
        help="Model to use for planning (default: gpt-4.1)"
    )

    parser.add_argument(
        "--model_researcher",
        type=str,
        default="o3",
        help="Model to use for research (default: o3)"
    )

    parser.add_argument(
        "--model_validator",
        type=str,
        default="o3",
        help="Model to use for validation (default: o3)"
    )

    return parser.parse_args()

def main():
    """
    Main entry point for the Awesome-List Researcher.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Parse command-line arguments
    args = parse_args()

    # Create and run the researcher
    researcher = AwesomeListResearcher(args)
    return researcher.run()

if __name__ == "__main__":
    sys.exit(main())
