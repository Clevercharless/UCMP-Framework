"""
demo_transformation_planner.py
=================================
Standalone demo for Module 8 (Transformation Planner), integrated with
Modules 1-7 (Orchestrator through Rule Service).

Pipeline order demonstrated:
    ConfigurationManager -> AuthenticationManager -> RepositoryManager ->
    ParserEngine -> RuleRepository -> RuleService -> TransformationPlanner

Run with:
    python demo_transformation_planner.py
"""

from __future__ import annotations

import os

from auth.auth_manager import AuthenticationManager
from config.config_manager import ConfigurationManager
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator
from parser.parser_engine import ParserEngine
from repository.repository_manager import RepositoryManager
from rule_service.rule_service import RuleService
from rules.rule_repository import RuleRepository
from transformation.transformation_planner import TransformationPlanner


def build_demo_pipeline(config_path: str | None) -> Orchestrator:
    auth_manager = AuthenticationManager()
    rule_repository = RuleRepository()

    stages = [
        ConfigurationManager(config_path=config_path),
        auth_manager,
        RepositoryManager(token_store=auth_manager.token_store),
        ParserEngine(),
        rule_repository,
        RuleService(rule_repository=rule_repository),
        TransformationPlanner(),
    ]
    return Orchestrator(stages=stages, fail_fast=True)


def main() -> None:
    sample_config_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "ucmp-demo", "docs", "sample_config.yaml")
    )
    config_path = sample_config_path if os.path.exists(sample_config_path) else None

    orchestrator = build_demo_pipeline(config_path)
    context = orchestrator.run(PipelineContext())

    print("\n=== Pipeline Summary ===")
    for entry in context.summary()["stages"]:
        print(f"  {entry['stage_name']:<28} {entry['status']:<10} {entry['duration_seconds']}s")
    print(f"\nOverall status: {context.summary()['overall_status']}")

    plan = context.get_artifact("transformation_plan")
    summary = plan["summary"]

    print(f"\nTransformation plan written to: {context.metadata.get('transformation_plan_path')}")

    print(f"\n=== Plan Summary ===")
    print(f"  notebooks:                  {summary['notebook_count']}")
    print(f"  total operations:           {summary['total_operations']}")
    print(f"  notebooks needing review:   {summary['notebooks_with_manual_review']}")
    print("  operations by type:")
    for op_type, count in sorted(summary["by_operation_type"].items()):
        print(f"    {op_type:<28} {count}")

    print("\n=== Sample Notebook Plans ===")
    # Show one clean notebook (no manual review) and one that needs review.
    clean = next(nb for nb in plan["notebook_plans"] if not nb["requires_manual_review"] and nb["operation_count"] > 1)
    needs_review = next(nb for nb in plan["notebook_plans"] if nb["requires_manual_review"])

    for nb in [clean, needs_review]:
        print(f"\n  [{nb['relative_path']}] ({nb['operation_count']} operation(s), "
              f"review needed: {nb['requires_manual_review']})")
        for op in nb["operations"]:
            if op["operation_type"] == "keep_business_logic":
                print(f"    - KEEP_BUSINESS_LOGIC: {op['notes'][:90]}...")
            else:
                arrow = f" -> {op['resolved_value']}" if op["resolved_value"] else ""
                flag = " [MANUAL REVIEW]" if op["requires_manual_review"] else ""
                print(f"    - {op['operation_type']}: {op['original_value']}{arrow}{flag}")

    print("\nEvery notebook explicitly preserves its business logic — the plan makes "
          "'keep' operations first-class, not just an absence of other operations.")


if __name__ == "__main__":
    main()
