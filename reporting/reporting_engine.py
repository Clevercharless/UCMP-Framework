"""
reporting.reporting_engine
=============================
ReportingEngine is the twelfth and final pipeline stage. It generates
all seven required reports as Markdown files in
context.config["output"]["reports_dir"]:

    ParserReport.md, DependencyReport.md, TransformationReport.md,
    ValidationReport.md, DeploymentReport.md, ManualReviewReport.md,
    MigrationSummaryReport.md

Every report is built purely from artifacts earlier stages already
produced - this stage adds no new analysis or decisions, only
presentation. It never writes to any notebook file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from common.exceptions import ReportingEngineError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from reporting.dependency_report import build_dependency_report
from reporting.deployment_report import build_deployment_report
from reporting.manual_review_report import build_manual_review_report
from reporting.migration_summary_report import build_migration_summary_report
from reporting.parser_report import build_parser_report
from reporting.transformation_report import build_transformation_report
from reporting.validation_report_md import build_validation_report_md

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_ARTIFACTS = [
    "knowledge_model", "transformation_plan", "validation_report",
    "deployment_plan", "repository", "replacement_summary", "rule_service_output",
]


class ReportingEngine(PipelineStage):
    """Generates all seven required Markdown reports from existing pipeline artifacts."""

    name = "ReportingEngine"

    def run(self, context: PipelineContext) -> PipelineContext:
        missing = [key for key in _REQUIRED_ARTIFACTS if not context.get_artifact(key)]
        if missing:
            raise ReportingEngineError(
                f"ReportingEngine requires the following artifacts to be populated first: {missing}"
            )
        if not context.config:
            raise ReportingEngineError("ReportingEngine requires context.config")

        knowledge_model = context.get_artifact("knowledge_model")
        transformation_plan = context.get_artifact("transformation_plan")
        validation_report = context.get_artifact("validation_report")
        deployment_plan = context.get_artifact("deployment_plan")
        repository = context.get_artifact("repository")
        replacement_summary = context.get_artifact("replacement_summary")
        rule_service_output = context.get_artifact("rule_service_output")

        reports = {
            "ParserReport.md": build_parser_report(knowledge_model),
            "DependencyReport.md": build_dependency_report(knowledge_model),
            "TransformationReport.md": build_transformation_report(transformation_plan),
            "ValidationReport.md": build_validation_report_md(validation_report),
            "DeploymentReport.md": build_deployment_report(deployment_plan),
            "ManualReviewReport.md": build_manual_review_report(
                knowledge_model, transformation_plan, validation_report
            ),
            "MigrationSummaryReport.md": build_migration_summary_report(
                context.config, repository, knowledge_model, rule_service_output,
                replacement_summary, validation_report, deployment_plan,
            ),
        }

        output_dir = self._resolve_reports_dir(context)
        written_paths = self._write_reports(output_dir, reports)

        context.set_artifact("reports", {"reports_dir": str(output_dir), "files": written_paths})
        context.metadata["reporting_complete"] = True
        context.metadata["pipeline_complete"] = True

        # Workspace mode uses only process-local selected-notebook/cache files to
        # satisfy the existing parser/validator interfaces. They are never stored
        # under output/_staging and are removed after reports are generated.
        self._cleanup_workspace_temp_data(context)

        logger.info(
            "Reporting Engine wrote %d report(s) to %s: %s",
            len(written_paths), output_dir, sorted(written_paths.keys()),
        )
        return context

    # -- internals --------------------------------------------------------

    @staticmethod
    def _cleanup_workspace_temp_data(context: PipelineContext) -> None:
        import shutil
        for key in ("workspace_selected_cache_root", "workspace_preview_root"):
            value = context.metadata.get(key)
            if value:
                path = Path(str(value))
                try:
                    if path.exists():
                        shutil.rmtree(path)
                except OSError as exc:
                    logger.warning("Could not clean temporary workspace data %s: %s", path, exc)

    def _resolve_reports_dir(self, context: PipelineContext) -> Path:
        configured = context.config["output"]["reports_dir"]
        path = Path(configured)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write_reports(output_dir: Path, reports: Dict[str, str]) -> Dict[str, str]:
        written_paths = {}
        for filename, content in reports.items():
            output_path = output_dir / filename
            output_path.write_text(content, encoding="utf-8")
            written_paths[filename] = str(output_path)
        return written_paths
