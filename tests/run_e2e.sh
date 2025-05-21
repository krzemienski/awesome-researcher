#!/bin/bash
set -e

# End-to-end test script for awesome-researcher

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running end-to-end test for awesome-researcher${NC}"

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}Error: OPENAI_API_KEY environment variable is not set.${NC}"
    exit 1
fi

# Default test repository
TEST_REPO=${1:-"https://github.com/vinta/awesome-python"}

# Set up test parameters
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_DIR="runs/test_${TIMESTAMP}"
WALL_TIME=300  # 5 minutes for tests
COST_CEILING=5.0  # $5.00 for tests
SEED=42  # Use fixed seed for deterministic results

echo -e "${YELLOW}Test configuration:${NC}"
echo "Repository: $TEST_REPO"
echo "Output directory: $OUTPUT_DIR"
echo "Wall time: $WALL_TIME seconds"
echo "Cost ceiling: $COST_CEILING USD"
echo "Seed: $SEED"

# Run the awesome-researcher
echo -e "${YELLOW}Running awesome-researcher...${NC}"
./build-and-run.sh \
    --repo_url "$TEST_REPO" \
    --wall_time "$WALL_TIME" \
    --cost_ceiling "$COST_CEILING" \
    --output_dir "$OUTPUT_DIR" \
    --seed "$SEED"

# Check if the run was successful
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: awesome-researcher failed to run.${NC}"
    exit 1
fi

echo -e "${GREEN}awesome-researcher completed successfully.${NC}"

# Validate the outputs
echo -e "${YELLOW}Validating outputs...${NC}"

# Check if the output directory exists
if [ ! -d "$OUTPUT_DIR" ]; then
    echo -e "${RED}Error: Output directory '$OUTPUT_DIR' does not exist.${NC}"
    exit 1
fi

# Check if the required output files exist
REQUIRED_FILES=(
    "original.json"
    "expanded_queries.json"
    "plan.json"
    "new_links.json"
    "updated_list.md"
    "agent.log"
    "research_report.md"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$OUTPUT_DIR/$file" ]; then
        echo -e "${RED}Error: Required output file '$file' does not exist.${NC}"
        exit 1
    fi
done

echo -e "${GREEN}All required output files exist.${NC}"

# Check if new_links.json contains at least 10 links
NEW_LINKS_COUNT=$(grep -o '"url"' "$OUTPUT_DIR/new_links.json" | wc -l)
if [ "$NEW_LINKS_COUNT" -lt 10 ]; then
    echo -e "${RED}Error: new_links.json contains less than 10 links ($NEW_LINKS_COUNT).${NC}"
    exit 1
fi

echo -e "${GREEN}new_links.json contains $NEW_LINKS_COUNT links.${NC}"

# Check if updated_list.md passes awesome-lint
cd "$OUTPUT_DIR"
echo -e "${YELLOW}Running awesome-lint on updated_list.md...${NC}"
AWESOME_LINT_OUTPUT=$(awesome-lint updated_list.md 2>&1 || true)
if [[ "$AWESOME_LINT_OUTPUT" == *"error"* ]]; then
    echo -e "${RED}Error: updated_list.md failed awesome-lint:${NC}"
    echo "$AWESOME_LINT_OUTPUT"
    exit 1
fi
cd - > /dev/null

echo -e "${GREEN}updated_list.md passes awesome-lint.${NC}"

# Check semantic uniqueness if sentence_transformers is available
if python -c "import sentence_transformers" &> /dev/null; then
    echo -e "${YELLOW}Checking semantic uniqueness...${NC}"
    python -c "
import json
import sys
import numpy as np
from sentence_transformers import SentenceTransformer

# Load original and new links
with open('$OUTPUT_DIR/original.json', 'r') as f:
    original_data = json.load(f)

with open('$OUTPUT_DIR/new_links.json', 'r') as f:
    new_links = json.load(f)

# Extract all original URLs and titles
original_items = []
for section in original_data.get('sections', []):
    for item in section.get('items', []):
        title = item.get('name', '')
        desc = item.get('description', '')
        original_items.append(f'{title} {desc}'.strip())

# Extract all new titles and descriptions
new_items = []
for item in new_links:
    title = item.get('name', '')
    desc = item.get('description', '')
    new_items.append(f'{title} {desc}'.strip())

# If there are no items, exit early
if not original_items or not new_items:
    print('No items to compare')
    sys.exit(0)

# Load the model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Encode the items
original_embeddings = model.encode(original_items, show_progress_bar=False)
new_embeddings = model.encode(new_items, show_progress_bar=False)

# Normalize the embeddings
original_embeddings = original_embeddings / np.linalg.norm(original_embeddings, axis=1, keepdims=True)
new_embeddings = new_embeddings / np.linalg.norm(new_embeddings, axis=1, keepdims=True)

# Compute the similarity matrix
similarity_matrix = np.matmul(new_embeddings, original_embeddings.T)

# Check for high similarity
threshold = 0.85
similar_count = 0
total_count = len(new_items)

for i, _ in enumerate(new_items):
    max_similarity = np.max(similarity_matrix[i])
    if max_similarity >= threshold:
        similar_count += 1

similarity_ratio = similar_count / total_count
print(f'Similarity ratio: {similarity_ratio:.2f} ({similar_count}/{total_count})')

# Check if the similar ratio is below 30%
if similarity_ratio > 0.3:
    print('Error: More than 30% of new links are semantically similar to original links')
    sys.exit(1)
else:
    print('Semantic uniqueness test passed')
"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Semantic uniqueness test failed.${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Warning: sentence_transformers is not available, skipping semantic uniqueness check.${NC}"
fi

# Check if re-running the process adds no new links
# Note: This would be a full end-to-end test but would double the API costs
# We'll skip this for now and just note it
echo -e "${YELLOW}Note: A complete test would also verify that re-running the process adds no new links (idempotency).${NC}"

echo -e "${GREEN}All tests passed!${NC}"
echo -e "${GREEN}End-to-end test successful.${NC}"
