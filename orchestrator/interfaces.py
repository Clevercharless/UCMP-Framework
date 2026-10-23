"""
orchestrator.interfaces
========================
Defines the `PipelineStage` contract. Every downstream module built later
in this project (Configuration Manager, Repository Manager, Parser Engine,
Rule Service, Transformation Planner, Replacement Engine, Validation
Engine, Deployment Engine, Reporting Engine) will implement this interface
so the Orchestrator can drive them uniformly without knowing their
internals.

This module has ZERO dependencies on any other UCMP module, by design —
the Orchestrator must be buildable and testable before any other module
exists.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class StageStatus(str, Enum):
    """Terminal status of a single stage execution."""

    NOT_RUN = "NOT_RUN"
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class PipelineStage(ABC):
    """
    Abstract base class every pipeline stage must implement.

    A stage is a single step in the migration pipeline:
    Repository Manager -> Parser Engine -> ... -> Reporting Engine.

    Contract:
      * `name` is a short, stable, human-readable identifier used in logs
        and reports (e.g. "RepositoryManager", "ParserEngine").
      * `run(context)` receives the shared PipelineContext, performs its
        work, mutates/enriches the context as needed, and returns the same
        (or a new) PipelineContext.
      * A stage must raise an exception on failure. It must NOT return
        None or swallow errors silently — the Orchestrator is responsible
        for catching, wrapping, and logging failures.
      * A stage should be side-effect-idempotent where practical, since the
        Orchestrator may support re-runs in future versions.
    """

    #: Stable identifier for this stage, overridden by subclasses.
    name: str = "UnnamedStage"

    @abstractmethod
    def run(self, context: "PipelineContext") -> "PipelineContext":  # noqa: F821
        """Execute this stage's work and return the (possibly updated) context."""
        raise NotImplementedError

    def is_enabled(self, context: "PipelineContext") -> bool:  # noqa: F821
        """
        Whether this stage should run at all for the given context. Stages
        can override this to support conditional/optional execution
        (e.g. skip Deployment Engine in a "dry-run" configuration).
        Defaults to always-enabled.
        """
        return True

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<PipelineStage:{self.name}>"
