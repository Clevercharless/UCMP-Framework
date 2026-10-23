"""
demo_rule_service.py
======================
Standalone demo for Module 7 (Rule Service), integrated with Modules 1-6
(Orchestrator, Configuration Manager, Authentication Manager, Repository
Manager, Parser Engine, Rule Repository).

Pipeline order demonstrated:
    ConfigurationManager -> AuthenticationManager -> RepositoryManager ->
    ParserEngine -> RuleRepository -> RuleService

Run with:
    python demo_rule_service.py
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

    output = context.get_artifact("rule_service_output")
    summary = output["summary"]
    print(f"\n=== Rule Service Summary ({summary['total']} construct(s) resolved) ===")
    for key in ["replace", "remove", "manual_review", "no_change", "unmatched"]:
        print(f"  {key:<15} {summary[key]}")
    print(f"  {'requires review':<15} {summary['requires_manual_review_count']} (may overlap with manual_review)")

    print("\n=== Automatic Replacements ===")
    for action in output["actions"]:
        if action["action"] == "replace":
            print(f"  [{action['matched_rule_id']}] {action['original_value']}")
            print(f"      -> {action['resolved_value']}")

    print("\n=== Flagged for Manual Review ===")
    for action in output["actions"]:
        if action["requires_manual_review"]:
            rule_id = action["matched_rule_id"] or "no rule matched"
            print(f"  [{rule_id}] ({action['action']}) {action['original_value'][:70]}")
            print(f"      found in: {action['found_in']}")
            print(f"      notes: {action['notes']}")

    print("\nRule Service never wrote to any notebook file — data-only output, "
          "ready for the Transformation Planner (Module 8).")


if __name__ == "__main__":
    main()
