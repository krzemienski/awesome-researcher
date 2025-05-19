# Unified Project Documentation

## Project Requirements Document

### 1. Project Overview

The “Awesome-List Researcher” is a Docker-first command-line tool that takes the GitHub URL of any Awesome-style repository, retrieves its raw `README.md`, and parses it into structured JSON. It then runs a multi-agent workflow using OpenAI models to discover new, non-duplicate resources that fit the Awesome-List specification. Finally, it merges all artifacts into a Markdown file that passes `awesome-lint`, enforcing alphabetical order, proper headings, and description length limits.

This tool is being built to help maintainers of Awesome lists quickly find and validate high-quality links without manual effort. Success is measured by the tool’s ability to fetch and parse existing content, generate new candidate links, filter duplicates, enforce cost and time budgets, and produce a lint-compliant Markdown list, all within a Docker container. It must also provide clear, structured logs for auditing and debugging.

### 2. In-Scope vs. Out-of-Scope

In-Scope

*   Docker-only execution with a Python 3.12-slim base image
*   CLI entrypoint via `./build-and-run.sh` accepting flags and environment variables
*   Fetching `README.md` through GitHub API and `/HEAD/` fallback
*   Parsing Markdown to `original.json` using `awesome_parser.py` with Bloom-filter dedup support
*   PlannerAgent to generate `plan.json` of search queries using a configurable OpenAI model
*   Parallel CategoryResearchAgent instances to collect candidate links
*   Aggregation and duplicate filtering into `new_links.json`
*   Validator module to check HTTP status, GitHub stars, and clean descriptions
*   Renderer to merge JSON data into `updated_list.md` and run `awesome-lint` until green
*   Structured logging (`agent.log`) with ISO 8601 timestamps, token usage, and cost in USD
*   Enforcement of wall-time and cost ceilings
*   End-to-end testing via `tests/run_e2e.sh`

Out-of-Scope

*   Any GUI or web interface beyond CLI output
*   Use of a GitHub personal access token or authenticated API beyond anonymous calls
*   License validation or SPDX checks via GitHub API
*   Custom Markdown templates or headers/footers beyond the Awesome-List spec
*   External CI configuration; all tests run inside Docker
*   Mocking or placeholder operations for live API calls

### 3. User Flow

A user begins by exporting `OPENAI_API_KEY` in their environment and ensuring Docker is installed. They clone the repository and run the build script with the required `--repo_url` flag and optional settings for wall time, cost ceiling, minimum stars, output directory, seed, and model overrides. Docker builds an image with Poetry, `awesome-lint`, and the OpenAI Agents SDK, then launches the orchestrator inside the container.

Inside the container, the orchestrator fetches the default branch of the target repository, retrieves the raw `README.md`, and parses it into `original.json`. It runs a PlannerAgent to produce search queries, then spawns CategoryResearchAgent instances per category found in `plan.json`. After collecting candidates, it aggregates results, filters duplicates, validates links, and renders the final `updated_list.md`. All actions and costs are logged. When finished, the user inspects `runs/<ISO-TS>/` for JSON artifacts, the updated Markdown file, logs, and a human-readable report.

### 4. Core Features

*   **CLI Entrypoint**: Single script `build-and-run.sh` that builds the Docker image and runs the container with flags and environment variables.
*   **README Fetcher**: Determines the default branch via GitHub REST API and falls back to `/HEAD/README.md`. Aborts on repeated failures.
*   **Markdown Parser**: `awesome_parser.py` converts Markdown lists into `original.json`, validating headings, order, URL format, and description length.
*   **PlannerAgent**: Generates `plan.json` of category-based search queries using a configurable OpenAI model, with cost estimation checks.
*   **CategoryResearchAgent**: Runs in parallel per category, using SearchTool and BrowserTool to discover new links and compile `candidate_<category>.json`.
*   **Aggregator & Duplicate Filter**: Merges candidate files, ensures no overlap with `original.json`, logs deduplication ratio, and outputs `new_links.json`.
*   **Validator**: Performs HTTP HEAD checks for 200 OK and GitHub star count filtering. Cleans up descriptions using a lightweight LLM.
*   **Renderer**: Merges `original.json` and `new_links.json` into `updated_list.md`, runs `awesome-lint` in a fix loop until passing.
*   **Structured Logging**: Single `agent.log` capturing ISO 8601 timestamps, events, token usage, and cost. Logs tool start/finish via callback hooks.
*   **E2E Testing**: `tests/run_e2e.sh` validates full workflow, shell scripts, and lint compliance, printing “✅ All good”.

### 5. Tech Stack & Tools

*   **Language & Runtime**: Python 3.12-slim inside Docker
*   **Dependency Management**: Poetry
*   **AI SDK**: OpenAI Agents SDK (`openai-agents`)
*   **Linting**: awesome-lint for Markdown, ShellCheck for shell scripts
*   **API Clients**: `requests` or similar for GitHub REST API and HTTP HEAD checks
*   **Containerization**: Docker, with `build-and-run.sh` as entrypoint
*   **Testing**: Bash scripting for end-to-end test
*   **Logging**: Python `logging` module with JSON output format

### 6. Non-Functional Requirements

*   Performance: Complete within user-specified `--wall_time` (default 600s)
*   Cost Control: Halt further API calls if projected spend plus used cost exceeds `--cost_ceiling` (default $5.00)
*   Reliability: Automatic retry with exponential back-off on rate limits or transient network errors
*   Security: No hard-coded secrets; require `OPENAI_API_KEY` as environment variable
*   Compliance: Output must pass `awesome-lint` with zero errors
*   Observability: Detailed, structured log of every agent call, including model names, tokens, and cost

### 7. Constraints & Assumptions

*   The tool runs exclusively inside Docker—no host-level Python or CI is needed
*   OpenAI pricing is fetched at runtime to estimate per-call cost
*   No GitHub authentication token is used; rely on anonymous API calls
*   One research agent per category in `plan.json`; unlimited parallelism as categories allow
*   If `README.md` fetching fails twice, the tool aborts rather than producing empty output
*   ISO 8601 timestamp format `YYYY-MM-DDTHH:MM:SSZ` is used for run folders and logs
*   A single consolidated `agent.log` file captures all events across agents

### 8. Known Issues & Potential Pitfalls

*   GitHub API rate limits may slow down branch detection or fallback; mitigate with retries and back-off
*   Cost estimations may be inaccurate if model pricing changes; ensure dynamic rate fetch
*   Markdown edge cases (nested lists, nonstandard formatting) could break the parser; add unit tests and fallback handling
*   Duplicate detection using Bloom filter may false-positive; tune filter parameters or fall back to exact set checks
*   Network instability can prematurely abort research; ensure graceful shutdown and partial result saving

## App Flow Document

### Onboarding and Sign-In/Sign-Up

There is no traditional sign-up flow, since this is a CLI tool. A user begins by cloning the repository and exporting their OpenAI API key with `export OPENAI_API_KEY=your_key`. They must have Docker installed locally or on their build server. No passwords or user accounts are managed by the tool.

### Main Dashboard or Home Page

After launching `./build-and-run.sh --repo_url <GitHub-URL> [options]`, users see build logs followed by orchestrator logs streaming to the console. There is no graphical dashboard. All results, including JSON artifacts and the updated Markdown list, are stored under `runs/<ISO-TS>/` in the project directory.

### Detailed Feature Flows and Page Transitions

When executed, the orchestrator first determines the repository’s default branch and fetches the raw `README.md`. It hands the content to the Markdown parser to produce `original.json`. Next, a PlannerAgent runs with a user-selected model to create `plan.json` of search queries. For each category in the plan, a research agent runs in parallel, using SearchTool and BrowserTool to gather candidates. Once all agents finish or wall time expires, the aggregator merges candidate files and the duplicate filter ensures `new_links.json` has no overlap with `original.json`. A Validator module then checks each link’s HTTP status and star count, cleaning up descriptions with the validator model. Finally, the renderer merges everything into `updated_list.md` and runs `awesome-lint` fix loops until compliance is achieved.

### Settings and Account Management

Users pass settings via CLI flags (e.g., `--cost_ceiling`, `--wall_time`, `--min_stars`, `--model_planner`, etc.) or environment variables (`OPENAI_API_KEY`). To change these, users stop the container, adjust their command or environment, and rerun the build script. After settings are picked up, the workflow returns to the main execution flow automatically.

### Error States and Alternate Paths

If fetching `README.md` fails on both the default-branch API and the `/HEAD/` fallback, the tool aborts with an error message. For transient network errors or rate limits, the system retries with exponential back-off. If projected API spend would exceed the cost ceiling, the tool logs a warning and stops issuing further calls. Wall-time overruns trigger a graceful shutdown via `signal.alarm`, preserving partial results. All errors and fallback events are recorded in `agent.log` for user inspection.

### Conclusion and Overall App Journey

From setting up the environment and exporting `OPENAI_API_KEY` to inspecting final artifacts in `runs/<ISO-TS>/`, the user journeys through a fully automated, Docker-contained pipeline. They never leave the CLI, yet they receive a validated, lint-compliant Awesome list with newly discovered links, complete logs, and a human-readable report.

## Tech Stack Document

### Frontend Technologies

*   This project uses a command-line interface rather than a traditional frontend stack. Console output is plain-text with clear prompts and structured logging for observability.

### Backend Technologies

*   Python 3.12-slim: Core language runtime for all modules and scripts
*   Poetry: Dependency management and virtual environment isolation inside Docker
*   OpenAI Agents SDK (`openai-agents`): Orchestrates LLM calls and agent workflows
*   Requests (or similar HTTP client): GitHub API access and HTTP HEAD checks
*   Shell scripting: `build-and-run.sh`, `tests/run_e2e.sh`, and helper scripts

### Infrastructure and Deployment

*   Docker: Containerizes the entire application, ensuring consistent environments across developer machines and CI/CD servers
*   Dockerfile: Defines Python installation, dependencies, and entrypoint
*   `build-and-run.sh`: Automates image build and container startup
*   No external CI: All tests and checks run inside the Docker container to satisfy the Docker-only constraint

### Third-Party Integrations

*   GitHub REST API: Fetches default branch information and raw `README.md`
*   OpenAI Chat Completions API: Powers the PlannerAgent, CategoryResearchAgent, and Validator LLM calls
*   awesome-lint: Validates and fixes final Markdown lists against the Awesome-List specification

### Security and Performance Considerations

*   API Key Management: `OPENAI_API_KEY` must be set as an environment variable, preventing hard-coded secrets
*   Retry & Back-off: Automatic retry logic for HTTP errors and rate limits to maintain stability
*   Cost Guard: Real-time cost estimation ensures the tool halts before exceeding the user’s budget
*   Wall-Time Enforcement: `signal.alarm` ensures the workflow does not overrun its allotted time
*   Lint & ShellCheck: Automated checks on Markdown and shell scripts maintain code quality and prevent script vulnerabilities

### Conclusion and Overall Tech Stack Summary

This stack combines lightweight, widely supported technologies—Docker, Python, Poetry—with the OpenAI Agents SDK and `awesome-lint` to deliver a portable, self-contained tool. It emphasizes reproducibility, observability, and strict compliance with cost, time, and linting constraints, aligning perfectly with the project’s goal of fully automated, production-ready Awesome list maintenance.

## Frontend Guidelines Document

### Frontend Architecture

Although this project does not include a graphical user interface, we treat the command-line interface (CLI) as the “frontend.” The CLI is implemented in Bash and Python, ensuring clear modular separation: shell scripts for container orchestration and Python modules for workflow logic. This architecture supports maintainability, as each script has a single responsibility, and performance, since we only load required modules at runtime.

### Design Principles

*   Usability: Clear help text (`--help`), descriptive flag names, and concise console logs guide the user.
*   Accessibility: Plain-text output avoids reliance on colors or advanced terminal features, ensuring compatibility.
*   Consistency: Uniform log formatting (ISO 8601 timestamps, structured JSON) helps users and tools parse output reliably.
*   Minimalism: The CLI exposes only essential options, reducing cognitive load.

### Styling and Theming

*   Output Style: Plain-text console logs with optional ANSI coloring for error and warning highlights.
*   Theming: No theming beyond standard terminal colors to maintain portability.
*   Markdown Reports: Generated files follow the Awesome-List spec, using only `##` and `###` headings and a consistent colorless style for compatibility with any Markdown renderer.

### Component Structure

*   `main.py`: Orchestrator coordinating all steps
*   `awesome_parser.py`: Markdown-to-JSON parsing logic
*   `planner_agent.py`: Search query planning
*   `category_agent.py`: Parallel research workflows
*   `aggregator.py` & `duplicate_filter.py`: Merging and deduplication
*   `validator.py`: Link and description checks
*   `renderer.py`: JSON-to-Markdown rendering and lint loop
*   Shell scripts: Container build, run, and testing

Each Python module exposes a clear function or class API, promoting reusability and testability.

### State Management

*   Module-Level State: Each agent or parser holds its own state until it outputs a file
*   File-Based Handoff: JSON artifacts (`original.json`, `plan.json`, etc.) serve as intermediate state, ensuring crash recovery and auditing
*   Seeded Randomness: A user-provided `--seed` flag ensures reproducible shuffle behavior in PlannerAgent

### Routing and Navigation

*   CLI Routing: The `build-and-run.sh` script passes flags to `main.py`, which routes execution through the defined workflow steps
*   Workflow Steps: Determined by sequential calls in `main.py`, each step writes to disk before the next step begins

### Performance Optimization

*   Lazy Imports: Python modules are only imported when needed, reducing startup time
*   Parallel Agents: CategoryResearchAgent instances run concurrently to shorten overall research time
*   Retry & Back-off: Prevents wasted time on transient failures

### Testing and Quality Assurance

*   Unit Tests: Python modules include unit tests where practical (run manually inside Docker)
*   Integration Tests: `tests/run_e2e.sh` script performs a full workflow run against a sample repo
*   Linting: `awesome-lint` for Markdown and ShellCheck for shell scripts ensure style and correctness

### Conclusion and Overall Frontend Summary

The CLI “frontend” is designed for clarity, consistency, and reliability. By treating each component as a standalone module or script, we ensure maintainability and testability. Uniform logging and file-based state management support debugging and reproducibility, aligning with the project’s goal of a robust, Docker-contained tool.

## Implementation Plan

1.  Initialize the Git repository with `.gitignore`, `README.md`, and `CONTRIBUTING_TEMPLATE.md`.
2.  Create a `Dockerfile` based on `python:3.12-slim`, installing Poetry, `awesome-lint`, and `openai-agents`.
3.  Write `build-and-run.sh` to build the Docker image and run the container with flag parsing.
4.  Implement `main.py` to parse flags, set up logging, enforce wall-time, and orchestrate workflow steps.
5.  Build `github_fetcher.py` logic in `main.py` or separate module to get default branch and raw `README.md`, with fallback and abort on failure.
6.  Develop `awesome_parser.py` to convert Markdown into `original.json`, enforcing spec rules and Bloom-filter setup.
7.  Create `planner_agent.py` to call the OpenAI model, generate `plan.json`, and implement cost-guard logic.
8.  Implement `category_agent.py` with parallel execution, using SearchTool and BrowserTool to produce `candidate_<category>.json`.
9.  Write `aggregator.py` and `duplicate_filter.py` to merge candidate files, remove overlaps, and output `new_links.json`.
10. Develop `validator.py` to check HTTP status, star count, and LLM-based description cleanup.
11. Create `renderer.py` to merge JSON files into `updated_list.md` and run `awesome-lint` loops until no errors.
12. Integrate structured logging across all modules, writing to `runs/<ISO-TS>/agent.log`.
13. Add `tests/run_e2e.sh` for end-to-end validation and integrate ShellCheck in CI-free mode.
14. Prepare example artifacts under `examples/sample_run/` to demonstrate a successful run.
15. Finalize documentation: `architecture.md`, user guide in `README.md`, and ensure all deliverables are present.
16. Conduct a full demo run against `https://github.com/sindresorhus/awesome-nodejs` to verify acceptance criteria.
