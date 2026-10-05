"""
validation.residue_detector
==============================
Azure Residue Detection: re-runs the Parser Engine's RegexParser (Module
5) against the MIGRATED notebooks, so it detects Azure constructs using
exactly the same logic that found them in the source repo. Any Azure
construct still present in a notebook whose Transformation Plan operation
was NOT manual_review/unmatched/no_change for that exact value is
unexpected residue (ERROR - something should have been replaced but
wasn't). A construct that IS expected to remain (per the plan) is reported
as a WARNING, not silently ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

from parser.regex_parser import AzureConstructType, RegexParser
from validation.banner_utils import strip_banner
from validation.finding import ValidationCategory, ValidationFinding, ValidationSeverity

# dbutils.secrets.get(scope=...) is a cloud-agnostic Databricks API - it is
# NOT itself Azure-specific residue. Only the scope NAME was Azure-specific
# (Key Vault-backed), and secret_rules.yaml already renames that; whether
# the rename actually happened is RuleValidator's job, not this detector's.
# Re-flagging every dbutils.secrets.get(...) call here would produce a false
# positive on every correctly-migrated secret reference.
_EXCLUDED_FROM_RESIDUE = {AzureConstructType.KEY_VAULT}


class AzureResidueDetector:
    def __init__(self):
        self._regex_parser = RegexParser()

    def validate(self, transformation_plan: Dict, target_root: Path, content_map: Dict[str, str] | None = None) -> List[ValidationFinding]:
        findings: List[ValidationFinding] = []

        for notebook_plan in transformation_plan["notebook_plans"]:
            relative_path = notebook_plan["relative_path"]
            output_path = target_root / relative_path
            if content_map is not None and relative_path in content_map:
                text = content_map[relative_path]
            else:
                if not output_path.exists():
                    continue
                text = None

            expected_residue = self._expected_residue_values(notebook_plan)
            text = strip_banner(text if text is not None else output_path.read_text(encoding="utf-8", errors="ignore"))
            constructs = self._regex_parser.parse(text)

            for construct in constructs:
                if construct.construct_type in _EXCLUDED_FROM_RESIDUE:
                    continue
                if construct.value in expected_residue:
                    findings.append(
                        ValidationFinding(
                            category=ValidationCategory.AZURE_RESIDUE,
                            severity=ValidationSeverity.WARNING,
                            message=f"Expected residual {construct.construct_type.value} "
                            f"(flagged for manual review, not auto-replaced)",
                            notebook=relative_path,
                            detail=construct.value,
                        )
                    )
                else:
                    findings.append(
                        ValidationFinding(
                            category=ValidationCategory.AZURE_RESIDUE,
                            severity=ValidationSeverity.ERROR,
                            message=f"Unexpected {construct.construct_type.value} residue - "
                            f"not accounted for in the transformation plan",
                            notebook=relative_path,
                            detail=construct.value,
                        )
                    )

        if not findings:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.AZURE_RESIDUE,
                    severity=ValidationSeverity.INFO,
                    message="No Azure constructs detected in migrated notebooks",
                )
            )
        return findings

    @staticmethod
    def _expected_residue_values(notebook_plan: Dict) -> Set[str]:
        """Values the plan intentionally left untouched (manual_review/unmatched/no_change)."""
        return {
            op["original_value"]
            for op in notebook_plan["operations"]
            if op["action"] in ("manual_review", "unmatched", "no_change")
            and op.get("original_value")
        }
