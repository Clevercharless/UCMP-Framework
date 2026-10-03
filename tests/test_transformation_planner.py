"""
tests.test_transformation_planner
===================================
Unit tests for transformation.operation_types, transformation.plan_models,
and transformation.transformation_planner.TransformationPlanner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.exceptions import TransformationPlannerError
from orchestrator.context import PipelineContext
from transformation.operation_types import OperationType, derive_operation_type
from transformation.transformation_planner import TransformationPlanner


# ---------------------------------------------------------------------------
# operation_types.derive_operation_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "category,action,expected",
    [
        ("storage", "replace", OperationType.REPLACE_STORAGE_PATH),
        ("secret", "replace", OperationType.REPLACE_SECRET_SCOPE),
        ("workspace", "replace", OperationType.REPLACE_WORKSPACE_URL),
        ("catalog", "replace", OperationType.REPLACE_CATALOG_NAME),
        ("unknown_category", "replace", OperationType.GENERIC_REPLACE),
        ("library", "remove", OperationType.REMOVE_AZURE_SDK_IMPORT),
        ("spark", "remove", OperationType.REMOVE_SPARK_CONFIG),
        ("storage", "remove", OperationType.REMOVE_STORAGE_REFERENCE),
        ("secret", "remove", OperationType.REMOVE_SECRET_REFERENCE),
        ("unknown_category", "remove", OperationType.GENERIC_REMOVE),
        ("storage", "manual_review", OperationType.FLAG_MANUAL_REVIEW),
        ("anything", "no_change", OperationType.NO_CHANGE),
        ("anything", "unmatched", OperationType.UNMATCHED_NEEDS_RULE),
    ],
)
def test_derive_operation_type(category, action, expected):
    assert derive_operation_type(category, action) == expected


# ---------------------------------------------------------------------------
# TransformationPlanner (PipelineStage)
# ---------------------------------------------------------------------------

def _base_context(config=None) -> PipelineContext:
    return PipelineContext(config=config or {"output": {"reports_dir": "unused"}})


def test_planner_requires_knowledge_model():
    planner = TransformationPlanner()
    context = _base_context()
    context.set_artifact("rule_service_output", {"actions": []})
    with pytest.raises(TransformationPlannerError, match="ParserEngine"):
        planner.run(context)


def test_planner_requires_rule_service_output():
    planner = TransformationPlanner()
    context = _base_context()
    context.set_artifact("knowledge_model", {"repo_name": "x", "notebook_metadata": []})
    with pytest.raises(TransformationPlannerError, match="RuleService"):
        planner.run(context)


def test_planner_every_notebook_gets_keep_business_logic_operation(tmp_path: Path):
    planner = TransformationPlanner()
    context = _base_context({"output": {"reports_dir": str(tmp_path)}})
    context.set_artifact(
        "knowledge_model",
        {
            "repo_name": "Test-Platform",
            "notebook_metadata": [
                {"relative_path": "Common/utils.py", "category": "Common",
                 "function_def_count": 3, "table_dependency_count": 0},
                {"relative_path": "Bronze/x.py", "category": "Bronze",
                 "function_def_count": 0, "table_dependency_count": 1},
            ],
        },
    )
    context.set_artifact("rule_service_output", {"actions": []})

    result_context = planner.run(context)
    plan = result_context.get_artifact("transformation_plan")

    assert len(plan["notebook_plans"]) == 2
    for nb in plan["notebook_plans"]:
        assert nb["operations"][0]["operation_type"] == "keep_business_logic"
        assert nb["operations"][0]["requires_manual_review"] is False


def test_planner_explodes_action_to_every_notebook_it_was_found_in(tmp_path: Path):
    planner = TransformationPlanner()
    context = _base_context({"output": {"reports_dir": str(tmp_path)}})
    context.set_artifact(
        "knowledge_model",
        {
            "repo_name": "Test-Platform",
            "notebook_metadata": [
                {"relative_path": "Bronze/a.py", "category": "Bronze",
                 "function_def_count": 0, "table_dependency_count": 0},
                {"relative_path": "Bronze/b.py", "category": "Bronze",
                 "function_def_count": 0, "table_dependency_count": 0},
                {"relative_path": "Silver/c.py", "category": "Silver",
                 "function_def_count": 0, "table_dependency_count": 0},
            ],
        },
    )
    context.set_artifact(
        "rule_service_output",
        {
            "actions": [
                {
                    "construct_type": "abfss_path", "original_value": "abfss://x",
                    "rule_category": "storage", "action": "replace",
                    "resolved_value": "s3://x", "matched_rule_id": "storage-001",
                    "requires_manual_review": False, "notes": "test",
                    "found_in": ["Bronze/a.py", "Bronze/b.py"],  # NOT in Silver/c.py
                }
            ]
        },
    )

    plan = planner.run(context).get_artifact("transformation_plan")
    by_path = {nb["relative_path"]: nb for nb in plan["notebook_plans"]}

    assert by_path["Bronze/a.py"]["operation_count"] == 2  # keep_business_logic + replace
    assert by_path["Bronze/b.py"]["operation_count"] == 2
    assert by_path["Silver/c.py"]["operation_count"] == 1  # keep_business_logic only


def test_planner_flags_notebook_as_requiring_manual_review(tmp_path: Path):
    planner = TransformationPlanner()
    context = _base_context({"output": {"reports_dir": str(tmp_path)}})
    context.set_artifact(
        "knowledge_model",
        {
            "repo_name": "Test-Platform",
            "notebook_metadata": [
                {"relative_path": "Bronze/a.py", "category": "Bronze",
                 "function_def_count": 0, "table_dependency_count": 0},
            ],
        },
    )
    context.set_artifact(
        "rule_service_output",
        {
            "actions": [
                {
                    "construct_type": "hardcoded_url", "original_value": "jdbc:x",
                    "rule_category": "api", "action": "manual_review",
                    "resolved_value": None, "matched_rule_id": "api-001",
                    "requires_manual_review": True, "notes": "test",
                    "found_in": ["Bronze/a.py"],
                }
            ]
        },
    )

    plan = planner.run(context).get_artifact("transformation_plan")
    assert plan["notebook_plans"][0]["requires_manual_review"] is True
    assert plan["summary"]["notebooks_with_manual_review"] == 1


def test_planner_writes_json_file(tmp_path: Path):
    planner = TransformationPlanner()
    context = _base_context({"output": {"reports_dir": str(tmp_path)}})
    context.set_artifact(
        "knowledge_model",
        {"repo_name": "Test-Platform", "notebook_metadata": [
            {"relative_path": "Bronze/a.py", "category": "Bronze",
             "function_def_count": 0, "table_dependency_count": 0},
        ]},
    )
    context.set_artifact("rule_service_output", {"actions": []})

    result_context = planner.run(context)
    output_path = Path(result_context.metadata["transformation_plan_path"])
    assert output_path.exists()
    assert output_path.name == "TransformationPlan.json"

    import json
    with output_path.open() as fh:
        written = json.load(fh)
    assert written["repo_name"] == "Test-Platform"


def test_planner_summary_counts_by_operation_type(tmp_path: Path):
    planner = TransformationPlanner()
    context = _base_context({"output": {"reports_dir": str(tmp_path)}})
    context.set_artifact(
        "knowledge_model",
        {"repo_name": "Test-Platform", "notebook_metadata": [
            {"relative_path": "Bronze/a.py", "category": "Bronze",
             "function_def_count": 0, "table_dependency_count": 0},
        ]},
    )
    context.set_artifact(
        "rule_service_output",
        {"actions": [
            {"construct_type": "abfss_path", "original_value": "abfss://x",
             "rule_category": "storage", "action": "replace", "resolved_value": "s3://x",
             "matched_rule_id": "r-1", "requires_manual_review": False, "notes": "t",
             "found_in": ["Bronze/a.py"]},
            {"construct_type": "mount", "original_value": "/mnt/x",
             "rule_category": "storage", "action": "manual_review", "resolved_value": None,
             "matched_rule_id": "r-2", "requires_manual_review": True, "notes": "t",
             "found_in": ["Bronze/a.py"]},
        ]},
    )

    plan = planner.run(context).get_artifact("transformation_plan")
    by_type = plan["summary"]["by_operation_type"]
    assert by_type["keep_business_logic"] == 1
    assert by_type["replace_storage_path"] == 1
    assert by_type["flag_manual_review"] == 1
    assert plan["summary"]["total_operations"] == 3


# ---------------------------------------------------------------------------
# Full pipeline integration against the real demo repo
# ---------------------------------------------------------------------------

def test_planner_full_pipeline_against_real_demo_repo():
    from auth.auth_manager import AuthenticationManager
    from config.config_manager import ConfigurationManager
    from orchestrator.orchestrator import Orchestrator
    from parser.parser_engine import ParserEngine
    from repository.repository_manager import RepositoryManager
    from rules.rule_repository import RuleRepository
    from rule_service.rule_service import RuleService

    config_manager = ConfigurationManager(config_path=None, env={})
    auth_manager = AuthenticationManager()
    repository_manager = RepositoryManager(token_store=auth_manager.token_store)
    parser_engine = ParserEngine()
    rule_repository = RuleRepository()
    rule_service = RuleService(rule_repository=rule_repository)
    planner = TransformationPlanner()

    orchestrator = Orchestrator(stages=[
        config_manager, auth_manager, repository_manager, parser_engine,
        rule_repository, rule_service, planner,
    ])
    context = orchestrator.run(PipelineContext())

    assert context.summary()["overall_status"] == "SUCCESS"
    plan = context.get_artifact("transformation_plan")

    assert plan["summary"]["notebook_count"] == 16
    # Every notebook has at least the keep_business_logic operation.
    assert all(nb["operation_count"] >= 1 for nb in plan["notebook_plans"])
    assert all(
        nb["operations"][0]["operation_type"] == "keep_business_logic"
        for nb in plan["notebook_plans"]
    )
    assert plan["summary"]["by_operation_type"]["keep_business_logic"] == 16
    assert plan["summary"]["total_operations"] > 16  # more than just the keep-logic ops
