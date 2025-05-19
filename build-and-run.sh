#!/bin/bash
set -e

# Build the Docker image if not running within Docker
if [ ! -f /.dockerenv ]; then
    echo "Building Docker image..."
    docker build -t awesome-list-researcher .

    # Run the container with the same arguments
    echo "Running container..."
    docker run --rm -it \
        -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
        -v "$(pwd)/runs:/app/runs" \
        awesome-list-researcher "$@"
    exit 0
fi

# If we're inside Docker, run the Python application
echo "Starting Awesome-List Researcher..."

# Run the main application with CLI arguments
python -m awesome_list_researcher.main "$@"
