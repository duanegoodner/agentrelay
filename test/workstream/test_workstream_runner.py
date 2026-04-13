"""Tests for WorkstreamRunner lifecycle behavior."""

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agentrelay.workstream import (
    IntegrationResult,
    StandardWorkstreamRunner,
    WorkstreamIntegrator,
    WorkstreamPreparer,
    WorkstreamRunner,
    WorkstreamRunResult,
    WorkstreamRuntime,
    WorkstreamSpec,
    WorkstreamStatus,
    WorkstreamTeardown,
)


def _make_runtime(workstream_id: str = "ws-1") -> WorkstreamRuntime:
    runtime = WorkstreamRuntime(spec=WorkstreamSpec(id=workstream_id))
    runtime.state.signal_dir = Path(tempfile.mkdtemp())
    return runtime


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

    def create_integration_pr(
        self, workstream_runtime: WorkstreamRuntime
    ) -> IntegrationResult:
        self.calls.append("integrate")
        self._maybe_fail("integrate")
        workstream_runtime.mark_pr_created(
            f"https://example.com/{workstream_runtime.spec.id}/integration-pr"
        )
        return IntegrationResult(skipped=False)

    def teardown_workstream(self, workstream_runtime: WorkstreamRuntime) -> None:
        self.calls.append("teardown")
        self._maybe_fail("teardown")


def _make_runner(fake: FakeWorkstreamIO | None = None) -> StandardWorkstreamRunner:
    if fake is None:
        fake = FakeWorkstreamIO()
    return StandardWorkstreamRunner(
        _preparer=fake,
        _integrator=fake,
        _teardown=fake,
    )


def test_prepare_calls_preparer() -> None:
    fake = FakeWorkstreamIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    runner.prepare(runtime)

    assert fake.calls == ["prepare"]
    assert runtime.status == WorkstreamStatus.ACTIVE


def test_prepare_failure_records_error_and_raises() -> None:
    fake = FakeWorkstreamIO(fail_stage="prepare")
    runner = _make_runner(fake)
    runtime = _make_runtime()

    with pytest.raises(RuntimeError, match="prepare boom"):
        runner.prepare(runtime)

    assert runtime.status == WorkstreamStatus.FAILED
    assert "prepare boom" in (runtime.state.error or "")


def test_integrate_success_transitions_to_pr_created() -> None:
    fake = FakeWorkstreamIO()
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = runner.integrate(runtime)

    assert fake.calls == ["integrate"]
    assert result.status == WorkstreamStatus.PR_CREATED
    assert result.error is None
    assert runtime.status == WorkstreamStatus.PR_CREATED


def test_integrate_failure_transitions_to_failed() -> None:
    fake = FakeWorkstreamIO(fail_stage="integrate")
    runner = _make_runner(fake)
    runtime = _make_runtime()

    result = runner.integrate(runtime)

    assert result.status == WorkstreamStatus.FAILED
    assert "integrate boom" in (result.error or "")
    assert runtime.status == WorkstreamStatus.FAILED


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
    assert isinstance(fake, WorkstreamIntegrator)
    assert isinstance(fake, WorkstreamTeardown)


def test_standard_runner_satisfies_protocol() -> None:
    runner = _make_runner()
    assert isinstance(runner, WorkstreamRunner)


def test_integrate_skip_transitions_to_merged() -> None:
    """When integrator marks merged (skip), runner returns MERGED status."""

    @dataclass
    class SkipIntegrator:
        calls: list[str] = field(default_factory=list)

        def create_integration_pr(
            self, workstream_runtime: WorkstreamRuntime
        ) -> IntegrationResult:
            self.calls.append("integrate")
            workstream_runtime.mark_merged()
            return IntegrationResult(
                skipped=True, target_branch_authoritative_sha="skip_sha_abc"
            )

    skip_io = SkipIntegrator()
    fake = FakeWorkstreamIO()
    runner = StandardWorkstreamRunner(
        _preparer=fake,
        _integrator=skip_io,
        _teardown=fake,
    )
    runtime = _make_runtime()

    result = runner.integrate(runtime)

    assert skip_io.calls == ["integrate"]
    assert result.status == WorkstreamStatus.MERGED
    assert result.error is None
    assert runtime.status == WorkstreamStatus.MERGED
    assert runtime.artifacts.target_branch_before_any_merge == "skip_sha_abc"


def test_workstream_run_result_from_runtime() -> None:
    runtime = _make_runtime("ws-test")
    runtime.mark_pr_created("https://example.com/ws-test/integration-pr")

    result = WorkstreamRunResult.from_runtime(runtime)

    assert result.workstream_id == "ws-test"
    assert result.status == WorkstreamStatus.PR_CREATED
    assert result.error is None
