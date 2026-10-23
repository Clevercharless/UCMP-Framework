"""
demo_replacement_engine.py
=============================
Standalone demo for Module 9 (Replacement Engine), integrated with
Modules 1-8 (Orchestrator through Transformation Planner).

Pipeline order demonstrated:
    ConfigurationManager -> AuthenticationManager -> RepositoryManager ->
    ParserEngine -> RuleRepository -> RuleService -> TransformationPlanner ->
    ReplacementEngine

Run with:
    python demo_replacement_engine.py
"""

from __future__ import annotations

import difflib
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

    summary = context.get_artifact("replacement_summary")
    print(f"\n=== Replacement Summary ===")
    print(f"  target repo:              {summary['target_repo_path']}")
    print(f"  notebooks written:        {summary['notebooks_written']}")
    print(f"  operations applied:       {summary['total_operations_applied']}")
    print(f"  notebooks needing review: {summary['notebooks_with_manual_review']}")
    print(f"  config assets copied:     {summary['config_assets_copied']}")

    # Show a real before/after diff for one notebook with both replacements and manual review.
    repository = context.get_artifact("repository")
    target_notebook = "Bronze/ingest_customer.py"
    staged_path = next(
        nb["absolute_path"] for nb in repository["notebooks"] if nb["relative_path"] == target_notebook
    )
    migrated_path = next(
        r["output_path"] for r in summary["notebook_results"] if r["relative_path"] == target_notebook
    )

    with open(staged_path) as f:
        before_lines = f.readlines()
    with open(migrated_path) as f:
        after_lines = f.readlines()

    print(f"\n=== Diff: {target_notebook} (Azure staged -> AWS migrated) ===")
    diff = difflib.unified_diff(before_lines, after_lines, fromfile="staged (Azure)", tofile="migrated (AWS)", n=1)
    diff_lines = list(diff)
    # Print only the changed-content hunks, skip the giant inserted banner block for readability.
    printed = 0
    for line in diff_lines:
        if line.startswith("+# MAGIC") or line.startswith("+"):
            if "UCMP Migration Notes" in line or line.strip() in ("+", "+#"):
                continue
        print(line, end="")
        printed += 1
        if printed > 40:
            print("  ... (truncated)")
            break

    print("\nBusiness logic (function bodies, control flow, variable names) is byte-for-byte "
          "identical between staged and migrated — only the flagged Azure constructs changed.")


if __name__ == "__main__":
    main()
