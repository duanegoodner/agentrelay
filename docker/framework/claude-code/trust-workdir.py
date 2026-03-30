#!/usr/bin/env python3
"""Seed Claude Code folder trust for the current working directory.

Claude Code stores per-project trust in ~/.claude.json under a
``projects.<path>.hasTrustDialogAccepted`` key. In ephemeral containers
the worktree path is not known at image build time, so this script
seeds trust at runtime before launching the agent.
"""

import json
import os
from pathlib import Path

config_path = Path.home() / ".claude.json"
data = json.loads(config_path.read_text()) if config_path.exists() else {}

cwd = os.getcwd()
projects = data.setdefault("projects", {})
project = projects.setdefault(cwd, {})
project["hasTrustDialogAccepted"] = True

config_path.write_text(json.dumps(data))
