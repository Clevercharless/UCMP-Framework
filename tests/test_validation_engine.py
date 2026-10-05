"""
tests.test_validation_engine
===============================
Unit tests for every one of the seven validators (Rule, Azure Residue,
Unsupported SDK, Syntax, Dependency, Configuration, Hardcoded Secret) and
the ValidationEngine PipelineStage itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.exceptions import ValidationEngineError
from orchestrator.context import PipelineContext
from replacement.migration_banner import build_banner
from validation.banner_utils import strip_banner
from validation.config_validator import ConfigValidator
from validation.dependency_validator import DependencyValidator
from validation.finding import ValidationSeverity
from validation.residue_detector import AzureResidueDetector
from validation.rule_validator import RuleValidator
from validation.sdk_detector import UnsupportedSDKDetector
from validation.secret_detector import HardcodedSecretDetector
from validation.syntax_validator import SyntaxValidator
from validation.validation_engine import ValidationEngine


# ---------------------------------------------------------------------------
# banner_utils.strip_banner
# ---------------------------------------------------------------------------

def test_strip_banner_removes_only_banner_block():
    banner = build_banner("python", applied_count=1, manual_review_ops=[
        {"original_value": "abfss://x", "notes": "test"}
    ])
    full_text = f"# Databricks notebook source\n\n{banner}\nreal_code = 1\n"
    stripped = strip_banner(full_text)
    assert "abfss://x" not in stripped
    assert "real_code = 1" in stripped
    assert "Databricks notebook source" in stripped


# ---------------------------------------------------------------------------
# RuleValidator
# ---------------------------------------------------------------------------

def _plan_with_op(relative_path: str, **op_overrides) -> dict:
    op = {
        "operation_type": "replace_storage_path", "action": "replace",
        "original_value": "abfss://x", "resolved_value": "s3://y",
        "rule_id": "r-1", "requires_manual_review": False, "notes": "t",
        "construct_type": "abfss_path",
    }
    op.update(op_overrides)
    return {"notebook_plans": [{"relative_path": relative_path, "operations": [op]}]}


def test_rule_validator_passes_when_replacement_correctly_applied(tmp_path: Path):
    (tmp_path / "nb.py").write_text("# Databricks notebook source\npath = 's3://y'\n")
    plan = _plan_with_op("nb.py")
    findings = RuleValidator().validate(plan, tmp_path)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


def test_rule_validator_fails_when_original_value_still_present(tmp_path: Path):
    (tmp_path / "nb.py").write_text("# Databricks notebook source\npath = 'abfss://x'\n")
    plan = _plan_with_op("nb.py")
    findings = RuleValidator().validate(plan, tmp_path)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


def test_rule_validator_fails_when_resolved_value_missing(tmp_path: Path):
    (tmp_path / "nb.py").write_text("# Databricks notebook source\nprint(1)\n")
    plan = _plan_with_op("nb.py")
    findings = RuleValidator().validate(plan, tmp_path)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# AzureResidueDetector
# ---------------------------------------------------------------------------

def test_residue_detector_flags_unexpected_construct_as_error(tmp_path: Path):
    (tmp_path / "nb.py").write_text(
        "# Databricks notebook source\npath = 'abfss://leaked@acct.dfs.core.windows.net/x'\n"
    )
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    findings = AzureResidueDetector().validate(plan, tmp_path)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


def test_residue_detector_downgrades_expected_residue_to_warning(tmp_path: Path):
    value = "abfss://x@acct.dfs.core.windows.net/y"
    (tmp_path / "nb.py").write_text(f"# Databricks notebook source\npath = '{value}'\n")
    plan = {
        "notebook_plans": [{
            "relative_path": "nb.py",
            "operations": [{
                "action": "manual_review", "original_value": value,
                "construct_type": "abfss_path",
            }],
        }]
    }
    findings = AzureResidueDetector().validate(plan, tmp_path)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)
    assert any(f.severity == ValidationSeverity.WARNING for f in findings)


def test_residue_detector_excludes_key_vault_from_false_positive(tmp_path: Path):
    """dbutils.secrets.get(...) is cloud-agnostic; migrated scope names must not
    be flagged as residue just because the same call syntax matches."""
    (tmp_path / "nb.py").write_text(
        '# Databricks notebook source\n'
        'x = dbutils.secrets.get(scope="loanplatform-kv-aws", key="x")\n'
    )
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    findings = AzureResidueDetector().validate(plan, tmp_path)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


def test_residue_detector_ignores_banner_content(tmp_path: Path):
    """A value quoted inside the banner's own documentation must not
    trigger a false 'unexpected residue' finding."""
    banner = build_banner("python", applied_count=0, manual_review_ops=[
        {"original_value": "abfss://banner-only@acct.dfs.core.windows.net/x", "notes": "t"}
    ])
    text = f"# Databricks notebook source\n\n{banner}\nprint('clean')\n"
    (tmp_path / "nb.py").write_text(text)
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    findings = AzureResidueDetector().validate(plan, tmp_path)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# UnsupportedSDKDetector
# ---------------------------------------------------------------------------

def test_sdk_detector_flags_undocumented_import_as_error(tmp_path: Path):
    (tmp_path / "nb.py").write_text("# Databricks notebook source\nimport azure.identity\n")
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    findings = UnsupportedSDKDetector().validate(plan, tmp_path)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


def test_sdk_detector_downgrades_documented_import_to_warning(tmp_path: Path):
    (tmp_path / "nb.py").write_text("# Databricks notebook source\nimport azure.identity\n")
    plan = {
        "notebook_plans": [{
            "relative_path": "nb.py",
            "operations": [{"construct_type": "azure_sdk_import", "original_value": "import azure.identity"}],
        }]
    }
    findings = UnsupportedSDKDetector().validate(plan, tmp_path)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# SyntaxValidator
# ---------------------------------------------------------------------------

def test_syntax_validator_passes_valid_python(tmp_path: Path):
    (tmp_path / "nb.py").write_text("# Databricks notebook source\nx = 1\n")
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    repository = {"notebooks": [{"relative_path": "nb.py", "language": "python"}]}
    findings = SyntaxValidator().validate(plan, tmp_path, repository)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


def test_syntax_validator_fails_invalid_python(tmp_path: Path):
    (tmp_path / "nb.py").write_text("# Databricks notebook source\ndef broken(:\n")
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    repository = {"notebooks": [{"relative_path": "nb.py", "language": "python"}]}
    findings = SyntaxValidator().validate(plan, tmp_path, repository)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


def test_syntax_validator_fails_missing_header(tmp_path: Path):
    (tmp_path / "nb.sql").write_text("SELECT 1;\n")
    plan = {"notebook_plans": [{"relative_path": "nb.sql", "operations": []}]}
    repository = {"notebooks": [{"relative_path": "nb.sql", "language": "sql"}]}
    findings = SyntaxValidator().validate(plan, tmp_path, repository)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# DependencyValidator
# ---------------------------------------------------------------------------

def test_dependency_validator_passes_clean_graph(tmp_path: Path):
    (tmp_path / "nb.py").write_text("x")
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    graph_summary = {"is_acyclic": True, "cycles": [], "unresolved_references": []}
    findings = DependencyValidator().validate(plan, tmp_path, graph_summary)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


def test_dependency_validator_flags_cycle_as_error(tmp_path: Path):
    plan = {"notebook_plans": []}
    graph_summary = {"is_acyclic": False, "cycles": [["A", "B"]], "unresolved_references": []}
    findings = DependencyValidator().validate(plan, tmp_path, graph_summary)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


def test_dependency_validator_flags_missing_output_file_as_error(tmp_path: Path):
    plan = {"notebook_plans": [{"relative_path": "never_written.py", "operations": []}]}
    graph_summary = {"is_acyclic": True, "cycles": [], "unresolved_references": []}
    findings = DependencyValidator().validate(plan, tmp_path, graph_summary)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# ConfigValidator
# ---------------------------------------------------------------------------

def test_config_validator_flags_missing_rule_category():
    knowledge_model = {"transformation_candidates": [{"rule_category_hint": "storage_rules"}]}
    rule_repo_artifact = {"categories": ["secret"]}  # storage missing
    repository = {"config_assets": []}
    replacement_summary = {"config_assets_copied": 0}
    findings = ConfigValidator().validate(knowledge_model, rule_repo_artifact, repository, replacement_summary)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


def test_config_validator_flags_config_asset_count_mismatch():
    knowledge_model = {"transformation_candidates": []}
    rule_repo_artifact = {"categories": []}
    repository = {"config_assets": [{"relative_path": "Config/a.yaml"}]}
    replacement_summary = {"config_assets_copied": 0}
    findings = ConfigValidator().validate(knowledge_model, rule_repo_artifact, repository, replacement_summary)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


def test_config_validator_passes_when_fully_covered():
    knowledge_model = {"transformation_candidates": [{"rule_category_hint": "storage_rules"}]}
    rule_repo_artifact = {"categories": ["storage"]}
    repository = {"config_assets": [{"relative_path": "Config/a.yaml"}]}
    replacement_summary = {"config_assets_copied": 1}
    findings = ConfigValidator().validate(knowledge_model, rule_repo_artifact, repository, replacement_summary)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# HardcodedSecretDetector
# ---------------------------------------------------------------------------

def test_secret_detector_flags_hardcoded_literal(tmp_path: Path):
    (tmp_path / "nb.py").write_text(
        '# Databricks notebook source\npassword = "SuperSecretValue123"\n'
    )
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    findings = HardcodedSecretDetector().validate(plan, tmp_path)
    assert any(f.severity == ValidationSeverity.ERROR for f in findings)


def test_secret_detector_ignores_dbutils_secrets_get(tmp_path: Path):
    (tmp_path / "nb.py").write_text(
        '# Databricks notebook source\n'
        'password = dbutils.secrets.get(scope="kv-aws", key="password")\n'
    )
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    findings = HardcodedSecretDetector().validate(plan, tmp_path)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


def test_secret_detector_ignores_comment_lines(tmp_path: Path):
    (tmp_path / "nb.py").write_text(
        '# Databricks notebook source\n# password = "example-not-real"\n'
    )
    plan = {"notebook_plans": [{"relative_path": "nb.py", "operations": []}]}
    findings = HardcodedSecretDetector().validate(plan, tmp_path)
    assert all(f.severity != ValidationSeverity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# ValidationEngine (PipelineStage)
# ---------------------------------------------------------------------------

def test_validation_engine_requires_all_upstream_artifacts():
    engine = ValidationEngine()
    context = PipelineContext(config={"output": {"reports_dir": "unused"}})
    with pytest.raises(ValidationEngineError, match="requires the following artifacts"):
        engine.run(context)


def test_validation_engine_overall_status_fail_when_error_present(tmp_path: Path):
    (tmp_path / "target").mkdir()
    engine = ValidationEngine()
    context = PipelineContext(config={"output": {"reports_dir": str(tmp_path / "reports")}})
    context.set_artifact("transformation_plan", {
        "notebook_plans": [{"relative_path": "missing.py", "operations": []}]
    })
    context.set_artifact("repository", {"repo_name": "T", "notebooks": [], "config_assets": []})
    context.set_artifact("replacement_summary", {
        "target_repo_path": str(tmp_path / "target"), "config_assets_copied": 0,
    })
    context.set_artifact("knowledge_model", {"transformation_candidates": []})
    context.set_artifact("rule_repository", {"categories": []})
    context.set_artifact("dependency_graph_summary", {"is_acyclic": True, "cycles": [], "unresolved_references": []})

    result_context = engine.run(context)
    report = result_context.get_artifact("validation_report")
    assert report["overall_status"] == "FAIL"  # missing.py was never written
    assert result_context.metadata["validation_status"] == "FAIL"


def test_validation_engine_writes_report_json(tmp_path: Path):
    (tmp_path / "target").mkdir()
    engine = ValidationEngine()
    reports_dir = tmp_path / "reports"
    context = PipelineContext(config={"output": {"reports_dir": str(reports_dir)}})
    context.set_artifact("transformation_plan", {"notebook_plans": []})
    context.set_artifact("repository", {"repo_name": "T", "notebooks": [], "config_assets": []})
    context.set_artifact("replacement_summary", {
        "target_repo_path": str(tmp_path / "target"), "config_assets_copied": 0,
    })
    context.set_artifact("knowledge_model", {"transformation_candidates": []})
    context.set_artifact("rule_repository", {"categories": []})
    context.set_artifact("dependency_graph_summary", {"is_acyclic": True, "cycles": [], "unresolved_references": []})

    result_context = engine.run(context)
    output_path = reports_dir / "ValidationReport.json"
    assert output_path.exists()
    assert result_context.get_artifact("validation_report")["overall_status"] == "PASS"


# ---------------------------------------------------------------------------
# Full pipeline integration against the real demo repo
# ---------------------------------------------------------------------------

def test_validation_engine_full_pipeline_passes_against_real_demo_repo(tmp_path: Path):
    from auth.auth_manager import AuthenticationManager
    from config.config_manager import ConfigurationManager
    from orchestrator.orchestrator import Orchestrator
    from parser.parser_engine import ParserEngine
    from replacement.replacement_engine import ReplacementEngine
    from repository.repository_manager import RepositoryManager, _PROJECT_ROOT
    from rules.rule_repository import RuleRepository
    from rule_service.rule_service import RuleService
    from transformation.transformation_planner import TransformationPlanner

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

    orchestrator = Orchestrator(stages=[
        config_manager, auth_manager, repository_manager, parser_engine,
        rule_repository, rule_service, planner, replacement_engine, validation_engine,
    ])
    context = orchestrator.run(PipelineContext())

    assert context.summary()["overall_status"] == "SUCCESS"
    report = context.get_artifact("validation_report")
    assert report["overall_status"] == "PASS"
    assert report["summary"]["error_count"] == 0
