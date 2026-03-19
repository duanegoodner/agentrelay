#!/usr/bin/env bash
# Run a graph against a target repo.
#
# Usage: tools/e2e_run.sh <graph.yaml> <target-repo-path> [extra run_graph flags...]
#
# The graph path is resolved relative to the agentrelay repo root.
# The script cd's to the target repo and uses its pixi environment.

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <graph.yaml> <target-repo-path> [extra flags...]" >&2
  exit 1
fi

GRAPH="$1"
TARGET_REPO="$2"
shift 2

# Resolve graph path relative to agentrelay repo root.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GRAPH_ABS="$(cd "$REPO_ROOT" && realpath "$GRAPH")"

if [ ! -f "$GRAPH_ABS" ]; then
  echo "Error: graph file not found: $GRAPH_ABS" >&2
  exit 1
fi

if [ ! -d "$TARGET_REPO" ]; then
  echo "Error: target repo not found: $TARGET_REPO" >&2
  exit 1
fi

# Validate target repo is clean.
cd "$TARGET_REPO"
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: target repo has uncommitted changes" >&2
  echo "  $(pwd)" >&2
  exit 1
fi

echo "[e2e] Running graph: $GRAPH_ABS"
echo "[e2e] Target repo:   $(pwd)"
echo ""

exec pixi run python -m agentrelay.run_graph "$GRAPH_ABS" "$@"
