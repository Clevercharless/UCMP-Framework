"""
validation.finding
====================
Shared data model every one of the seven validators (Rule, Azure Residue,
Unsupported SDK, Syntax, Dependency, Configuration, Hardcoded Secret)
reports through. A single flat list of `ValidationFinding`s, tagged by
category and severity, is all the ValidationEngine needs to compute the
overall PASS/FAIL and build the ValidationReport.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class ValidationSeverity(str, Enum):
    ERROR = "error"  # causes overall FAIL
    WARNING = "warning"  # reported, but does not fail the run
    INFO = "info"


class ValidationCategory(str, Enum):
    RULE_VALIDATION = "rule_validation"
    AZURE_RESIDUE = "azure_residue"
    UNSUPPORTED_SDK = "unsupported_sdk"
    SYNTAX = "syntax"
    DEPENDENCY = "dependency"
    CONFIGURATION = "configuration"
    HARDCODED_SECRET = "hardcoded_secret"


@dataclass(frozen=True)
class ValidationFinding:
    category: ValidationCategory
    severity: ValidationSeverity
    message: str
    notebook: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "notebook": self.notebook,
            "detail": self.detail,
        }
