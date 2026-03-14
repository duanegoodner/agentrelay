"""Concrete workstream protocol implementations.

This subpackage contains environment-specific implementations of the
per-step protocols defined in ``workstream.core.io``. Each module is named
after the protocol it implements.
"""

from agentrelay.workstream.implementations.workstream_merger import (
    GhWorkstreamMerger,
)
from agentrelay.workstream.implementations.workstream_preparer import (
    GitWorkstreamPreparer,
)
from agentrelay.workstream.implementations.workstream_teardown import (
    GitWorkstreamTeardown,
)

__all__ = [
    "GhWorkstreamMerger",
    "GitWorkstreamPreparer",
    "GitWorkstreamTeardown",
]
