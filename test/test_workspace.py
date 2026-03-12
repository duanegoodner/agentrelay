"""Tests for workspace reference types."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agentrelay.workspace import LocalWorkspaceRef


def test_local_workspace_ref_is_frozen() -> None:
    ref = LocalWorkspaceRef(worktree_path=Path("/tmp/w"), branch_name="feat")

    assert ref.worktree_path == Path("/tmp/w")
    assert ref.branch_name == "feat"
    with pytest.raises(FrozenInstanceError):
        ref.branch_name = "other"  # type: ignore[misc]
