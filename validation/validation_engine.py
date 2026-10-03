"""
validation.validation_engine
===============================
ValidationEngine is the tenth pipeline stage. It runs all seven
validators (Rule, Azure Residue, Unsupported SDK, Syntax, Dependency,
Configuration, Hardcoded Secret) against the migrated output, aggregates
every finding into a single ValidationReport, and computes the overall
PASS/FAIL: FAIL if any finding has ERROR severity, PASS otherwise
(WARNING/INFO findings never fail the run).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from common.exceptions import ValidationEngineError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from validation.config_validator import ConfigValidator
from validation.dependency_validator import DependencyValidator
from validation.finding import ValidationFinding, ValidationSeverity
from validation.residue_detector import AzureResidueDetector
from validation.rule_validator import RuleValidator
from validation.sdk_detector import UnsupportedSDKDetector
from validation.secret_detector import HardcodedSecretDetector
from validation.syntax_validator import SyntaxValidator

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_ARTIFACTS = [
    "transformation_plan", "repository", "replacement_summary",
    "knowledge_model", "rule_repository", "dependency_graph_summary",
]


class ValidationEngine(PipelineStage):
    """Runs all seven validators and produces the ValidationReport with overall PASS/FAIL."""

    name = "ValidationEngine"

    def __init__(self):
        self._rule_validator = RuleValidator()
        self._residue_detector = AzureResidueDetector()
        self._sdk_detector = UnsupportedSDKDetector()
        self._syntax_validator = SyntaxValidator()
        self._dependency_validator = DependencyValidator()
        self._config_validator = ConfigValidator()
        self._secret_detector = HardcodedSecretDetector()

    def run(self, context: PipelineContext) -> PipelineContext:
        missing = [key for key in _REQUIRED_ARTIFACTS if not context.get_artifact(key)]
        if missing:
            raise ValidationEngineError(
                f"ValidationEngine requires the following artifacts to be populated first: "
                f"{missing}"
            )

        transformation_plan = context.get_artifact("transformation_plan")
        repository = context.get_artifact("repository")
        replacement_summary = context.get_artifact("replacement_summary")
        knowledge_model = context.get_artifact("knowledge_model")
        rule_repository_artifact = context.get_artifact("rule_repository")
        dependency_graph_summary = context.get_artifact("dependency_graph_summary")

        target_root = Path(replacement_summary["target_repo_path"])

        findings: List[ValidationFinding] = []
        findings += self._rule_validator.validate(transformation_plan, target_root)
        findings += self._residue_detector.validate(transformation_plan, target_root)
        findings += self._sdk_detector.validate(transformation_plan, target_root)
        findings += self._syntax_validator.validate(transformation_plan, target_root, repository)
        findings += self._dependency_validator.validate(
            transformation_plan, target_root, dependency_graph_summary
        )
        findings += self._config_validator.validate(
            knowledge_model, rule_repository_artifact, repository, replacement_summary
        )
        findings += self._secret_detector.validate(transformation_plan, target_root)

        report = self._build_report(repository["repo_name"], findings)
        output_path = self._write_report(context, report)

        context.set_artifact("validation_report", report)
        context.metadata["validation_complete"] = True
        context.metadata["validation_status"] = report["overall_status"]
        context.metadata["validation_report_path"] = str(output_path)

        logger.info(
            "Validation complete: overall_status=%s (%d error(s), %d warning(s), %d info)",
            report["overall_status"],
            report["summary"]["error_count"],
            report["summary"]["warning_count"],
            report["summary"]["info_count"],
        )
        return context

    # -- internals --------------------------------------------------------

    @staticmethod
    def _build_report(repo_name: str, findings: List[ValidationFinding]) -> Dict:
        error_count = sum(1 for f in findings if f.severity == ValidationSeverity.ERROR)
        warning_count = sum(1 for f in findings if f.severity == ValidationSeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == ValidationSeverity.INFO)

        by_category: Dict[str, Dict[str, int]] = {}
        for finding in findings:
            bucket = by_category.setdefault(
                finding.category.value, {"error": 0, "warning": 0, "info": 0}
            )
            bucket[finding.severity.value] += 1

        return {
            "repo_name": repo_name,
            "overall_status": "FAIL" if error_count > 0 else "PASS",
            "summary": {
                "total_findings": len(findings),
                "error_count": error_count,
                "warning_count": warning_count,
                "info_count": info_count,
                "by_category": by_category,
            },
            "findings": [f.to_dict() for f in findings],
        }

    def _write_report(self, context: PipelineContext, report: Dict) -> Path:
        output_dir_config = context.config["output"]["reports_dir"]
        output_dir = Path(output_dir_config)
        if not output_dir.is_absolute():
            output_dir = _PROJECT_ROOT / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "ValidationReport.json"
        output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return output_path
