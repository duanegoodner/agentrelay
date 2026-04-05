"""CLI entry points for agent-side task workflow commands.

Shell-friendly wrappers around :class:`~agentrelay.agent_sdk.TaskHelper`
so agents can call commands instead of writing inline Python:

.. code-block:: bash

    agentrelay-complete --title "Add feature X" --body "## Summary\n- ..."
    agentrelay-failed --reason "Tests cannot pass due to spec contradiction"
    agentrelay-concern --message "Spec says X but tests expect Y"
    agentrelay-ops-concern --message "pixi install took >30s"
    agentrelay-summary --message "## Summary\n- reviewed all tests"

All commands read ``$AGENTRELAY_SIGNAL_DIR`` from the environment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentrelay.agent_sdk.output_manifest import OutputAction
from agentrelay.agent_sdk.task_helper import TaskHelper


def complete() -> None:
    """CLI entry point: create PR and signal task completion."""
    parser = argparse.ArgumentParser(
        description="Create a PR and signal task completion.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="PR title (defaults to task ID)",
    )
    parser.add_argument(
        "--body",
        default=None,
        help="PR body in markdown (defaults to 'Automated task PR')",
    )
    args = parser.parse_args()

    try:
        helper = TaskHelper.from_env()
        helper.complete(title=args.title, body=args.body)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def complete_no_pr() -> None:
    """CLI entry point: signal task completion without creating a PR."""
    parser = argparse.ArgumentParser(
        description="Signal task completion without creating a PR.",
    )
    _ = parser.parse_args()

    try:
        helper = TaskHelper.from_env()
        helper.complete_without_pr()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def failed() -> None:
    """CLI entry point: signal task failure."""
    parser = argparse.ArgumentParser(
        description="Signal task failure.",
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="Human-readable reason for the failure",
    )
    args = parser.parse_args()

    try:
        helper = TaskHelper.from_env()
        helper.mark_failed(args.reason)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def concern() -> None:
    """CLI entry point: record a design concern."""
    parser = argparse.ArgumentParser(
        description="Record a design concern.",
    )
    parser.add_argument(
        "--message",
        required=True,
        help="Description of the concern",
    )
    args = parser.parse_args()

    try:
        helper = TaskHelper.from_env()
        helper.record_concern(args.message)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def ops_concern() -> None:
    """CLI entry point: record an operational concern."""
    parser = argparse.ArgumentParser(
        description="Record an operational concern.",
    )
    parser.add_argument(
        "--message",
        required=True,
        help="Description of the operational concern",
    )
    args = parser.parse_args()

    try:
        helper = TaskHelper.from_env()
        helper.record_ops_concern(args.message)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def summary() -> None:
    """CLI entry point: write a task summary."""
    parser = argparse.ArgumentParser(
        description="Write a task summary.",
    )
    parser.add_argument(
        "--message",
        required=True,
        help="Summary text (markdown)",
    )
    args = parser.parse_args()

    try:
        helper = TaskHelper.from_env()
        helper.write_summary(args.message)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def declare() -> None:
    """CLI entry point: declare a file in the output manifest."""
    parser = argparse.ArgumentParser(
        description="Declare a file in the output manifest.",
    )
    parser.add_argument(
        "--path",
        required=True,
        help="File path relative to the repository root",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=[a.value for a in OutputAction],
        help="Action performed on the file (created, modified, deleted)",
    )
    parser.add_argument(
        "--category",
        required=True,
        help="Semantic category (e.g. stubs, tests, implementation)",
    )
    args = parser.parse_args()

    try:
        helper = TaskHelper.from_env()
        helper.declare_output(Path(args.path), OutputAction(args.action), args.category)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
