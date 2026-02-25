import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentrelaysmall.agent_task import AgentTask
from agentrelaysmall.task_launcher import (
    close_agent_pane,
    create_worktree,
    launch_agent,
    merge_pr,
    poll_for_completion,
    pull_main,
    read_done_note,
    remove_worktree,
    save_agent_log,
    send_prompt,
    write_merged_signal,
    write_task_context,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def make_task(task_id: str = "task_001") -> AgentTask:
    return AgentTask(id=task_id, description="test task")


# ── create_worktree ───────────────────────────────────────────────────────────

def test_create_worktree_calls_git(tmp_path):
    task = make_task()
    target_repo = tmp_path / "target"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        create_worktree(task, "demo", tmp_path, target_repo)
    expected_path = tmp_path / "demo" / "task_001"
    mock_run.assert_called_once_with(
        ["git", "-C", str(target_repo), "worktree", "add",
         "-b", "task/demo/task_001", str(expected_path), "main"],
        check=True,
    )


def test_create_worktree_sets_state(tmp_path):
    task = make_task()
    target_repo = tmp_path / "target"
    with patch("agentrelaysmall.task_launcher.subprocess.run"):
        result = create_worktree(task, "demo", tmp_path, target_repo, base_branch="main")
    assert task.state.worktree_path == tmp_path / "demo" / "task_001"
    assert task.state.branch_name == "task/demo/task_001"
    assert result == task.state.worktree_path


def test_create_worktree_branch_uses_graph_name(tmp_path):
    task = make_task("task_002")
    target_repo = tmp_path / "target"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        create_worktree(task, "my-graph", tmp_path, target_repo)
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
    assert any("claude" in part for part in cmd)
    assert any("--dangerously-skip-permissions" in part for part in cmd)


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

def test_send_prompt_navigates_bypass_dialog():
    with patch("agentrelaysmall.task_launcher.time.sleep"), \
         patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        send_prompt("%3", "do the thing", bypass_delay=0, startup_delay=0, submit_delay=0)
    # First call sends Down to move cursor to "Yes, I accept"
    first_call_args = mock_run.call_args_list[0][0][0]
    assert "%3" in first_call_args
    assert "Down" in first_call_args
    # Second call sends Enter to confirm
    second_call_args = mock_run.call_args_list[1][0][0]
    assert "%3" in second_call_args
    assert "Enter" in second_call_args


def test_send_prompt_sends_prompt_to_pane():
    with patch("agentrelaysmall.task_launcher.time.sleep"), \
         patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        send_prompt("%3", "do the thing", bypass_delay=0, startup_delay=0, submit_delay=0)
    # Third call (index 2) sends the prompt text only
    cmd = mock_run.call_args_list[2][0][0]
    assert "%3" in cmd
    assert "do the thing" in cmd


def test_send_prompt_sends_enter_last():
    with patch("agentrelaysmall.task_launcher.time.sleep"), \
         patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        send_prompt("%3", "do the thing", bypass_delay=0, startup_delay=0, submit_delay=0)
    # Last call sends Enter to submit the prompt
    last_cmd = mock_run.call_args_list[-1][0][0]
    assert "%3" in last_cmd
    assert "Enter" in last_cmd
    assert len(mock_run.call_args_list) == 4


def test_send_prompt_sleeps_four_times():
    with patch("agentrelaysmall.task_launcher.time.sleep") as mock_sleep, \
         patch("agentrelaysmall.task_launcher.subprocess.run"):
        send_prompt("%3", "prompt", bypass_delay=4.0, startup_delay=6.0, submit_delay=0.5)
    assert mock_sleep.call_count == 4
    sleep_args = [c[0][0] for c in mock_sleep.call_args_list]
    assert 4.0 in sleep_args
    assert 0.2 in sleep_args
    assert 6.0 in sleep_args
    assert 0.5 in sleep_args


# ── read_done_note ────────────────────────────────────────────────────────────

def test_read_done_note_returns_note(tmp_path):
    task = make_task()
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    signal_dir.mkdir(parents=True)
    (signal_dir / ".done").write_text("2024-01-01T00:00:00+00:00\nhttps://github.com/org/repo/pull/42")
    assert read_done_note(task, "demo", tmp_path) == "https://github.com/org/repo/pull/42"


def test_read_done_note_returns_empty_when_no_note(tmp_path):
    task = make_task()
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    signal_dir.mkdir(parents=True)
    (signal_dir / ".done").write_text("2024-01-01T00:00:00+00:00")
    assert read_done_note(task, "demo", tmp_path) == ""


# ── merge_pr ──────────────────────────────────────────────────────────────────

def test_merge_pr_calls_gh():
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        merge_pr("https://github.com/org/repo/pull/42")
    cmd = mock_run.call_args[0][0]
    assert "gh" in cmd
    assert "pr" in cmd
    assert "merge" in cmd
    assert "https://github.com/org/repo/pull/42" in cmd


def test_merge_pr_uses_merge_strategy():
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        merge_pr("https://github.com/org/repo/pull/42")
    cmd = mock_run.call_args[0][0]
    assert "--merge" in cmd


# ── write_merged_signal ───────────────────────────────────────────────────────

def test_write_merged_signal_creates_file(tmp_path):
    task = make_task()
    write_merged_signal(task, "demo", tmp_path)
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    assert (signal_dir / ".merged").exists()


def test_write_merged_signal_contains_timestamp(tmp_path):
    task = make_task()
    write_merged_signal(task, "demo", tmp_path)
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    content = (signal_dir / ".merged").read_text()
    assert "T" in content  # ISO 8601 timestamp contains 'T'


def test_write_merged_signal_creates_signal_dir(tmp_path):
    task = make_task()
    write_merged_signal(task, "demo", tmp_path)
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    assert signal_dir.exists()


# ── close_agent_pane ─────────────────────────────────────────────────────────

def test_close_agent_pane_kills_window():
    task = make_task()
    task.state.pane_id = "%7"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        close_agent_pane(task)
    cmd = mock_run.call_args[0][0]
    assert "tmux" in cmd
    assert "kill-window" in cmd
    assert "%7" in cmd


def test_close_agent_pane_skips_when_no_pane_id():
    task = make_task()
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        close_agent_pane(task)
    mock_run.assert_not_called()


# ── save_agent_log ────────────────────────────────────────────────────────────

def test_save_agent_log_calls_tmux_capture_pane(tmp_path):
    task = make_task()
    task.state.pane_id = "%7"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.stdout = "log output"
        save_agent_log(task, tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "tmux" in cmd
    assert "capture-pane" in cmd
    assert "%7" in cmd
    assert "-p" in cmd
    assert "-S" in cmd


def test_save_agent_log_writes_to_signal_dir(tmp_path):
    task = make_task()
    task.state.pane_id = "%7"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.stdout = "agent output here"
        save_agent_log(task, tmp_path)
    assert (tmp_path / "agent.log").read_text() == "agent output here"


def test_save_agent_log_skips_when_no_pane_id(tmp_path):
    task = make_task()
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        save_agent_log(task, tmp_path)
    mock_run.assert_not_called()
    assert not (tmp_path / "agent.log").exists()


# ── remove_worktree ───────────────────────────────────────────────────────────

def test_remove_worktree_calls_git_commands(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path / "worktree"
    task.state.branch_name = "task/demo/task_001"
    target_repo = tmp_path / "target"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        remove_worktree(task, target_repo)
    calls = mock_run.call_args_list
    assert any("worktree" in str(c) and "remove" in str(c) and "force" in str(c) for c in calls)
    assert any("branch" in str(c) and "-D" in str(c) for c in calls)
    assert all(str(target_repo) in str(c) for c in calls)


def test_remove_worktree_requires_worktree_path(tmp_path):
    task = make_task()
    task.state.branch_name = "task/demo/task_001"
    with pytest.raises(AssertionError):
        remove_worktree(task, tmp_path)


def test_remove_worktree_requires_branch_name(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path / "worktree"
    with pytest.raises(AssertionError):
        remove_worktree(task, tmp_path)


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


# ── pull_main ─────────────────────────────────────────────────────────────────

def test_pull_main_returns_true_on_success(tmp_path):
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert pull_main(tmp_path) is True
    cmd = mock_run.call_args[0][0]
    assert "git" in cmd
    assert "pull" in cmd
    assert "--ff-only" in cmd


def test_pull_main_returns_false_on_failure(tmp_path):
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert pull_main(tmp_path) is False


def test_pull_main_uses_repo_root(tmp_path):
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        pull_main(tmp_path)
    cmd = mock_run.call_args[0][0]
    assert str(tmp_path) in cmd
