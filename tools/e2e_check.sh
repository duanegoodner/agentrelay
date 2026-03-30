#!/usr/bin/env bash
# Preflight check on a target repo for E2E testing.
#
# Usage: tools/e2e_check.sh <target-repo-path> [--env <type>]
#
# Validates that the target repo is ready for agentrelay E2E testing.
# The --env flag specifies the agent environment to check (default: tmux).

set -euo pipefail

usage() {
  cat <<HELP
Usage: pixi run e2e-check <target-repo-path> [--env <type>]

Preflight check on a target repository for E2E testing.

Validates: git repo, pixi setup, agentrelay importable (from agentrelay env),
gh auth, agent environment (default: tmux), working tree cleanliness,
and leftover graph state.

Arguments:
  target-repo-path   Path to the target repo to check

Options:
  --env <type>       Agent environment to check for (default: tmux)

Examples:
  pixi run e2e-check /path/to/demos
  pixi run e2e-check /path/to/demos --env tmux
HELP
}

ENV_TYPE="tmux"
TARGET_REPO=""

# Parse arguments.
while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --env) ENV_TYPE="$2"; shift 2 ;;
    -*) echo "Unknown flag: $1" >&2; usage >&2; exit 1 ;;
    *) TARGET_REPO="$1"; shift ;;
  esac
done

if [ -z "$TARGET_REPO" ]; then
  usage >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0
WARN=0

check() {
  local label="$1"
  local status="$2"
  local detail="${3:-}"

  case "$status" in
    pass) printf "  %-40s %s" "$label" "PASS"; PASS=$((PASS + 1)) ;;
    fail) printf "  %-40s %s" "$label" "FAIL"; FAIL=$((FAIL + 1)) ;;
    warn) printf "  %-40s %s" "$label" "WARN"; WARN=$((WARN + 1)) ;;
  esac
  if [ -n "$detail" ]; then
    printf "  (%s)" "$detail"
  fi
  echo ""
}

echo "Preflight check: $TARGET_REPO"
echo "Agent environment: $ENV_TYPE"
echo ""

# 1. Path exists and is a git repo.
if [ -d "$TARGET_REPO/.git" ] || git -C "$TARGET_REPO" rev-parse --git-dir >/dev/null 2>&1; then
  check "Git repository" pass
else
  check "Git repository" fail "not a git repo"
fi

# 2. pixi.toml exists.
if [ -f "$TARGET_REPO/pixi.toml" ]; then
  check "pixi.toml" pass
else
  check "pixi.toml" fail "no pixi.toml found"
fi

# 3. Python version (from agentrelay's pixi env).
PY_VERSION=$(pixi run --manifest-path "$REPO_ROOT/pixi.toml" python --version 2>&1) || PY_VERSION=""
if [ -n "$PY_VERSION" ]; then
  check "Python (agentrelay env)" pass "$PY_VERSION"
else
  check "Python (agentrelay env)" fail "pixi run python failed"
fi

# 4. agentrelay importable (from agentrelay's pixi env).
AR_LOCATION=$(pixi run --manifest-path "$REPO_ROOT/pixi.toml" python -c "import agentrelay; print(agentrelay.__file__)" 2>&1) || AR_LOCATION=""
if [ -n "$AR_LOCATION" ]; then
  check "agentrelay importable" pass "$AR_LOCATION"
else
  check "agentrelay importable" fail "import failed"
fi

# 5. Working tree clean.
DIRTY=$(cd "$TARGET_REPO" && git status --porcelain 2>&1)
if [ -z "$DIRTY" ]; then
  check "Working tree clean" pass
else
  DIRTY_COUNT=$(echo "$DIRTY" | wc -l | tr -d ' ')
  check "Working tree clean" warn "$DIRTY_COUNT uncommitted change(s)"
fi

# 6. gh auth.
if gh auth status >/dev/null 2>&1; then
  check "GitHub CLI authenticated" pass
else
  check "GitHub CLI authenticated" fail "run: gh auth login"
fi

# 7. Agent environment.
case "$ENV_TYPE" in
  tmux)
    if command -v tmux >/dev/null 2>&1; then
      TMUX_VER=$(tmux -V 2>&1)
      check "Agent env ($ENV_TYPE)" pass "$TMUX_VER"
    else
      check "Agent env ($ENV_TYPE)" fail "tmux not found"
    fi
    ;;
  *)
    check "Agent env ($ENV_TYPE)" warn "unknown environment type"
    ;;
esac

# 8. Conflict check — look for leftover state from graphs in agentrelay/graphs/.
CONFLICT_COUNT=0
for GRAPH_FILE in "$REPO_ROOT"/graphs/*.yaml; do
  [ -f "$GRAPH_FILE" ] || continue
  GRAPH_NAME=$(grep '^name:' "$GRAPH_FILE" | head -1 | sed 's/^name:[[:space:]]*//')
  if [ -d "$TARGET_REPO/.workflow/$GRAPH_NAME" ] || [ -d "$TARGET_REPO/.worktrees/$GRAPH_NAME" ]; then
    CONFLICT_COUNT=$((CONFLICT_COUNT + 1))
    check "No leftover state ($GRAPH_NAME)" warn "run reset first"
  fi
done
if [ "$CONFLICT_COUNT" -eq 0 ]; then
  check "No leftover graph state" pass
fi

# Summary.
echo ""
echo "Results: $PASS pass, $FAIL fail, $WARN warn"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
