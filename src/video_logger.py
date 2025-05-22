"""Enhanced logging system with detailed cost, timing, and git tracking."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, Any, Optional
import uuid

class VideoLogger:
    """Enhanced logger for Awesome Video Researcher with cost and timing tracking."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        git_branch: Optional[str] = None,
        git_commit: Optional[str] = None
    ):
        """Initialize the video logger.

        Args:
            logger: Base logger instance
            output_dir: Directory to store logs
            git_branch: Current git branch name
            git_commit: Current git commit hash
        """
        self.logger = logger
        self.output_dir = output_dir
        self.git_branch = git_branch
        self.git_commit = git_commit
        self.run_id = str(uuid.uuid4())
        self.phases = {}
        self.category_stats = {}

        # Set up environment variables for git info
        if git_branch:
            os.environ["GIT_BRANCH"] = git_branch
        if git_commit:
            os.environ["GIT_COMMIT"] = git_commit

    def log_phase(self, name: str, event: str, **kwargs) -> None:
        """Log a phase event with timing and git information.

        Args:
            name: Phase name
            event: Event type (start, end, progress)
            **kwargs: Additional logging information
        """
        ts = time.time()
        log_data = {
            "phase": name,
            "event": event,
            "ts": ts,
            "branch": self.git_branch,
            "commit": self.git_commit,
            "run_id": self.run_id,
            **kwargs
        }

        # Store phase information for summary
        if name not in self.phases:
            self.phases[name] = {"start": None, "end": None, "events": 0}

        self.phases[name]["events"] += 1

        if event == "start":
            self.phases[name]["start"] = ts
        elif event == "end":
            self.phases[name]["end"] = ts

        # Log as JSON
        self.logger.info(json.dumps(log_data))

        # Write to agent.log file
        self._write_to_agent_log(log_data)

    def log_category_result(self, category: str, success: bool, result_count: int, retries: int = 0, **kwargs) -> None:
        """Log category research results.

        Args:
            category: Category name
            success: Whether the research was successful
            result_count: Number of results found
            retries: Number of retries performed
            **kwargs: Additional logging information
        """
        if category not in self.category_stats:
            self.category_stats[category] = {
                "success": False,
                "result_count": 0,
                "retries": 0
            }

        self.category_stats[category]["success"] = success
        self.category_stats[category]["result_count"] = result_count
        self.category_stats[category]["retries"] = retries

        log_data = {
            "category": category,
            "success": success,
            "result_count": result_count,
            "retries": retries,
            "ts": time.time(),
            "branch": self.git_branch,
            "commit": self.git_commit,
            "run_id": self.run_id,
            **kwargs
        }

        self.logger.info(json.dumps(log_data))
        self._write_to_agent_log(log_data)

    def log_validation_result(self, schema_valid: bool, markdown_lint_pass: bool, url_valid: bool, **kwargs) -> None:
        """Log validation results.

        Args:
            schema_valid: Whether the JSON schema validation passed
            markdown_lint_pass: Whether the awesome-lint validation passed
            url_valid: Whether URL validation passed
            **kwargs: Additional logging information
        """
        log_data = {
            "validation": {
                "schema_valid": schema_valid,
                "markdown_lint_pass": markdown_lint_pass,
                "url_valid": url_valid
            },
            "ts": time.time(),
            "branch": self.git_branch,
            "commit": self.git_commit,
            "run_id": self.run_id,
            **kwargs
        }

        self.logger.info(json.dumps(log_data))
        self._write_to_agent_log(log_data)

    def generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of the run.

        Returns:
            Dictionary containing run summary
        """
        summary = {
            "run_id": self.run_id,
            "git": {
                "branch": self.git_branch,
                "commit": self.git_commit
            },
            "phases": {},
            "categories": self.category_stats
        }

        # Calculate phase durations
        for name, phase in self.phases.items():
            if phase["start"] and phase["end"]:
                duration = phase["end"] - phase["start"]
                summary["phases"][name] = {
                    "duration": duration,
                    "events": phase["events"]
                }

        return summary

    def _write_to_agent_log(self, data: Dict[str, Any]) -> None:
        """Write log data to agent.log file.

        Args:
            data: Log data dictionary
        """
        log_path = os.path.join(self.output_dir, "agent.log")

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")
