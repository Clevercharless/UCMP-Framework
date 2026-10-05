"""
demo_repository_manager.py
============================
Standalone demo for Module 4 (Repository Manager), integrated with
Modules 1-3 (Orchestrator, Configuration Manager, Authentication Manager).

Pipeline order demonstrated:
    ConfigurationManager -> AuthenticationManager -> RepositoryManager ->
    [placeholder stages for Parser Engine onward]

This is the first demo that runs against the REAL ucmp-demo/Loan-Platform
repository (14 notebooks, 2 SQL scripts, 2 config assets) rather than mock
data.

Run with:
    python demo_repository_manager.py
"""

from __future__ import annotations

from auth.auth_manager import AuthenticationManager
from config.config_manager import ConfigurationManager
from demo_orchestrator import _PlaceholderStage
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator
from repository.repository_manager import RepositoryManager


def build_demo_pipeline(config_path: str | None) -> Orchestrator:
    config_manager = ConfigurationManager(config_path=config_path)
    auth_manager = AuthenticationManager()
    # RepositoryManager consumes the SAME TokenStore instance AuthenticationManager
    # writes into, so it can prove a valid token exists before it "clones" anything.
    repository_manager = RepositoryManager(token_store=auth_manager.token_store)

    stages = [
        config_manager,
        auth_manager,
        repository_manager,
        _PlaceholderStage("ParserEngine", "parsed_notebooks", "16/16 notebooks parsed"),
        _PlaceholderStage("ReportingEngine", "final_report", "MigrationSummaryReport.json (stub)"),
    ]
    return Orchestrator(stages=stages, fail_fast=True)


def main() -> None:
    import os

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

    repo = context.get_artifact("repository", {})
    print("\n=== Repository Inventory ===")
    print(f"  repo_name:      {repo.get('repo_name')}")
    print(f"  source_path:    {repo.get('source_path')}")
    print(f"  staged_path:    {repo.get('staged_path')}")
    print(f"  notebook_count: {repo.get('notebook_count')}")
    print(f"  categories:     {repo.get('categories_found')}")
    print(f"  config_assets:  {len(repo.get('config_assets', []))}")

    print("\n=== Notebooks by Category ===")
    by_category: dict[str, list[str]] = {}
    for nb in repo.get("notebooks", []):
        by_category.setdefault(nb["category"], []).append(
            f"{nb['relative_path']} ({nb['language']}, {nb['line_count']} lines)"
        )
    for category in sorted(by_category):
        print(f"  [{category}]")
        for entry in by_category[category]:
            print(f"      {entry}")

    print(f"\nrepository_synced flag in metadata: {context.metadata.get('repository_synced')}")


if __name__ == "__main__":
    main()
