import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentrelaysmall.agent_task import AgentTask
from agentrelaysmall.task_launcher import (
    create_worktree,
    launch_agent,
    poll_for_completion,
    remove_worktree,
    send_prompt,
    write_task_context,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def make_task(task_id: str = "task_001") -> AgentTask:
    return AgentTask(id=task_id, description="test task")


# ── create_worktree ───────────────────────────────────────────────────────────

def test_create_worktree_calls_git(tmp_path):
    task = make_task()
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        create_worktree(task, "demo", tmp_path)
    expected_path = tmp_path / "demo" / "task_001"
    mock_run.assert_called_once_with(
        ["git", "worktree", "add", "-b", "task/demo/task_001", str(expected_path), "main"],
        check=True,
    )


def test_create_worktree_sets_state(tmp_path):
    task = make_task()
    with patch("agentrelaysmall.task_launcher.subprocess.run"):
        result = create_worktree(task, "demo", tmp_path, base_branch="main")
    assert task.state.worktree_path == tmp_path / "demo" / "task_001"
    assert task.state.branch_name == "task/demo/task_001"
    assert result == task.state.worktree_path


def test_create_worktree_branch_uses_graph_name(tmp_path):
    task = make_task("task_002")
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        create_worktree(task, "my-graph", tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "task/my-graph/task_002" in cmd


# ── write_task_context ────────────────────────────────────────────────────────

def test_write_task_context_creates_json(tmp_path):
    task = make_task()
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    task.state.worktree_path = worktree
    write_task_context(task, "demo", tmp_path)
    data = json.loads((worktree / "task_context.json").read_text())
    assert data["task_id"] == "task_001"
    assert data["graph_name"] == "demo"


def test_write_task_context_signal_dir_path(tmp_path):
    task = make_task()
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    task.state.worktree_path = worktree
    write_task_context(task, "demo", tmp_path)
    data = json.loads((worktree / "task_context.json").read_text())
    expected = str(tmp_path / ".workflow" / "demo" / "signals" / "task_001")
    assert data["signal_dir"] == expected


def test_write_task_context_requires_worktree_path():
    task = make_task()
    with pytest.raises(AssertionError):
        write_task_context(task, "demo", Path("/some/root"))


# ── launch_agent ──────────────────────────────────────────────────────────────

def test_launch_agent_creates_tmux_window(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path
    with patch("agentrelaysmall.task_launcher.subprocess.check_output", return_value=b"%3\n") as mock_out, \
         patch("agentrelaysmall.task_launcher.subprocess.run"):
        launch_agent(task, "agentrelaysmall")
    cmd = mock_out.call_args[0][0]
    assert "tmux" in cmd
    assert "new-window" in cmd
    assert "agentrelaysmall" in cmd
    assert "task_001" in cmd


def test_launch_agent_sends_claude_command(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path
    with patch("agentrelaysmall.task_launcher.subprocess.check_output", return_value=b"%3\n"), \
         patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        launch_agent(task, "agentrelaysmall")
    cmd = mock_run.call_args[0][0]
    assert "claude" in cmd


def test_launch_agent_sets_pane_id(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path
    with patch("agentrelaysmall.task_launcher.subprocess.check_output", return_value=b"%7\n"), \
         patch("agentrelaysmall.task_launcher.subprocess.run"):
        pane_id = launch_agent(task, "agentrelaysmall")
    assert pane_id == "%7"
    assert task.state.pane_id == "%7"
    assert task.state.tmux_session == "agentrelaysmall"


def test_launch_agent_requires_worktree_path():
    task = make_task()
    with pytest.raises(AssertionError):
        launch_agent(task, "agentrelaysmall")


# ── send_prompt ───────────────────────────────────────────────────────────────

def test_send_prompt_sends_to_pane():
    with patch("agentrelaysmall.task_launcher.time.sleep"), \
         patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        send_prompt("%3", "do the thing", startup_delay=0)
    cmd = mock_run.call_args[0][0]
    assert "%3" in cmd
    assert "do the thing" in cmd
    assert "Enter" in cmd


def test_send_prompt_sleeps_before_sending():
    with patch("agentrelaysmall.task_launcher.time.sleep") as mock_sleep, \
         patch("agentrelaysmall.task_launcher.subprocess.run"):
        send_prompt("%3", "prompt", startup_delay=5.0)
    mock_sleep.assert_called_once_with(5.0)


# ── remove_worktree ───────────────────────────────────────────────────────────

def test_remove_worktree_calls_git_commands(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path / "worktree"
    task.state.branch_name = "task/demo/task_001"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        remove_worktree(task)
    calls = mock_run.call_args_list
    assert any("worktree" in str(c) and "remove" in str(c) for c in calls)
    assert any("branch" in str(c) and "-d" in str(c) for c in calls)


def test_remove_worktree_requires_worktree_path():
    task = make_task()
    task.state.branch_name = "task/demo/task_001"
    with pytest.raises(AssertionError):
        remove_worktree(task)


def test_remove_worktree_requires_branch_name(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path / "worktree"
    with pytest.raises(AssertionError):
        remove_worktree(task)


# ── poll_for_completion ───────────────────────────────────────────────────────

def test_poll_detects_existing_done(tmp_path):
    task = make_task()
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    signal_dir.mkdir(parents=True)
    (signal_dir / ".done").write_text("2024-01-01T00:00:00+00:00")
    result = asyncio.run(poll_for_completion(task, "demo", tmp_path, poll_interval=0.05))
    assert result == "done"


def test_poll_detects_existing_failed(tmp_path):
    task = make_task()
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    signal_dir.mkdir(parents=True)
    (signal_dir / ".failed").write_text("2024-01-01T00:00:00+00:00\noops")
    result = asyncio.run(poll_for_completion(task, "demo", tmp_path, poll_interval=0.05))
    assert result == "failed"


async def _write_after_delay(path: Path, delay: float) -> None:
    await asyncio.sleep(delay)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("done")


def test_poll_waits_for_done(tmp_path):
    task = make_task()
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    done_file = signal_dir / ".done"

    async def run() -> str:
        results = await asyncio.gather(
            poll_for_completion(task, "demo", tmp_path, poll_interval=0.05),
            _write_after_delay(done_file, 0.2),
        )
        return str(results[0])

    assert asyncio.run(run()) == "done"
