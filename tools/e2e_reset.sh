#!/usr/bin/env bash
# Reset a graph run in a target repo.
#
# Usage: tools/e2e_reset.sh <graph.yaml> <target-repo-path>
#
# The graph path is resolved relative to the agentrelay repo root.
# The script cd's to the target repo and uses its pixi environment.
# Passes --yes to skip the interactive confirmation prompt.

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <graph.yaml> <target-repo-path>" >&2
  exit 1
fi

GRAPH="$1"
TARGET_REPO="$2"

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

cd "$TARGET_REPO"

echo "[e2e-reset] Resetting graph: $GRAPH_ABS"
echo "[e2e-reset] Target repo:     $(pwd)"
echo ""

exec pixi run python -m agentrelay.reset_graph "$GRAPH_ABS" --yes
