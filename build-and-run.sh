#!/bin/bash
set -e

# Load environment variables from .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo "Loaded environment variables from .env file"
fi

# Determine if we're running inside Docker
if [ -f /.dockerenv ]; then
    INSIDE_DOCKER=true
else
    INSIDE_DOCKER=false
fi

# Set default values
REPO_URL=""
WALL_TIME=600
COST_CEILING=10
OUTPUT_DIR="runs"
SEED=""
MODEL_PLANNER="gpt-4.1"
MODEL_RESEARCHER="gpt-4o"
MODEL_VALIDATOR="gpt-4o"
CONTENTS_FILE=""
MIN_RESULTS=10
GLOBAL_TIMEOUT=""
GEN_AWESOME_LIST=false
UPDATE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --repo_url)
            REPO_URL="$2"
            shift 2
            ;;
        --wall_time | --time-limit)
            WALL_TIME="$2"
            shift 2
            ;;
        --cost_ceiling)
            COST_CEILING="$2"
            shift 2
            ;;
        --output_dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --seed)
            SEED="$2"
            shift 2
            ;;
        --model_planner)
            MODEL_PLANNER="$2"
            shift 2
            ;;
        --model_researcher)
            MODEL_RESEARCHER="$2"
            shift 2
            ;;
        --model_validator)
            MODEL_VALIDATOR="$2"
            shift 2
            ;;
        --contents)
            CONTENTS_FILE="$2"
            shift 2
            ;;
        --min-results)
            MIN_RESULTS="$2"
            shift 2
            ;;
        --global-timeout)
            GLOBAL_TIMEOUT="$2"
            shift 2
            ;;
        --gen-awesome-list)
            GEN_AWESOME_LIST=true
            shift
            ;;
        --update)
            UPDATE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$REPO_URL" ]; then
    echo "Error: --repo_url is required"
    echo "Usage: ./build-and-run.sh --repo_url <url> [--wall_time <seconds>] [--cost_ceiling <usd>] [--output_dir <dir>] [--seed <int>] [--model_planner <model>] [--model_researcher <model>] [--model_validator <model>] [--contents <file>] [--min-results <int>] [--global-timeout <seconds>] [--gen-awesome-list] [--update]"
    exit 1
fi

# Check for OPENAI_API_KEY
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY environment variable is required"
    exit 1
fi

# If not inside Docker, build and run the Docker container
if [ "$INSIDE_DOCKER" = false ]; then
    # Build Docker image
    echo "Building Docker image..."
    docker build -t awesome-researcher .

    # Run Docker container with arguments explicitly passed
    echo "Running inside Docker container..."
    docker_args=(
        --rm -it
        -e OPENAI_API_KEY="$OPENAI_API_KEY"
        -v "$(pwd)/${OUTPUT_DIR}:/app/${OUTPUT_DIR}"
    )

    # If contents file specified, add volume mount
    if [ -n "$CONTENTS_FILE" ]; then
        # Get the directory containing the contents file
        contents_dir=$(dirname "$CONTENTS_FILE")
        docker_args+=(-v "$(pwd)/${contents_dir}:/app/${contents_dir}")
    fi

    docker run "${docker_args[@]}" awesome-researcher \
        --repo_url "$REPO_URL" \
        --wall_time "$WALL_TIME" \
        --cost_ceiling "$COST_CEILING" \
        --output_dir "$OUTPUT_DIR" \
        --model_planner "$MODEL_PLANNER" \
        --model_researcher "$MODEL_RESEARCHER" \
        --model_validator "$MODEL_VALIDATOR" \
        $([ -n "$SEED" ] && echo "--seed $SEED") \
        $([ -n "$CONTENTS_FILE" ] && echo "--contents $CONTENTS_FILE") \
        $([ -n "$MIN_RESULTS" ] && echo "--min-results $MIN_RESULTS") \
        $([ -n "$GLOBAL_TIMEOUT" ] && echo "--global-timeout $GLOBAL_TIMEOUT") \
        $([ "$GEN_AWESOME_LIST" = true ] && echo "--gen-awesome-list") \
        $([ "$UPDATE" = true ] && echo "--update")
    exit 0
fi

# Inside Docker execution
echo "Starting Awesome-List Researcher"
echo "Repository URL: $REPO_URL"
echo "Wall time: $WALL_TIME seconds"
echo "Cost ceiling: $COST_CEILING USD"
echo "Output directory: $OUTPUT_DIR"
if [ -n "$SEED" ]; then
    echo "Seed: $SEED"
fi
echo "Model (planner): $MODEL_PLANNER"
echo "Model (researcher): $MODEL_RESEARCHER"
echo "Model (validator): $MODEL_VALIDATOR"
if [ -n "$CONTENTS_FILE" ]; then
    echo "Content taxonomy file: $CONTENTS_FILE"
fi

# Create timestamp for this run
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_DIR="${OUTPUT_DIR}/${TIMESTAMP}"
mkdir -p "$RUN_DIR"

# Create branch & commit utilities - with graceful fallback
BRANCH_NAME="feature/run-${TIMESTAMP}"
if command -v git &> /dev/null; then
    # Try to create a branch
    if git branch -C "$(pwd)" "$BRANCH_NAME" 2>/dev/null; then
        echo ":: Created branch $BRANCH_NAME"
    else
        echo ":: Warning: Could not create Git branch, continuing without Git operations"
    fi
else
    echo ":: Git not available, continuing without Git operations"
fi

# Save branch name to run directory for tracking
echo "$BRANCH_NAME" > "${RUN_DIR}/git_branch.txt"

# Prepare arguments for Python script
PYTHON_ARGS=""
if [ -n "$SEED" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --seed $SEED"
fi
if [ -n "$CONTENTS_FILE" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --contents $CONTENTS_FILE"
fi
if [ -n "$MIN_RESULTS" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --min-results $MIN_RESULTS"
fi
if [ -n "$GLOBAL_TIMEOUT" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --global-timeout $GLOBAL_TIMEOUT"
fi
if [ "$GEN_AWESOME_LIST" = true ]; then
    PYTHON_ARGS="$PYTHON_ARGS --gen-awesome-list"
fi
if [ "$UPDATE" = true ]; then
    PYTHON_ARGS="$PYTHON_ARGS --update"
fi

# Run the main Python script
python -m src.main \
    --repo_url "$REPO_URL" \
    --wall_time "$WALL_TIME" \
    --cost_ceiling "$COST_CEILING" \
    --output_dir "$RUN_DIR" \
    --model_planner "$MODEL_PLANNER" \
    --model_researcher "$MODEL_RESEARCHER" \
    --model_validator "$MODEL_VALIDATOR" \
    $PYTHON_ARGS

# Commit all changes with graceful fallback
if command -v git &> /dev/null; then
    # Try to commit changes
    run_id=$(basename "$RUN_DIR")
    commit_msg="run ${run_id}: auto-generated research update"

    if git add . 2>/dev/null && git commit -m "$commit_msg" 2>/dev/null; then
        SHA=$(git rev-parse HEAD 2>/dev/null)
        echo ":: Committed changes with message: '${commit_msg}'"
        echo ":: Commit SHA: ${SHA}"
        # Save commit SHA to run directory for tracking
        echo "$SHA" > "${RUN_DIR}/git_commit.txt"
    else
        echo ":: Warning: Could not commit changes, but research was completed"
    fi
else
    echo ":: Git not available, research completed without Git commit"
fi

echo "Run completed. Results are available in $RUN_DIR"
