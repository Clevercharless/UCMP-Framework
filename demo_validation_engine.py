"""
demo_validation_engine.py
============================
Standalone demo for Module 10 (Validation Engine), integrated with
Modules 1-9 (Orchestrator through Replacement Engine).

Pipeline order demonstrated:
    ConfigurationManager -> AuthenticationManager -> RepositoryManager ->
    ParserEngine -> RuleRepository -> RuleService -> TransformationPlanner ->
    ReplacementEngine -> ValidationEngine

Run with:
    python demo_validation_engine.py
"""

from __future__ import annotations

import os

from auth.auth_manager import AuthenticationManager
from config.config_manager import ConfigurationManager
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator
from parser.parser_engine import ParserEngine
from replacement.replacement_engine import ReplacementEngine
from repository.repository_manager import RepositoryManager
from rule_service.rule_service import RuleService
from rules.rule_repository import RuleRepository
from transformation.transformation_planner import TransformationPlanner
from validation.validation_engine import ValidationEngine


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
        ReplacementEngine(),
        ValidationEngine(),
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

    report = context.get_artifact("validation_report")
    summary = report["summary"]

    print(f"\nValidation report written to: {context.metadata.get('validation_report_path')}")
    print(f"\n{'='*60}")
    print(f"  OVERALL VALIDATION STATUS: {report['overall_status']}")
    print(f"{'='*60}")
    print(f"  errors:   {summary['error_count']}")
    print(f"  warnings: {summary['warning_count']}")
    print(f"  info:     {summary['info_count']}")

    print("\n=== Findings by Category ===")
    for category, counts in sorted(summary["by_category"].items()):
        print(f"  {category:<20} error={counts['error']:<3} warning={counts['warning']:<3} info={counts['info']}")

    print("\n=== All Warnings (expected residue awaiting manual review) ===")
    for f in report["findings"]:
        if f["severity"] == "warning":
            print(f"  [{f['category']}] {f['notebook']}: {f['message']}")
            print(f"      -> {f['detail']}")

    errors = [f for f in report["findings"] if f["severity"] == "error"]
    if errors:
        print(f"\n=== {len(errors)} ERROR(S) — pipeline would FAIL ===")
        for f in errors:
            print(f"  [{f['category']}] {f['notebook']}: {f['message']}")
    else:
        print("\nNo errors found — migrated repository is clean, with all remaining "
              "residue explicitly documented and expected per the transformation plan.")


if __name__ == "__main__":
    main()
