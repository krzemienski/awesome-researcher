# Tech Stack Document

This document explains the technology choices for the “Awesome-List Researcher” tool in everyday language. It covers how each piece works together to create a reliable, portable, and user-friendly system without assuming you’re a developer.

## 1. Frontend Technologies

Although this tool doesn’t have a graphical user interface, it still offers a clear “frontend” via the command line:

- **Bash Script (`build-and-run.sh`)**
  - Serves as the entry point: builds the Docker image, launches the container, and passes your flags.
  - Provides a familiar, shell-based experience on macOS, Linux, or Windows (via WSL).
- **Python’s `argparse` Library**
  - Parses command-line flags like `--repo_url`, `--wall_time`, and model overrides.
  - Generates helpful `--help` text so users know exactly what options are available.
- **ShellCheck**
  - A linting tool for shell scripts that ensures our `build-and-run.sh` follows best practices.
  - Catches simple mistakes and improves script readability.

These tools give you a consistent, self-documenting command-line interface that works identically on any machine with Docker installed.

## 2. Backend Technologies

All the core logic—fetching README files, parsing, AI calls, filtering, and rendering—runs in Python inside Docker:

- **Python 3.12 (slim)**
  - A lightweight, modern interpreter for writing our modules.
  - Slim base keeps the Docker image small.
- **Poetry**
  - Manages and locks dependencies (like `openai-agents`, `requests`, and any Bloom filter library).
  - Ensures everyone on the project uses the same library versions.
- **openai-agents SDK**
  - Drives three types of AI agents: Planner, Researcher, and Validator.
  - Provides built-in tools (`SearchTool`, `BrowserTool`) plus parallel execution support.
- **awesome-lint**
  - Validates and auto-fixes Markdown so the final list meets the Awesome-List spec.
- **GitHub REST API**
  - Retrieves the default branch and raw `README.md`.
  - Performs HTTP HEAD requests to check URL status codes and star counts.
- **`requests` (or similar HTTP client)**
  - Handles all HTTP calls to GitHub and third-party sites.
- **Bloom Filter**
  - A memory-efficient data structure to quickly check for duplicate links.
- **Python Standard Libraries**
  - `argparse`: handles CLI flags.
  - `signal`: enforces the wall-time limit.
  - `logging`: produces a single structured log (`agent.log`) with ISO 8601 timestamps, events, token counts, and cost in USD.

Together, these components let the orchestrator (`main.py`) drive the workflow step by step, ensuring spec compliance, cost controls, and robust error handling.

## 3. Infrastructure and Deployment

We chose a fully Docker-based setup so the tool runs the same everywhere:

- **Docker & Dockerfile**
  - Base image: `python:3.12-slim` plus Poetry, `awesome-lint`, and `openai-agents` preinstalled.
  - Guarantees no external dependencies are required on your host or CI system.
- **`build-and-run.sh`**
  - Automates building the Docker image and running the container with your chosen flags and environment variables (e.g., `OPENAI_API_KEY`).
- **Git & GitHub**
  - Source code versioned via Git with branching, squash-merges, and tags.
  - Repository includes everything needed: code, `Dockerfile`, scripts, tests, and templates.
- **Testing Inside Container**
  - `tests/run_e2e.sh` runs end-to-end checks (no external CI needed).
  - Enforces awesome-lint, ShellCheck, cost ceilings, and wall-time limits in a single command.

This approach maximizes portability, reproducibility, and ease of deployment—whether on a developer’s laptop, a CI service, or a production server.

## 4. Third-Party Integrations

We integrate a handful of external services to power AI, linting, and data retrieval:

- **OpenAI API**
  - Provides LLM models for planning, researching, and validating links.
  - Configurable via flags (`--model_planner`, `--model_researcher`, `--model_validator`).
- **SearchTool & BrowserTool** (from openai-agents)
  - Enable web searches and page scraping within research agents.
- **GitHub REST API**
  - Fetches raw `README.md` files.
  - Checks link status and star counts for validation.
- **awesome-lint**
  - Ensures generated Markdown adheres to community standards and rules.
- **ShellCheck**
  - Validates our shell scripts for best practices and error prevention.

By leveraging these mature services and libraries, we avoid reinventing the wheel and focus on orchestrating a seamless, spec-compliant workflow.

## 5. Security and Performance Considerations

Security Measures:
- **Container Isolation**: All code runs inside Docker, preventing host-level contamination.
- **Environment Variables**: Secrets (like `OPENAI_API_KEY`) never appear in code or logs—only in container runtime.
- **Early Failures**: If critical steps (e.g., fetching `README.md`) fail, the tool aborts immediately to avoid wasted work.
- **Rate-Limit Resilience**: Automatic retries with exponential backoff for GitHub and OpenAI API calls.

Performance Optimizations:
- **Parallel Research**: Spawns one research agent per category to speed up link discovery.
- **Bloom Filter Deduplication**: Quickly filters out duplicates without heavy database lookups.
- **Cost-Guard Logic**: Estimates next-call cost and halts further calls if the user’s budget ceiling would be exceeded.
- **Wall-Time Enforcement**: Uses `signal.alarm` to ensure the entire run respects the user’s time limit.

These measures ensure a secure, cost-effective, and responsive experience for users.

## 6. Conclusion and Overall Tech Stack Summary

In crafting the Awesome-List Researcher, we balanced portability, reliability, and user friendliness by choosing:

- **Docker** for containerized, environment-agnostic execution
- **Python 3.12 + Poetry** for clear, reproducible backend development
- **openai-agents SDK** for multi-agent AI workflows
- **awesome-lint** and **ShellCheck** for automated spec and script compliance
- **GitHub REST API** and **requests** for robust data retrieval
- **Bash + `argparse`** for a simple yet powerful command-line interface
- **Logging, Bloom filters, and cost/wall-time guards** for observability, deduplication, and resource control

Together, these technologies deliver a fully Docker-First, production-ready tool that transforms any Awesome-style repository into an up-to-date, lint-compliant list of resources—securely, efficiently, and consistently across all environments.