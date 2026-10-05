"""
tests.test_orchestrator
========================
Unit tests for orchestrator.orchestrator.Orchestrator, orchestrator.context,
and orchestrator.interfaces.

Since no downstream modules (Repository Manager, Parser Engine, etc.) exist
yet, these tests use small mock PipelineStage implementations defined
locally. That is intentional: it proves the Orchestrator works purely
against the PipelineStage contract, with zero coupling to any concrete
module implementation.
"""

from __future__ import annotations

import pytest

from common.exceptions import StageContractViolation
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage, StageStatus
from orchestrator.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Mock stages used only for testing
# ---------------------------------------------------------------------------

class _RecordingStage(PipelineStage):
    """Writes its name into artifacts so we can assert ordering."""

    def __init__(self, name: str):
        self.name = name

    def run(self, context: PipelineContext) -> PipelineContext:
        order = context.get_artifact("execution_order", [])
        order.append(self.name)
        context.set_artifact("execution_order", order)
        return context


class _FailingStage(PipelineStage):
    name = "FailingStage"

    def run(self, context: PipelineContext) -> PipelineContext:
        raise ValueError("simulated stage failure")


class _DisabledStage(PipelineStage):
    name = "DisabledStage"

    def run(self, context: PipelineContext) -> PipelineContext:  # pragma: no cover
        raise AssertionError("Disabled stage should never run")

    def is_enabled(self, context: PipelineContext) -> bool:
        return False


class _BadReturnStage(PipelineStage):
    name = "BadReturnStage"

    def run(self, context: PipelineContext):
        return {"not": "a context"}  # violates contract


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_orchestrator_requires_at_least_one_stage():
    with pytest.raises(StageContractViolation):
        Orchestrator(stages=[])


def test_stages_run_in_order():
    stages = [_RecordingStage("A"), _RecordingStage("B"), _RecordingStage("C")]
    orchestrator = Orchestrator(stages=stages)

    context = orchestrator.run()

    assert context.get_artifact("execution_order") == ["A", "B", "C"]
    assert [r.status for r in context.stage_results] == [StageStatus.SUCCESS] * 3


def test_fail_fast_stops_pipeline():
    stages = [_RecordingStage("A"), _FailingStage(), _RecordingStage("C")]
    orchestrator = Orchestrator(stages=stages, fail_fast=True)

    context = orchestrator.run()

    assert context.get_artifact("execution_order") == ["A"]
    statuses = [r.status for r in context.stage_results]
    assert statuses == [StageStatus.SUCCESS, StageStatus.FAILED]
    assert context.has_failed_stage() is True


def test_continue_on_error_runs_remaining_stages():
    stages = [_RecordingStage("A"), _FailingStage(), _RecordingStage("C")]
    orchestrator = Orchestrator(stages=stages, fail_fast=False)

    context = orchestrator.run()

    assert context.get_artifact("execution_order") == ["A", "C"]
    statuses = [r.status for r in context.stage_results]
    assert statuses == [StageStatus.SUCCESS, StageStatus.FAILED, StageStatus.SUCCESS]


def test_disabled_stage_is_skipped():
    stages = [_RecordingStage("A"), _DisabledStage(), _RecordingStage("C")]
    orchestrator = Orchestrator(stages=stages)

    context = orchestrator.run()

    assert context.get_artifact("execution_order") == ["A", "C"]
    statuses = {r.stage_name: r.status for r in context.stage_results}
    assert statuses["DisabledStage"] == StageStatus.SKIPPED


def test_stage_returning_non_context_raises_contract_violation():
    orchestrator = Orchestrator(stages=[_BadReturnStage()])
    with pytest.raises(StageContractViolation):
        orchestrator.run()


def test_stage_result_duration_is_recorded():
    stages = [_RecordingStage("A")]
    orchestrator = Orchestrator(stages=stages)

    context = orchestrator.run()

    result = context.stage_results[0]
    assert result.duration_seconds is not None
    assert result.duration_seconds >= 0


def test_context_summary_reports_overall_status():
    ok_context = Orchestrator(stages=[_RecordingStage("A")]).run()
    assert ok_context.summary()["overall_status"] == "SUCCESS"

    failed_context = Orchestrator(
        stages=[_FailingStage()], fail_fast=False
    ).run()
    assert failed_context.summary()["overall_status"] == "FAILED"


def test_custom_context_is_reused_and_enriched():
    context = PipelineContext(metadata={"source_repo": "azure-loan-platform"})
    stages = [_RecordingStage("A")]
    orchestrator = Orchestrator(stages=stages)

    result_context = orchestrator.run(context)

    assert result_context is context
    assert result_context.metadata["source_repo"] == "azure-loan-platform"
    assert result_context.get_artifact("execution_order") == ["A"]
