# .windsurfrules

## Project Overview
- **Type:** CLI Tool (Python)
- **Description:** Docker-first, command-line tool to automate the discovery and integration of new, spec-compliant resources into "awesome-style" GitHub repositories.
- **Primary Goal:** Automate discovery and integration of new spec-compliant links into existing awesome-lists.

## Project Structure
### Framework-Specific Routing
- **Directory Rules:**
  - [Python CLI]: No routing directories; use `src/` for modules and a single entrypoint `main.py`.

### Core Directories
- **Versioned Structure:**
  - [src/awesome_list_researcher]: Python 3.10+ package modules implementing parser, agents, aggregator, validator, renderer, and CLI.
  - [tests]: E2E and unit tests, including `run_e2e.sh`.
  - [runs]: Runtime artifacts under `runs/<ISO-TS>/`, containing JSON outputs, Markdown, logs, and reports.

### Key Files
- **Stack-Versioned Patterns:**
  - [Dockerfile]: Multi-stage Docker build using `python:3.10-slim`, installs dependencies, sets `ENTRYPOINT ["python","-m","awesome_list_researcher.main"]`.
  - [build-and-run.sh]: Bash wrapper to build the Docker image and run the container with CLI flags.
  - [main.py]: Orchestrates entire workflow; enforces wall-time via `signal.alarm`; parses CLI flags and env vars.
  - [awesome_parser.py]: Parses `README.md` into `original.json` using Markdown AST and Bloom filter for dedupe.
  - [planner_agent.py]: Generates `plan.json` with search queries; defaults to `gpt-4.1-mini`.
  - [category_agent.py]: Spawns parallel research agents per category using `SearchTool` and `BrowserTool`; outputs `candidate_<category>.json`.
  - [aggregator.py]: Merges `candidate_*.json` into a single list.
  - [duplicate_filter.py]: Removes duplicates against `original.json`; outputs `new_links.json`.
  - [validator.py]: Performs HTTP HEAD checks (200 OK) and GitHub star count validation against `--min_stars`; cleans descriptions via model.
  - [renderer.py]: Merges `original.json` and `new_links.json` into `updated_list.md`; loops `awesome-lint@latest` until zero errors.
  - [tests/run_e2e.sh]: Executes full build-and-run with sample repo; expects output `"✅ All good"`.

## Tech Stack Rules
- **Version Enforcement:**
  - [python@3.10]: Enforce PEP 8, use `venv` paths inside Docker, no deprecated stdlib.
  - [docker@20.10]: Multi-stage build; no host Python or external CI dependencies.
  - [openai@*]: Live API calls; dynamic rate calculation at runtime; no mocking.
  - [awesome-lint@latest]: Must pass linting on generated Markdown; loop until zero errors.

## PRD Compliance
- **Non-Negotiable:**
  - "Docker-Only: The entire application must run inside a Docker container built from a `Dockerfile`. No host Python or external CI dependencies are allowed.": Enforce single Dockerfile and multi-stage build, no host Python.
  - "Live Operations: No mocks or placeholders are permitted; the tool must interact with live services.": HTTP and OpenAI calls must be real and retry-backed.
  - "Structured Logging: All actions must be logged with ISO 8601 timestamps, event names, token counts, and cost in USD, into `agent.log`.": Use JSON Lines logger.
  - "CLI Flags/Env Vars: The tool must accept `--repo_url`, `--wall_time`, `--cost_ceiling`, `--min_stars`, `--output_dir`, `--seed`, `--model_planner`, `--model_researcher`, `--model_validator`, `OPENAI_API_KEY`.": Exact flag names and defaults.
  - "Rate Limit Resilience: The tool must implement retry/back-off mechanisms for API requests.": Exponential backoff on HTTP and OpenAI errors.
  - "Cost Ceiling Enforcement: The tool must terminate when the predicted spend reaches or exceeds the `--cost_ceiling`.": Pre-calc token costs and abort if threshold hit.
  - "Awesome-List Spec Adherence: The generated Markdown must pass `awesome-lint`.": Use only `##` and `###` headings, maintain alphabetical order, include title, tagline, optional badges.

## App Flow Integration
- **Stack-Aligned Flow:**
  - Input → `main.py` reads CLI flags and env vars, creates `runs/<ISO-TS>/`.
  - Fetch README → `github_client.py` via GitHub default-branch API or `/HEAD/` fallback; abort on failure.
  - Parse → `awesome_parser.py` generates `original.json`.
  - Plan → `planner_agent.py` writes `plan.json`.
  - Research → `category_agent.py` runs parallel agents producing `candidate_<category>.json`.
  - Aggregate → `aggregator.py` merges candidates.
  - Deduplicate → `duplicate_filter.py` outputs `new_links.json` without duplicates.
  - Validate → `validator.py` checks HTTP 200 and star count ≥ `--min_stars`.
  - Render → `renderer.py` merges JSON and loops `awesome-lint` until passing; outputs `updated_list.md`.
  - Output → Persist `original.json`, `plan.json`, `candidate_*.json`, `new_links.json`, `updated_list.md`, `agent.log`, `research_report.md` under `runs/<ISO-TS>/`.
