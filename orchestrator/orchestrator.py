"""
orchestrator.orchestrator
==========================
The Orchestrator is the top-level coordinator of the UCMP migration
pipeline. It owns:

  * The ordered list of PipelineStage instances to run.
  * A single PipelineContext that is threaded through every stage.
  * Error handling / fail-fast vs. continue-on-error policy.
  * Timing and structured logging of each stage.

It has NO knowledge of what any individual stage does internally — it only
depends on the `PipelineStage` interface. This is what lets later modules
(Repository Manager, Parser Engine, Rule Service, ...) be built and slotted
in one at a time without ever touching this file again.
"""

from __future__ import annotations

import time
from typing import List, Optional, Sequence

from common.exceptions import StageContractViolation, StageExecutionError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext, StageResult
from orchestrator.interfaces import PipelineStage, StageStatus

logger = get_logger(__name__)


class Orchestrator:
    """
    Drives a sequence of PipelineStage objects against a shared
    PipelineContext.

    Parameters
    ----------
    stages:
        Ordered list of stages to execute, e.g.
        [RepositoryManager(), ParserEngine(), ..., ReportingEngine()].
    fail_fast:
        If True (default), the pipeline stops at the first stage failure.
        If False, the Orchestrator logs the failure, marks that stage
        FAILED, and continues to the next stage (useful for producing a
        best-effort report even when one stage errors out).
    """

    def __init__(self, stages: Sequence[PipelineStage], fail_fast: bool = True):
        if not stages:
            raise StageContractViolation("Orchestrator requires at least one stage.")
        self._stages: List[PipelineStage] = list(stages)
        self._fail_fast = fail_fast

    @property
    def stages(self) -> List[PipelineStage]:
        return list(self._stages)

    def run(self, context: Optional[PipelineContext] = None) -> PipelineContext:
        """
        Execute all configured stages in order against `context` (a fresh
        PipelineContext is created if none is supplied). Returns the final
        context, which callers (e.g. Reporting Engine, or a CLI/demo
        script) can inspect via `context.artifacts` and
        `context.stage_results`.
        """
        context = context or PipelineContext()

        logger.info(
            "Starting migration pipeline run_id=%s with %d stage(s)",
            context.run_id,
            len(self._stages),
        )

        for stage in self._stages:
            if not stage.is_enabled(context):
                result = StageResult(stage_name=stage.name, status=StageStatus.SKIPPED)
                context.record_result(result)
                logger.info("Skipping stage '%s' (disabled for this run)", stage.name)
                continue

            result = self._run_stage(stage, context)
            context.record_result(result)

            if result.status == StageStatus.FAILED and self._fail_fast:
                logger.error(
                    "Stage '%s' failed; aborting pipeline (fail_fast=True)",
                    stage.name,
                )
                break

        overall = "FAILED" if context.has_failed_stage() else "SUCCESS"
        logger.info(
            "Pipeline run_id=%s finished with overall status=%s",
            context.run_id,
            overall,
        )
        return context

    def _run_stage(self, stage: PipelineStage, context: PipelineContext) -> StageResult:
        """Execute a single stage with timing, logging, and error wrapping."""
        result = StageResult(stage_name=stage.name, started_at=time.time())
        logger.info("-> Running stage '%s'", stage.name)

        try:
            updated_context = stage.run(context)
            if updated_context is None or not isinstance(updated_context, PipelineContext):
                raise StageContractViolation(
                    f"Stage '{stage.name}' must return a PipelineContext instance, "
                    f"got {type(updated_context).__name__}."
                )
            # Stages may return a new context object (e.g. wrapping/copying);
            # keep the caller's reference in sync either way.
            if updated_context is not context:
                context.artifacts.update(updated_context.artifacts)
                context.metadata.update(updated_context.metadata)

            result.status = StageStatus.SUCCESS
            logger.info("<- Stage '%s' completed successfully", stage.name)

        except StageContractViolation:
            # Contract violations are programmer errors in the stage itself;
            # re-raise immediately rather than treating as a normal failure.
            raise

        except Exception as exc:  # noqa: BLE001 - intentionally broad; stages are untrusted
            wrapped = StageExecutionError(stage.name, exc)
            result.status = StageStatus.FAILED
            result.error_message = str(wrapped)
            logger.exception("<- Stage '%s' failed: %s", stage.name, exc)

        finally:
            result.finished_at = time.time()

        return result
