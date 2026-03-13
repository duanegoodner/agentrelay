"""Tests for TmuxTaskKickoff."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agentrelay.agent import TmuxAddress, TmuxAgent
from agentrelay.task import AgentRole, Task
from agentrelay.task_runner.core.io import TaskKickoff
from agentrelay.task_runner.implementations.task_kickoff import TmuxTaskKickoff
from agentrelay.task_runtime import TaskRuntime


def _make_runtime(
    signal_dir: Path | None = Path("/repo/.workflow/demo/signals/task_1"),
) -> TaskRuntime:
    runtime = TaskRuntime(task=Task(id="task_1", role=AgentRole.GENERIC))
    runtime.state.signal_dir = signal_dir
    return runtime


class TestTmuxTaskKickoff:
    """Tests for TmuxTaskKickoff.kickoff."""

    def test_sends_correct_instructions_path(self) -> None:
        """Sends the instructions.md path from signal_dir to the agent."""
        agent = MagicMock(spec=TmuxAgent)
        runtime = _make_runtime()
        kickoff = TmuxTaskKickoff()

        kickoff.kickoff(runtime, agent)

        agent.send_kickoff.assert_called_once_with(
            str(Path("/repo/.workflow/demo/signals/task_1/instructions.md"))
        )

    def test_raises_when_signal_dir_is_none(self) -> None:
        """Raises ValueError if signal_dir is not set."""
        agent = MagicMock(spec=TmuxAgent)
        runtime = _make_runtime(signal_dir=None)
        kickoff = TmuxTaskKickoff()

        with pytest.raises(ValueError, match="signal_dir"):
            kickoff.kickoff(runtime, agent)

    def test_satisfies_task_kickoff_protocol(self) -> None:
        """TmuxTaskKickoff satisfies the TaskKickoff protocol."""
        kickoff = TmuxTaskKickoff()
        assert isinstance(kickoff, TaskKickoff)
