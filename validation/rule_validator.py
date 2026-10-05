"""
validation.rule_validator
============================
Rule Validation: spot-checks that every `replace` operation in the
Transformation Plan actually landed in the migrated notebook - the
original value is gone, the resolved value is present. This validates the
*execution* (Module 9), not the *decision* (Module 7) - it would catch a
Replacement Engine bug even if Rule Service's logic were perfect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from validation.finding import ValidationCategory, ValidationFinding, ValidationSeverity


class RuleValidator:
    def validate(self, transformation_plan: Dict, target_root: Path, content_map: Dict[str, str] | None = None) -> List[ValidationFinding]:
        findings: List[ValidationFinding] = []

        for notebook_plan in transformation_plan["notebook_plans"]:
            relative_path = notebook_plan["relative_path"]
            output_path = target_root / relative_path
            if content_map is not None and relative_path in content_map:
                text = content_map[relative_path]
            else:
                if not output_path.exists():
                    continue  # reported by DependencyValidator instead
                text = output_path.read_text(encoding="utf-8", errors="ignore")

            for op in notebook_plan["operations"]:
                if op["action"] != "replace":
                    continue
                original_value = op.get("original_value")
                resolved_value = op.get("resolved_value")

                if original_value and original_value in text:
                    findings.append(
                        ValidationFinding(
                            category=ValidationCategory.RULE_VALIDATION,
                            severity=ValidationSeverity.ERROR,
                            message=f"Rule {op['rule_id']} was supposed to replace this value "
                            f"but the original value is still present",
                            notebook=relative_path,
                            detail=original_value,
                        )
                    )
                if resolved_value and resolved_value not in text:
                    findings.append(
                        ValidationFinding(
                            category=ValidationCategory.RULE_VALIDATION,
                            severity=ValidationSeverity.ERROR,
                            message=f"Rule {op['rule_id']}'s resolved value was not found in "
                            f"the migrated notebook - replacement may not have been applied",
                            notebook=relative_path,
                            detail=resolved_value,
                        )
                    )

        if not findings:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.RULE_VALIDATION,
                    severity=ValidationSeverity.INFO,
                    message="All planned replace operations were correctly applied",
                )
            )
        return findings
