"""
tests.test_reporting_engine
==============================
Unit tests for each of the 7 report builders and the ReportingEngine
PipelineStage itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.exceptions import ReportingEngineError
from orchestrator.context import PipelineContext
from reporting.dependency_report import build_dependency_report
from reporting.deployment_report import build_deployment_report
from reporting.manual_review_report import build_manual_review_report
from reporting.migration_summary_report import build_migration_summary_report
from reporting.parser_report import build_parser_report
from reporting.reporting_engine import ReportingEngine
from reporting.transformation_report import build_transformation_report
from reporting.validation_report_md import build_validation_report_md


# ---------------------------------------------------------------------------
# Fixtures: minimal-but-realistic artifact shapes
# ---------------------------------------------------------------------------

def _knowledge_model() -> dict:
    return {
        "repo_name": "Test-Platform",
        "notebook_metadata": [
            {"relative_path": "Bronze/x.py", "category": "Bronze", "language": "python",
             "cell_count": 3, "azure_construct_count": 1, "parse_error": None},
        ],
        "dependencies": {
            "edges": [
                {"source_notebook": "Bronze/x.py", "dependency_type": "run_magic",
                 "resolved_target": "Common/utils.py", "is_resolved": True,
                 "raw_reference": "../Common/utils"},
            ],
            "graph_summary": {
                "node_count": 2, "edge_count": 1, "is_acyclic": True,
                "cycles": [], "topological_order": ["Common/utils.py", "Bronze/x.py"],
                "unresolved_references": [],
            },
        },
        "azure_constructs": [
            {"construct_type": "abfss_path", "value": "abfss://x", "occurrences": 1, "found_in": ["Bronze/x.py"]},
        ],
        "configuration_references": [],
        "transformation_candidates": [
            {"construct_type": "abfss_path", "value": "abfss://x", "rule_category_hint": "storage_rules",
             "occurrences": 1, "found_in": ["Bronze/x.py"]},
        ],
        "business_objects": [
            {"name": "bronze.customers", "type": "table", "referenced_in": ["Bronze/x.py"]},
            {"name": "get_run_id", "type": "shared_function", "defined_in": "Common/utils.py", "arg_count": 0},
        ],
        "manual_review_items": [
            {"notebook": "Bronze/x.py", "reason": "JDBC connection", "detail": "jdbc:sqlserver://x"},
        ],
    }


def _transformation_plan() -> dict:
    return {
        "repo_name": "Test-Platform",
        "summary": {
            "notebook_count": 1, "total_operations": 2,
            "notebooks_with_manual_review": 1,
            "by_operation_type": {"keep_business_logic": 1, "flag_manual_review": 1},
        },
        "notebook_plans": [
            {
                "relative_path": "Bronze/x.py", "category": "Bronze",
                "operation_count": 2, "requires_manual_review": True,
                "operations": [
                    {"operation_type": "keep_business_logic", "action": "keep",
                     "construct_type": None, "original_value": None, "resolved_value": None,
                     "requires_manual_review": False, "notes": "keep"},
                    {"operation_type": "flag_manual_review", "action": "manual_review",
                     "construct_type": "mount_path", "original_value": "/mnt/x", "resolved_value": None,
                     "requires_manual_review": True, "notes": "needs review"},
                ],
            }
        ],
    }


def _validation_report() -> dict:
    return {
        "repo_name": "Test-Platform",
        "overall_status": "PASS",
        "summary": {
            "total_findings": 2, "error_count": 0, "warning_count": 1, "info_count": 1,
            "by_category": {"azure_residue": {"error": 0, "warning": 1, "info": 0}},
        },
        "findings": [
            {"category": "azure_residue", "severity": "warning", "notebook": "Bronze/x.py",
             "message": "Expected residual", "detail": "/mnt/x"},
            {"category": "syntax", "severity": "info", "notebook": None,
             "message": "All passed", "detail": None},
        ],
    }


def _deployment_plan() -> dict:
    return {
        "repo_name": "Test-Platform", "deployment_mode": "dry_run",
        "validation_gate_status": "PASS", "overall_status": "DRY_RUN_COMPLETE",
        "steps": [
            {"name": "validation_gate", "status": "completed", "detail": {}, "notes": "ok"},
            {"name": "git_commit", "status": "completed",
             "detail": {"commit_hash": "abc123def456"}, "notes": None},
            {"name": "git_push", "status": "skipped", "detail": {}, "notes": "dry run"},
        ],
    }


def _repository() -> dict:
    return {"repo_name": "Test-Platform"}


def _replacement_summary() -> dict:
    return {
        "target_repo_path": "/tmp/migrated", "notebooks_written": 1,
        "total_operations_applied": 1, "config_assets_copied": 0,
    }


def _rule_service_output() -> dict:
    return {"summary": {"total": 2, "replace": 1, "remove": 0, "manual_review": 1, "no_change": 0, "unmatched": 0}}


def _config() -> dict:
    return {"source": {"platform": "azure_databricks", "repo_path": "src"},
            "target": {"platform": "aws_databricks"}}


# ---------------------------------------------------------------------------
# Individual report builders
# ---------------------------------------------------------------------------

def test_parser_report_contains_key_sections():
    report = build_parser_report(_knowledge_model())
    assert "# Parser Report" in report
    assert "Bronze/x.py" in report
    assert "abfss_path" in report
    assert "bronze.customers" in report


def test_dependency_report_shows_topological_order():
    report = build_dependency_report(_knowledge_model())
    assert "# Dependency Report" in report
    assert "Topological Execution Order" in report
    assert "Common/utils.py" in report


def test_dependency_report_flags_cycles():
    km = _knowledge_model()
    km["dependencies"]["graph_summary"]["is_acyclic"] = False
    km["dependencies"]["graph_summary"]["cycles"] = [["A.py", "B.py"]]
    report = build_dependency_report(km)
    assert "Cycles Detected" in report
    assert "A.py -> B.py" in report


def test_transformation_report_shows_operation_counts():
    report = build_transformation_report(_transformation_plan())
    assert "# Transformation Report" in report
    assert "keep_business_logic" in report
    assert "Bronze/x.py" in report


def test_validation_report_md_shows_overall_status():
    report = build_validation_report_md(_validation_report())
    assert "# Validation Report" in report
    assert "PASS" in report
    assert "Expected residual" in report


def test_deployment_report_shows_commit_hash():
    report = build_deployment_report(_deployment_plan())
    assert "# Deployment Report" in report
    assert "abc123def456" in report
    assert "DRY_RUN_COMPLETE" in report


def test_manual_review_report_consolidates_all_sources():
    report = build_manual_review_report(
        _knowledge_model(), _transformation_plan(), _validation_report()
    )
    assert "# Manual Review Report" in report
    assert "/mnt/x" in report  # from transformation plan
    assert "jdbc:sqlserver://x" in report  # from knowledge model parser-level flags
    assert "Expected residual" in report  # from validation warnings


def test_migration_summary_report_shows_automation_rate():
    report = build_migration_summary_report(
        _config(), _repository(), _knowledge_model(), _rule_service_output(),
        _replacement_summary(), _validation_report(), _deployment_plan(),
    )
    assert "# Migration Summary Report" in report
    assert "azure_databricks -> aws_databricks" in report
    assert "50.0%" in report  # 1 of 2 constructs automated


def test_migration_summary_report_handles_zero_candidates():
    rs_output = {"summary": {"total": 0, "replace": 0, "remove": 0, "manual_review": 0, "no_change": 0, "unmatched": 0}}
    report = build_migration_summary_report(
        _config(), _repository(), _knowledge_model(), rs_output,
        _replacement_summary(), _validation_report(), _deployment_plan(),
    )
    assert "No transformation candidates" in report


# ---------------------------------------------------------------------------
# ReportingEngine (PipelineStage)
# ---------------------------------------------------------------------------

def _full_context(tmp_path: Path) -> PipelineContext:
    context = PipelineContext(config={
        **_config(),
        "output": {"reports_dir": str(tmp_path / "reports")},
    })
    context.set_artifact("knowledge_model", _knowledge_model())
    context.set_artifact("transformation_plan", _transformation_plan())
    context.set_artifact("validation_report", _validation_report())
    context.set_artifact("deployment_plan", _deployment_plan())
    context.set_artifact("repository", _repository())
    context.set_artifact("replacement_summary", _replacement_summary())
    context.set_artifact("rule_service_output", _rule_service_output())
    return context


def test_reporting_engine_requires_all_upstream_artifacts():
    engine = ReportingEngine()
    context = PipelineContext(config={"output": {"reports_dir": "unused"}})
    with pytest.raises(ReportingEngineError, match="requires the following artifacts"):
        engine.run(context)


def test_reporting_engine_writes_all_seven_reports(tmp_path: Path):
    engine = ReportingEngine()
    context = _full_context(tmp_path)

    result_context = engine.run(context)
    reports = result_context.get_artifact("reports")

    expected_files = {
        "ParserReport.md", "DependencyReport.md", "TransformationReport.md",
        "ValidationReport.md", "DeploymentReport.md", "ManualReviewReport.md",
        "MigrationSummaryReport.md",
    }
    assert set(reports["files"].keys()) == expected_files
    for path_str in reports["files"].values():
        assert Path(path_str).exists()
        assert Path(path_str).read_text().strip()  # non-empty

    assert result_context.metadata["reporting_complete"] is True
    assert result_context.metadata["pipeline_complete"] is True


# ---------------------------------------------------------------------------
# Full pipeline integration against the real demo repo (all 12 modules)
# ---------------------------------------------------------------------------

def test_reporting_engine_full_12_stage_pipeline_against_real_demo_repo(tmp_path: Path):
    from auth.auth_manager import AuthenticationManager
    from config.config_manager import ConfigurationManager
    from deployment.deployment_engine import DeploymentEngine
    from orchestrator.orchestrator import Orchestrator
    from parser.parser_engine import ParserEngine
    from replacement.replacement_engine import ReplacementEngine
    from repository.repository_manager import RepositoryManager, _PROJECT_ROOT
    from rules.rule_repository import RuleRepository
    from rule_service.rule_service import RuleService
    from transformation.transformation_planner import TransformationPlanner
    from validation.validation_engine import ValidationEngine

    real_source = _PROJECT_ROOT / "ucmp-demo" / "Loan-Platform"
    if not real_source.exists():
        pytest.skip("ucmp-demo/Loan-Platform not present in this checkout")

    env = {
        "UCMP__SOURCE__REPO_PATH": str(real_source),
        "UCMP__TARGET__REPO_PATH": str(tmp_path / "migrated"),
        "UCMP__OUTPUT__KNOWLEDGE_MODEL_DIR": str(tmp_path / "knowledge_model"),
        "UCMP__OUTPUT__REPORTS_DIR": str(tmp_path / "reports"),
    }
    config_manager = ConfigurationManager(config_path=None, env=env)
    auth_manager = AuthenticationManager()
    repository_manager = RepositoryManager(
        token_store=auth_manager.token_store, staging_dir=str(tmp_path / "staging")
    )
    parser_engine = ParserEngine()
    rule_repository = RuleRepository()
    rule_service = RuleService(rule_repository=rule_repository)
    planner = TransformationPlanner()
    replacement_engine = ReplacementEngine()
    validation_engine = ValidationEngine()
    deployment_engine = DeploymentEngine(
        token_store=auth_manager.token_store, remote_root=str(tmp_path / "remote")
    )
    reporting_engine = ReportingEngine()

    orchestrator = Orchestrator(stages=[
        config_manager, auth_manager, repository_manager, parser_engine,
        rule_repository, rule_service, planner, replacement_engine,
        validation_engine, deployment_engine, reporting_engine,
    ])
    context = orchestrator.run(PipelineContext())

    assert context.summary()["overall_status"] == "SUCCESS"
    assert len(context.stage_results) == 11  # all 11 real stages (Module 1 has no separate stage)

    reports = context.get_artifact("reports")
    assert len(reports["files"]) == 7

    summary_text = Path(reports["files"]["MigrationSummaryReport.md"]).read_text()
    assert "Loan-Platform" in summary_text
    assert "16" in summary_text  # notebook count appears somewhere

    manual_review_text = Path(reports["files"]["ManualReviewReport.md"]).read_text()
    assert "azure_sdk_import" in manual_review_text
