"""
demo_reporting_engine.py
===========================
Standalone demo for Module 12 (Reporting Engine) - and, since it's the
final stage, this demo runs the COMPLETE UCMP pipeline end to end:

    ConfigurationManager -> AuthenticationManager -> RepositoryManager ->
    ParserEngine -> RuleRepository -> RuleService -> TransformationPlanner ->
    ReplacementEngine -> ValidationEngine -> DeploymentEngine -> ReportingEngine

From the Azure Databricks Loan-Platform source repo all the way to seven
Markdown reports describing exactly what happened.

Run with:
    python demo_reporting_engine.py
"""

from __future__ import annotations

import os

from auth.auth_manager import AuthenticationManager
from config.config_manager import ConfigurationManager
from deployment.deployment_engine import DeploymentEngine
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator
from parser.parser_engine import ParserEngine
from replacement.replacement_engine import ReplacementEngine
from reporting.reporting_engine import ReportingEngine
from repository.repository_manager import RepositoryManager
from rule_service.rule_service import RuleService
from rules.rule_repository import RuleRepository
from transformation.transformation_planner import TransformationPlanner
from validation.validation_engine import ValidationEngine


def build_full_pipeline(config_path) -> Orchestrator:
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
        DeploymentEngine(token_store=auth_manager.token_store),
        ReportingEngine(),
    ]
    return Orchestrator(stages=stages, fail_fast=True)


def main() -> None:
    sample_config_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "ucmp-demo", "docs", "sample_config.yaml")
    )
    config_path = sample_config_path if os.path.exists(sample_config_path) else None

    print("Running the complete UCMP pipeline (12 modules, 11 stages)...\n")

    orchestrator = build_full_pipeline(config_path)
    context = orchestrator.run(PipelineContext())

    print("=== Full Pipeline Stage Summary ===")
    for entry in context.summary()["stages"]:
        print(f"  {entry['stage_name']:<28} {entry['status']:<10} {entry['duration_seconds']}s")
    print(f"\nOverall pipeline status: {context.summary()['overall_status']}")

    reports = context.get_artifact("reports")
    print(f"\n=== Reports Generated ({len(reports['files'])}) ===")
    print(f"  Location: {reports['reports_dir']}")
    for filename in sorted(reports["files"]):
        size = len(open(reports["files"][filename]).read())
        print(f"    - {filename:<28} ({size} chars)")

    print("\n" + "=" * 70)
    print("MIGRATION SUMMARY REPORT (the executive view)")
    print("=" * 70)
    with open(reports["files"]["MigrationSummaryReport.md"]) as f:
        print(f.read())


if __name__ == "__main__":
    main()
