"""
demo_config_manager.py
========================
Standalone demo for Module 2 (Configuration Manager), integrated with
Module 1 (Orchestrator).

This demo:
  1. Builds a REAL ConfigurationManager (loads defaults, merges a sample
     user config file, applies an env var override) — the first
     non-mock stage in the pipeline.
  2. Wires it in front of the same placeholder stages used in
     demo_orchestrator.py, to prove downstream stages can now read
     `context.config` populated by a real module.

Run with:
    python demo_config_manager.py
"""

from __future__ import annotations

import os

from config.config_manager import ConfigurationManager
from demo_orchestrator import _PlaceholderStage
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from orchestrator.orchestrator import Orchestrator


class _ConfigAwareStage(PipelineStage):
    """
    A placeholder stage that actually reads context.config — proving the
    hand-off from ConfigurationManager to downstream stages works, without
    needing the real Repository Manager to exist yet.
    """

    name = "RepositoryManager"

    def run(self, context: PipelineContext) -> PipelineContext:
        source_repo = context.config["source"]["repo_path"]
        target_repo = context.config["target"]["repo_path"]
        context.set_artifact(
            "repository",
            f"Would sync '{source_repo}' -> staging, "
            f"and prepare deployment target '{target_repo}'",
        )
        return context


def build_demo_pipeline(config_path: str | None) -> Orchestrator:
    stages = [
        ConfigurationManager(config_path=config_path),
        _ConfigAwareStage(),
        _PlaceholderStage("ParserEngine", "parsed_notebooks", "12/12 notebooks parsed"),
        _PlaceholderStage("DependencyGraphBuilder", "dependency_graph", "18 edges, 12 nodes"),
        _PlaceholderStage("KnowledgeModelGenerator", "knowledge_model", "MigrationKnowledgeModel.json (stub)"),
        _PlaceholderStage("ReportingEngine", "final_report", "MigrationSummaryReport.json (stub)"),
    ]
    return Orchestrator(stages=stages, fail_fast=True)


def main() -> None:
    sample_config_path = os.path.join(
        os.path.dirname(__file__), "..", "ucmp-demo", "docs", "sample_config.yaml"
    )
    sample_config_path = os.path.normpath(sample_config_path)
    config_path = sample_config_path if os.path.exists(sample_config_path) else None

    orchestrator = build_demo_pipeline(config_path)
    context = orchestrator.run(PipelineContext())

    print("\n=== Pipeline Summary ===")
    for entry in context.summary()["stages"]:
        print(f"  {entry['stage_name']:<28} {entry['status']:<10} {entry['duration_seconds']}s")

    print(f"\nOverall status: {context.summary()['overall_status']}")

    print("\n=== Resolved Config Summary (from ConfigurationManager) ===")
    for key, value in context.get_artifact("resolved_config_summary", {}).items():
        print(f"  {key:<20} -> {value}")

    print("\n=== Artifacts Produced ===")
    for key, value in context.artifacts.items():
        if key == "resolved_config_summary":
            continue
        print(f"  {key:<24} -> {value}")


if __name__ == "__main__":
    main()
