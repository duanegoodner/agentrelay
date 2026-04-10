"""Tests for the top-level agentrelay CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentrelay.cli import (
    _do_dry_run,
    _handle_check,
    _handle_dry_run,
    _handle_list,
    _handle_reset,
    _handle_run,
    _resolve_graph_path,
    _resolve_graph_with_index,
    _resolve_repo_path,
    build_parser,
)

# --- build_parser: run subcommand ---


def test_run_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "graph.yaml"])
    assert args.command == "run"
    assert args.graph == "graph.yaml"
    assert args.target_repo is None
    assert args.max_concurrency is None
    assert args.max_task_attempts is None
    assert args.teardown_mode is None
    assert args.tmux_session is None
    assert args.model is None
    assert args.credentials is None
    assert args.anthropic_credential is None
    assert args.fail_fast_workstream is None
    assert args.fail_fast_internal is None
    assert args.sandbox is None
    assert args.dry_run is False
    assert args.verbose is False


def test_run_all_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "graph.yaml",
            "--target-repo",
            "/tmp/repo",
            "--max-concurrency",
            "4",
            "--max-task-attempts",
            "3",
            "--teardown-mode",
            "always",
            "--tmux-session",
            "mysession",
            "--model",
            "claude-opus-4-6",
            "--credentials",
            "/tmp/creds.yaml",
            "--anthropic-credential",
            "max_plan",
            "--sandbox",
            "oci",
            "--fail-fast-workstream",
            "--fail-fast-internal",
            "--dry-run",
            "-v",
        ]
    )
    assert args.target_repo == "/tmp/repo"
    assert args.max_concurrency == 4
    assert args.max_task_attempts == 3
    assert args.teardown_mode == "always"
    assert args.tmux_session == "mysession"
    assert args.model == "claude-opus-4-6"
    assert args.credentials == "/tmp/creds.yaml"
    assert args.anthropic_credential == "max_plan"
    assert args.sandbox == "oci"
    assert args.fail_fast_workstream is True
    assert args.fail_fast_internal is True
    assert args.dry_run is True
    assert args.verbose is True


def test_run_no_fail_fast_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "graph.yaml",
            "--no-fail-fast-workstream",
            "--no-fail-fast-internal",
        ]
    )
    assert args.fail_fast_workstream is False
    assert args.fail_fast_internal is False


# --- build_parser: reset subcommand ---


def test_reset_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["reset", "graph.yaml"])
    assert args.command == "reset"
    assert args.graph == "graph.yaml"
    assert args.target_repo is None
    assert args.yes is False


def test_reset_yes_long() -> None:
    parser = build_parser()
    args = parser.parse_args(["reset", "graph.yaml", "--yes"])
    assert args.yes is True


def test_reset_yes_short() -> None:
    parser = build_parser()
    args = parser.parse_args(["reset", "graph.yaml", "-y"])
    assert args.yes is True


def test_reset_target_repo() -> None:
    parser = build_parser()
    args = parser.parse_args(["reset", "graph.yaml", "--target-repo", "/tmp/repo"])
    assert args.target_repo == "/tmp/repo"


# --- build_parser: check subcommand ---


def test_check_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["check"])
    assert args.command == "check"
    assert args.target_repo is None
    assert args.env == "tmux"


def test_check_env() -> None:
    parser = build_parser()
    args = parser.parse_args(["check", "--env", "docker"])
    assert args.env == "docker"


def test_check_env_short() -> None:
    parser = build_parser()
    args = parser.parse_args(["check", "-e", "docker"])
    assert args.env == "docker"


def test_check_target_repo() -> None:
    parser = build_parser()
    args = parser.parse_args(["check", "--target-repo", "/tmp/repo"])
    assert args.target_repo == "/tmp/repo"


# --- build_parser: dry-run subcommand ---


def test_dry_run_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["dry-run", "graph.yaml"])
    assert args.command == "dry-run"
    assert args.graph == "graph.yaml"
    assert args.target_repo is None


def test_dry_run_target_repo() -> None:
    parser = build_parser()
    args = parser.parse_args(["dry-run", "graph.yaml", "--target-repo", "/tmp/repo"])
    assert args.target_repo == "/tmp/repo"


# --- build_parser: no subcommand ---


def test_no_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.command is None


# --- short options ---


def test_run_short_options() -> None:
    """Short option aliases resolve to the same attributes."""
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "graph.yaml",
            "-t",
            "/tmp/repo",
            "-m",
            "claude-opus-4-6",
            "-c",
            "4",
            "-a",
            "3",
            "-T",
            "always",
            "-s",
            "mysession",
            "-C",
            "/tmp/creds.yaml",
            "-A",
            "max_plan",
            "-S",
            "oci",
            "-W",
            "-I",
            "-d",
        ]
    )
    assert args.target_repo == "/tmp/repo"
    assert args.model == "claude-opus-4-6"
    assert args.max_concurrency == 4
    assert args.max_task_attempts == 3
    assert args.teardown_mode == "always"
    assert args.tmux_session == "mysession"
    assert args.credentials == "/tmp/creds.yaml"
    assert args.anthropic_credential == "max_plan"
    assert args.sandbox == "oci"
    assert args.fail_fast_workstream is True
    assert args.fail_fast_internal is True
    assert args.dry_run is True


def test_run_sandbox_none() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "graph.yaml", "--sandbox", "none"])
    assert args.sandbox == "none"


def test_run_sandbox_default_is_none() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "graph.yaml"])
    assert args.sandbox is None


def test_reset_short_target_repo() -> None:
    parser = build_parser()
    args = parser.parse_args(["reset", "graph.yaml", "-t", "/tmp/repo"])
    assert args.target_repo == "/tmp/repo"


def test_dry_run_short_target_repo() -> None:
    parser = build_parser()
    args = parser.parse_args(["dry-run", "graph.yaml", "-t", "/tmp/repo"])
    assert args.target_repo == "/tmp/repo"


def test_check_short_target_repo() -> None:
    parser = build_parser()
    args = parser.parse_args(["check", "-t", "/tmp/repo"])
    assert args.target_repo == "/tmp/repo"


# --- _resolve_repo_path ---


class _FakeArgs:
    """Minimal namespace for testing _resolve_repo_path."""

    def __init__(self, target_repo: str | None = None) -> None:
        self.target_repo = target_repo


def test_resolve_repo_path_defaults_to_cwd() -> None:
    args = _FakeArgs(target_repo=None)
    assert _resolve_repo_path(args) == Path.cwd()  # type: ignore[arg-type]


def test_resolve_repo_path_uses_target_repo(tmp_path: Path) -> None:
    args = _FakeArgs(target_repo=str(tmp_path))
    assert _resolve_repo_path(args) == tmp_path.resolve()  # type: ignore[arg-type]


# --- _resolve_graph_path ---


def test_resolve_graph_path_returns_resolved(tmp_path: Path) -> None:
    graph = tmp_path / "g.yaml"
    graph.write_text("name: test\ntasks: []\n")
    result = _resolve_graph_path(str(graph))
    assert result == graph.resolve()


def test_resolve_graph_path_exits_on_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="1"):
        _resolve_graph_path(str(tmp_path / "nonexistent.yaml"))


# --- _do_dry_run ---


@patch("agentrelay.cli._dry_run_conflict_check")
@patch("agentrelay.cli.dry_run")
def test_do_dry_run_calls_dry_run_and_conflict_check(
    mock_dry_run: MagicMock,
    mock_conflict_check: MagicMock,
    tmp_path: Path,
) -> None:
    graph = tmp_path / "g.yaml"
    graph.write_text("name: test-graph\ntasks: []\n")
    repo = tmp_path / "repo"
    repo.mkdir()

    _do_dry_run(graph, repo)

    mock_dry_run.assert_called_once_with(graph)
    mock_conflict_check.assert_called_once_with(repo, "test-graph")


@patch("agentrelay.cli._dry_run_conflict_check")
@patch("agentrelay.cli.dry_run")
def test_do_dry_run_skips_conflict_check_when_no_name(
    mock_dry_run: MagicMock,
    mock_conflict_check: MagicMock,
    tmp_path: Path,
) -> None:
    graph = tmp_path / "g.yaml"
    graph.write_text("tasks: []\n")

    _do_dry_run(graph, tmp_path)

    mock_dry_run.assert_called_once()
    mock_conflict_check.assert_not_called()


# --- _handle_run ---


@patch("agentrelay.cli.run_graph", new_callable=AsyncMock)
@patch("agentrelay.cli._print_result")
def test_handle_run_calls_run_graph(
    mock_print: MagicMock,
    mock_run: AsyncMock,
    tmp_path: Path,
) -> None:
    from agentrelay.orchestrator import OrchestratorOutcome, OrchestratorResult

    graph = tmp_path / "g.yaml"
    graph.write_text("name: test\ntasks: []\n")

    mock_run.return_value = OrchestratorResult(
        outcome=OrchestratorOutcome.SUCCEEDED,
        task_runtimes={},
        workstream_runtimes={},
        events=(),
    )

    parser = build_parser()
    args = parser.parse_args(["run", str(graph), "--target-repo", str(tmp_path)])
    _handle_run(args)

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args
    assert call_kwargs.kwargs["graph_path"] == graph.resolve()
    assert call_kwargs.kwargs["repo_path"] == tmp_path.resolve()


@patch("agentrelay.cli._do_dry_run")
def test_handle_run_dry_run_flag_delegates(
    mock_do_dry_run: MagicMock,
    tmp_path: Path,
) -> None:
    graph = tmp_path / "g.yaml"
    graph.write_text("name: test\ntasks: []\n")

    parser = build_parser()
    args = parser.parse_args(["run", str(graph), "--dry-run"])
    _handle_run(args)

    mock_do_dry_run.assert_called_once()


@patch("agentrelay.cli.run_graph", new_callable=AsyncMock)
@patch("agentrelay.cli._print_result")
def test_handle_run_target_repo_forwarded(
    mock_print: MagicMock,
    mock_run: AsyncMock,
    tmp_path: Path,
) -> None:
    from agentrelay.orchestrator import OrchestratorOutcome, OrchestratorResult

    graph = tmp_path / "g.yaml"
    graph.write_text("name: test\ntasks: []\n")
    target = tmp_path / "myrepo"
    target.mkdir()

    mock_run.return_value = OrchestratorResult(
        outcome=OrchestratorOutcome.SUCCEEDED,
        task_runtimes={},
        workstream_runtimes={},
        events=(),
    )

    parser = build_parser()
    args = parser.parse_args(["run", str(graph), "--target-repo", str(target)])
    _handle_run(args)

    assert mock_run.call_args.kwargs["repo_path"] == target.resolve()


@patch("agentrelay.cli.run_graph", new_callable=AsyncMock)
def test_handle_run_conflict_error_exits_1(
    mock_run: AsyncMock,
    tmp_path: Path,
) -> None:
    from agentrelay.run_graph import _ConflictError

    graph = tmp_path / "g.yaml"
    graph.write_text("name: test\ntasks: []\n")

    mock_run.side_effect = _ConflictError("leftover state")

    parser = build_parser()
    args = parser.parse_args(["run", str(graph)])
    with pytest.raises(SystemExit, match="1"):
        _handle_run(args)


@patch("agentrelay.cli.run_graph", new_callable=AsyncMock)
@patch("agentrelay.cli._print_result")
def test_handle_run_failed_outcome_exits_1(
    mock_print: MagicMock,
    mock_run: AsyncMock,
    tmp_path: Path,
) -> None:
    from agentrelay.orchestrator import OrchestratorOutcome, OrchestratorResult

    graph = tmp_path / "g.yaml"
    graph.write_text("name: test\ntasks: []\n")

    mock_run.return_value = OrchestratorResult(
        outcome=OrchestratorOutcome.COMPLETED_WITH_FAILURES,
        task_runtimes={},
        workstream_runtimes={},
        events=(),
    )

    parser = build_parser()
    args = parser.parse_args(["run", str(graph)])
    with pytest.raises(SystemExit, match="1"):
        _handle_run(args)


# --- _handle_reset ---


@patch("agentrelay.cli.reset_graph")
@patch("agentrelay.cli._resolve_graph_name", return_value="test-graph")
def test_handle_reset_calls_reset_graph(
    mock_resolve: MagicMock,
    mock_reset: MagicMock,
    tmp_path: Path,
) -> None:
    graph = tmp_path / "g.yaml"
    graph.write_text("name: test-graph\ntasks: []\n")

    parser = build_parser()
    args = parser.parse_args(
        ["reset", str(graph), "--target-repo", str(tmp_path), "--yes"]
    )
    _handle_reset(args)

    mock_resolve.assert_called_once_with(graph.resolve())
    mock_reset.assert_called_once_with("test-graph", tmp_path.resolve(), yes=True)


@patch("agentrelay.cli.reset_graph", side_effect=FileNotFoundError("no run_info"))
@patch("agentrelay.cli._resolve_graph_name", return_value="test-graph")
def test_handle_reset_file_not_found_exits_1(
    mock_resolve: MagicMock,
    mock_reset: MagicMock,
    tmp_path: Path,
) -> None:
    graph = tmp_path / "g.yaml"
    graph.write_text("name: test-graph\ntasks: []\n")

    parser = build_parser()
    args = parser.parse_args(["reset", str(graph)])
    with pytest.raises(SystemExit, match="1"):
        _handle_reset(args)


# --- _handle_check ---


@patch("agentrelay.cli.subprocess.run")
def test_handle_check_calls_subprocess(
    mock_subprocess: MagicMock,
    tmp_path: Path,
) -> None:
    mock_subprocess.return_value = MagicMock(returncode=0)

    # Patch the script path to exist.
    script = Path(__file__).resolve().parent.parent / "src" / "agentrelay" / "cli.py"
    expected_script = script.parent.parent.parent / "tools" / "e2e_check.sh"

    parser = build_parser()
    args = parser.parse_args(["check", "--target-repo", str(tmp_path)])

    if expected_script.is_file():
        with pytest.raises(SystemExit, match="0"):
            _handle_check(args)
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "bash"
        assert call_args[1] == str(expected_script)
        assert call_args[2] == str(tmp_path.resolve())
        assert call_args[3:] == ["--env", "tmux"]
    else:
        # Running from installed package — script not found.
        with pytest.raises(SystemExit, match="1"):
            _handle_check(args)


@patch("agentrelay.cli.subprocess.run")
def test_handle_check_custom_env(
    mock_subprocess: MagicMock,
    tmp_path: Path,
) -> None:
    mock_subprocess.return_value = MagicMock(returncode=0)

    expected_script = Path(__file__).resolve().parent.parent / "tools" / "e2e_check.sh"

    parser = build_parser()
    args = parser.parse_args(
        ["check", "--target-repo", str(tmp_path), "--env", "docker"]
    )

    if expected_script.is_file():
        with pytest.raises(SystemExit, match="0"):
            _handle_check(args)
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[3:] == ["--env", "docker"]


# --- _handle_dry_run ---


@patch("agentrelay.cli._do_dry_run")
def test_handle_dry_run_subcommand(
    mock_do: MagicMock,
    tmp_path: Path,
) -> None:
    graph = tmp_path / "g.yaml"
    graph.write_text("name: test\ntasks: []\n")

    parser = build_parser()
    args = parser.parse_args(["dry-run", str(graph), "--target-repo", str(tmp_path)])
    _handle_dry_run(args)

    mock_do.assert_called_once_with(graph.resolve(), tmp_path.resolve())


# --- run_graph.py error message update ---


def test_conflict_error_message_uses_new_cli(tmp_path: Path) -> None:
    from agentrelay.run_graph import _check_for_conflicts, _ConflictError

    (tmp_path / ".workflow" / "test-graph").mkdir(parents=True)
    with pytest.raises(_ConflictError, match="agentrelay reset"):
        _check_for_conflicts(tmp_path, "test-graph")


# --- build_parser: --graph-dir on run ---


def test_run_graph_dir_default() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "graph.yaml"])
    assert args.graph_dir is None


def test_run_graph_dir_long() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "graph.yaml", "--graph-dir", "graphs/"])
    assert args.graph_dir == "graphs/"


def test_run_graph_dir_short() -> None:
    parser = build_parser()
    args = parser.parse_args(["run", "graph.yaml", "-g", "graphs/"])
    assert args.graph_dir == "graphs/"


# --- build_parser: --graph-dir on reset ---


def test_reset_graph_dir() -> None:
    parser = build_parser()
    args = parser.parse_args(["reset", "graph.yaml", "-g", "graphs/"])
    assert args.graph_dir == "graphs/"


# --- build_parser: --graph-dir on dry-run ---


def test_dry_run_graph_dir() -> None:
    parser = build_parser()
    args = parser.parse_args(["dry-run", "graph.yaml", "-g", "graphs/"])
    assert args.graph_dir == "graphs/"


# --- build_parser: list subcommand ---


def test_list_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["list", "-g", "graphs/"])
    assert args.command == "list"
    assert args.graph_dir == "graphs/"


def test_list_requires_graph_dir() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["list"])


# --- _resolve_graph_with_index ---


def _make_args(graph: str, graph_dir: str | None = None) -> MagicMock:
    """Build a minimal namespace for _resolve_graph_with_index."""
    args = MagicMock()
    args.graph = graph
    args.graph_dir = graph_dir
    return args


def test_resolve_graph_with_index_by_name(tmp_path: Path) -> None:
    g = tmp_path / "smoke" / "quick.yaml"
    g.parent.mkdir()
    g.write_text("name: quick-chained\ntasks: []\n")

    args = _make_args("quick-chained", graph_dir=str(tmp_path))
    result = _resolve_graph_with_index(args)
    assert result == g.resolve()


def test_resolve_graph_with_index_no_graph_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    g = tmp_path / "g.yaml"
    g.write_text("name: test\ntasks: []\n")

    args = _make_args(str(g), graph_dir=None)
    result = _resolve_graph_with_index(args)
    assert result == g.resolve()

    captured = capsys.readouterr()
    assert "name uniqueness not validated" in captured.err


def test_resolve_graph_with_index_duplicate_names_exits(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.yaml").write_text("name: dup\ntasks: []\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "two.yaml").write_text("name: dup\ntasks: []\n")

    args = _make_args("dup", graph_dir=str(tmp_path))
    with pytest.raises(SystemExit, match="1"):
        _resolve_graph_with_index(args)


def test_resolve_graph_with_index_name_not_found_exits(tmp_path: Path) -> None:
    g = tmp_path / "g.yaml"
    g.write_text("name: existing\ntasks: []\n")

    args = _make_args("nonexistent", graph_dir=str(tmp_path))
    with pytest.raises(SystemExit, match="1"):
        _resolve_graph_with_index(args)


# --- _handle_list ---


def test_handle_list_prints_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    g = tmp_path / "smoke" / "quick.yaml"
    g.parent.mkdir()
    g.write_text("name: quick-chained\ntasks: []\n")

    parser = build_parser()
    args = parser.parse_args(["list", "-g", str(tmp_path)])
    _handle_list(args)

    captured = capsys.readouterr()
    assert "quick-chained" in captured.out
    assert "smoke" in captured.out
    assert "NAME" in captured.out


def test_handle_list_empty_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = build_parser()
    args = parser.parse_args(["list", "-g", str(tmp_path)])
    _handle_list(args)

    captured = capsys.readouterr()
    assert "No graphs found." in captured.err


def test_handle_list_duplicate_names_exits(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.yaml").write_text("name: dup\ntasks: []\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "two.yaml").write_text("name: dup\ntasks: []\n")

    parser = build_parser()
    args = parser.parse_args(["list", "-g", str(tmp_path)])
    with pytest.raises(SystemExit, match="1"):
        _handle_list(args)
