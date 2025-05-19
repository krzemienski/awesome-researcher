# Architecture

## System Overview

The Awesome-List Researcher is designed as a modular system with distinct components that handle different stages of the research and aggregation process.

```mermaid
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
```

## Core Components

### 1. Markdown Extraction and Parsing

- **Raw Markdown Derivation**: Obtains README.md from GitHub repository
- **awesome_parser.py**: Parses Markdown to structured JSON format with categories and links

### 2. Research Planning

- **planner_agent.py**: Uses the chosen language model to analyze the original list and develop a research plan
- Generates diverse search queries with synonym expansion
- Outputs structured plan.json with research targets for each category

### 3. Parallel Research

- **category_agent.py**: Implements parallel research agents
- Each agent handles specific categories from the plan
- Leverages web search and browser tools for web research
- Produces candidate resources with descriptions and metadata

### 4. Aggregation and Filtering

- **aggregator.py**: Combines results from all research agents
- **duplicate_filter.py**: Removes duplicates using fuzzy matching
- Ensures no overlap with original list resources

### 5. Validation

- **validator.py**: Performs validation checks:
  - HTTP HEAD requests to verify accessibility
  - Description cleanup and formatting
  - URL validation (HTTPS)

### 6. Rendering

- **renderer.py**: Merges new resources into the original list
- Maintains proper formatting and sorting
- Ensures the resulting Markdown passes awesome-lint

### 7. Orchestration

- **main.py**: Coordinates the entire process
- Enforces wall-time and cost constraints
- Handles logging and artifact persistence

## Containerization

The entire system runs in a Docker container with all dependencies pre-installed:

- Python 3.12-slim
- Poetry for dependency management
- awesome-lint for validation
- OpenAI API client

## Cost and Resource Management

- Dynamic cost estimation before each OpenAI API call
- Abort mechanism when approaching cost ceiling
- Wall-time enforcement via signal.alarm
- Retry mechanisms with exponential backoff for API rate limits

## Logging and Observability

- Structured logging with ISO 8601 timestamps
- Detailed tracking of tokens used and cost per operation
- Full prompt and completion logging
- Per-agent logging for debugging and analysis

## Implementation Notes

- Uses web_search and firecrawl_scrape functions to emulate BrowserTool
- Multi-threading with ThreadPoolExecutor for parallel research
- RapidFuzz for name-based fuzzy matching
- Mistletoe for Markdown AST parsing
- Tenacity for retry mechanisms
