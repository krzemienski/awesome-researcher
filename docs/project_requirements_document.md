# Project Requirements Document (PRD)

## 1. Project Overview

Awesome-List Researcher is a Docker-first command-line tool that automates the discovery and integration of new links into any “awesome-style” GitHub repository. A user points it at a repository URL, and inside a self-contained Docker container the tool fetches the repo’s `README.md`, parses it to JSON, and then runs a multi-agent OpenAI workflow. Agents plan search queries, fetch candidate resources in parallel, deduplicate against the original list, validate HTTP status and star counts, and finally render an updated Markdown file that passes **awesome-lint** without any host dependencies or external CI.

We’re building this to eliminate manual curation and ensure each update is consistent, repeatable, and cost-controlled. Key success criteria are:

*   **Production-ready**: All steps run inside Docker via `./build-and-run.sh`.
*   **Quality**: Final Markdown passes awesome-lint with no custom templates.
*   **Cost & Time Guards**: Enforce user-configurable wall-time and cost ceilings.
*   **Traceability**: Structured logging (ISO 8601 timestamps, tokens, cost) in a single `agent.log`.
*   **Deduplication Guarantee**: New links never overlap with the original list.

## 2. In-Scope vs. Out-of-Scope

### In-Scope

*   Docker build (`Dockerfile`) and run script (`build-and-run.sh`).
*   CLI flags & environment variables: `--repo_url` (required), `--wall_time`, `--cost_ceiling`, `--min_stars`, `--output_dir`, `--seed`, `--model_planner`, `--model_researcher`, `--model_validator`, plus `OPENAI_API_KEY`.
*   Fetch default branch via GitHub REST API and fallback to `/HEAD/README.md`.
*   Parse `README.md` into `original.json` enforcing Awesome-List spec (headings, alphabetical order, HTTPS URLs, description length).
*   PlannerAgent to generate `plan.json` using `gpt-4.1-mini` (or override).
*   Parallel CategoryResearchAgents to produce `candidate_<category>.json` using `o3` (or override).
*   Aggregator + DuplicateFilter ⇒ `new_links.json` with zero overlap.
*   Validator performing HTTP HEAD checks (200 OK) and star-count threshold.
*   Renderer merging JSONs into `updated_list.md`, loops awesome-lint until green.
*   Structured logging in `runs/<ISO-TS>/agent.log`.
*   E2E test script `tests/run_e2e.sh` that prints “✅ All good” on success.
*   Artifacts under `runs/<ISO-TS>/`: JSONs, Markdown, log, `research_report.md`.

### Out-of-Scope

*   Writing back to GitHub or creating PRs.
*   Advanced license validation (beyond existence checks).
*   Support for multiple repos in one run.
*   Graphical user interface or web dashboards.
*   CI/CD integration outside of Docker.
*   Custom headers/footers beyond Awesome-List spec.
*   GitHub authentication tokens (beyond public API).

## 3. User Flow

A developer clones the repo, ensures Docker is installed, and exports their `OPENAI_API_KEY`. They run:

`./build-and-run.sh \ --repo_url https://github.com/owner/awesome-repo \ --wall_time 600 \ --cost_ceiling 5.00 \ --min_stars 100 \ --model_planner gpt-4.1-mini \ --model_researcher o3 \ --model_validator o3`

Docker builds a Python 3.12-slim image with Poetry, awesome-lint, and openai-agents, then starts the container. From the moment it launches, every action is logged to `runs/2024-07-15T12:00:00Z/agent.log` with ISO 8601 timestamps, agent names, token usage, and cost in USD.

Inside the container, `main.py` orchestrates the workflow:

1.  Fetch `README.md` → parse to `original.json`.
2.  PlannerAgent → `plan.json`.
3.  Spawn one CategoryResearchAgent per category → parallel `candidate_*.json`.
4.  Aggregator + DuplicateFilter → `new_links.json`.
5.  Validator → filter by HTTP 200 and stars.
6.  Renderer → `updated_list.md`, run awesome-lint until no errors.
7.  Persist all artifacts under the run’s timestamped folder.

When complete, the user inspects `runs/<ISO-TS>/`: JSON files, `updated_list.md`, `agent.log`, and `research_report.md`. Running `tests/run_e2e.sh` inside the container confirms “✅ All good.”

## 4. Core Features

*   **Docker-Only Execution**: Single-container runtime; no host Python or CI dependencies.
*   **CLI & Env-Var Configuration**: Flexible flags for cost, time, model overrides.
*   **README Ingestion & Parsing**: GitHub API fetch + fallback; spec-compliant JSON via `awesome_parser.py`.
*   **PlannerAgent**: LLM-driven query generation (`plan.json`).
*   **Parallel Research Agents**: One per category using SearchTool/BrowserTool → `candidate_*.json`.
*   **Aggregation & Deduplication**: Merge candidates and enforce zero overlap with original.
*   **Validation**: HTTP HEAD status, star threshold, description cleanup via validator model.
*   **Rendering & Linting**: Final Markdown with awesome-lint loop until clean.
*   **Cost & Time Guards**: Runtime estimation halts on ceiling breach; `signal.alarm` for wall-time.
*   **Structured Logging**: Unified `agent.log` with ISO 8601 timestamps, events, tokens, cost.
*   **End-to-End Testing**: Shell script for full workflow without mocks.

## 5. Tech Stack & Tools

*   **Container & Language**

    *   Docker (build + run)
    *   Python 3.12-slim
    *   Poetry (dependency management)

*   **AI & Agents**

    *   OpenAI Agents SDK (`openai-agents`)
    *   Default models: `gpt-4.1-mini` (planner), `o3` (researcher), `o3` (validator)

*   **Parsing & Linting**

    *   `awesome-lint` (Markdown linting for awesome lists)
    *   Custom `awesome_parser.py`, `renderer.py`

*   **APIs & Networking**

    *   GitHub REST API (default branch lookup)
    *   HTTP HEAD for link validation

*   **Shell + Scripts**

    *   Bash (`build-and-run.sh`, `tests/run_e2e.sh`)
    *   ShellCheck (linting shell scripts)

*   **IDE / Extensions (for dev experience)**

    *   VS Code with Cursor & Aider extensions
    *   Windsurf or Bolt for AI-powered scaffolding & real-time code suggestions

## 6. Non-Functional Requirements

*   **Performance**

    *   Total runtime ≤ user’s `--wall_time` (default 600 s).
    *   Parallel research to maximize throughput.

*   **Reliability & Resilience**

    *   Retry + exponential back-off on network or rate-limit errors.
    *   Abort on critical failures (e.g., missing README).

*   **Security & Compliance**

    *   Secrets only via `OPENAI_API_KEY` env var.
    *   No GitHub tokens; read-only public API.
    *   Adhere to Awesome-List spec for Markdown.

*   **Usability & Observability**

    *   Single CLI command entry point.
    *   Clear structured logs in `agent.log`.
    *   Artifacts organized by ISO 8601 timestamped directories.

*   **Maintainability**

    *   PEP 8 compliance; whole-file codegen.
    *   Modular Python scripts (parser, agents, aggregator, etc.).

## 7. Constraints & Assumptions

*   **Docker-Only**: All steps must run inside the container; no host installs.
*   **OpenAI Availability**: Requires internet access and a valid `OPENAI_API_KEY`.
*   **GitHub Rate Limits**: Public API only; assume occasional 403 responses—retry logic in place.
*   **Pricing**: Cost estimates use OpenAI’s published rates at runtime.
*   **No GitHub Auth Token**: Only unauthenticated endpoints.
*   **Timestamp Format**: ISO 8601 `YYYY-MM-DDTHH:MM:SSZ`.
*   **Parallel Tasks**: One ResearchAgent per category in `plan.json`; no hard cap.

## 8. Known Issues & Potential Pitfalls

*   **GitHub API Limits**

    *   Public API may hit 60 req/hr. Mitigation: exponential back-off, abort if persistent.

*   **Network Failures**

    *   Docker container relies on network; add retry/back-off for fetch and HEAD checks.

*   **Cost Overruns**

    *   Estimation may be imperfect. The tool stops further LLM calls once the ceiling is predicted to be exceeded, but in-flight calls might slightly overshoot.

*   **README Format Variations**

    *   Unusual Markdown (e.g., nonstandard headings) may break parser. Recommendation: clear error messages and abort.

*   **Parallel Overhead**

    *   Spawning too many agents may exhaust container resources; monitor memory usage and consider a soft cap if stability issues arise.

*This document is the single source of truth for all subsequent technical specs, code structures, and implementation guidelines.*
