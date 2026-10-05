"""
demo_auth_manager.py
======================
Standalone demo for Module 3 (Authentication Manager), integrated with
Modules 1-2 (Orchestrator, Configuration Manager).

Pipeline order demonstrated:
    ConfigurationManager -> AuthenticationManager -> [placeholder stages]

Run with:
    python demo_auth_manager.py
"""

from __future__ import annotations

import os

from auth.auth_manager import AuthenticationManager
from config.config_manager import ConfigurationManager
from demo_orchestrator import _PlaceholderStage
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator


def build_demo_pipeline(config_path: str | None) -> Orchestrator:
    stages = [
        ConfigurationManager(config_path=config_path),
        AuthenticationManager(),
        _PlaceholderStage("RepositoryManager", "repository", "Loan-Platform synced (12 notebooks)"),
        _PlaceholderStage("ParserEngine", "parsed_notebooks", "12/12 notebooks parsed"),
        _PlaceholderStage("ReportingEngine", "final_report", "MigrationSummaryReport.json (stub)"),
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

    print("\n=== Simulated Auth Session (tokens masked) ===")
    session = context.get_artifact("auth_session", {})
    for platform, info in session.items():
        print(f"  [{platform}]")
        for key, value in info.items():
            print(f"      {key:<14} -> {value}")

    print(f"\nauthenticated flag in metadata: {context.metadata.get('authenticated')}")

    print("\n=== Artifacts Produced ===")
    for key, value in context.artifacts.items():
        if key == "auth_session":
            continue
        print(f"  {key:<24} -> {value}")


if __name__ == "__main__":
    main()
