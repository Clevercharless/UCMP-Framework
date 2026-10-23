"""
tests.test_replacement_engine
================================
Unit tests for replacement.migration_banner and
replacement.replacement_engine.ReplacementEngine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.exceptions import ReplacementError
from orchestrator.context import PipelineContext
from replacement.migration_banner import build_banner
from replacement.replacement_engine import ReplacementEngine


# ---------------------------------------------------------------------------
# migration_banner.build_banner
# ---------------------------------------------------------------------------

def test_banner_uses_python_comment_prefix():
    banner = build_banner("python", applied_count=2, manual_review_ops=[])
    assert banner.startswith("# COMMAND ----------")
    assert "# MAGIC %md" in banner


def test_banner_uses_sql_comment_prefix():
    banner = build_banner("sql", applied_count=1, manual_review_ops=[])
    assert banner.startswith("-- COMMAND ----------")
    assert "-- MAGIC %md" in banner


def test_banner_lists_manual_review_items():
    ops = [{"original_value": "/mnt/x", "notes": "needs a human decision"}]
    banner = build_banner("python", applied_count=0, manual_review_ops=ops)
    assert "/mnt/x" in banner
    assert "needs a human decision" in banner
    assert "Manual review required (1 item(s))" in banner


def test_banner_says_none_when_no_manual_review_items():
    banner = build_banner("python", applied_count=3, manual_review_ops=[])
    assert "Manual review required:** none" in banner


# ---------------------------------------------------------------------------
# ReplacementEngine (PipelineStage)
# ---------------------------------------------------------------------------

def _base_context(config=None) -> PipelineContext:
    return PipelineContext(config=config or {"target": {"repo_path": "unused"}})


def test_engine_requires_transformation_plan():
    engine = ReplacementEngine()
    context = _base_context()
    context.set_artifact("repository", {"notebooks": [], "config_assets": []})
    with pytest.raises(ReplacementError, match="TransformationPlanner"):
        engine.run(context)


def test_engine_requires_repository_artifact():
    engine = ReplacementEngine()
    context = _base_context()
    context.set_artifact("transformation_plan", {"notebook_plans": []})
    with pytest.raises(ReplacementError, match="RepositoryManager"):
        engine.run(context)


def _write_staged_notebook(tmp_path: Path, name: str, content: str) -> Path:
    staged = tmp_path / "staged"
    staged.mkdir(exist_ok=True)
    f = staged / name
    f.write_text(content)
    return f


def test_engine_applies_replace_operation_and_leaves_rest_untouched(tmp_path: Path):
    content = (
        "# Databricks notebook source\n"
        "def business_logic(x):\n"
        "    return x * 2\n\n"
        "path = 'abfss://bronze@acct.dfs.core.windows.net/x'\n"
    )
    source = _write_staged_notebook(tmp_path, "nb.py", content)
    target_dir = tmp_path / "target"

    engine = ReplacementEngine()
    context = _base_context({"target": {"repo_path": str(target_dir)}})
    context.set_artifact(
        "repository",
        {
            "notebooks": [{"relative_path": "nb.py", "absolute_path": str(source), "language": "python"}],
            "config_assets": [],
        },
    )
    context.set_artifact(
        "transformation_plan",
        {
            "notebook_plans": [
                {
                    "relative_path": "nb.py",
                    "operations": [
                        {
                            "operation_type": "keep_business_logic", "action": "keep",
                            "original_value": None, "resolved_value": None,
                            "requires_manual_review": False, "notes": "keep",
                        },
                        {
                            "operation_type": "replace_storage_path", "action": "replace",
                            "original_value": "abfss://bronze@acct.dfs.core.windows.net/x",
                            "resolved_value": "s3://acct-bronze/x",
                            "requires_manual_review": False, "notes": "test",
                        },
                    ],
                }
            ]
        },
    )

    result_context = engine.run(context)
    output_file = target_dir / "nb.py"
    assert output_file.exists()
    output_text = output_file.read_text()

    assert "s3://acct-bronze/x" in output_text
    assert "abfss://" not in output_text
    # Business logic byte-for-byte preserved
    assert "def business_logic(x):\n    return x * 2" in output_text

    summary = result_context.get_artifact("replacement_summary")
    assert summary["total_operations_applied"] == 1
    assert summary["notebooks_written"] == 1


def test_engine_never_modifies_manual_review_construct_text(tmp_path: Path):
    content = "# Databricks notebook source\nx = '/mnt/raw/customers'\n"
    source = _write_staged_notebook(tmp_path, "nb.py", content)
    target_dir = tmp_path / "target"

    engine = ReplacementEngine()
    context = _base_context({"target": {"repo_path": str(target_dir)}})
    context.set_artifact(
        "repository",
        {"notebooks": [{"relative_path": "nb.py", "absolute_path": str(source), "language": "python"}],
         "config_assets": []},
    )
    context.set_artifact(
        "transformation_plan",
        {"notebook_plans": [{
            "relative_path": "nb.py",
            "operations": [{
                "operation_type": "flag_manual_review", "action": "manual_review",
                "original_value": "/mnt/raw/customers", "resolved_value": None,
                "requires_manual_review": True, "notes": "needs review",
            }],
        }]},
    )

    engine.run(context)
    output_text = (target_dir / "nb.py").read_text()
    # The flagged value must remain EXACTLY as-is in the code (untouched)
    assert "x = '/mnt/raw/customers'" in output_text
    # But a banner should have been inserted noting it needs review
    assert "Manual review required (1 item(s))" in output_text


def test_engine_remove_action_erases_construct(tmp_path: Path):
    content = "# Databricks notebook source\nconf = {'fs.azure.account.key': 'x'}\n"
    source = _write_staged_notebook(tmp_path, "nb.py", content)
    target_dir = tmp_path / "target"

    engine = ReplacementEngine()
    context = _base_context({"target": {"repo_path": str(target_dir)}})
    context.set_artifact(
        "repository",
        {"notebooks": [{"relative_path": "nb.py", "absolute_path": str(source), "language": "python"}],
         "config_assets": []},
    )
    context.set_artifact(
        "transformation_plan",
        {"notebook_plans": [{
            "relative_path": "nb.py",
            "operations": [{
                "operation_type": "remove_spark_config", "action": "remove",
                "original_value": "fs.azure.account.key", "resolved_value": None,
                "requires_manual_review": False, "notes": "removed",
            }],
        }]},
    )
    engine.run(context)
    output_text = (target_dir / "nb.py").read_text()
    assert "fs.azure.account.key" not in output_text


def test_engine_copies_config_assets_verbatim(tmp_path: Path):
    config_asset_src = tmp_path / "workspace_config.yaml"
    config_asset_src.write_text("workspace:\n  name: test\n")
    target_dir = tmp_path / "target"

    engine = ReplacementEngine()
    context = _base_context({"target": {"repo_path": str(target_dir)}})
    context.set_artifact(
        "repository",
        {
            "notebooks": [],
            "config_assets": [
                {"relative_path": "Config/workspace_config.yaml", "absolute_path": str(config_asset_src)}
            ],
        },
    )
    context.set_artifact("transformation_plan", {"notebook_plans": []})

    result_context = engine.run(context)
    copied = target_dir / "Config" / "workspace_config.yaml"
    assert copied.exists()
    assert copied.read_text() == config_asset_src.read_text()
    assert result_context.get_artifact("replacement_summary")["config_assets_copied"] == 1


def test_engine_raises_when_plan_references_unknown_notebook(tmp_path: Path):
    target_dir = tmp_path / "target"
    engine = ReplacementEngine()
    context = _base_context({"target": {"repo_path": str(target_dir)}})
    context.set_artifact("repository", {"notebooks": [], "config_assets": []})
    context.set_artifact(
        "transformation_plan",
        {"notebook_plans": [{"relative_path": "Nonexistent/x.py", "operations": []}]},
    )
    with pytest.raises(ReplacementError, match="not present in the repository inventory"):
        engine.run(context)


def test_engine_no_banner_when_nothing_applied_and_no_review_needed(tmp_path: Path):
    content = "# Databricks notebook source\nprint('hello')\n"
    source = _write_staged_notebook(tmp_path, "nb.py", content)
    target_dir = tmp_path / "target"

    engine = ReplacementEngine()
    context = _base_context({"target": {"repo_path": str(target_dir)}})
    context.set_artifact(
        "repository",
        {"notebooks": [{"relative_path": "nb.py", "absolute_path": str(source), "language": "python"}],
         "config_assets": []},
    )
    context.set_artifact(
        "transformation_plan",
        {"notebook_plans": [{
            "relative_path": "nb.py",
            "operations": [{
                "operation_type": "keep_business_logic", "action": "keep",
                "original_value": None, "resolved_value": None,
                "requires_manual_review": False, "notes": "keep",
            }],
        }]},
    )
    engine.run(context)
    output_text = (target_dir / "nb.py").read_text()
    assert "UCMP Migration Notes" not in output_text
    assert output_text == content  # completely untouched


# ---------------------------------------------------------------------------
# Full pipeline integration against the real demo repo
# ---------------------------------------------------------------------------

def test_engine_full_pipeline_against_real_demo_repo(tmp_path: Path):
    from auth.auth_manager import AuthenticationManager
    from config.config_manager import ConfigurationManager
    from orchestrator.orchestrator import Orchestrator
    from parser.parser_engine import ParserEngine
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

    orchestrator = Orchestrator(stages=[
        config_manager, auth_manager, repository_manager, parser_engine,
        rule_repository, rule_service, planner, replacement_engine,
    ])
    context = orchestrator.run(PipelineContext())

    assert context.summary()["overall_status"] == "SUCCESS"
    summary = context.get_artifact("replacement_summary")

    assert summary["notebooks_written"] == 16
    assert summary["config_assets_copied"] == 2
    assert summary["total_operations_applied"] > 0

    migrated_customer_nb = tmp_path / "migrated" / "Bronze" / "ingest_customer.py"
    assert migrated_customer_nb.exists()
    text = migrated_customer_nb.read_text()
    assert "s3://loanplatformdl-raw/customers" in text

    # Business logic (Common/utils.py's function definitions) survives untouched
    migrated_utils_nb = tmp_path / "migrated" / "Common" / "utils.py"
    utils_text = migrated_utils_nb.read_text()
    assert "def standardize_columns(df: DataFrame) -> DataFrame:" in utils_text
    assert "def get_run_id() -> str:" in utils_text


def test_engine_in_place_mode_writes_back_to_source_repository(tmp_path: Path):
    source_repo = tmp_path / "Loan-Platform"
    notebook = source_repo / "Bronze" / "ingest_customer.py"
    notebook.parent.mkdir(parents=True)
    notebook.write_text(
        "# Databricks notebook source\n"
        "path = 'abfss://bronze@acct.dfs.core.windows.net/customer/'\n"
    )

    engine = ReplacementEngine()
    context = _base_context({
        "source": {"repo_path": str(source_repo), "source_mode": "local_repo"},
        "target": {"repo_path": str(tmp_path / "should-not-be-used")},
        "output": {"mode": "in_place"},
    })
    context.set_artifact(
        "repository",
        {
            "notebooks": [{
                "relative_path": "Bronze/ingest_customer.py",
                "absolute_path": str(notebook),
                "language": "python",
            }],
            "config_assets": [],
        },
    )
    context.set_artifact(
        "transformation_plan",
        {"notebook_plans": [{
            "relative_path": "Bronze/ingest_customer.py",
            "operations": [{
                "operation_type": "replace_storage_path", "action": "replace",
                "original_value": "abfss://bronze@acct.dfs.core.windows.net/customer/",
                "resolved_value": "s3://raw-bronze/customer/",
                "requires_manual_review": False, "notes": "test",
            }],
        }]},
    )

    result_context = engine.run(context)

    assert notebook.read_text().find("s3://raw-bronze/customer/") >= 0
    assert not (tmp_path / "should-not-be-used" / "Bronze" / "ingest_customer.py").exists()
    summary = result_context.get_artifact("replacement_summary")
    assert summary["target_repo_path"] == str(source_repo.resolve())


def test_engine_in_place_mode_supports_workspace_source(monkeypatch, tmp_path: Path):
    class FakeWorkspaceClient:
        def __init__(self):
            self.calls = []

        def import_source(self, path, content, overwrite=True):
            self.calls.append((path, content, overwrite))

    fake = FakeWorkspaceClient()
    monkeypatch.setattr(ReplacementEngine, "_build_workspace_client", lambda self, context: fake)

    staged = tmp_path / "staged" / "PFL" / "job.py"
    staged.parent.mkdir(parents=True)
    staged.write_text(
        "# Databricks notebook source\n"
        "path = 'abfss://bronze@acct.dfs.core.windows.net/x'\n"
    )

    engine = ReplacementEngine()
    context = _base_context({
        "source": {
            "repo_path": "/Workspace/Users/test/pfl-repo",
            "source_mode": "workspace",
            "workspace_url": "https://dbc-test.cloud.databricks.com",
        },
        "target": {
            "repo_path": "/Workspace/Users/test/pfl-repo",
            "workspace_url": "https://dbc-test.cloud.databricks.com",
        },
        "output": {"mode": "in_place"},
    })
    context.set_artifact("repository", {
        "notebooks": [{
            "relative_path": "PFL/job.py",
            "absolute_path": str(staged),
            "language": "python",
        }],
        "config_assets": [],
    })
    context.set_artifact("transformation_plan", {
        "notebook_plans": [{
            "relative_path": "PFL/job.py",
            "operations": [{
                "operation_type": "replace_storage_path", "action": "replace",
                "original_value": "abfss://bronze@acct.dfs.core.windows.net/x",
                "resolved_value": "s3://raw-bronze/x",
                "requires_manual_review": False, "notes": "test",
            }],
        }]
    })

    result_context = engine.run(context)

    # ReplacementEngine prepares a local preview only. Workspace write-back is
    # performed exclusively by DeploymentEngine when auto_deploy=true and
    # dry_run=false.
    assert len(fake.calls) == 0
    preview_root = Path(result_context.metadata["workspace_preview_root"])
    preview_file = preview_root / "PFL/job.py"
    assert preview_file.exists()
    assert "s3://raw-bronze/x" in preview_file.read_text()
