# Task Prompt · Build a Docker‑First **“Awesome‑List Researcher”** (Consolidated Spec v4)

> **Mission** — Produce a **production‑ready** tool that, given the **GitHub URL** of any Awesome‑style repository, fetches the **raw** `README.md` (without using the GitHub API), parses it into JSON, and launches a **multi‑agent OpenAI workflow** to find **new, not‑yet‑listed resources**. All candidates are deduplicated, validated, and merged into Markdown that passes `awesome‑lint`. Everything (build → run → test) is executed **only** through `./build-and-run.sh` **inside Docker**. No host Python, no external CI, **no GitHub API**. Logs must capture every logical step **plus** the full prompts and responses exchanged with external APIs. Wall‑time and cost ceilings guarantee predictable runtime and spend.

---

## 1 · Reference Knowledge

### 1.1 Awesome‑List Spec — essentials

* `# Awesome <Topic>` heading + one‑sentence tagline
* Optional badge row immediately after title
* Table of Contents if list > 40 items
* Only `##` (primary) and `###` (sub) headings
* Item format `* [Name](URL) – description` (≤ 100 chars, sentence case, no period)
* Alphabetical order (ignore *A / An / The*)
* Links **must** be HTTPS and return **200 OK ≤ 3 s**
* Mandatory **Contributing** section
* Must pass `awesome‑lint` before **and** after regeneration

### 1.2 OpenAI Agents SDK insights (from `examples/research_bot`)

* Abstractions `Agent`, `SearchTool`, `BrowserTool` (for live browsing)
* Parallel execution via `Parallel([...])`
* Callbacks `on_tool_start/finish` → granular streaming logs
* Cost measured by `usage.total_cost_usd`

### 1.3 Raw Markdown derivation (no GitHub API)

1. Try, in order, and use first **200 OK** URL:
   `https://raw.githubusercontent.com/<owner>/<repo>/refs/heads/master/README.md`
   `https://raw.githubusercontent.com/<owner>/<repo>/refs/heads/main/README.md`
   `https://raw.githubusercontent.com/<owner>/<repo>/HEAD/README.md`
2. Abort with clear error if all three fail.

---

## 2 · Non‑Negotiable Constraints

|  #   |  Rule                                                                                                                                                                                                                                                                                                                                                                                               |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|  1   |  **Docker‑only** – Image from `Dockerfile` (Python 3.12‑slim + Poetry + `awesome‑lint` + `openai‑agents`).                                                                                                                                                                                                                                                                                          |
|  2   |  **Live network** – No mocks / placeholders.                                                                                                                                                                                                                                                                                                                                                        |
|  3   |  **ISO 8601 logs** – agent id, event, latency, tokens, **USD cost**, *full prompt & completion text*.                                                                                                                                                                                                                                                                                               |
|  4   |  **CLI flags & env‑vars**  <br>• `--repo_url` (required)  <br>• `--wall_time` (s, default 600)  <br>• `--cost_ceiling` (USD, default 10)  <br>• `--output_dir` (default `runs/`)  <br>• `--seed` (int; omit→random)  <br>• `--model_planner` (default **gpt‑4.1**)  <br>• `--model_researcher` (default **o3**)  <br>• `--model_validator` (default **o3**)  <br>• Env `OPENAI_API_KEY` (required)  |
|  5   |  Outputs go to `runs/<ISO‑TIMESTAMP>/` (see § 7.2).                                                                                                                                                                                                                                                                                                                                                 |
|  6   |  Functional test = `tests/run_e2e.sh` (shell only).                                                                                                                                                                                                                                                                                                                                                 |
|  7   |  PEP 8, minimal comments, **whole‑file** codegen.                                                                                                                                                                                                                                                                                                                                                   |
|  8   |  Dedup guarantee – `new_links.json` ∩ `original.json` = ∅.                                                                                                                                                                                                                                                                                                                                          |
|  9   |  Retry/back‑off on HTTP 429/503.                                                                                                                                                                                                                                                                                                                                                                    |
|  10  |  **Cost guard only** – Stop when projected spend ≥ `--cost_ceiling`; tokens otherwise unrestricted.                                                                                                                                                                                                                                                                                                 |

---

## 3 · Model‑Selection Strategy

|  Agent                  |  Default Model  |  Rationale                                                |  Override Flag         |
| ----------------------- | --------------- | --------------------------------------------------------- | ---------------------- |
|  PlannerAgent           |  `gpt‑4.1`      | Deeper reasoning to craft high‑quality query permutations |  `--model_planner`     |
|  CategoryResearchAgent  |  `o3`           | Large volume of inexpensive web‑search prompts            |  `--model_researcher`  |
|  Validator              |  `o3`           | Lightweight description cleanup                           |  `--model_validator`   |

---

## 4 · System Architecture

```mermaid
flowchart TD
    A[--repo_url] --> B[Derive RAW README]
    B --> C[awesome_parser.py → original.json]
    C --> D[PlannerAgent (gpt-4.1)]
    D --> E[plan.json]
    E --> F[CategoryResearchAgents × N (o3 + BrowserTool)]
    F --> G[Aggregator]
    G --> H[DuplicateFilter]
    H --> I[Validator (o3)]
    I --> J[new_links.json]
    J & C --> K[renderer.py → updated_list.md]
    K --> L[awesome-lint ✓]
    L --> M[Persist logs & artifacts]
```

---

## 5 · Module Highlights

**awesome\_parser.py** – Fetch raw README; parse AST → JSON + Bloom filter; abort if baseline lint fails.
**planner\_agent.py** – Uses `gpt‑4.1`; builds synonym‑rich queries per category; cost guard each call; optional seed randomisation.
**category\_agent.py** – Uses `o3`; **must** employ `BrowserTool`; stores `candidate_<cat>.json`.
**aggregator / duplicate\_filter** – Merge, canonicalise, dedup; abort if > 30 % duplicates.
**validator.py** – HTTP HEAD ≤ 3 s + optional description trim (`o3`); **no GitHub‑stars logic**.
**renderer.py** – Inject new links alphabetically; rebuild ToC; insert Contributing; auto‑fix lint until green.
**main.py** – Orchestrator; wall‑time guard with `signal.alarm`.

---

## 6 · Cost Guard (pseudocode)

```python
est = price_per_1k_tokens(model) * expected_tokens / 1000
if usage.total_cost_usd + est >= cost_ceiling:
    logger.warning("Cost ceiling hit – halting further calls")
    break
```

---

## 7 · Deliverables

### 7.1 Repository Assets

* `Dockerfile`, `build-and-run.sh`, core modules
* **README.md** = complete user guide (includes model override examples)
* `architecture.md` (with Mermaid diagram)
* `CONTRIBUTING_TEMPLATE.md`
* `tests/run_e2e.sh`
* `.gitignore`

### 7.2 Runtime Artifacts (git‑ignored)

* `original.json`, `plan.json`, `candidate_*.json`, `new_links.json`, `updated_list.md`, `agent.log`, `research_report.md`

*(No sample output directory should be committed.)*

---

## 8 · Cursor Workflow (MCP rules — summary)

* Load **Context 7** + `ContextStore`, `FileGraph`, `DependencyGraph` at *every* task start.
* Branch per feature; squash merge after tests pass; include `cursor.task:` notes.
* Execute only inside container; never call host Python.
* Logs must include full prompt & response payloads.

---

## 9 · Acceptance Test

```bash
./build-and-run.sh \
  --repo_url https://github.com/vinta/awesome-python \
  --wall_time 600 \
  --cost_ceiling 10 \
  --model_planner gpt-4.1 \
  --model_researcher o3
```

*Pass when:*

1. Completes within limits
2. Adds ≥ 1 new link
3. `awesome-lint` green
4. Logs every API call with prompt & response

---

### Begin Implementation 🚀
