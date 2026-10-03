"""
validation.config_validator
==============================
Configuration Validation: checks migration-specific configuration
concerns that ConfigurationManager (Module 2) doesn't cover, because they
depend on what was actually FOUND during parsing, not just the config
file's own internal consistency:

  * Every rule category referenced by a transformation candidate has at
    least one loaded rule (a coverage gap here means some construct type
    had NO way to be resolved at all).
  * Every Config/* asset discovered by the Repository Manager was actually
    copied to the migrated output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from validation.finding import ValidationCategory, ValidationFinding, ValidationSeverity


class ConfigValidator:
    def validate(
        self,
        knowledge_model: Dict,
        rule_repository_artifact: Dict,
        repository: Dict,
        replacement_summary: Dict,
    ) -> List[ValidationFinding]:
        findings: List[ValidationFinding] = []

        needed_categories = {
            tc["rule_category_hint"].removesuffix("_rules")
            for tc in knowledge_model["transformation_candidates"]
        }
        available_categories = set(rule_repository_artifact.get("categories", []))
        missing_categories = needed_categories - available_categories

        for category in sorted(missing_categories):
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.CONFIGURATION,
                    severity=ValidationSeverity.ERROR,
                    message=f"No rules loaded for category '{category}', which is needed by "
                    f"at least one transformation candidate",
                )
            )

        expected_config_assets = len(repository.get("config_assets", []))
        actual_config_assets = replacement_summary.get("config_assets_copied", 0)
        if actual_config_assets != expected_config_assets:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.CONFIGURATION,
                    severity=ValidationSeverity.ERROR,
                    message=f"Expected {expected_config_assets} config asset(s) to be migrated, "
                    f"but only {actual_config_assets} were copied",
                )
            )

        if not findings:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.CONFIGURATION,
                    severity=ValidationSeverity.INFO,
                    message="Rule category coverage is complete and all config assets were migrated",
                )
            )
        return findings
