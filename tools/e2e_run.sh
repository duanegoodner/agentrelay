#!/usr/bin/env bash
# Run a graph against a target repo.
#
# Usage: tools/e2e_run.sh <graph.yaml> <target-repo-path> [extra run_graph flags...]
#
# The graph path is resolved relative to the agentrelay repo root.
# The script cd's to the target repo but runs the orchestrator from
# agentrelay's own pixi environment (not the target repo's).

set -euo pipefail

usage() {
  cat <<HELP
Usage: pixi run e2e <graph.yaml> <target-repo-path> [flags...]

Run an agentrelay graph in a target repository.

Arguments:
  graph.yaml         Path to graph YAML (relative to agentrelay repo root)
  target-repo-path   Path to the target repo where agents will work

Extra flags are passed through to run_graph (e.g. --dry-run, --model).

Examples:
  pixi run e2e graphs/smoke/quick_chained.yaml /path/to/demos
  pixi run e2e graphs/smoke/quick_parallel.yaml /path/to/demos --dry-run
  pixi run e2e graphs/smoke/quick_parallel.yaml /path/to/demos --model claude-opus-4-6
HELP
}

if [ $# -lt 1 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  usage
  exit 0
fi

if [ $# -lt 2 ]; then
  usage >&2
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

# Validate target repo is clean.  Ignore:
#   .workflow/, .worktrees/ — created by graph runs, safe during parallel execution
#   pixi.lock — pixi run --manifest-path may trigger lock resolution as a side effect
cd "$TARGET_REPO"
if [ -n "$(git status --porcelain | grep -v '^?? \.wor' | grep -v 'pixi\.lock')" ]; then
  echo "Error: target repo has uncommitted changes" >&2
  echo "  $(pwd)" >&2
  exit 1
fi

echo "[e2e] Running graph: $GRAPH_ABS"
echo "[e2e] Target repo:   $(pwd)"
echo ""

exec pixi run --manifest-path "$REPO_ROOT/pixi.toml" python -m agentrelay.run_graph "$GRAPH_ABS" "$@"
