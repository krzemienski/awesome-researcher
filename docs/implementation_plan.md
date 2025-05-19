# Implementation plan

## Phase 1: Environment Setup

1.  **Prevalidation**: Check if current directory is already initialized as a project by verifying the presence of a `Dockerfile`. If found, prompt to confirm you want to reuse this directory. (Project Summary: Key Requirements & Constraints)
2.  Install Docker Engine v20.10 or higher on your machine if not already installed.  
    **Validation**: Run `docker --version` and confirm output starts with `Docker version 20.10` or above. (Project Summary: Key Requirements & Constraints)
3.  Create the project directory structure:  
    -  `/src/`  
    -  `/tests/`  
    -  `/runs/`  
    -  `/scripts/`  
    -  `build-and-run.sh` (executable)  
    -  `Dockerfile`  
    **Validation**: Run `ls -R .` and verify all directories and files exist. (Project Summary: System Architecture & Modules)
4.  Initialize a Git repository and add a `.gitignore` file with entries:  
    ```gitignore
    __pycache__/
    *.pyc
    /runs/
    .env
    ```  
    **Validation**: Run `git status` to ensure `.gitignore` is respected. (Project Summary: Code Quality)
5.  Create a `cursor_metrics.md` file in the project root to track code metrics. Refer to `cursor_project_rules.mdc` for required metrics fields. (Environment Setup Guide for Cursor)
6.  Install **ShellCheck** locally for linting shell scripts.  
    **Validation**: Run `shellcheck --version` and confirm it outputs a version number. (Project Summary: Tools)
7.  Install **Flake8** inside the container via the `Dockerfile` to enforce PEP 8 compliance.  
    **Validation**: Will be validated after container build in Step 10. (Project Summary: Code Quality)

## Phase 2: Docker & CLI Bootstrap

8.  Create `Dockerfile` in project root using base image `python:3.12-slim` with the following content:  
    ```dockerfile
    FROM python:3.12-slim
    WORKDIR /app
    RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*
    COPY pyproject.toml poetry.lock ./
    RUN pip install poetry && poetry config virtualenvs.create false && poetry install --no-root
    COPY . .
    RUN chmod +x build-and-run.sh
    ENTRYPOINT ["./build-and-run.sh"]
    ```  
    **Validation**: Build with `docker build -t awesome-list-researcher .` and confirm success. (Project Summary: Docker-Only)
9.  Create `build-and-run.sh` at project root with executable permission, containing:  
    ```bash
    #!/usr/bin/env bash
    set -euo pipefail
    ISO_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    export RUN_DIR="runs/$ISO_TS"
    mkdir -p "$RUN_DIR"
    python -m src.cli "$@"
    ```  
    **Validation**: Run `./build-and-run.sh --help` and confirm CLI usage is displayed. (Project Summary: CLI/Env Configuration)
10. Add Flake8 and ShellCheck steps to the Dockerfile:  
    -  `RUN pip install flake8 shellcheck`  
    **Validation**: Inside container, run `flake8 src/` and `shellcheck build-and-run.sh` with zero errors. (Project Summary: Code Quality)

## Phase 3: Core Module Development

11.  Create `/src/cli.py` defining the CLI interface using `argparse` with flags:  
    -  `--repo_url` (required)  
    -  `--wall_time`, `--cost_ceiling`, `--min_stars`, `--output_dir`, `--seed`, `--model_planner`, `--model_researcher`, `--model_validator`  
    Include environment variable `OPENAI_API_KEY` check.  
    **Validation**: Run `python -m src.cli --help` and confirm all flags are listed. (Project Summary: CLI/Env Configuration)
12.  Create `/src/awesome_parser.py` with a function `parse_readme(repo_url: str, output_path: Path)` that:  
    -  Uses GitHub REST API unauthenticated endpoints to fetch `README.md`  
    -  Falls back to raw `https://raw.githubusercontent.com/.../master/README.md` on failure  
    -  Parses Markdown into a JSON structure `original.json` per Awesome-List spec  
    -  Writes `original.json` to `runs/<ISO-TS>/original.json`  
    **Validation**: Write `tests/test_awesome_parser.py` to mock a simple repo and run `pytest tests/test_awesome_parser.py`. (Project Summary: System Architecture & Modules)
13.  Create `/src/planner_agent.py` that uses the `openai-agents` SDK to instantiate a `PlannerAgent` with default model `gpt-4.1-mini` (override via `--model_planner`), reads `original.json`, and writes `plan.json`.  
    **Validation**: Add `tests/test_planner_agent.py` to call planning on a minimal `original.json` and assert schema of `plan.json`. (Project Summary: Model Selection Strategy)
14.  Create `/src/research_agent.py` that reads `plan.json`, spawns one `CategoryResearchAgent` per category with default model `o3` (override via `--model_researcher`), uses `SearchTool` and `BrowserTool` to generate `candidate_{category}.json`.  
    **Validation**: Add `tests/test_research_agent.py` to simulate one category and verify output file created. (Project Summary: System Architecture & Modules)
15.  Create `/src/aggregator.py` with function `aggregate(candidates_dir: Path, output_path: Path)` that merges all `candidate_*.json` into a single `new_links.raw.json`.  
    **Validation**: Add `tests/test_aggregator.py` to merge two sample files and verify correct merge. (Project Summary: System Architecture & Modules)
16.  Create `/src/duplicate_filter.py` to compare `new_links.raw.json` against `original.json`, remove duplicates, and output `new_links.json`.  
    **Validation**: Add `tests/test_duplicate_filter.py` with sample overlap and assert only unique items remain. (Project Summary: Deduplication Guarantee)
17.  Create `/src/validator.py` with function `validate_links(input_path: Path, output_path: Path, min_stars: int)` that:  
    -  Performs HTTP HEAD checks with retry/back-off for rate-limit resilience  
    -  Checks GitHub stars via REST API against `min_stars`  
    -  Writes filtered links to `new_links.validated.json`  
    **Validation**: Add `tests/test_validator.py` mocking HTTP 200/404 and GitHub stars to confirm filtering. (Project Summary: Rate-Limit Resilience)
18.  Create `/src/renderer.py` with function `render(original_path: Path, new_links_path: Path, output_path: Path)` that:  
    -  Merges JSONs into `updated_list.md`  
    -  Runs `awesome-lint --fix` in a loop until no errors  
    -  Writes final `updated_list.md` to `runs/<ISO-TS>/updated_list.md`  
    **Validation**: Add `tests/test_renderer.py` with sample JSONs and run `awesome-lint` to verify clean lint. (Project Summary: System Architecture & Modules)

## Phase 4: CLI Integration & Logging

19.  In `/src/cli.py`, orchestrate module calls in order:  
    1.  `parse_readme` → `original.json`  
    2.  `planner_agent` → `plan.json`  
    3.  `research_agent` → `candidate_*.json`  
    4.  `aggregator` → `new_links.raw.json`  
    5.  `duplicate_filter` → `new_links.json`  
    6.  `validator` → `new_links.validated.json`  
    7.  `renderer` → `updated_list.md`  
    8.  Write all logs (ISO 8601 timestamp, event, tokens, cost USD) to `runs/<ISO-TS>/agent.log`.  
    **Validation**: Run `./build-and-run.sh --repo_url https://github.com/some/awesome` and inspect `runs/<ISO-TS>/agent.log` for entries. (Project Summary: Structured Logging)
20.  Create `/tests/run_e2e.sh` to:  
    -  Invoke `docker build`  
    -  Run container with `--repo_url` pointing to a small test repo  
    -  Assert exit code 0 and last line `✅ All good`  
    **Validation**: Run `bash tests/run_e2e.sh` locally and confirm success. (Project Summary: Functional Testing)

## Phase 5: Continuous Integration & Quality Gates

21.  Create `.github/workflows/ci.yml` with:  
    ```yaml
    name: CI
    on: [push, pull_request]
    jobs:
      build-and-test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v3
          - name: Build Docker Image
            run: docker build -t awesome-list-researcher .
          - name: Run E2E Tests
            run: bash tests/run_e2e.sh
    ```  
    **Validation**: Push a branch and confirm GitHub Actions CI passes. (Project Summary: Code Quality)
22.  Enforce PEP 8 in CI by adding a `flake8 src/` step after build.  
    **Validation**: CI should fail on any style violations. (Project Summary: Code Quality)
23.  Enforce ShellCheck on `build-and-run.sh` in CI.  
    **Validation**: CI should fail on any ShellCheck errors. (Project Summary: Code Quality)

## Phase 6: Release & Deployment

24.  Tag the initial release in Git with `v1.0.0`.  
    **Validation**: Run `git tag | grep v1.0.0`. (Project Summary: Deployment)
25.  Publish the Docker image to Docker Hub under `yourusername/awesome-list-researcher:latest`.  
    **Validation**: Run `docker pull yourusername/awesome-list-researcher:latest`. (Project Summary: Deployment)

---
_Total steps: 25_