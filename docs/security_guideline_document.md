# Step-by-Step Implementation Plan for Awesome-List Researcher

This plan is organized by milestones, each with security, reliability, and maintainability considerations baked in.

## 1. Project Scaffolding & Repository Setup

- Initialize Git repository with a clear branch structure (main, develop).
- Add a `.gitignore` for Python, Docker, and IDE artifacts.
- Create the following top-level directories:
  - `src/` (Python modules)
  - `tests/` (end-to-end scripts)
  - `examples/` (sample run output)
  - `scripts/` (helper shell scripts)
  - `runs/` (output artifacts, ignored in VCS)
- Add a `README.md` with build/run instructions and project overview.
- Security & Hygiene:
  - Enable branch protection on `main` (no direct pushes).
  - Require PR reviews for all changes.
  - Enforce a lockfile (`poetry.lock`) in version control.

## 2. Docker & Build-and-Run Script

- Create `Dockerfile` based on `python:3.12-slim`:
  - Install Poetry, `awesome-lint`, `openai-agents`.
  - Create a non-root user (e.g., `appuser`), set as default.
  - Use `COPY --chown=appuser:appuser` for source files.
  - Lock permissions: `chmod 400` on any secrets entrypoint.
- Implement `build-and-run.sh`:
  - Build image with a fixed tag (`awesome-researcher:latest`).
  - Run container with minimal privileges (`--cap-drop=ALL`, `--security-opt=no-new-privileges`).
  - Pass CLI flags and environment variables (`OPENAI_API_KEY`) into container.
  - Trap `SIGALRM` for wall-time enforcement.

## 3. Configuration & Secrets Management

- Use `argparse` in a top-level script (`main.py`) to parse flags:
  - `--repo_url`, `--wall_time`, `--cost_ceiling`, `--min_stars`, `--output_dir`, `--seed`, model overrides.
  - Validate inputs (e.g., URL regex, positive numeric values).
- Pull `OPENAI_API_KEY` from environment and fail fast if missing.
- Implement secure defaults for any optional setting.
- Consider supporting a secrets manager interface for future integration.

## 4. Structured Logging Infrastructure

- Add a `logger.py` module that:
  - Emits JSON logs with ISO 8601 timestamps, event names, token counts, cost USD.
  - Provides hooks: `on_tool_start`, `on_tool_finish`.
  - Writes to `runs/<ISO-TS>/agent.log` with file locking.
- Ensure logs do not leak PII, API keys, stack traces.
- Set log-level via CLI flag (default `INFO`).

## 5. README Fetcher & Parser

### 5.1 GitHub README Retrieval (`fetcher.py`)
- Use GitHub REST API to discover default branch.
- Fallback to `HEAD` if API fails, with exponential backoff and retry limit.
- Sanitize `repo_url` to prevent SSRF or path traversal.
- Abort with a sanitized error message if both attempts fail.

### 5.2 Awesome-List Parser (`awesome_parser.py`)
- Parse `README.md` into a structured JSON:
  - Validate headings structure.
  - Enforce alphabetical order per category.
  - Ensure URLs are HTTPS and descriptions ≤ 100 chars.
  - Schema-validate output against a JSON Schema.
- Reject or sanitize invalid entries.

## 6. Agentic Discovery Workflow

### 6.1 PlannerAgent
- Implement a wrapper around `openai-agents`:
  - Uses `--model_planner` (default `gpt-4.o`).
  - Generates `plan.json` of search queries per category.
- Track token usage and cost; log via `logger.py`.
- Abort if predicted cost pushes above `--cost_ceiling`.

### 6.2 Parallel CategoryResearchAgents
- For each category in `plan.json`:
  - Spawn an asynchronous task (e.g., `asyncio` or `concurrent.futures`).
  - Use `SearchTool` and `BrowserTool` from `openai-agents`.
  - Save raw results to `candidate_<category>.json`.
- Respect rate limits with retry/back-off.
- Aggregate token counts and predicted cost.

## 7. Aggregation & Deduplication

- `aggregator.py`:
  - Merge all `candidate_*.json` into a single candidate list.
  - Schema-validate candidate objects.
- `duplicate_filter.py`:
  - Load `original.json` URLs into a set.
  - Filter out any overlap, guaranteeing `new_links.json ∩ original.json = ∅`.
  - Log counts before/after filtering.

## 8. Validation & Cleanup

- `validator.py`:
  - Perform HTTP `HEAD` requests (with timeouts, retry) to ensure links return 200.
  - Trim or enrich descriptions via `--model_validator`.
  - Sanitize outputs.
- Fail securely on network or service errors; continue with best-effort.

## 9. Rendering & Linting

- `renderer.py`:
  - Merge `original.json` + `new_links.json` into `updated_list.md`.
  - Loop: run `awesome-lint`, parse errors, auto-fix where possible, until clean.
  - Abort if unfixable lint failures after N attempts.
- Use `subprocess.run` with timeouts; sanitize shell arguments.

## 10. Cost & Wall-Time Enforcement

- Integrate a global cost tracker:
  - Before each OpenAI call, predict incremental cost and compare to `--cost_ceiling`.
  - If exceeding, abort with a user-friendly message.
- Use `signal.alarm(wall_time)` to enforce max runtime.
  - Catch `SIGALRM` and exit cleanly (still writing logs).

## 11. Directory Management & Artifacts

- On start, compute `ISO_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")`.
- Create `runs/$ISO_TS/` with restrictive permissions (`700`).
- Write all artifacts there:
  - `original.json`, `plan.json`, `candidate_*.json`, `new_links.json`, `updated_list.md`, `agent.log`, `research_report.md`.
- Populate `examples/sample_run/` with a committed sample.

## 12. End-to-End Testing

- Write `tests/run_e2e.sh` that:
  - Builds the Docker image.
  - Invokes `./build-and-run.sh` with a known small repo (e.g., test fixture).
  - Verifies:
    - Exit code is zero.
    - At least one new link added.
    - `awesome-lint` passes.
    - No duplicates on a second run.
  - Prints `✅ All good` on success.
- Run ShellCheck on all scripts.

## 13. Dependency & CI/CD Hygiene

- Pin direct dependencies in `pyproject.toml` and lock with `poetry.lock`.
- Integrate Dependabot or SCA scanning (optional placeholder).
- Add a GitHub Actions workflow that: lint checks Dockerfile, ShellCheck, Python formatting (Black), and runs `tests/run_e2e.sh` inside the container on PRs.

## 14. Documentation & Maintenance

- Update `README.md` with:
  - Full CLI reference.
  - Security considerations.
  - Contribution guidelines.
- Provide a `CONTRIBUTING.md` describing the design, module layout, and security policies.

---

By following this plan, we ensure the Awesome-List Researcher is robust, secure by design, and ready for production usage entirely within Docker.