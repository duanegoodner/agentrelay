#!/usr/bin/env bash
# Copy BoundedQueue fixture files into the target repo and commit them.
#
# Usage: ./setup_fixtures.sh <mode> <target-repo-path>
#
# Modes:
#   stubs   — copy bounded_queue.py only (for test_writer experiment)
#   all     — copy bounded_queue.py + test_bounded_queue.py
#             (for test_reviewer and implementer experiments)
#
# The spec_writer experiment needs no fixtures (contradiction is in the task
# description). Just run the graph on a clean target repo.
#
# Between experiments, reset the target repo to undo both the graph run and
# the fixture commit:
#   pixi run e2e-reset <graph.yaml> <target-repo>
#   git -C <target-repo> reset --hard HEAD~1

set -euo pipefail

usage() {
    echo "Usage: $0 <stubs|all> <target-repo-path>" >&2
    exit 1
}

if [[ $# -ne 2 ]]; then
    usage
fi

MODE="$1"
TARGET_REPO="$2"
FIXTURES_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ "$MODE" != "stubs" && "$MODE" != "all" ]]; then
    echo "Error: mode must be 'stubs' or 'all'" >&2
    usage
fi

if [[ ! -d "$TARGET_REPO/.git" && ! -f "$TARGET_REPO/.git" ]]; then
    echo "Error: $TARGET_REPO is not a git repository" >&2
    exit 1
fi

echo "Setting up fixtures (mode: $MODE) in $TARGET_REPO ..."

# Stubs → src/agentrelaydemos/
mkdir -p "$TARGET_REPO/src/agentrelaydemos"
cp "$FIXTURES_DIR/bounded_queue.py" "$TARGET_REPO/src/agentrelaydemos/bounded_queue.py"

FILES_TO_ADD="src/agentrelaydemos/bounded_queue.py"

# Tests → tests/ (only in 'all' mode)
if [[ "$MODE" == "all" ]]; then
    mkdir -p "$TARGET_REPO/tests"
    cp "$FIXTURES_DIR/test_bounded_queue.py" "$TARGET_REPO/tests/test_bounded_queue.py"
    FILES_TO_ADD="$FILES_TO_ADD tests/test_bounded_queue.py"
fi

# Stage and commit (only if there are changes).
cd "$TARGET_REPO"
git add $FILES_TO_ADD

if git diff --cached --quiet; then
    echo "No changes — fixtures already up to date."
else
    git commit -m "Add concern experiment fixtures ($MODE)"
    echo "Committed fixture files."
fi
