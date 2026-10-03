"""
demo_orchestrator.py
=====================
Standalone demo for Module 1 (Orchestrator).

No other UCMP module has been built yet, so this demo wires the
Orchestrator to lightweight PLACEHOLDER stages that stand in for the real
Repository Manager, Parser Engine, Rule Service, Transformation Planner,
Replacement Engine, Validation Engine, Deployment Engine, and Reporting
Engine that will be built in later modules.

This proves two things ahead of building anything else:
  1. The Orchestrator can drive an arbitrary ordered pipeline using only
     the PipelineStage interface.
  2. Each future module can be dropped in later by implementing
     PipelineStage.run(context) — the Orchestrator itself will not need to
     change.

Run with:
    python demo_orchestrator.py
"""

from __future__ import annotations

from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from orchestrator.orchestrator import Orchestrator


class _PlaceholderStage(PipelineStage):
    """
    Generic stand-in for a not-yet-built module. Simply logs that it ran
    and stamps an artifact, so the demo output visibly shows the full
    pipeline order end to end.
    """

    def __init__(self, name: str, artifact_key: str, artifact_value: str):
        self.name = name
        self._artifact_key = artifact_key
        self._artifact_value = artifact_value

    def run(self, context: PipelineContext) -> PipelineContext:
        context.set_artifact(self._artifact_key, self._artifact_value)
        return context


def build_demo_pipeline() -> Orchestrator:
    """
    Wires up placeholder stages in the exact pipeline order defined by the
    UCMP architecture:

    Repository Manager -> Parser Engine -> Dependency Graph ->
    Migration Knowledge Model -> Rule Repository -> Rule Service ->
    Transformation Planner -> Replacement Engine -> Validation Engine ->
    Deployment Engine -> Reporting Engine
    """
    stages = [
        _PlaceholderStage("RepositoryManager", "repository", "Loan-Platform synced (12 notebooks)"),
        _PlaceholderStage("ParserEngine", "parsed_notebooks", "12/12 notebooks parsed"),
        _PlaceholderStage("DependencyGraphBuilder", "dependency_graph", "18 edges, 12 nodes"),
        _PlaceholderStage("KnowledgeModelGenerator", "knowledge_model", "MigrationKnowledgeModel.json (stub)"),
        _PlaceholderStage("RuleRepository", "rules_loaded", "7 rule files loaded"),
        _PlaceholderStage("RuleService", "applicable_rules", "23 applicable rules resolved"),
        _PlaceholderStage("TransformationPlanner", "transformation_plan", "TransformationPlan.json (stub)"),
        _PlaceholderStage("ReplacementEngine", "replacement_summary", "41 constructs replaced"),
        _PlaceholderStage("ValidationEngine", "validation_report", "PASS (0 blocking issues)"),
        _PlaceholderStage("DeploymentEngine", "deployment_plan", "Simulated push to AWS Databricks repo"),
        _PlaceholderStage("ReportingEngine", "final_report", "MigrationSummaryReport.json (stub)"),
    ]
    return Orchestrator(stages=stages, fail_fast=True)


def main() -> None:
    orchestrator = build_demo_pipeline()
    context = PipelineContext(
        metadata={
            "source_platform": "Azure Databricks",
            "target_platform": "AWS Databricks",
            "source_repo": "Loan-Platform",
        }
    )

    result_context = orchestrator.run(context)

    print("\n=== Pipeline Summary ===")
    for entry in result_context.summary()["stages"]:
        print(f"  {entry['stage_name']:<28} {entry['status']:<10} "
              f"{entry['duration_seconds']}s")

    print(f"\nOverall status: {result_context.summary()['overall_status']}")
    print(f"Run ID: {result_context.run_id}")

    print("\n=== Artifacts Produced ===")
    for key, value in result_context.artifacts.items():
        print(f"  {key:<24} -> {value}")


if __name__ == "__main__":
    main()
