"""Tests for ShellGateChecker."""

import tempfile
from pathlib import Path

from agentrelay.task import AgentRole, Task
from agentrelay.task_runner.implementations.task_gate_checker import (
    GATE_OUTPUT_FILE,
    ShellGateChecker,
)
from agentrelay.task_runtime import TaskRuntime


def _make_runtime(
    command: str,
    tmp_path: Path,
    *,
    max_gate_attempts: int | None = None,
) -> TaskRuntime:
    runtime = TaskRuntime(
        task=Task(
            id="gated_task",
            role=AgentRole.GENERIC,
            completion_gate=command,
            max_gate_attempts=max_gate_attempts,
        )
    )
    signal_dir = tmp_path / "signals" / "gated_task"
    signal_dir.mkdir(parents=True, exist_ok=True)
    runtime.state.signal_dir = signal_dir
    runtime.state.worktree_path = tmp_path
    return runtime


class TestShellGateChecker:
    def test_passing_gate(self, tmp_path: Path) -> None:
        runtime = _make_runtime("true", tmp_path)
        checker = ShellGateChecker()

        result = checker.check_gate(runtime)

        assert result.passed is True

    def test_failing_gate(self, tmp_path: Path) -> None:
        runtime = _make_runtime("false", tmp_path)
        checker = ShellGateChecker()

        result = checker.check_gate(runtime)

        assert result.passed is False

    def test_captures_stdout_and_stderr(self, tmp_path: Path) -> None:
        runtime = _make_runtime(
            'echo "hello stdout" && echo "hello stderr" >&2',
            tmp_path,
        )
        checker = ShellGateChecker()

        result = checker.check_gate(runtime)

        assert result.passed is True
        assert "hello stdout" in result.output
        assert "hello stderr" in result.output

    def test_writes_output_file(self, tmp_path: Path) -> None:
        runtime = _make_runtime('echo "gate output"', tmp_path)
        checker = ShellGateChecker()

        checker.check_gate(runtime)

        assert runtime.state.signal_dir is not None
        output_file = runtime.state.signal_dir / GATE_OUTPUT_FILE
        assert output_file.is_file()
        assert "gate output" in output_file.read_text()

    def test_output_file_overwritten_on_each_attempt(self, tmp_path: Path) -> None:
        runtime = _make_runtime('echo "attempt output"', tmp_path)
        checker = ShellGateChecker()

        # First run.
        checker.check_gate(runtime)
        assert runtime.state.signal_dir is not None
        output_file = runtime.state.signal_dir / GATE_OUTPUT_FILE

        # Overwrite task command and run again.
        runtime2 = _make_runtime('echo "second output"', tmp_path)
        runtime2.state.signal_dir = runtime.state.signal_dir
        checker.check_gate(runtime2)

        content = output_file.read_text()
        assert "second output" in content

    def test_command_not_found(self, tmp_path: Path) -> None:
        runtime = _make_runtime("nonexistent_command_xyz_12345", tmp_path)
        checker = ShellGateChecker()

        result = checker.check_gate(runtime)

        assert result.passed is False
        assert result.output != ""

    def test_runs_in_worktree_directory(self, tmp_path: Path) -> None:
        runtime = _make_runtime("pwd", tmp_path)
        checker = ShellGateChecker()

        result = checker.check_gate(runtime)

        assert result.passed is True
        assert str(tmp_path) in result.output

    def test_exit_code_nonzero(self, tmp_path: Path) -> None:
        runtime = _make_runtime("exit 42", tmp_path)
        checker = ShellGateChecker()

        result = checker.check_gate(runtime)

        assert result.passed is False

    def test_no_signal_dir_skips_file_write(self) -> None:
        """Gate runs even without a signal_dir (output not saved to file)."""
        with tempfile.TemporaryDirectory() as td:
            runtime = TaskRuntime(
                task=Task(
                    id="no_sig",
                    role=AgentRole.GENERIC,
                    completion_gate="true",
                )
            )
            runtime.state.worktree_path = Path(td)
            # signal_dir is None

            checker = ShellGateChecker()
            result = checker.check_gate(runtime)

            assert result.passed is True
