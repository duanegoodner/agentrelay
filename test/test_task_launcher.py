import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentrelaysmall.agent_task import AgentTask
from agentrelaysmall.task_launcher import (
    close_agent_pane,
    commit_pixi_lock_to_main,
    create_worktree,
    delete_remote_branches,
    launch_agent,
    list_remote_task_branches,
    merge_pr,
    neutralize_pixi_lock_in_pr,
    pixi_toml_changed_in_pr,
    poll_for_completion,
    pull_main,
    read_done_note,
    read_run_info,
    record_run_start,
    remove_worktree,
    reset_target_repo_to_head,
    run_pixi_install,
    save_agent_log,
    save_pr_summary,
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
        [
            "git",
            "-C",
            str(target_repo),
            "worktree",
            "add",
            "-b",
            "task/demo/task_001",
            str(expected_path),
            "main",
        ],
        check=True,
    )


def test_create_worktree_sets_state(tmp_path):
    task = make_task()
    target_repo = tmp_path / "target"
    with patch("agentrelaysmall.task_launcher.subprocess.run"):
        result = create_worktree(
            task, "demo", tmp_path, target_repo, base_branch="main"
        )
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
    with (
        patch(
            "agentrelaysmall.task_launcher.subprocess.check_output",
            return_value=b"%3\n",
        ) as mock_out,
        patch("agentrelaysmall.task_launcher.subprocess.run"),
    ):
        launch_agent(task, "agentrelaysmall")
    cmd = mock_out.call_args[0][0]
    assert "tmux" in cmd
    assert "new-window" in cmd
    assert "agentrelaysmall" in cmd
    assert "task_001" in cmd


def test_launch_agent_sends_claude_command(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path
    with (
        patch(
            "agentrelaysmall.task_launcher.subprocess.check_output",
            return_value=b"%3\n",
        ),
        patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run,
    ):
        launch_agent(task, "agentrelaysmall")
    cmd = mock_run.call_args[0][0]
    assert any("claude" in part for part in cmd)
    assert any("--dangerously-skip-permissions" in part for part in cmd)


def test_launch_agent_sets_pane_id(tmp_path):
    task = make_task()
    task.state.worktree_path = tmp_path
    with (
        patch(
            "agentrelaysmall.task_launcher.subprocess.check_output",
            return_value=b"%7\n",
        ),
        patch("agentrelaysmall.task_launcher.subprocess.run"),
    ):
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
    with (
        patch("agentrelaysmall.task_launcher.time.sleep"),
        patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run,
    ):
        send_prompt(
            "%3", "do the thing", bypass_delay=0, startup_delay=0, submit_delay=0
        )
    # First call sends Down to move cursor to "Yes, I accept"
    first_call_args = mock_run.call_args_list[0][0][0]
    assert "%3" in first_call_args
    assert "Down" in first_call_args
    # Second call sends Enter to confirm
    second_call_args = mock_run.call_args_list[1][0][0]
    assert "%3" in second_call_args
    assert "Enter" in second_call_args


def test_send_prompt_sends_prompt_to_pane():
    with (
        patch("agentrelaysmall.task_launcher.time.sleep"),
        patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run,
    ):
        send_prompt(
            "%3", "do the thing", bypass_delay=0, startup_delay=0, submit_delay=0
        )
    # Third call (index 2) sends the prompt text only
    cmd = mock_run.call_args_list[2][0][0]
    assert "%3" in cmd
    assert "do the thing" in cmd


def test_send_prompt_sends_enter_last():
    with (
        patch("agentrelaysmall.task_launcher.time.sleep"),
        patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run,
    ):
        send_prompt(
            "%3", "do the thing", bypass_delay=0, startup_delay=0, submit_delay=0
        )
    # Last call sends Enter to submit the prompt
    last_cmd = mock_run.call_args_list[-1][0][0]
    assert "%3" in last_cmd
    assert "Enter" in last_cmd
    assert len(mock_run.call_args_list) == 4


def test_send_prompt_sleeps_four_times():
    with (
        patch("agentrelaysmall.task_launcher.time.sleep") as mock_sleep,
        patch("agentrelaysmall.task_launcher.subprocess.run"),
    ):
        send_prompt(
            "%3", "prompt", bypass_delay=4.0, startup_delay=6.0, submit_delay=0.5
        )
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
    (signal_dir / ".done").write_text(
        "2024-01-01T00:00:00+00:00\nhttps://github.com/org/repo/pull/42"
    )
    assert (
        read_done_note(task, "demo", tmp_path) == "https://github.com/org/repo/pull/42"
    )


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
    assert any(
        "worktree" in str(c) and "remove" in str(c) and "force" in str(c) for c in calls
    )
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
    result = asyncio.run(
        poll_for_completion(task, "demo", tmp_path, poll_interval=0.05)
    )
    assert result == "done"


def test_poll_detects_existing_failed(tmp_path):
    task = make_task()
    signal_dir = tmp_path / ".workflow" / "demo" / "signals" / "task_001"
    signal_dir.mkdir(parents=True)
    (signal_dir / ".failed").write_text("2024-01-01T00:00:00+00:00\noops")
    result = asyncio.run(
        poll_for_completion(task, "demo", tmp_path, poll_interval=0.05)
    )
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


# ── pixi_toml_changed_in_pr ───────────────────────────────────────────────────


def test_pixi_toml_changed_in_pr_returns_true_when_present():
    pr_url = "https://github.com/org/repo/pull/42"
    payload = '["pixi.toml", "src/foo.py"]'
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = payload
        assert pixi_toml_changed_in_pr(pr_url) is True
    cmd = mock_run.call_args[0][0]
    assert "gh" in cmd
    assert "pr" in cmd
    assert "view" in cmd
    assert pr_url in cmd


def test_pixi_toml_changed_in_pr_returns_false_when_absent():
    pr_url = "https://github.com/org/repo/pull/42"
    payload = '["src/foo.py", "README.md"]'
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = payload
        assert pixi_toml_changed_in_pr(pr_url) is False


def test_pixi_toml_changed_in_pr_returns_false_on_gh_error():
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        assert pixi_toml_changed_in_pr("https://github.com/org/repo/pull/1") is False


# ── run_pixi_install ──────────────────────────────────────────────────────────


def test_run_pixi_install_returns_true_on_success(tmp_path):
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert run_pixi_install(tmp_path) is True
    cmd = mock_run.call_args[0][0]
    assert "pixi" in cmd
    assert "install" in cmd
    assert str(tmp_path / "pixi.toml") in cmd


def test_run_pixi_install_returns_false_on_failure(tmp_path):
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert run_pixi_install(tmp_path) is False


# ── neutralize_pixi_lock_in_pr ────────────────────────────────────────────────


def _make_task_with_worktree(tmp_path: Path) -> AgentTask:
    task = make_task()
    task.state.worktree_path = tmp_path / "worktree"
    task.state.branch_name = "task/demo/task_001"
    return task


def test_neutralize_calls_git_fetch_and_checkout(tmp_path):
    task = _make_task_with_worktree(tmp_path)

    # diff returns empty → no pixi.lock change → no commit/push
    def fake_run(cmd, **kwargs):
        m = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        return m

    with patch(
        "agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run
    ) as mock_run:
        neutralize_pixi_lock_in_pr(task)
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert any("fetch" in c and "origin" in c and "main" in c for c in calls)
    assert any(
        "checkout" in c and "origin/main" in c and "pixi.lock" in c for c in calls
    )


def test_neutralize_commits_and_pushes_when_lock_changed(tmp_path):
    task = _make_task_with_worktree(tmp_path)
    call_count = [0]

    def fake_run(cmd, **kwargs):
        call_count[0] += 1
        # Third call is git diff --staged; return pixi.lock to trigger commit
        stdout = "pixi.lock\n" if "diff" in cmd else ""
        return type("R", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    with patch(
        "agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run
    ) as mock_run:
        neutralize_pixi_lock_in_pr(task)
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert any("commit" in c for c in calls)
    assert any("push" in c for c in calls)


def test_neutralize_skips_commit_when_lock_unchanged(tmp_path):
    task = _make_task_with_worktree(tmp_path)

    def fake_run(cmd, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch(
        "agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run
    ) as mock_run:
        neutralize_pixi_lock_in_pr(task)
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert not any("commit" in c for c in calls)
    assert not any("push" in c for c in calls)


# ── commit_pixi_lock_to_main ──────────────────────────────────────────────────


def test_commit_pixi_lock_stages_and_commits_when_changed(tmp_path):
    def fake_run(cmd, **kwargs):
        stdout = "pixi.lock\n" if "diff" in cmd else ""
        return type("R", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    with patch(
        "agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run
    ) as mock_run:
        commit_pixi_lock_to_main(tmp_path)
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert any("add" in c and "pixi.lock" in c for c in calls)
    assert any("commit" in c for c in calls)
    assert any("push" in c and "origin" in c and "main" in c for c in calls)


def test_commit_pixi_lock_skips_when_unchanged(tmp_path):
    def fake_run(cmd, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch(
        "agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run
    ) as mock_run:
        commit_pixi_lock_to_main(tmp_path)
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert any("add" in c and "pixi.lock" in c for c in calls)
    assert not any("commit" in c for c in calls)
    assert not any("push" in c for c in calls)


# ── record_run_start ──────────────────────────────────────────────────────────


def test_record_run_start_writes_run_info(tmp_path):
    sha = "abc1234def5678"

    def fake_run(cmd, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": sha + "\n", "stderr": ""})()

    with patch("agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run):
        record_run_start("demo", tmp_path)
    p = tmp_path / ".workflow" / "demo" / "run_info.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["start_head"] == sha
    assert "started_at" in data


def test_record_run_start_overwrites_existing(tmp_path):
    first_sha = "aaa111"
    second_sha = "bbb222"
    shas = iter([first_sha, second_sha])

    def fake_run(cmd, **kwargs):
        return type(
            "R", (), {"returncode": 0, "stdout": next(shas) + "\n", "stderr": ""}
        )()

    with patch("agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run):
        record_run_start("demo", tmp_path)
    with patch("agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run):
        record_run_start("demo", tmp_path)
    p = tmp_path / ".workflow" / "demo" / "run_info.json"
    data = json.loads(p.read_text())
    assert data["start_head"] == second_sha


# ── read_run_info ─────────────────────────────────────────────────────────────


def test_read_run_info_returns_dict(tmp_path):
    run_info_dir = tmp_path / ".workflow" / "demo"
    run_info_dir.mkdir(parents=True)
    payload = {"start_head": "deadbeef", "started_at": "2024-01-01T00:00:00+00:00"}
    (run_info_dir / "run_info.json").write_text(json.dumps(payload))
    result = read_run_info("demo", tmp_path)
    assert result == payload


# ── reset_target_repo_to_head ─────────────────────────────────────────────────


def test_reset_target_repo_calls_git_reset_and_push(tmp_path):
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        reset_target_repo_to_head("abc1234", tmp_path)
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert any("reset" in c and "--hard" in c and "abc1234" in c for c in calls)
    assert any(
        "push" in c and "--force-with-lease" in c and "origin" in c for c in calls
    )


# ── list_remote_task_branches ─────────────────────────────────────────────────


def test_list_remote_task_branches_parses_ls_remote_output(tmp_path):
    ls_remote_output = (
        "abc123\trefs/heads/task/demo/write_greet_fn\n"
        "def456\trefs/heads/task/demo/write_farewell_fn\n"
    )

    def fake_run(cmd, **kwargs):
        return type(
            "R", (), {"returncode": 0, "stdout": ls_remote_output, "stderr": ""}
        )()

    with patch("agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run):
        branches = list_remote_task_branches("demo", tmp_path)
    assert branches == ["task/demo/write_greet_fn", "task/demo/write_farewell_fn"]


def test_list_remote_task_branches_empty_when_none(tmp_path):
    def fake_run(cmd, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch("agentrelaysmall.task_launcher.subprocess.run", side_effect=fake_run):
        branches = list_remote_task_branches("demo", tmp_path)
    assert branches == []


# ── delete_remote_branches ────────────────────────────────────────────────────


def test_delete_remote_branches_passes_all_names(tmp_path):
    branches = ["task/demo/t1", "task/demo/t2"]
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        delete_remote_branches(branches, tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "push" in cmd
    assert "--delete" in cmd
    assert "task/demo/t1" in cmd
    assert "task/demo/t2" in cmd


def test_delete_remote_branches_skips_when_empty(tmp_path):
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        delete_remote_branches([], tmp_path)
    mock_run.assert_not_called()


# ── save_pr_summary ───────────────────────────────────────────────────────────


def test_save_pr_summary_writes_body_to_file(tmp_path):
    signal_dir = tmp_path / "signals" / "task_001"
    pr_url = "https://github.com/org/repo/pull/42"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "## Summary\nDid the thing.\n"
        save_pr_summary(pr_url, signal_dir)
    assert (signal_dir / "summary.md").read_text() == "## Summary\nDid the thing."


def test_save_pr_summary_calls_gh_pr_view(tmp_path):
    signal_dir = tmp_path / "signals" / "task_001"
    pr_url = "https://github.com/org/repo/pull/42"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "some body\n"
        save_pr_summary(pr_url, signal_dir)
    cmd = mock_run.call_args[0][0]
    assert "gh" in cmd
    assert "pr" in cmd
    assert "view" in cmd
    assert pr_url in cmd
    assert "--json" in cmd
    assert "body" in cmd


def test_save_pr_summary_skips_when_gh_fails(tmp_path):
    signal_dir = tmp_path / "signals" / "task_001"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        save_pr_summary("https://github.com/org/repo/pull/1", signal_dir)
    assert not (signal_dir / "summary.md").exists()


def test_save_pr_summary_skips_when_body_empty(tmp_path):
    signal_dir = tmp_path / "signals" / "task_001"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        save_pr_summary("https://github.com/org/repo/pull/1", signal_dir)
    assert not (signal_dir / "summary.md").exists()


def test_save_pr_summary_creates_signal_dir(tmp_path):
    signal_dir = tmp_path / "deep" / "nested" / "dir"
    with patch("agentrelaysmall.task_launcher.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "body text\n"
        save_pr_summary("https://github.com/org/repo/pull/1", signal_dir)
    assert (signal_dir / "summary.md").exists()
