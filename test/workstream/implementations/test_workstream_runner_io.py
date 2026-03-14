"""Tests for WorkstreamRunnerIO composition with concrete implementations."""

from __future__ import annotations

from pathlib import Path

from agentrelay.workstream.core.io import WorkstreamRunnerIO
from agentrelay.workstream.implementations import (
    GhWorkstreamMerger,
    GitWorkstreamPreparer,
    GitWorkstreamTeardown,
)


class TestWorkstreamRunnerIOComposition:
    """Verify WorkstreamRunnerIO can be composed from all implementations."""

    def test_constructs_from_all_implementations(self) -> None:
        """WorkstreamRunnerIO accepts all three concrete implementations."""
        io = WorkstreamRunnerIO(
            preparer=GitWorkstreamPreparer(repo_path=Path("/repo"), graph_name="demo"),
            merger=GhWorkstreamMerger(repo_path=Path("/repo")),
            teardown_handler=GitWorkstreamTeardown(repo_path=Path("/repo")),
        )

        assert io.preparer is not None
        assert io.merger is not None
        assert io.teardown_handler is not None
