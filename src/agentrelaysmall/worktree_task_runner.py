import json
import os
from datetime import datetime, timezone
from pathlib import Path


class WorktreeTaskRunner:
    def __init__(
        self,
        task_id: str,
        graph_name: str,
        signal_dir: Path,
        role: str | None = None,
        description: str | None = None,
        graph_branch: str | None = None,
        completion_gate: str | None = None,
        agent_index: int | None = None,
    ) -> None:
        self.task_id = task_id
        self.graph_name = graph_name
        self.signal_dir = signal_dir
        self.role = role
        self.description = description
        self.graph_branch = graph_branch
        self.completion_gate = completion_gate
        self.agent_index = agent_index

    @classmethod
    def from_config(cls) -> "WorktreeTaskRunner":
        signal_dir = Path(os.environ["AGENTRELAY_SIGNAL_DIR"])
        data = json.loads((signal_dir / "task_context.json").read_text())
        return cls(
            task_id=data["task_id"],
            graph_name=data["graph_name"],
            signal_dir=signal_dir,
            role=data.get("role"),
            description=data.get("description"),
            graph_branch=data.get("graph_branch"),
            completion_gate=data.get("completion_gate"),
            agent_index=data.get("agent_index"),
        )

    def get_context(self) -> str | None:
        context_file = self.signal_dir / "context.md"
        return context_file.read_text() if context_file.exists() else None

    def get_instructions(self) -> str | None:
        instructions_file = self.signal_dir / "instructions.md"
        return instructions_file.read_text() if instructions_file.exists() else None

    def _write_signal(self, name: str, content: str) -> None:
        self.signal_dir.mkdir(parents=True, exist_ok=True)
        (self.signal_dir / name).write_text(content)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def mark_done(self, note: str = "") -> None:
        body = self._timestamp()
        if note:
            body += f"\n{note}"
        self._write_signal(".done", body)

    def mark_failed(self, reason: str) -> None:
        self._write_signal(".failed", f"{self._timestamp()}\n{reason}")
