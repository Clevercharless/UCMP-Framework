"""
rule_service.transformation_action
=====================================
`TransformationAction` is the Rule Service's output unit: one concrete,
per-construct decision, ready for the Transformation Planner (Module 8)
to turn into an ordered plan. Rule Service produces these; it does not
apply them to any file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TransformationAction:
    """The resolved outcome for a single construct found by the Parser Engine."""

    construct_type: str
    original_value: str
    rule_category: str
    action: str  # replace | remove | manual_review | no_change | unmatched
    matched_rule_id: Optional[str]
    resolved_value: Optional[str]
    requires_manual_review: bool
    occurrences: int
    found_in: List[str] = field(default_factory=list)
    candidate_rule_ids: List[str] = field(default_factory=list)
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "construct_type": self.construct_type,
            "original_value": self.original_value,
            "rule_category": self.rule_category,
            "action": self.action,
            "matched_rule_id": self.matched_rule_id,
            "resolved_value": self.resolved_value,
            "requires_manual_review": self.requires_manual_review,
            "occurrences": self.occurrences,
            "found_in": self.found_in,
            "candidate_rule_ids": self.candidate_rule_ids,
            "notes": self.notes,
        }
