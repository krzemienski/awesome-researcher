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
MODEL_RESEARCHER="o3"
MODEL_VALIDATOR="o3"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --repo_url)
            REPO_URL="$2"
            shift 2
            ;;
        --wall_time)
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
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$REPO_URL" ]; then
    echo "Error: --repo_url is required"
    echo "Usage: ./build-and-run.sh --repo_url <url> [--wall_time <seconds>] [--cost_ceiling <usd>] [--output_dir <dir>] [--seed <int>] [--model_planner <model>] [--model_researcher <model>] [--model_validator <model>]"
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
    docker run --rm -it \
        -e OPENAI_API_KEY="$OPENAI_API_KEY" \
        -v "$(pwd)/${OUTPUT_DIR}:/app/${OUTPUT_DIR}" \
        awesome-researcher \
        --repo_url "$REPO_URL" \
        --wall_time "$WALL_TIME" \
        --cost_ceiling "$COST_CEILING" \
        --output_dir "$OUTPUT_DIR" \
        --model_planner "$MODEL_PLANNER" \
        --model_researcher "$MODEL_RESEARCHER" \
        --model_validator "$MODEL_VALIDATOR" \
        $([ -n "$SEED" ] && echo "--seed $SEED")
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

# Create timestamp for this run
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_DIR="${OUTPUT_DIR}/${TIMESTAMP}"
mkdir -p "$RUN_DIR"

# Prepare arguments for Python script
PYTHON_ARGS=""
if [ -n "$SEED" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --seed $SEED"
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

echo "Run completed. Results are available in $RUN_DIR"
