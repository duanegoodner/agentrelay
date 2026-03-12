"""Tmux pane address type.

Classes:
    TmuxAddress: Concrete address for agents running in tmux panes.
"""

from dataclasses import dataclass

from agentrelay.agent.core.addressing import AgentAddress


@dataclass(frozen=True)
class TmuxAddress(AgentAddress):
    """Address of an agent running in a tmux pane.

    Attributes:
        session: The name of the tmux session.
        pane_id: The identifier of the tmux pane (e.g., "%1", "%2").
    """

    session: str
    pane_id: str

    @property
    def label(self) -> str:
        """Return a human-readable identifier combining session and pane.

        Returns:
            String in format "session:pane_id" (e.g., "agentrelay:%1").
        """
        return f"{self.session}:{self.pane_id}"
