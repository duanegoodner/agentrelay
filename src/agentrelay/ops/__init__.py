"""Operations primitives — thin, stateless subprocess and filesystem wrappers.

This package is a private implementation detail of agentrelay.
Protocol implementations (in ``task_runner/implementations/``,
``workstream/implementations/``, and ``agent/implementations/``)
import directly from submodules::

    from agentrelay.ops.git import worktree_add
    from agentrelay.ops.tmux import new_window
    from agentrelay.ops.gh import pr_merge
    from agentrelay.ops.signals import poll_signal_files
"""
