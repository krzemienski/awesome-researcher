# Frontend Guideline Document

This document describes the “frontend” of the **Awesome-List Researcher** tool, which in our case is a command-line interface (CLI). Even though there’s no graphical UI, it still has an architecture, design principles, styling, and interaction patterns that we treat like a frontend. Anyone reading this will understand how users interact with the tool and how the CLI is organized.

## 1. Frontend Architecture

### Overview
- The “frontend” is a Python-based CLI built with:
  - **Python 3.12-slim** as the runtime (inside Docker).
  - **Poetry** for dependency and environment management.
  - **Argparse** (or similar) to parse command flags and environment variables.
- All user interactions happen via flags (`--repo_url`, `--wall_time`, etc.) and log/output files in `runs/<ISO-TS>/`.

### How It Supports Scalability, Maintainability, Performance
- **Modular Code**: Each step (parsing, planning, research, validation, rendering) lives in its own Python module. This makes it easy to extend or swap out a component.
- **Docker-First**: By running completely inside Docker, we guarantee the same environment everywhere—no “it works on my machine” issues.
- **Whole-File CodeGen**: Generates entire modules in one go, reducing merge conflicts and simplifying code reviews.
- **Parallel Research Agents**: Spawns multiple processes (one per category) so that research scales with CPU availability.
- **Structured Logging**: A single `agent.log` collects timestamped events, token counts, and cost. This keeps performance overhead low and debugging straightforward.

## 2. Design Principles

### Usability
- **Clear Flags**: Flags are self-documenting (`--repo_url`, `--cost_ceiling`, etc.). A `--help` message lists all options and defaults.
- **Meaningful Defaults**: Sensible defaults (e.g., 600s wall time, $5 cost ceiling, 100 stars) let users run without extra configuration.
- **Informative Errors**: If required inputs are missing or invalid, the CLI prints a clear error and exits with a nonzero status.

### Accessibility
- **Minimal Dependencies**: No GUI libraries—users on headless servers can run the tool.
- **ANSI-Free Logs**: Logs are plain text (no color codes) so they’re readable in any terminal or forwarded to log aggregators.

### Responsiveness
- **Signal-Based Timeouts**: Uses `signal.alarm` to enforce wall-time limits, so the tool halts promptly when time runs out.
- **Cost Guard**: Checks estimated cost before each API call to halt before overspending.

## 3. Styling and Theming

Since this is a command-line tool, visual styling is minimal. We adopt a **flat text** style:

- **Font**: Whatever the user’s terminal uses.
- **Colors**: No colors in logs to maximize compatibility. If colored output were added (e.g., warnings in yellow), it would be optional and controlled by a `--color` flag.
- **Formatting**: Indentation is two spaces for human-readable logs. JSON outputs (`original.json`, `new_links.json`) use 2-space indentation.

## 4. Component Structure

```
awesome-list-researcher/       # Root of project
├── Dockerfile                # Builds python:3.12-slim + dependencies
├── build-and-run.sh          # Wrapper script to build Docker and run the CLI
├── main.py                   # Entry point, orchestrates workflow
├── awesome_parser.py         # Parses README.md → original.json
├── planner_agent.py          # Crafts search queries → plan.json
├── category_agent.py         # Runs research per category → candidate_*.json
├── aggregator.py             # Merges candidate files
├── duplicate_filter.py       # Filters out original links
├── validator.py              # Validates new links → new_links.json
├── renderer.py               # Renders updated_list.md + runs awesome-lint
├── tests/                    # Contains run_e2e.sh
└── runs/                     # Default output directory
```

### Reusability and Maintainability
- Each module has a clear responsibility and a simple function or class interface.
- Shared utilities (e.g., cost estimation, back-off logic, logging setup) live in a common utils file or can be extracted as needed.
- Adding a new step involves creating a new module and updating `main.py` orchestration.

## 5. State Management

- The CLI’s “state” is passed explicitly between steps via JSON files in the run folder (`original.json`, `plan.json`, `new_links.json`, etc.).
- Configuration flags and environment variables are parsed once in `main.py` and passed to each module as arguments.
- No in-memory global state beyond the runtime of `main.py`—this makes restarts and debugging easier.

## 6. Routing and Navigation

- **Argument Parsing**: `main.py` uses Argparse to read:
  - `--repo_url` (required)
  - `--wall_time`, `--cost_ceiling`, `--min_stars`, `--output_dir`, `--seed`, `--model_planner`, `--model_researcher`, `--model_validator`
  - `OPENAI_API_KEY` from environment.
- **Workflow Flow**: Inside `main.py`, steps are invoked in order: README fetch → parse → plan → research → aggregate → dedupe → validate → render.
- **Error Handling**: If any step fails (HTTP error, lint error, cost limit reached), the CLI logs the failure and exits.

## 7. Performance Optimization

- **Lazy Loading**: Modules and heavy libraries (e.g., OpenAI client) are imported only when needed.
- **Parallel Research Agents**: Uses Python’s `concurrent.futures.ProcessPoolExecutor` or `multiprocessing` to run category searches concurrently.
- **Back-off & Retry**: HTTP and OpenAI calls implement exponential back-off on rate limits to avoid interruptions.
- **Asset Optimization**: Output files are plain JSON/Markdown—no binary assets to bloat the container.

## 8. Testing and Quality Assurance

- **End-to-End Test**: A single shell script (`tests/run_e2e.sh`) runs the built Docker image against a known repo and checks for:
  - Completion within limits.
  - At least one new link added.
  - `awesome-lint` passes.
  - Output “✅ All good” on success.
- **Linting**:
  - `shellcheck` for all shell scripts.
  - `awesome-lint` for final Markdown.
- **Code Style**: Enforced PEP 8 via `flake8` or `black` (as configured in Poetry).
- **Logging Verification**: Tests ensure that `agent.log` contains ISO 8601 timestamps, event names, token counts, and cost breakdowns.

## 9. Conclusion and Overall Frontend Summary

The CLI “frontend” of **Awesome-List Researcher** is designed for clarity, reliability, and reproducibility. By using a modular architecture, clear design principles, and minimal styling, we ensure anyone can:

- Understand how to invoke the tool and configure its behavior.
- Trace each step of the workflow via structured logs.
- Extend or maintain the code without grappling with hidden state or magic.

Unique aspects: 100% Docker portability, a cost-guard built into the CLI, and a single E2E shell test that acts as both documentation and a quality gate. This makes the tool robust in diverse environments—from local dev machines to CI systems—without additional setup or GUI dependencies.