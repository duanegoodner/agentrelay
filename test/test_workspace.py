"""Tests for workspace reference types."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agentrelay.workspace import LocalWorkspaceRef, RemoteWorkspaceRef


def test_local_workspace_ref_is_frozen_and_tagged() -> None:
    ref = LocalWorkspaceRef(worktree_path=Path("/tmp/w"), branch_name="feat")

    assert ref.kind == "local"
    assert ref.worktree_path == Path("/tmp/w")
    assert ref.branch_name == "feat"
    with pytest.raises(FrozenInstanceError):
        ref.branch_name = "other"  # type: ignore[misc]


def test_remote_workspace_ref_fields_and_kind() -> None:
    ref = RemoteWorkspaceRef(
        workspace_id="ws-123",
        branch_name="feature/cloud",
        workspace_uri="https://api.example/workspaces/ws-123",
        repo_ref="org/repo@abc123",
        execution_target="job-17",
        artifacts_uri="s3://bucket/path/",
    )

    assert ref.kind == "remote"
    assert ref.workspace_id == "ws-123"
    assert ref.workspace_uri is not None
    assert ref.repo_ref == "org/repo@abc123"
    assert ref.execution_target == "job-17"
    assert ref.artifacts_uri == "s3://bucket/path/"
