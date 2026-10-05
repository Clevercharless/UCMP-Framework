"""
rules.rule_models
===================
Defines the schema every rule in every YAML mapping file must conform to.
This file contains ONLY data structures and structural validation
(required fields present, enum values valid, regex patterns compile) —
never any decision about *whether* or *how* a given rule applies to a
specific notebook. That decision-making is the Rule Service's job
(Module 7); the Rule Repository's job is purely "load and validate the
data."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from common.exceptions import RuleRepositoryError


class RuleMatchType(str, Enum):
    """How a rule's `pattern` should be matched against a construct value."""

    EXACT = "exact"
    PREFIX = "prefix"
    REGEX = "regex"


class RuleAction(str, Enum):
    """What should happen to a construct that matches this rule."""

    REPLACE = "replace"  # substitute using replacement_template
    REMOVE = "remove"  # construct has no AWS equivalent; drop it
    MANUAL_REVIEW = "manual_review"  # no safe automatic action; flag for a human
    NO_CHANGE = "no_change"  # construct is already cloud-agnostic; leave as-is


REQUIRED_FIELDS = {"rule_id", "category", "match_type", "pattern", "action", "description"}


@dataclass(frozen=True)
class MigrationRule:
    """A single externalized migration mapping, loaded from a YAML rule file."""

    rule_id: str
    category: str  # storage | secret | workspace | catalog | library | spark | api
    match_type: RuleMatchType
    pattern: str
    action: RuleAction
    description: str
    replacement_template: Optional[str] = None
    priority: int = 100  # lower runs first; used by Rule Service to resolve overlaps
    requires_manual_review: bool = False
    source_file: str = ""

    def to_dict(self) -> Dict:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "match_type": self.match_type.value,
            "pattern": self.pattern,
            "action": self.action.value,
            "description": self.description,
            "replacement_template": self.replacement_template,
            "priority": self.priority,
            "requires_manual_review": self.requires_manual_review,
            "source_file": self.source_file,
        }


def validate_and_build_rule(raw: Dict, source_file: str) -> MigrationRule:
    """
    Validates a single raw rule dict (as loaded from YAML) and constructs a
    MigrationRule. Raises RuleRepositoryError with a message that names the
    offending rule_id/file, since a rule author needs to find their typo fast.
    """
    missing = REQUIRED_FIELDS - raw.keys()
    if missing:
        rule_id = raw.get("rule_id", "<unknown>")
        raise RuleRepositoryError(
            f"Rule '{rule_id}' in {source_file} is missing required field(s): {sorted(missing)}"
        )

    rule_id = raw["rule_id"]

    try:
        match_type = RuleMatchType(raw["match_type"])
    except ValueError:
        raise RuleRepositoryError(
            f"Rule '{rule_id}' in {source_file} has invalid match_type "
            f"'{raw['match_type']}'; must be one of {[m.value for m in RuleMatchType]}"
        )

    try:
        action = RuleAction(raw["action"])
    except ValueError:
        raise RuleRepositoryError(
            f"Rule '{rule_id}' in {source_file} has invalid action "
            f"'{raw['action']}'; must be one of {[a.value for a in RuleAction]}"
        )

    if action == RuleAction.REPLACE and not raw.get("replacement_template"):
        raise RuleRepositoryError(
            f"Rule '{rule_id}' in {source_file} has action=replace but no "
            f"replacement_template"
        )

    if match_type == RuleMatchType.REGEX:
        try:
            re.compile(raw["pattern"])
        except re.error as exc:
            raise RuleRepositoryError(
                f"Rule '{rule_id}' in {source_file} has an invalid regex pattern: {exc}"
            )

    priority = raw.get("priority", 100)
    if not isinstance(priority, int):
        raise RuleRepositoryError(
            f"Rule '{rule_id}' in {source_file} has non-integer priority: {priority!r}"
        )

    return MigrationRule(
        rule_id=rule_id,
        category=raw["category"],
        match_type=match_type,
        pattern=raw["pattern"],
        action=action,
        description=raw["description"],
        replacement_template=raw.get("replacement_template"),
        priority=priority,
        requires_manual_review=bool(
            raw.get("requires_manual_review", action == RuleAction.MANUAL_REVIEW)
        ),
        source_file=source_file,
    )
