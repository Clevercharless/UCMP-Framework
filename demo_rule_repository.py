"""
demo_rule_repository.py
=========================
Standalone demo for Module 6 (Rule Repository), integrated with Modules
1-5 (Orchestrator, Configuration Manager, Authentication Manager,
Repository Manager, Parser Engine).

Pipeline order demonstrated:
    ConfigurationManager -> AuthenticationManager -> RepositoryManager ->
    ParserEngine -> RuleRepository

Run with:
    python demo_rule_repository.py
"""

from __future__ import annotations

import os

from auth.auth_manager import AuthenticationManager
from config.config_manager import ConfigurationManager
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator
from parser.parser_engine import ParserEngine
from repository.repository_manager import RepositoryManager
from rules.rule_repository import RuleRepository


def build_demo_pipeline(config_path: str | None) -> Orchestrator:
    stages = [
        ConfigurationManager(config_path=config_path),
        AuthenticationManager(),
    ]
    auth_manager = stages[-1]
    stages.append(RepositoryManager(token_store=auth_manager.token_store))
    stages.append(ParserEngine())
    stages.append(RuleRepository())
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

    rule_repo = context.get_artifact("rule_repository")
    print(f"\n=== Rule Repository: {rule_repo['rule_count']} rule(s) from {len(rule_repo['source_files'])} file(s) ===")
    print(f"  rules_dir: {rule_repo['rules_dir']}")
    print(f"  files:     {rule_repo['source_files']}")

    print("\n=== Rules by Category ===")
    for category in sorted(rule_repo["rules_by_category"]):
        rules = rule_repo["rules_by_category"][category]
        print(f"\n  [{category}] {len(rules)} rule(s)")
        for rule in rules:
            review_flag = " (MANUAL REVIEW)" if rule["requires_manual_review"] else ""
            print(f"    - {rule['rule_id']:<16} action={rule['action']:<14}{review_flag}")
            print(f"      {rule['description'].strip().splitlines()[0]}")

    # Cross-check against what the Parser Engine (Module 5) actually found,
    # to prove the rule categories genuinely cover what this repo needs.
    transformation_candidates = context.get_artifact("knowledge_model")["transformation_candidates"]
    needed_categories = {tc["rule_category_hint"].removesuffix("_rules") for tc in transformation_candidates}
    available_categories = set(rule_repo["categories"])
    print(f"\n=== Coverage Check ===")
    print(f"  Categories needed by parsed notebooks: {sorted(needed_categories)}")
    print(f"  Categories available in Rule Repository: {sorted(available_categories)}")
    print(f"  Fully covered: {needed_categories.issubset(available_categories)}")


if __name__ == "__main__":
    main()
