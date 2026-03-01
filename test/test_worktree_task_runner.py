import json
from pathlib import Path

import pytest

from agentrelaysmall.worktree_task_runner import WorktreeTaskRunner


def make_config(
    signal_dir: Path, **extras: str | int | None
) -> dict[str, str | int | None]:
    base: dict[str, str | int | None] = {
        "task_id": "task_001",
        "graph_name": "demo",
        "signal_dir": str(signal_dir),
    }
    base.update(extras)
    return base


def write_config(signal_dir: Path) -> None:
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(make_config(signal_dir)))


# ── from_config ──────────────────────────────────────────────────────────────


def test_from_config_reads_task_id(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    write_config(signal_dir)
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.task_id == "task_001"


def test_from_config_reads_graph_name(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    write_config(signal_dir)
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.graph_name == "demo"


def test_from_config_reads_signal_dir(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    write_config(signal_dir)
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.signal_dir == signal_dir


def test_from_config_missing_file_raises(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    signal_dir.mkdir(parents=True)
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    with pytest.raises(FileNotFoundError):
        WorktreeTaskRunner.from_config()


def test_from_config_missing_env_var_raises(monkeypatch):
    monkeypatch.delenv("AGENTRELAY_SIGNAL_DIR", raising=False)
    with pytest.raises(KeyError):
        WorktreeTaskRunner.from_config()


# ── mark_done ─────────────────────────────────────────────────────────────────


def test_mark_done_creates_file(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.mark_done()
    assert (signal_dir / ".done").exists()


def test_mark_done_creates_signal_dir_if_missing(tmp_path):
    signal_dir = tmp_path / "nested" / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.mark_done()
    assert (signal_dir / ".done").exists()


def test_mark_done_contains_timestamp(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.mark_done()
    content = (signal_dir / ".done").read_text()
    assert "T" in content  # ISO 8601 timestamp contains 'T'


def test_mark_done_includes_note(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.mark_done("wrote hello.py")
    content = (signal_dir / ".done").read_text()
    assert "wrote hello.py" in content


def test_mark_done_no_note_no_trailing_newline_noise(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.mark_done()
    content = (signal_dir / ".done").read_text()
    # Without a note, content should just be the timestamp line
    assert "\n" not in content


# ── mark_failed ───────────────────────────────────────────────────────────────


def test_mark_failed_creates_file(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.mark_failed("something broke")
    assert (signal_dir / ".failed").exists()


def test_mark_failed_contains_reason(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.mark_failed("something broke")
    content = (signal_dir / ".failed").read_text()
    assert "something broke" in content


def test_mark_failed_contains_timestamp(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.mark_failed("oops")
    content = (signal_dir / ".failed").read_text()
    assert "T" in content


# ── get_context ───────────────────────────────────────────────────────────────


def test_get_context_returns_none_when_missing(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    assert runner.get_context() is None


def test_get_context_returns_content(tmp_path):
    signal_dir = tmp_path / "signals"
    signal_dir.mkdir()
    (signal_dir / "context.md").write_text("# Deps output\nsome stuff")
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    assert runner.get_context() == "# Deps output\nsome stuff"


# ── new fields from enriched task_context.json ───────────────────────────────


def test_from_config_reads_role(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    cfg = make_config(
        signal_dir,
        role="generic",
        description="d",
        graph_branch="graph/demo",
        completion_gate=None,
        agent_index=2,
    )
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.role == "generic"


def test_from_config_reads_description(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    cfg = make_config(signal_dir, description="do the thing")
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.description == "do the thing"


def test_from_config_reads_graph_branch(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    cfg = make_config(signal_dir, graph_branch="graph/demo")
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.graph_branch == "graph/demo"


def test_from_config_reads_completion_gate(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    cfg = make_config(signal_dir, completion_gate="pixi run pytest")
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.completion_gate == "pixi run pytest"


def test_from_config_reads_agent_index(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    cfg = make_config(signal_dir, agent_index=7)
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.agent_index == 7


def test_from_config_new_fields_default_to_none_when_absent(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    signal_dir.mkdir(parents=True, exist_ok=True)
    # Minimal config — no new fields
    (signal_dir / "task_context.json").write_text(
        json.dumps(
            {"task_id": "task_001", "graph_name": "demo", "signal_dir": str(signal_dir)}
        )
    )
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.role is None
    assert runner.description is None
    assert runner.graph_branch is None
    assert runner.completion_gate is None
    assert runner.agent_index is None
    assert runner.coverage_threshold is None
    assert runner.review_model is None
    assert runner.max_gate_retries is None


def test_from_config_reads_coverage_threshold(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    cfg = make_config(signal_dir, coverage_threshold=90)
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.coverage_threshold == 90


def test_from_config_reads_review_model(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    cfg = make_config(signal_dir, review_model="claude-sonnet-4-6")
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.review_model == "claude-sonnet-4-6"


def test_from_config_reads_max_gate_retries(tmp_path, monkeypatch):
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    cfg = make_config(signal_dir, max_gate_retries=3)
    signal_dir.mkdir(parents=True, exist_ok=True)
    (signal_dir / "task_context.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("AGENTRELAY_SIGNAL_DIR", str(signal_dir))
    runner = WorktreeTaskRunner.from_config()
    assert runner.max_gate_retries == 3


# ── get_instructions ─────────────────────────────────────────────────────────


def test_get_instructions_returns_none_when_missing(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    assert runner.get_instructions() is None


def test_get_instructions_returns_content(tmp_path):
    signal_dir = tmp_path / "signals"
    signal_dir.mkdir()
    (signal_dir / "instructions.md").write_text("## Step 1\nDo the thing.\n")
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    assert runner.get_instructions() == "## Step 1\nDo the thing.\n"


# ── record_gate_attempt ───────────────────────────────────────────────────────


def test_record_gate_attempt_creates_log_file(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.record_gate_attempt(1, False)
    assert (signal_dir / "gate_retries.log").exists()


def test_record_gate_attempt_contains_attempt_number(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.record_gate_attempt(2, True)
    content = (signal_dir / "gate_retries.log").read_text()
    assert "attempt=2" in content


def test_record_gate_attempt_contains_passed_value(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.record_gate_attempt(1, True)
    content = (signal_dir / "gate_retries.log").read_text()
    assert "passed=True" in content


def test_record_gate_attempt_appends_multiple_entries(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.record_gate_attempt(1, False)
    runner.record_gate_attempt(2, True)
    lines = (signal_dir / "gate_retries.log").read_text().splitlines()
    assert len(lines) == 2
    assert "attempt=1" in lines[0]
    assert "attempt=2" in lines[1]


def test_record_gate_attempt_contains_timestamp(tmp_path):
    signal_dir = tmp_path / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.record_gate_attempt(1, False)
    content = (signal_dir / "gate_retries.log").read_text()
    # ISO 8601 timestamps contain 'T'
    assert "T" in content


def test_record_gate_attempt_creates_signal_dir_if_missing(tmp_path):
    signal_dir = tmp_path / "nested" / "signals"
    runner = WorktreeTaskRunner("task_001", "demo", signal_dir)
    runner.record_gate_attempt(1, False)
    assert signal_dir.is_dir()
    assert (signal_dir / "gate_retries.log").exists()
