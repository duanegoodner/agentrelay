"""Implementation of :class:`~agentrelay.task_runner.core.io.TaskGateChecker`.

Classes:
    ShellGateChecker: Runs a completion gate shell command in the task worktree
    and captures output.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from agentrelay.ops import signals
from agentrelay.task_runner.core.io import GateCheckResult
from agentrelay.task_runtime import TaskRuntime

#: Filename for capturing the last gate command output in the signal directory.
GATE_OUTPUT_FILE = "gate_last_output.txt"


@dataclass
class ShellGateChecker:
    """Run a completion gate shell command and return the result.

    Executes the gate command from ``runtime.task.completion_gate`` in the
    task's workstream worktree.  Captures combined stdout and stderr to
    ``gate_last_output.txt`` in the signal directory.

    The checker does NOT raise on command failure — a non-zero exit code
    is returned as ``GateCheckResult(passed=False, ...)``.
    """

    def check_gate(self, runtime: TaskRuntime) -> GateCheckResult:
        """Execute the completion gate command for a task.

        Args:
            runtime: Runtime envelope with gate command and worktree path.

        Returns:
            GateCheckResult: Pass/fail outcome and captured output.
        """
        command = runtime.task.completion_gate
        assert command is not None, "check_gate called without completion_gate"
        cwd = runtime.state.worktree_path

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            output = result.stdout + result.stderr
            passed = result.returncode == 0
        except subprocess.TimeoutExpired as exc:
            output = f"Gate command timed out after 600s: {command}\n"
            if exc.stdout:
                output += (
                    exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode()
                )
            if exc.stderr:
                output += (
                    exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode()
                )
            passed = False
        except Exception as exc:
            output = f"Gate command error: {type(exc).__name__}: {exc}\n"
            passed = False

        if runtime.state.signal_dir is not None:
            signals.write_text(runtime.state.signal_dir, GATE_OUTPUT_FILE, output)

        return GateCheckResult(passed=passed, output=output)
