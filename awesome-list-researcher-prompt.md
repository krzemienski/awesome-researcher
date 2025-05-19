Task Prompt • Build a Docker‑First “Awesome‑List Researcher”  (Full Aggregate Spec v2)

Mission  — Create a production‑ready tool that ingests the GitHub URL of any Awesome‑style repository, derives its raw README.md, parses it to JSON, and launches a multi‑agent OpenAI workflow to discover new, non‑duplicate, spec‑compliant resources.  All artifacts are merged into Markdown that passes awesome‑lint.  Everything runs inside Docker via ./build-and-run.sh; no host Python or external CI.  The system enforces wall‑time and cost ceilings, logs every action, and offers configurable OpenAI model selection for each agent role.

⸻

1 • Reference Knowledge

1.1 Awesome‑List Spec (key rules)
	•	Title + tagline; optional badge row.
	•	Only ## and ### headings; items * [Name](URL) – description ≤ 100 chars.
	•	Alphabetical, HTTPS + 200 OK, mandatory Contributing.
	•	awesome‑lint must pass.

1.2 OpenAI Agents SDK Research‑Bot Insights
	•	ResearchBot, SearchTool, BrowserTool, Parallel([...]) for concurrency.
	•	Cost guard via usage.total_cost_usd.
	•	Callback hooks on_tool_start/finish for granular logs.

1.3 Raw Markdown Derivation
example - https://raw.githubusercontent.com/krzemienski/awesome-video/refs/heads/master/README.md
	2.	Build: https://raw.githubusercontent.com/{owner}/{reponame}/refs/heads/{main or master}/README.md
	3.	Fallback /HEAD/README.md if API fails.

⸻

2 • Non‑Negotiable Constraints

#	Rule
1	Docker‑only – Image from Dockerfile (python 3.12‑slim + Poetry + awesome‑lint + openai‑agents).
2	Live operations – No mocks or placeholders.
3	Structured logging – ISO 8601 timestamps, event, tokens, cost USD.
4	CLI flags / env vars
  	--repo_url (required)
  	--wall_time (s, default 600)
  	--cost_ceiling (USD, default 5.00)
  	--min_stars (GitHub, default 100)
  	--output_dir (default runs/)
  	--seed (int; omit → random)
  	--model_planner (default gpt‑4.1‑mini)
  	--model_researcher (default o3)
  	--model_validator (default o3)
  	Env OPENAI_API_KEY (required)
5	Outputs under runs/<ISO‑TS>/ (see §7.2).
6	Functional test – tests/run_e2e.sh; no pytest/CI.
7	PEP 8 & whole‑file codegen.
8	Dedup guarantee – new_links.json ∩ original.json = ∅.
9	Rate‑limit resilience – retry/back‑off.
10	Cost ceiling only – No token caps; terminate when predicted spend ≥ ceiling.


⸻

3 • Model‑Selection Strategy

Agent Role	Default Model	Rationale	Override Flag
PlannerAgent	gpt‑4.1‑mini	Requires deeper reasoning to craft high‑quality, diverse search queries; accuracy prioritized.	--model_planner
CategoryResearchAgent (parallel)	o3	Large volume of lightweight web‑search prompts; lower latency & cost are ideal.	--model_researcher
Validator (optional LLM description cleanup)	o3	Simple transformations (description trimming); inexpensive.	--model_validator

If a flag is provided, all instances of that agent will use the specified model parameter in openai.chat.completions.

⸻

4 • Cost Guard Logic

est_cost = price_per_1k_tokens(model) * expected_tokens / 1000
if usage.total_cost_usd + est_cost > cost_ceiling:
    logger.warning("Cost ceiling reached – halting further calls.")
    break


⸻

5 • System Architecture

flowchart TD
    A[--repo_url] --> B[Derive RAW README]
    B --> C[awesome_parser.py → original.json]
    C --> D[PlannerAgent (model_planner)]
    D --> E[plan.json]
    E --> F[CategoryResearchAgents×N (model_researcher)]
    F --> G[Aggregator]
    G --> H[DuplicateFilter]
    H --> I[Validator (model_validator)]
    I --> J[new_links.json]
    J & C --> K[renderer.py → updated_list.md]
    K --> L[awesome-lint ✓] --> M[Persist artifacts]


⸻

6 • Module Details
	•	awesome_parser.py – parse Markdown ➜ JSON; Bloom filter.
	•	planner_agent.py – uses selected model; synonym expansion + random shuffle (seeded).
	•	category_agent.py – parallel; leverages SearchTool/BrowserTool.
	•	aggregator.py / duplicate_filter.py – merge + dedup ratio guard.
	•	validator.py – HTTP HEAD, GitHub stars, SPDX license, description cleanup via chosen model.
	•	renderer.py – merge, lint‑fix loop.
	•	main.py – orchestrator; wall‑time via signal.alarm.

⸻

7 • Cursor Workflow (MCP)
	•	Load Context 7 via MCP at start of each automated task; utilise MCP utilities (FileGraph, DependencyGraph).
	•	Branch per feature; squash merge; tag next steps with cursor.task:.
	•	All commands executed via container entrypoint.

⸻

8 • Deliverables

8.1 Repository Assets
	•	Dockerfile, build-and-run.sh, core modules, README.md (user guide + model flag docs), architecture.md, CONTRIBUTING_TEMPLATE.md, tests/run_e2e.sh, .gitignore.

8.2 Runtime Artifacts
	•	original.json, plan.json, candidate_*.json, new_links.json, updated_list.md, agent.log, research_report.md.
	•	Example run directory under examples/sample_run/ (uncompressed).

8.3 Quality Gates
	•	awesome-lint green; shellcheck clean; test script prints “✅ All good”.
	•	Cost ≤ --cost_ceiling; wall‑time enforced.

⸻

9 • Acceptance Criteria

Running

./build-and-run.sh --repo_url https://github.com/sindresorhus/awesome-nodejs \
  --wall_time 600 --cost_ceiling 10.00 --min_stars 200 \
  --model_planner gpt-4o --model_researcher o3 --model_validator o3

	•	Completes within limits, adds ≥ 1 new link, passes awesome‑lint.
	•	Subsequent rerun yields no duplicates.
	•	agent.log shows model names, tokens, and cost per call.

⸻

Begin Implementation 🚀