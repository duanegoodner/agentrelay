"""Execution environment configuration types for v2 agents.

Concrete environment types determine where and how an agent process is deployed
(tmux pane, cloud API, etc.) and the communication protocol used (file-based signals
vs HTTP-based). Each concrete type is a frozen dataclass.

Type alias:
    AgentEnvironment: Union of all supported environment config types.
        Add new types here as they are implemented.
        If a behavioral contract (shared method or attribute) is ever identified that
        all environments must satisfy, replace this alias with an ABC or Protocol.

TypeVar:
    AgentEnvironmentT: Bound to AgentEnvironment. Use in generic code that needs
        to preserve the concrete environment type through a function signature.
        Update the bound here whenever AgentEnvironment gains a new member.
"""

from dataclasses import dataclass
from typing import TypeAlias, TypeVar


@dataclass(frozen=True)
class TmuxEnvironment:
    """Deploy agent as a Claude Code process in a tmux pane.

    Attributes:
        session: The tmux session name where the pane will be created.
            Defaults to "agentrelaysmall".
    """

    session: str = "agentrelaysmall"


# ── Type alias and TypeVar ──
#
# AgentEnvironment is the union of all supported environment config types.
# To add a new environment: define its dataclass above, then add | NewEnvironment here
# and update the AgentEnvironmentT bound below to match.
#
# If a shared behavioral contract emerges (e.g. all environments need validate() or
# an environment_name attribute), replace this alias with an ABC or Protocol.

AgentEnvironment: TypeAlias = TmuxEnvironment  # | CloudEnvironment | ...

AgentEnvironmentT = TypeVar("AgentEnvironmentT", bound=AgentEnvironment)
