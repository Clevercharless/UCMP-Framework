"""
demo_deployment_engine.py
============================
Standalone demo for Module 11 (Deployment Engine), integrated with
Modules 1-10 (Orchestrator through Validation Engine). This is the FULL
UCMP pipeline, end to end.

Demonstrates three scenarios:
  1. Dry run (config default) - commits locally, skips push/deploy.
  2. Full deploy (dry_run=false) - real local git push to a simulated
     AWS Databricks Repos backing store, plus the simulated API update.
  3. The validation gate blocking a deployment outright.

Run with:
    python demo_deployment_engine.py
"""

from __future__ import annotations

import os
import subprocess

from auth.auth_manager import AuthenticationManager
from config.config_manager import ConfigurationManager
from deployment.deployment_engine import DeploymentEngine
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator
from parser.parser_engine import ParserEngine
from replacement.replacement_engine import ReplacementEngine
from repository.repository_manager import RepositoryManager
from rule_service.rule_service import RuleService
from rules.rule_repository import RuleRepository
from transformation.transformation_planner import TransformationPlanner
from validation.validation_engine import ValidationEngine


def build_pipeline(config_path, env=None, remote_root=None) -> Orchestrator:
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
        DeploymentEngine(token_store=auth_manager.token_store, remote_root=remote_root),
    ]
    return Orchestrator(stages=stages, fail_fast=True)


def print_deployment_result(context: PipelineContext) -> None:
    plan = context.get_artifact("deployment_plan")
    print(f"  overall_status: {plan['overall_status']} (mode={plan['deployment_mode']})")
    for step in plan["steps"]:
        print(f"    - {step['name']:<32} {step['status']}")
        if step["name"] == "git_commit" and step["detail"].get("committed"):
            print(f"        commit_hash: {step['detail']['commit_hash'][:10]}")
        if step["name"] == "git_push" and step["status"] == "completed":
            print(f"        remote_commit_hash: {step['detail']['remote_commit_hash'][:10]}")


def main() -> None:
    sample_config_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "ucmp-demo", "docs", "sample_config.yaml")
    )
    config_path = sample_config_path if os.path.exists(sample_config_path) else None

    print("=" * 70)
    print("SCENARIO 1: Dry run (config default: pipeline.dry_run=true)")
    print("=" * 70)
    orchestrator = build_pipeline(config_path)
    context = orchestrator.run(PipelineContext())
    print(f"Pipeline overall status: {context.summary()['overall_status']}")
    print_deployment_result(context)

    print("\n" + "=" * 70)
    print("SCENARIO 2: Full deployment (pipeline.dry_run=false)")
    print("=" * 70)
    remote_root = "/tmp/ucmp_demo_aws_remote"
    subprocess.run(["rm", "-rf", remote_root])
    orchestrator = build_pipeline(
        config_path=None, env={"UCMP__PIPELINE__DRY_RUN": "false"}, remote_root=remote_root
    )
    context = orchestrator.run(PipelineContext())
    print(f"Pipeline overall status: {context.summary()['overall_status']}")
    print_deployment_result(context)

    print("\nVerifying with an independent real git command against the simulated remote:")
    remote_repo_path = f"{remote_root}/Loan-Platform.git"
    result = subprocess.run(["git", "log", "--oneline"], cwd=remote_repo_path, capture_output=True, text=True)
    print(f"  git log --oneline (in {remote_repo_path}):")
    print(f"  {result.stdout.strip()}")

    print("\n" + "=" * 70)
    print("SCENARIO 3: Validation gate blocks deployment on FAIL")
    print("=" * 70)
    orchestrator = build_pipeline(config_path)
    context = orchestrator.run(PipelineContext())
    # Simulate a failed validation by overwriting the report artifact directly,
    # then re-run only the Deployment Engine stage to show the gate in isolation.
    context.artifacts["validation_report"]["overall_status"] = "FAIL"
    deployment_stage = orchestrator.stages[-1]
    context = deployment_stage.run(context)
    print_deployment_result(context)
    print("\nNo git operations were performed once validation_report showed FAIL.")


if __name__ == "__main__":
    main()
