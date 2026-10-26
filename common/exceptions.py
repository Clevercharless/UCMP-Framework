"""
common.exceptions
==================
Shared exception hierarchy for the Universal Cloud Migration Platform (UCMP).

Every module in ucmp-core should raise subclasses of `UCMPError` rather than
bare exceptions, so the Orchestrator (and any caller) can reason about
failures generically.
"""

from __future__ import annotations


class UCMPError(Exception):
    """Base class for all UCMP-raised exceptions."""


class StageExecutionError(UCMPError):
    """
    Raised when a pipeline stage fails during execution.

    Wraps the original exception so the Orchestrator can log a clean
    stage-level failure while preserving the root cause for debugging.
    """

    def __init__(self, stage_name: str, original_exception: Exception):
        self.stage_name = stage_name
        self.original_exception = original_exception
        super().__init__(
            f"Stage '{stage_name}' failed: "
            f"{type(original_exception).__name__}: {original_exception}"
        )


class StageContractViolation(UCMPError):
    """
    Raised when a stage does not honor the PipelineStage contract, e.g. it
    returns an object of the wrong type, or mutates the context in a way
    that violates required invariants.
    """


class ConfigurationError(UCMPError):
    """Raised for invalid or missing pipeline / module configuration."""


class AuthenticationError(UCMPError):
    """
    Raised by the (simulated) Authentication Manager when a required
    credential/config field is missing, a simulated token has expired and
    cannot be silently refreshed, or an unsupported platform is requested.

    No real network authentication ever occurs in UCMP v1 — this exception
    exists purely to model realistic auth failure modes for the demo.
    """


class RepositoryError(UCMPError):
    """
    Raised by the Repository Manager when the source repository cannot be
    located, synced, or does not match the expected medallion (Bronze /
    Silver / Gold / Common / Jobs) folder structure.
    """


class ParserError(UCMPError):
    """
    Raised by the Parser Engine when a notebook cannot be read or its
    structure cannot be understood well enough to extract cells (e.g. no
    recognizable Databricks export header). Malformed *code* inside a
    cell is handled gracefully (recorded as a manual-review item), not
    raised — this exception is reserved for structural failures.
    """


class RuleRepositoryError(UCMPError):
    """
    Raised when a rule YAML file is missing, malformed, or contains a rule
    that fails schema validation (missing required field, invalid
    match_type/action, or a regex pattern that fails to compile).
    """


class RuleServiceError(UCMPError):
    """
    Raised by the Rule Service when required upstream artifacts
    (Migration Knowledge Model, loaded Rule Repository) are missing. Never
    raised for an individual construct having no matching rule — that is
    a normal, expected outcome recorded as an "unmatched" transformation
    action, not an error.
    """


class TransformationPlannerError(UCMPError):
    """
    Raised by the Transformation Planner when required upstream artifacts
    (Migration Knowledge Model, Rule Service output) are missing. Never
    raised for a construct with no matching rule or a notebook with no
    Azure constructs at all — both are normal, expected plan contents.
    """


class ReplacementError(UCMPError):
    """
    Raised by the Replacement Engine when required upstream artifacts
    (Transformation Plan, repository inventory) are missing, or when a
    staged notebook referenced by the plan cannot be read/written. Never
    raised for a construct flagged manual_review/unmatched — those are
    correctly left untouched, not an error condition.
    """


class ValidationEngineError(UCMPError):
    """
    Raised by the Validation Engine when required upstream artifacts are
    missing. Never raised because a validation CHECK failed — a failed
    check produces an ERROR-severity finding and an overall FAIL status
    in the ValidationReport, not a Python exception. This exception is
    reserved for the Validation Engine being unable to run at all.
    """


class DeploymentError(UCMPError):
    """
    Raised by the Deployment Engine when required upstream artifacts are
    missing, or when a local git operation fails unexpectedly (e.g. git
    is not installed). Never raised because the validation gate blocked
    deployment — that produces an ABORTED DeploymentPlan, not an
    exception, since a blocked deployment is a normal, expected outcome.
    """


class ReportingEngineError(UCMPError):
    """
    Raised by the Reporting Engine when required upstream artifacts are
    missing. The Reporting Engine only formats data other stages already
    produced — it never raises for the *content* of that data (e.g. a
    FAIL validation status or an ABORTED deployment are simply reported
    as-is, not treated as errors).
    """
