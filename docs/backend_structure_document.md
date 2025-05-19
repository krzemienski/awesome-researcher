# Awesome-List Researcher Backend Structure

This document describes the backend architecture, hosting setup, and infrastructure components for the _Awesome-List Researcher_ command-line tool. It’s written in everyday language so anyone can understand how the tool works under the hood.

## 1. Backend Architecture

Overall, the backend is a modular, orchestrated Python application that runs entirely inside a Docker container. It follows a monolithic-but-modular pattern, where each piece has a single responsibility and the `main.py` orchestrator wires them together in sequence.

- **Orchestrator Pattern**  
  `main.py` handles command-line flags, sets up the run folder, enforces wall-time limits, and invokes each module in turn.

- **Module Breakdown**  
  • **awesome_parser.py** – Downloads and parses the `README.md` into a JSON structure. Uses a Bloom filter to catch duplicates early.  
  • **planner_agent.py** – Decides what to search for, expands synonyms, randomizes order (seeded).  
  • **category_agent.py** – Spawns one research agent per category, runs in parallel. Each agent uses live browser/search tools.  
  • **aggregator.py** & **duplicate_filter.py** – Gathers all candidates, merges them, and filters out any that already exist.  
  • **validator.py** – Runs HTTP HEAD checks, fetches GitHub star counts, cleans up descriptions via a small LLM prompt.  
  • **renderer.py** – Merges original and new links into a combined Markdown file, runs `awesome-lint` in a loop until it’s clean.  

- **Multi-Agent Pattern**  
  We use three distinct agent roles—Planner, Researcher, Validator—each configurable to a different OpenAI model via flags.

- **Scalability**  
  • Parallel research across categories.  
  • Docker-first design lets you spin up multiple containers if needed.  

- **Maintainability**  
  • Clear separation of concerns.  
  • Single-file modules make whole-file code generation easy.  

- **Performance**  
  • Bloom filter and HTTP HEAD pre-checks avoid waste.  
  • Exponential backoff for rate-limit resilience.  

## 2. Database Management

We don’t use a traditional database. Instead, we manage data with structured JSON files and a directory hierarchy under `runs/<timestamp>/`.

- **Storage Type**  
  • File-based (JSON + Markdown).  
  • All artifacts are versioned by ISO timestamp.

- **Data Flow**  
  1. **original.json** – Parsed input list.  
  2. **plan.json** – Categories and search queries.  
  3. **candidate_*.json** – Raw link suggestions per category.  
  4. **new_links.json** – Filtered, validated new links.  
  5. **updated_list.md** – Final merged README.  

- **Data Practices**  
  • Deduplication with Bloom filter + final pass.  
  • Structured logging (`agent.log`) tracks every event with timestamps, token counts, and cost in USD.  

## 3. Database Schema

Below is a human-readable summary of each JSON file’s structure.

• **original.json**  
  – An array of items. Each item has:  
    • `category` – Name of the section.  
    • `title` – Link text.  
    • `url` – Link URL.  
    • `description` – Brief description.  
    • `stars` (optional) – GitHub star count if available.

• **plan.json**  
  – An array of category objects. Each contains:  
    • `category` – Section name.  
    • `search_query` – Prompt text for the PlannerAgent.

• **candidate_<category>.json**  
  – An array of link suggestions for that category. Each has:  
    • `url`  
    • `description`  
    • `source` – (optional) which tool or search engine.

• **new_links.json**  
  – An array of final new link objects, same fields as above, guaranteed not to overlap with `original.json`.

• **updated_list.md**  
  – A single Markdown string in Awesome-List format.

## 4. API Design and Endpoints

The tool interacts with live APIs only. Key endpoints include:

- **GitHub API**  
  • `GET /repos/:owner/:repo/readme` – Fetch the base64-encoded README.  
  • Fallback to raw URL: `https://raw.githubusercontent.com/:owner/:repo/main/README.md`.

- **OpenAI API**  
  • `POST /v1/chat/completions` – For Planner, Researcher, and Validator agents.  
  • Models are chosen via flags: `--model_planner`, `--model_researcher`, `--model_validator`.

- **HTTP HEAD Checks**  
  • Plain HEAD requests to each candidate URL to ensure it’s live.

- **Retry/Backoff**  
  • All external calls are wrapped in retry logic with exponential backoff to handle rate limits.

## 5. Hosting Solutions

The entire backend runs inside a Docker container based on `python:3.12-slim`.

- **Why Docker?**  
  • Guarantees a consistent environment.  
  • No external host dependencies.  
  • Simplifies local use, CI, or cloud deployment.

- **Container Setup**  
  • Base image: `python:3.12-slim`.  
  • Pre-installed via Dockerfile: Poetry, `awesome-lint`, `openai-agents`, `shellcheck`.  
  • Entrypoint: `main.py` with flag parsing.

## 6. Infrastructure Components

Because this is a CLI tool, infrastructure is light:

- **Docker Container**  
  Provides isolation, repeatability, and easy distribution.

- **Signal Alarm**  
  Python’s `signal.alarm` enforces the `--wall_time` limit.

- **Logging**  
  All events go to `agent.log` in the run folder. Structured JSON lines include timestamp, event name, tokens used, and cost.

- **Artifacts Directory**  
  Everything lives under `runs/<ISO-TS>/` (e.g., `2024-07-15T12:00:00Z`).

- **Rate-Limit Resilience**  
  Exponential backoff on HTTP and OpenAI calls.

## 7. Security Measures

- **API Keys**  
  • `OPENAI_API_KEY` is required as an environment variable.  
  • No GitHub token—only public endpoints are used.

- **Encrypted Transport**  
  • All API calls use HTTPS.

- **Input Validation**  
  • Tool checks that `--repo_url` is a well-formed GitHub URL.  
  • Verifies required flags and env vars at startup.

- **Logging Hygiene**  
  • Sensitive values (like the API key) are not written to logs.

- **Failure Handling**  
  • Fatal errors (like a missing README) abort the run with a clear message.

## 8. Monitoring and Maintenance

- **Structured Logging**  
  Every step, success or failure, is logged with ISO 8601 timestamps, token usage, and cost. This log is the primary source for debugging and cost auditing.

- **End-to-End Test**  
  `tests/run_e2e.sh` must pass without needing pytest or external CI. It verifies a full run, lint checks, and rate-limit handling.

- **Quality Gates**  
  • `awesome-lint` on `updated_list.md`.  
  • `shellcheck` on any shell scripts.  
  • PEP 8 compliance via Poetry hooks or `flake8`.

- **Updates & Maintenance**  
  • Modules are single files—easy to regenerate entirely if interfaces change.  
  • New LLM models or API versions can be plugged in via flags and config.

## 9. Conclusion and Overall Backend Summary

The _Awesome-List Researcher_ backend is a self-contained, Dockerized Python application built for reliability, reproducibility, and cost control.  Its modular design makes it easy to maintain and extend. By using live APIs, structured logging, and clear artifact management, we ensure each run is transparent, auditable, and repeatable.

Key highlights:

- A clear orchestrator pattern with single-purpose modules  
- File-based JSON “database” for simplicity and portability  
- Live GitHub and OpenAI API interactions with built-in rate-limit resilience  
- Docker-only setup for maximum reproducibility  
- Comprehensive logging for cost tracking and debugging

This structure meets the project goals by automating link discovery, validation, and rendering, all within strict time and cost bounds, while keeping the system easy to understand and maintain.