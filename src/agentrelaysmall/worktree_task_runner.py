import json
from datetime import datetime, timezone
from pathlib import Path


class WorktreeTaskRunner:
    def __init__(self, task_id: str, graph_name: str, signal_dir: Path) -> None:
        self.task_id = task_id
        self.graph_name = graph_name
        self.signal_dir = signal_dir

    @classmethod
    def from_config(cls, worktree_path: Path | None = None) -> "WorktreeTaskRunner":
        root = worktree_path if worktree_path is not None else Path.cwd()
        config_path = root / "task_context.json"
        data = json.loads(config_path.read_text())
        return cls(
            task_id=data["task_id"],
            graph_name=data["graph_name"],
            signal_dir=Path(data["signal_dir"]),
        )

    def get_context(self) -> str | None:
        context_file = Path.cwd() / "context.md"
        return context_file.read_text() if context_file.exists() else None

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
