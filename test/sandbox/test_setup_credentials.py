"""Tests for the container startup script setup-credentials.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docker"
    / "framework"
    / "claude-code"
    / "setup-credentials.py"
)

# Wrapper script that patches HOME and MOUNT_CREDS before executing the
# real setup-credentials.py source.  The mount path is passed via the
# _TEST_MOUNT_PATH env var to avoid quoting issues in generated code.
_WRAPPER_SOURCE = """\
import os, json, shutil
from pathlib import Path

os.environ["HOME"] = os.environ["_TEST_HOME"]

source = Path(os.environ["_TEST_SCRIPT"]).read_text()
mount_override = os.environ.get("_TEST_MOUNT_PATH", "")
if mount_override:
    source = source.replace(
        'Path("/tmp/.claude-credentials.json")',
        "Path(" + repr(mount_override) + ")",
    )
exec(compile(source, os.environ["_TEST_SCRIPT"], "exec"))
"""


def _run_script(
    tmp_path: Path,
    *,
    env_overrides: dict[str, str] | None = None,
    mount_creds_content: str | None = None,
) -> None:
    """Run setup-credentials.py with a controlled HOME directory."""
    wrapper = tmp_path / "run_setup.py"
    mount_path = tmp_path / "mount-creds.json"
    wrapper.write_text(_WRAPPER_SOURCE)

    if mount_creds_content is not None:
        mount_path.write_text(mount_creds_content)

    env = {
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "_TEST_HOME": str(tmp_path),
        "_TEST_SCRIPT": str(SCRIPT_PATH),
    }
    if mount_creds_content is not None:
        env["_TEST_MOUNT_PATH"] = str(mount_path)
    if env_overrides:
        env.update(env_overrides)

    subprocess.run(
        [sys.executable, str(wrapper)],
        check=True,
        env=env,
        timeout=10,
    )


class TestSetupCredentialsApiKeyMode:
    """Tests for API key mode (apiKeyHelper present)."""

    def test_settings_includes_api_key_helper(self, tmp_path: Path) -> None:
        _run_script(tmp_path, env_overrides={"_ANTHROPIC_API_KEY": "sk-test"})

        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        settings = json.loads(settings_path.read_text())
        assert settings["apiKeyHelper"] == "echo $_ANTHROPIC_API_KEY"
        assert settings["skipDangerousModePermissionPrompt"] is True

    def test_no_credentials_file_copied(self, tmp_path: Path) -> None:
        _run_script(tmp_path, env_overrides={"_ANTHROPIC_API_KEY": "sk-test"})

        creds_path = tmp_path / ".claude" / ".credentials.json"
        assert not creds_path.exists()


class TestSetupCredentialsOAuthMode:
    """Tests for OAuth mode (no apiKeyHelper)."""

    def test_settings_omits_api_key_helper(self, tmp_path: Path) -> None:
        _run_script(tmp_path)

        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        settings = json.loads(settings_path.read_text())
        assert "apiKeyHelper" not in settings
        assert settings["skipDangerousModePermissionPrompt"] is True

    def test_empty_api_key_is_oauth_mode(self, tmp_path: Path) -> None:
        _run_script(tmp_path, env_overrides={"_ANTHROPIC_API_KEY": ""})

        settings_path = tmp_path / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text())
        assert "apiKeyHelper" not in settings

    def test_copies_credentials_from_mount(self, tmp_path: Path) -> None:
        creds_content = json.dumps({"accessToken": "test-token"})
        _run_script(tmp_path, mount_creds_content=creds_content)

        target = tmp_path / ".claude" / ".credentials.json"
        assert target.exists()
        assert json.loads(target.read_text()) == {"accessToken": "test-token"}

    def test_no_crash_without_mount(self, tmp_path: Path) -> None:
        _run_script(tmp_path)

        target = tmp_path / ".claude" / ".credentials.json"
        assert not target.exists()

    def test_creates_claude_dir_if_missing(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / ".claude"
        assert not claude_dir.exists()

        _run_script(tmp_path)

        assert claude_dir.is_dir()
        assert (claude_dir / "settings.json").exists()
