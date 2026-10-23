"""
orchestrator.context
=====================
Defines `PipelineContext`, the single shared state object that flows
through the entire migration pipeline:

    Repository -> Parser -> Dependency Graph -> Knowledge Model ->
    Rule Repository -> Rule Service -> Transformation Planner ->
    Replacement Engine -> Validation Engine -> Deployment Engine ->
    Reporting Engine

Rather than have every module invent its own hand-off format, each module
reads what it needs from `PipelineContext.artifacts` and writes its output
back into the same dict under its own stage name. This keeps stages
loosely coupled: a stage only needs to agree on a key name, not on another
stage's internal classes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from orchestrator.interfaces import StageStatus


@dataclass
class StageResult:
    """Record of a single stage's execution, kept for reporting/audit."""

    stage_name: str
    status: StageStatus = StageStatus.NOT_RUN
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error_message: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at is None or self.finished_at is None:
            return None
        return round(self.finished_at - self.started_at, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
        }


@dataclass
class PipelineContext:
    """
    Shared mutable state passed to every stage in order.

    Attributes:
        run_id: Unique identifier for this migration run, used to namespace
            output folders and reports.
        config: Fully resolved configuration (populated by the future
            Configuration Manager module). Left as a generic dict for now
            so the Orchestrator has no compile-time dependency on that
            module.
        artifacts: The main hand-off bag. Each stage stores its output
            under a well-known key, e.g. artifacts["repository"],
            artifacts["knowledge_model"], artifacts["transformation_plan"].
            Downstream stages read the keys they depend on.
        stage_results: Ordered execution history, one StageResult per stage
            that has been attempted. Used by the Reporting Engine later.
        metadata: Free-form bag for cross-cutting info (source repo path,
            target repo path, dry_run flag, etc.) that multiple stages may
            want without it belonging to any one stage's artifact.
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    config: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    stage_results: List[StageResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def record_result(self, result: StageResult) -> None:
        self.stage_results.append(result)

    def get_artifact(self, key: str, default: Any = None) -> Any:
        return self.artifacts.get(key, default)

    def set_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value

    def has_failed_stage(self) -> bool:
        return any(r.status == StageStatus.FAILED for r in self.stage_results)

    def summary(self) -> Dict[str, Any]:
        """Lightweight summary suitable for logging or the final report."""
        return {
            "run_id": self.run_id,
            "stages": [r.to_dict() for r in self.stage_results],
            "overall_status": "FAILED" if self.has_failed_stage() else "SUCCESS",
        }
