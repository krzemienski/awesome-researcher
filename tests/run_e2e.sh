#!/bin/bash
set -e

# End-to-end test script for the Awesome-List Researcher
# This script tests the entire pipeline with a small example

echo "Running end-to-end test for Awesome-List Researcher..."

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY environment variable not set"
    exit 1
fi

# Create temporary directory for test outputs
TEST_DIR="$(pwd)/tests/test_output"
mkdir -p "$TEST_DIR"

# Define test parameters
TEST_REPO="https://github.com/sindresorhus/awesome-nodejs"
TEST_WALL_TIME=300  # 5 minutes
TEST_COST_CEILING=3.0

echo "Test parameters:"
echo "  Repo URL: $TEST_REPO"
echo "  Wall time: $TEST_WALL_TIME seconds"
echo "  Cost ceiling: $TEST_COST_CEILING USD"
echo "  Output directory: $TEST_DIR"
echo ""

# Run the Awesome-List Researcher
echo "Running Awesome-List Researcher..."
./build-and-run.sh \
    --repo_url "$TEST_REPO" \
    --wall_time "$TEST_WALL_TIME" \
    --cost_ceiling "$TEST_COST_CEILING" \
    --output_dir "$TEST_DIR" \
    --model_planner "gpt-4.1" \
    --model_researcher "o3" \
    --model_validator "o3"

# Check if the command succeeded
if [ $? -ne 0 ]; then
    echo "Error: Awesome-List Researcher failed"
    exit 1
fi

# Find the most recent output directory
LATEST_DIR=$(find "$TEST_DIR" -type d -depth 1 | sort -r | head -n 1)

echo "Checking test outputs in $LATEST_DIR..."

# Check if required files exist
REQUIRED_FILES=(
    "README.md"
    "original.json"
    "plan.json"
    "aggregated_results.json"
    "new_links.json"
    "updated_list.md"
    "agent.log"
    "research_report.md"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$LATEST_DIR/$file" ]; then
        echo "Error: Required file $file not found"
        exit 1
    fi
    echo "✓ Found $file"
done

# Check if new_links.json contains any entries
NEW_LINKS_COUNT=$(jq '. | length' "$LATEST_DIR/new_links.json")
if [ "$NEW_LINKS_COUNT" -eq 0 ]; then
    echo "Warning: No new links found"
    # This is a warning, not an error, since some runs might genuinely find no new links
fi

echo "Found $NEW_LINKS_COUNT new links"

# Check if awesome-lint passes on the updated list
echo "Validating updated_list.md with awesome-lint..."
cd "$LATEST_DIR"
cp updated_list.md README.md  # awesome-lint expects the file to be named README.md
awesome-lint
LINT_RESULT=$?
cd - > /dev/null

if [ $LINT_RESULT -ne 0 ]; then
    echo "Error: awesome-lint validation failed"
    exit 1
fi

echo "✓ awesome-lint validation passed"

# Clean up test directory
if [ "$1" != "--keep" ]; then
    echo "Cleaning up test directory..."
    rm -rf "$TEST_DIR"
fi

echo "✅ All tests passed!"
exit 0
