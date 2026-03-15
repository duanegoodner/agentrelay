"""Tests for WorkstreamRunner lifecycle behavior."""

from dataclasses import dataclass, field

import pytest

from agentrelay.workstream import (
    WorkstreamMerger,
    WorkstreamPreparer,
    WorkstreamRunner,
    WorkstreamRunResult,
    WorkstreamRuntime,
    WorkstreamSpec,
    WorkstreamStatus,
    WorkstreamTeardown,
)


def _make_runtime(workstream_id: str = "ws-1") -> WorkstreamRuntime:
    return WorkstreamRuntime(spec=WorkstreamSpec(id=workstream_id))


@dataclass
class FakeWorkstreamIO:
    """I/O double implementing all three workstream protocols."""

    fail_stage: str | None = None
    calls: list[str] = field(default_factory=list)

    def _maybe_fail(self, stage: str) -> None:
        if self.fail_stage == stage:
            raise RuntimeError(f"{stage} boom")

    def prepare_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        self.calls.append("prepare")
        self._maybe_fail("prepare")

    def merge_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        self.calls.append("merge")
        self._maybe_fail("merge")

    def teardown_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        self.calls.append("teardown")
        self._maybe_fail("teardown")


def _make_runner(fake: FakeWorkstreamIO | None = None) -> WorkstreamRunner:
    if fake is None:
        fake = FakeWorkstreamIO()
    return WorkstreamRunner(
        _preparer=fake,
        _merger=fake,
        _teardown=fake,
    )


def test_prepare_calls_preparer() -> None:
    fake = FakeWorkstreamIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    runner.prepare(runtime)

    assert fake.calls == ["prepare"]


def test_prepare_failure_records_error_and_raises() -> None:
    fake = FakeWorkstreamIO(fail_stage="prepare")
    runner = _make_runner(fake)
    runtime = _make_runtime()

    with pytest.raises(RuntimeError, match="prepare boom"):
        runner.prepare(runtime)

    assert runtime.state.status == WorkstreamStatus.FAILED
    assert "prepare boom" in (runtime.state.error or "")


def test_merge_success_transitions_to_merged() -> None:
    fake = FakeWorkstreamIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = runner.merge(runtime)

    assert fake.calls == ["merge"]
    assert result.status == WorkstreamStatus.MERGED
    assert result.error is None
    assert runtime.state.status == WorkstreamStatus.MERGED


def test_merge_failure_transitions_to_failed() -> None:
    fake = FakeWorkstreamIO(fail_stage="merge")
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = runner.merge(runtime)

    assert result.status == WorkstreamStatus.FAILED
    assert "merge boom" in (result.error or "")
    assert runtime.state.status == WorkstreamStatus.FAILED


def test_teardown_calls_teardown_handler() -> None:
    fake = FakeWorkstreamIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    runner.teardown(runtime)

    assert fake.calls == ["teardown"]


def test_teardown_failure_records_concern() -> None:
    fake = FakeWorkstreamIO(fail_stage="teardown")
    runner = _make_runner(fake)
    runtime = _make_runtime()

    runner.teardown(runtime)

    assert runtime.artifacts.concerns
    assert runtime.artifacts.concerns[-1].startswith("teardown_failed:")


def test_protocol_runtime_checkable_instances() -> None:
    fake = FakeWorkstreamIO()
    assert isinstance(fake, WorkstreamPreparer)
    assert isinstance(fake, WorkstreamMerger)
    assert isinstance(fake, WorkstreamTeardown)


def test_workstream_run_result_from_runtime() -> None:
    runtime = _make_runtime("ws-test")
    runtime.state.status = WorkstreamStatus.MERGED

    result = WorkstreamRunResult.from_runtime(runtime)

    assert result.workstream_id == "ws-test"
    assert result.status == WorkstreamStatus.MERGED
    assert result.error is None
