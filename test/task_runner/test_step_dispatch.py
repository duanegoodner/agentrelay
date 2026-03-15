"""Tests for StepDispatch dispatch logic."""

import pytest

from agentrelay.environments import TmuxEnvironment
from agentrelay.task import AgentConfig, AgentFramework, AgentRole, Task
from agentrelay.task_runner import StepDispatch
from agentrelay.task_runtime import TaskRuntime


def _runtime_with(
    framework: AgentFramework = AgentFramework.CLAUDE_CODE,
    env_type: type = TmuxEnvironment,
) -> TaskRuntime:
    return TaskRuntime(
        task=Task(
            id="t1",
            role=AgentRole.GENERIC,
            primary_agent=AgentConfig(framework=framework, environment=env_type()),
        )
    )


def test_default_only_dispatch() -> None:
    dispatch: StepDispatch[str] = StepDispatch(default=lambda rt: "default_impl")
    assert dispatch(_runtime_with()) == "default_impl"


def test_exact_key_match_takes_precedence() -> None:
    key = (AgentFramework.CLAUDE_CODE, TmuxEnvironment)
    dispatch: StepDispatch[str] = StepDispatch(
        entries={key: lambda rt: "keyed_impl"},
        default=lambda rt: "default_impl",
    )
    assert dispatch(_runtime_with()) == "keyed_impl"


def test_fallback_to_default_when_no_key_match() -> None:
    # Use a sentinel type that won't match
    class OtherEnv:
        pass

    key = (AgentFramework.CLAUDE_CODE, OtherEnv)
    dispatch: StepDispatch[str] = StepDispatch(
        entries={key: lambda rt: "other_impl"},
        default=lambda rt: "default_impl",
    )
    assert dispatch(_runtime_with()) == "default_impl"


def test_no_match_and_no_default_raises_key_error() -> None:
    class OtherEnv:
        pass

    key = (AgentFramework.CLAUDE_CODE, OtherEnv)
    dispatch: StepDispatch[str] = StepDispatch(
        entries={key: lambda rt: "other_impl"},
    )
    with pytest.raises(KeyError, match="No implementation registered"):
        dispatch(_runtime_with())


def test_empty_dispatch_raises_key_error() -> None:
    dispatch: StepDispatch[str] = StepDispatch()
    with pytest.raises(KeyError, match="No implementation registered"):
        dispatch(_runtime_with())


def test_factory_receives_runtime() -> None:
    def factory(rt: TaskRuntime) -> str:
        return f"task_{rt.task.id}"

    dispatch: StepDispatch[str] = StepDispatch(default=factory)
    assert dispatch(_runtime_with()) == "task_t1"
