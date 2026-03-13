"""Protocol schemas, builders, and template resolution for agent communication.

This package implements Layers 1-3 of the agent communication protocol:

- **Layer 1**: :class:`TaskManifest` — structured facts about a task.
- **Layer 2**: :func:`resolve_instructions` — role-specific work instructions.
- **Layer 3**: :class:`WorkflowPolicies` — composable workflow configuration.

All types and functions are framework-agnostic.  Framework adapters
(in ``task_runner/implementations/``) consume these outputs.
"""

from agentrelay.agent_comm_protocol.manifest import (
    MANIFEST_SCHEMA_VERSION,
    DependencyInfo,
    TaskManifest,
    build_manifest,
    manifest_to_dict,
)
from agentrelay.agent_comm_protocol.policies import (
    POLICIES_SCHEMA_VERSION,
    AdrPolicy,
    CommitPolicy,
    CompletionGatePolicy,
    PrBodySection,
    PrPolicy,
    ReviewPolicy,
    VerificationPolicy,
    WorkflowAction,
    WorkflowPolicies,
    build_policies,
    policies_to_dict,
)
from agentrelay.agent_comm_protocol.templates import resolve_instructions

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "POLICIES_SCHEMA_VERSION",
    "AdrPolicy",
    "CommitPolicy",
    "CompletionGatePolicy",
    "DependencyInfo",
    "PrBodySection",
    "PrPolicy",
    "ReviewPolicy",
    "TaskManifest",
    "VerificationPolicy",
    "WorkflowAction",
    "WorkflowPolicies",
    "build_manifest",
    "build_policies",
    "manifest_to_dict",
    "policies_to_dict",
    "resolve_instructions",
]
