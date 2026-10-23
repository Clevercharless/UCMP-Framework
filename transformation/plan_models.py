"""
transformation.plan_models
============================
Data model for the Transformation Plan: one `TransformationOperation` per
construct-per-notebook occurrence, grouped into a `NotebookTransformationPlan`
per notebook, rolled up into the overall `TransformationPlan`.

Every notebook's plan always includes exactly one `KEEP_BUSINESS_LOGIC`
operation - a positive, explicit statement of what will NOT change -
alongside whatever Azure-construct operations apply. This makes "business
logic is preserved" a first-class, checkable fact in the plan rather than
an implicit assumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from transformation.operation_types import OperationType


@dataclass
class TransformationOperation:
    """One planned operation against one construct occurrence in one notebook."""

    operation_type: OperationType
    category: str
    action: str  # replace | remove | manual_review | no_change | unmatched | keep
    construct_type: Optional[str]
    original_value: Optional[str]
    resolved_value: Optional[str]
    rule_id: Optional[str]
    requires_manual_review: bool
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "operation_type": self.operation_type.value,
            "category": self.category,
            "action": self.action,
            "construct_type": self.construct_type,
            "original_value": self.original_value,
            "resolved_value": self.resolved_value,
            "rule_id": self.rule_id,
            "requires_manual_review": self.requires_manual_review,
            "notes": self.notes,
        }


@dataclass
class NotebookTransformationPlan:
    """All planned operations for a single notebook, in execution order."""

    relative_path: str
    category: str
    operations: List[TransformationOperation] = field(default_factory=list)

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    @property
    def requires_manual_review(self) -> bool:
        return any(op.requires_manual_review for op in self.operations if op.operation_type != OperationType.KEEP_BUSINESS_LOGIC)

    @property
    def classification(self) -> str:
        changed_actions = {"replace", "remove", "add_config"}
        return "CHANGED" if any(op.action in changed_actions for op in self.operations) else "NO_CHANGE"

    def to_dict(self) -> Dict:
        return {
            "relative_path": self.relative_path,
            "category": self.category,
            "operation_count": self.operation_count,
            "requires_manual_review": self.requires_manual_review,
            "classification": self.classification,
            "operations": [op.to_dict() for op in self.operations],
        }


@dataclass
class TransformationPlan:
    """The complete, ordered Transformation Plan for the whole repository."""

    repo_name: str
    notebook_plans: List[NotebookTransformationPlan] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "repo_name": self.repo_name,
            "summary": self._summary(),
            "notebook_plans": [nb.to_dict() for nb in self.notebook_plans],
        }

    def _summary(self) -> Dict:
        by_operation_type: Dict[str, int] = {}
        total_operations = 0
        notebooks_with_manual_review = 0
        notebooks_changed = 0
        notebooks_no_change = 0

        for nb in self.notebook_plans:
            if nb.requires_manual_review:
                notebooks_with_manual_review += 1
            if nb.classification == "CHANGED":
                notebooks_changed += 1
            else:
                notebooks_no_change += 1
            for op in nb.operations:
                total_operations += 1
                by_operation_type[op.operation_type.value] = (
                    by_operation_type.get(op.operation_type.value, 0) + 1
                )

        return {
            "notebook_count": len(self.notebook_plans),
            "total_operations": total_operations,
            "notebooks_with_manual_review": notebooks_with_manual_review,
            "notebooks_changed": notebooks_changed,
            "notebooks_no_change": notebooks_no_change,
            "by_operation_type": by_operation_type,
        }
