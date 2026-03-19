"""Output package — presentation layer for orchestrator events and results."""

from agentrelay.output.console import ConsoleListener, print_summary

__all__ = [
    "ConsoleListener",
    "print_summary",
]
