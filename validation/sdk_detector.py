"""
validation.sdk_detector
=========================
Unsupported SDK Detection: specifically checks for Azure SDK imports
(azure.identity, azure.storage.blob, etc.) surviving in migrated code -
these have no drop-in AWS equivalent (per library_rules.yaml) and running
them on AWS Databricks will fail at import time. An import that the
Transformation Plan already flagged manual_review is a WARNING (known,
documented, awaiting a human rewrite); one that slipped through
undocumented is an ERROR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

from parser.regex_parser import AzureConstructType, RegexParser
from validation.banner_utils import strip_banner
from validation.finding import ValidationCategory, ValidationFinding, ValidationSeverity


class UnsupportedSDKDetector:
    def __init__(self):
        self._regex_parser = RegexParser()

    def validate(self, transformation_plan: Dict, target_root: Path) -> List[ValidationFinding]:
        findings: List[ValidationFinding] = []

        for notebook_plan in transformation_plan["notebook_plans"]:
            relative_path = notebook_plan["relative_path"]
            output_path = target_root / relative_path
            if not output_path.exists():
                continue

            documented_imports = self._documented_sdk_imports(notebook_plan)
            text = strip_banner(output_path.read_text(encoding="utf-8", errors="ignore"))
            constructs = self._regex_parser.parse(text)

            for construct in constructs:
                if construct.construct_type != AzureConstructType.AZURE_SDK_IMPORT:
                    continue
                if construct.value in documented_imports:
                    findings.append(
                        ValidationFinding(
                            category=ValidationCategory.UNSUPPORTED_SDK,
                            severity=ValidationSeverity.WARNING,
                            message="Azure SDK import present, documented in the transformation "
                            "plan as requiring manual rewrite",
                            notebook=relative_path,
                            detail=construct.value,
                        )
                    )
                else:
                    findings.append(
                        ValidationFinding(
                            category=ValidationCategory.UNSUPPORTED_SDK,
                            severity=ValidationSeverity.ERROR,
                            message="Undocumented Azure SDK import: will fail on AWS Databricks "
                            "at import time and was not flagged during planning",
                            notebook=relative_path,
                            detail=construct.value,
                        )
                    )

        if not findings:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.UNSUPPORTED_SDK,
                    severity=ValidationSeverity.INFO,
                    message="No Azure SDK imports detected in migrated notebooks",
                )
            )
        return findings

    @staticmethod
    def _documented_sdk_imports(notebook_plan: Dict) -> Set[str]:
        return {
            op["original_value"]
            for op in notebook_plan["operations"]
            if op["construct_type"] == "azure_sdk_import" and op.get("original_value")
        }
