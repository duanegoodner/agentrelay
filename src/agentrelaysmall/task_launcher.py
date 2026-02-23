from pathlib import Path
import subprocess

from agentrelaysmall.agent_task import AgentTask, TaskStatus

if __name__ == "__main__":
    TMUX_SESSION = "agentrelaysmall"
    TASK_ID = "task_001"
    WORKTREE_PATH = Path(f"/data/git/agentrelaysmall/{TASK_ID}")
    
    task = AgentTask(
        id=TASK_ID,
        description="Implement the task launcher for AgentRelaySmall",
    )

    
    if task.state.tmux_session is None:
        raise ValueError("Task must have a tmux session assigned")
    
    pane_id = (
        subprocess.check_output(
            [
                "tmux",
                "new-window",
                "-t",
                task.state.tmux_session,
                "-n",
                task.id,
                "-P",
                "-F",
                "#{window_index}:#{pane_id}",
                "-c",
                str(task.state.worktree_path),
            ]
        )
        .decode()
        .strip()
    )

    window_index, pane_id = pane_id.split(":")
    print(f"Window: {window_index}, Pane: {pane_id}")

    subprocess.run(["tmux", "send-keys", "-t", pane_id, "claude", "Enter"])
