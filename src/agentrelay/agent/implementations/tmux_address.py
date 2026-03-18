"""Tmux pane address type.

Classes:
    TmuxAddress: Concrete address for agents running in tmux panes.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agentrelay.agent.core.addressing import AgentAddress
from agentrelay.ops import signals, tmux


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

    def teardown(
        self,
        signal_dir: Optional[Path] = None,
        keep_panes: bool = False,
    ) -> None:
        """Capture pane scrollback and optionally kill the tmux window.

        Best-effort: errors are swallowed since the pane may already be gone.

        Args:
            signal_dir: If provided, pane scrollback is written as ``agent.log``.
            keep_panes: If True, keep the tmux window open for debugging.
        """
        try:
            log = tmux.capture_pane(self.pane_id, full_history=True)
            if signal_dir is not None:
                signals.write_text(signal_dir, "agent.log", log)
        except subprocess.CalledProcessError:
            pass  # Best-effort: pane may already be gone

        if not keep_panes:
            try:
                tmux.kill_window(self.pane_id)
            except subprocess.CalledProcessError:
                pass  # Best-effort
