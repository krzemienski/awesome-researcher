flowchart TD
    A[--repo_url] --> B[Derive RAW README]
    B --> C[awesome_parser.py → original.json]
    C --> D[PlannerAgent model_planner]
    D --> E[plan.json]
    E --> F[CategoryResearchAgents xN model_researcher]
    F --> G[Aggregator]
    G --> H[DuplicateFilter]
    H --> I[Validator model_validator]
    I --> J[new_links.json]
    J & C --> K[renderer.py → updated_list.md]
    K --> L[awesome-lint check]
    L --> M[Persist artifacts]