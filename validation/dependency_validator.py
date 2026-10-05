"""
validation.dependency_validator
==================================
Dependency Validation: re-checks the dependency graph summary the Parser
Engine already computed (Module 5) - circular %run chains and unresolved
notebook references are real migration risks regardless of cloud, so it's
worth surfacing them again at validation time, not just during parsing.
Also confirms every notebook the Transformation Plan expected to write
actually exists in the migrated output (catches a Replacement Engine
that silently skipped a file).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from validation.finding import ValidationCategory, ValidationFinding, ValidationSeverity


class DependencyValidator:
    def validate(
        self, transformation_plan: Dict, target_root: Path, dependency_graph_summary: Dict
    ) -> List[ValidationFinding]:
        findings: List[ValidationFinding] = []

        if not dependency_graph_summary.get("is_acyclic", True):
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.DEPENDENCY,
                    severity=ValidationSeverity.ERROR,
                    message="Circular %run / dbutils.notebook.run dependency detected",
                    detail=str(dependency_graph_summary.get("cycles")),
                )
            )

        for unresolved in dependency_graph_summary.get("unresolved_references", []):
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.DEPENDENCY,
                    severity=ValidationSeverity.WARNING,
                    message="Unresolved notebook reference could not be matched to a real "
                    "notebook during parsing",
                    notebook=unresolved.get("source_notebook"),
                    detail=unresolved.get("raw_reference"),
                )
            )

        for notebook_plan in transformation_plan["notebook_plans"]:
            relative_path = notebook_plan["relative_path"]
            if not (target_root / relative_path).exists():
                findings.append(
                    ValidationFinding(
                        category=ValidationCategory.DEPENDENCY,
                        severity=ValidationSeverity.ERROR,
                        message="Notebook was planned but was not written to the migrated "
                        "output; a downstream %run reference to it will fail",
                        notebook=relative_path,
                    )
                )

        if not findings:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.DEPENDENCY,
                    severity=ValidationSeverity.INFO,
                    message="Dependency graph is acyclic, fully resolved, and every planned "
                    "notebook was written",
                )
            )
        return findings
