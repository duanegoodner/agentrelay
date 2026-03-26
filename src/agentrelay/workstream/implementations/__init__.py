"""Concrete workstream protocol implementations.

This subpackage contains environment-specific implementations of the
per-step protocols defined in ``workstream.core.io``. Each module is named
after the protocol it implements.
"""

from agentrelay.workstream.implementations.integration_auto_merger import (
    GhIntegrationAutoMerger,
)
from agentrelay.workstream.implementations.integration_merge_checker import (
    GhIntegrationMergeChecker,
)
from agentrelay.workstream.implementations.workstream_integrator import (
    GhWorkstreamIntegrator,
)
from agentrelay.workstream.implementations.workstream_preparer import (
    GitWorkstreamPreparer,
)
from agentrelay.workstream.implementations.workstream_teardown import (
    GitWorkstreamTeardown,
)

__all__ = [
    "GhIntegrationAutoMerger",
    "GhIntegrationMergeChecker",
    "GhWorkstreamIntegrator",
    "GitWorkstreamPreparer",
    "GitWorkstreamTeardown",
]
