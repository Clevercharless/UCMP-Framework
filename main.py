"""
main.py
========
The official entry point for running the complete UCMP migration pipeline
(all 12 modules, 11 pipeline stages) end to end.

Usage:
    python main.py                               # use built-in defaults
    python main.py --config path/to/config.yaml   # use a specific config file
    python main.py --deploy                       # force a full (non-dry-run) deployment
    python main.py --config path/to/config.yaml --deploy   # combine flags

See EXECUTION_GUIDE.md at the project root for full setup and usage instructions.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

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


def build_pipeline(config_path: Optional[str], force_deploy: bool) -> Orchestrator:
    env = {"UCMP__PIPELINE__DRY_RUN": "false"} if force_deploy else None

    auth_manager = AuthenticationManager()
    rule_repository = RuleRepository()

    stages = [
        ConfigurationManager(config_path=config_path, env=env),
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Universal Cloud Migration Platform (UCMP) pipeline "
        "end to end: Azure Databricks -> AWS Databricks notebook migration, fully simulated."
    )
    parser.add_argument(
        "--config", dest="config_path", default=None,
        help="Path to a YAML config file (deep-merged over config/default_config.yaml). "
        "Defaults to ucmp-demo/docs/sample_config.yaml if present, otherwise built-in defaults.",
    )
    parser.add_argument(
        "--deploy", action="store_true",
        help="Force a full (non-dry-run) deployment: real local git push to the simulated "
        "AWS Databricks Repos backing store, plus the simulated API update.",
    )
    args = parser.parse_args()

    config_path = args.config_path
    if config_path is None:
        default_sample = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "ucmp-demo", "docs", "sample_config.yaml")
        )
        config_path = default_sample if os.path.exists(default_sample) else None

    orchestrator = build_pipeline(config_path, force_deploy=args.deploy)
    context = orchestrator.run(PipelineContext())

    print("\n" + "=" * 70)
    print("UCMP PIPELINE RESULT")
    print("=" * 70)
    for entry in context.summary()["stages"]:
        print(f"  {entry['stage_name']:<28} {entry['status']:<10} {entry['duration_seconds']}s")

    overall = context.summary()["overall_status"]
    print(f"\nOverall pipeline status: {overall}")

    if overall == "SUCCESS":
        validation_status = context.metadata.get("validation_status")
        deployment_status = context.metadata.get("deployment_status")
        reports = context.get_artifact("reports")
        print(f"Validation status:  {validation_status}")
        print(f"Deployment status:  {deployment_status}")
        if reports:
            print(f"\nReports written to: {reports['reports_dir']}")
            for filename in sorted(reports["files"]):
                print(f"  - {filename}")

    return 0 if overall == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
