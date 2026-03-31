#!/usr/bin/env python3
"""Generate Claude Code settings.json and copy OAuth credentials if present.

Claude Code settings must exist before the agent launches. This script
runs at container startup to generate ``~/.claude/settings.json``
based on which authentication mode is active:

- **API key mode** (``_ANTHROPIC_API_KEY`` is set and non-empty):
  includes ``apiKeyHelper`` so Claude Code reads the key without an
  interactive prompt.
- **OAuth mode** (no API key): omits ``apiKeyHelper`` so Claude Code
  falls back to reading ``~/.claude/.credentials.json`` natively.

If an OAuth credentials file is mounted read-only at
``/tmp/.claude-credentials.json``, this script copies it to
``~/.claude/.credentials.json`` so the agent owns a writable copy
(needed for token refresh).
"""

import json
import os
import shutil
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
MOUNT_CREDS = Path("/tmp/.claude-credentials.json")
TARGET_CREDS = CLAUDE_DIR / ".credentials.json"

# Build settings based on auth mode.
settings: dict[str, object] = {"skipDangerousModePermissionPrompt": True}

api_key = os.environ.get("_ANTHROPIC_API_KEY", "")
if api_key:
    settings["apiKeyHelper"] = "echo $_ANTHROPIC_API_KEY"

CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH.write_text(json.dumps(settings))

# Copy OAuth credentials from read-only mount to writable location.
if MOUNT_CREDS.exists():
    shutil.copy2(str(MOUNT_CREDS), str(TARGET_CREDS))
