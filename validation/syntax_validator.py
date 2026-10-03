"""
validation.syntax_validator
==============================
Syntax Validation: confirms every migrated notebook is still structurally
valid after the Replacement Engine's text substitutions and banner
insertion. For Python notebooks this means ast.parse() succeeds (the
export format makes the whole file valid Python, including comments and
inserted banner cells - see Module 5's notebook_reader.py for why). For
SQL/Scala notebooks, confirms the Databricks export header survived and
the file is non-empty, since no full SQL/Scala grammar validator is in
scope for this simulation.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List

from validation.finding import ValidationCategory, ValidationFinding, ValidationSeverity


class SyntaxValidator:
    def validate(self, transformation_plan: Dict, target_root: Path, repository: Dict) -> List[ValidationFinding]:
        findings: List[ValidationFinding] = []
        language_by_path = {nb["relative_path"]: nb["language"] for nb in repository["notebooks"]}

        for notebook_plan in transformation_plan["notebook_plans"]:
            relative_path = notebook_plan["relative_path"]
            output_path = target_root / relative_path
            if not output_path.exists():
                continue

            language = language_by_path.get(relative_path, "python")
            text = output_path.read_text(encoding="utf-8", errors="ignore")

            if language == "python":
                findings.extend(self._validate_python(relative_path, text))
            else:
                findings.extend(self._validate_non_python(relative_path, language, text))

        if not any(f.severity == ValidationSeverity.ERROR for f in findings):
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.SYNTAX,
                    severity=ValidationSeverity.INFO,
                    message="All migrated notebooks passed syntax validation",
                )
            )
        return findings

    @staticmethod
    def _validate_python(relative_path: str, text: str) -> List[ValidationFinding]:
        try:
            ast.parse(text)
        except SyntaxError as exc:
            return [
                ValidationFinding(
                    category=ValidationCategory.SYNTAX,
                    severity=ValidationSeverity.ERROR,
                    message=f"Migrated notebook is not valid Python: {exc.msg} (line {exc.lineno})",
                    notebook=relative_path,
                )
            ]
        return []

    @staticmethod
    def _validate_non_python(relative_path: str, language: str, text: str) -> List[ValidationFinding]:
        findings: List[ValidationFinding] = []
        if not text.strip():
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.SYNTAX,
                    severity=ValidationSeverity.ERROR,
                    message="Migrated notebook is empty",
                    notebook=relative_path,
                )
            )
            return findings

        expected_prefix = {"sql": "--", "scala": "//"}.get(language, "#")
        first_line = text.splitlines()[0].strip()
        if not first_line.startswith(expected_prefix) or "Databricks notebook source" not in first_line:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.SYNTAX,
                    severity=ValidationSeverity.ERROR,
                    message="Migrated notebook lost its Databricks export header",
                    notebook=relative_path,
                    detail=first_line,
                )
            )
        return findings
