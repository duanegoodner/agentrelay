#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building agentrelay-agent-base:latest"
docker build -t agentrelay-agent-base:latest \
    -f "$REPO_ROOT/docker/base/Dockerfile" \
    "$REPO_ROOT"

echo "==> Building agentrelay-agent-python:latest"
docker build -t agentrelay-agent-python:latest \
    -f "$REPO_ROOT/docker/toolchain/python/Dockerfile" \
    "$REPO_ROOT"

echo "==> Building agentrelay-agent-claude-code-python:latest"
docker build -t agentrelay-agent-claude-code-python:latest \
    -f "$REPO_ROOT/docker/framework/claude-code/Dockerfile" \
    "$REPO_ROOT"

echo "==> All images built successfully."
