"""
tests.test_deployment_engine
===============================
Unit tests for deployment.git_commit_service, deployment.git_push_service,
deployment.aws_repository_updater, and
deployment.deployment_engine.DeploymentEngine.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from auth.credentials import SimulatedToken
from auth.token_store import TokenStore
from common.exceptions import DeploymentError
from deployment.aws_repository_updater import AWSDatabricksRepositoryUpdater, RepositorySynchronizer
from deployment.deployment_engine import DeploymentEngine
from deployment.git_commit_service import GitCommitService
from deployment.git_push_service import GitPushService
from orchestrator.context import PipelineContext


# ---------------------------------------------------------------------------
# GitCommitService
# ---------------------------------------------------------------------------

def test_git_commit_service_creates_initial_commit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("print(1)\n")

    result = GitCommitService().commit(repo, "initial commit")

    assert result["committed"] is True
    assert result["commit_hash"] is not None
    assert (repo / ".git").exists()


def test_git_commit_service_reports_no_changes_on_second_identical_run(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("print(1)\n")
    service = GitCommitService()

    first = service.commit(repo, "first")
    second = service.commit(repo, "second")  # nothing changed since first commit

    assert first["committed"] is True
    assert second["committed"] is False
    assert second["commit_hash"] == first["commit_hash"]


def test_git_commit_service_creates_second_commit_when_content_changes(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("print(1)\n")
    service = GitCommitService()

    first = service.commit(repo, "first")
    (repo / "a.py").write_text("print(2)\n")
    second = service.commit(repo, "second")

    assert second["committed"] is True
    assert second["commit_hash"] != first["commit_hash"]


def test_git_commit_service_sets_main_branch(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x")
    GitCommitService().commit(repo, "initial")

    result = subprocess.run(
        ["git", "branch", "--show-current"], cwd=str(repo), capture_output=True, text=True
    )
    assert result.stdout.strip() == "main"


# ---------------------------------------------------------------------------
# GitPushService
# ---------------------------------------------------------------------------

def test_git_push_service_creates_bare_remote(tmp_path: Path):
    remote_root = tmp_path / "remotes"
    service = GitPushService(remote_root=remote_root)

    remote_path = service.ensure_remote_exists("Test-Repo")

    assert remote_path.exists()
    assert (remote_path / "HEAD").exists()  # bare repo marker


def test_git_push_service_push_lands_commit_on_remote(tmp_path: Path):
    local_repo = tmp_path / "local"
    local_repo.mkdir()
    (local_repo / "a.py").write_text("x = 1\n")
    commit_result = GitCommitService().commit(local_repo, "initial")

    push_service = GitPushService(remote_root=tmp_path / "remotes")
    remote_path = push_service.ensure_remote_exists("Test-Repo")
    push_result = push_service.push(local_repo, remote_path)

    assert push_result["pushed"] is True
    assert push_result["remote_commit_hash"] == commit_result["commit_hash"]

    # Verify with a REAL git command against the remote, independent of our code
    log_result = subprocess.run(
        ["git", "log", "--oneline", "main"], cwd=str(remote_path), capture_output=True, text=True
    )
    assert commit_result["commit_hash"][:7] in log_result.stdout


# ---------------------------------------------------------------------------
# AWSDatabricksRepositoryUpdater / RepositorySynchronizer
# ---------------------------------------------------------------------------

def _make_token() -> SimulatedToken:
    now = time.time()
    return SimulatedToken(
        principal="svc-aws", platform="aws_databricks", token_value="SIM-AWS-STS.abcdef123456",
        issued_at=now, expires_at=now + 3600, scopes=["workspace.write"],
    )


def test_repository_synchronizer_returns_synced_status():
    result = RepositorySynchronizer().synchronize("https://x.cloud.databricks.com", "abc123")
    assert result["status"] == "SYNCED"
    assert result["synced_commit_hash"] == "abc123"


def test_aws_updater_masks_token_in_request():
    token = _make_token()
    result = AWSDatabricksRepositoryUpdater().update(
        token, "https://x.cloud.databricks.com", "/Repos/prod/Loan-Platform", "abc123"
    )
    assert result["status"] == "UPDATED"
    assert token.token_value not in str(result)  # never leak the raw token
    assert result["response"]["head_commit_id"] == "abc123"


# ---------------------------------------------------------------------------
# DeploymentEngine (PipelineStage)
# ---------------------------------------------------------------------------

def _valid_token_store() -> TokenStore:
    store = TokenStore()
    now = time.time()
    store.put(SimulatedToken(
        principal="svc-aws", platform="aws_databricks", token_value="SIM.x",
        issued_at=now, expires_at=now + 3600, scopes=[],
    ))
    return store


def _base_context(tmp_path: Path, dry_run: bool, validation_status: str = "PASS") -> PipelineContext:
    target_repo = tmp_path / "migrated"
    target_repo.mkdir()
    (target_repo / "nb.py").write_text("# Databricks notebook source\nprint(1)\n")

    context = PipelineContext(config={
        "pipeline": {"dry_run": dry_run},
        "target": {"workspace_url": "https://x.cloud.databricks.com", "repo_path": "/Repos/prod/Test"},
        "output": {"reports_dir": str(tmp_path / "reports")},
    })
    context.set_artifact("validation_report", {"overall_status": validation_status})
    context.set_artifact("replacement_summary", {
        "target_repo_path": str(target_repo), "notebooks_written": 1, "total_operations_applied": 0,
    })
    context.set_artifact("repository", {"repo_name": "Test-Repo"})
    return context


def test_deployment_engine_requires_upstream_artifacts(tmp_path: Path):
    engine = DeploymentEngine(token_store=_valid_token_store(), remote_root=str(tmp_path / "remote"))
    context = PipelineContext(config={"output": {"reports_dir": str(tmp_path)}})
    with pytest.raises(DeploymentError, match="requires the following artifacts"):
        engine.run(context)


def test_deployment_engine_aborts_when_validation_failed(tmp_path: Path):
    engine = DeploymentEngine(token_store=_valid_token_store(), remote_root=str(tmp_path / "remote"))
    context = _base_context(tmp_path, dry_run=True, validation_status="FAIL")

    result_context = engine.run(context)
    plan = result_context.get_artifact("deployment_plan")

    assert plan["overall_status"] == "ABORTED"
    assert len(plan["steps"]) == 1
    assert result_context.metadata["deployment_status"] == "ABORTED"
    # No git repo should have been created in the target dir
    target = Path(context.get_artifact("replacement_summary")["target_repo_path"])
    assert not (target / ".git").exists()


def test_deployment_engine_dry_run_commits_but_skips_push(tmp_path: Path):
    engine = DeploymentEngine(token_store=_valid_token_store(), remote_root=str(tmp_path / "remote"))
    context = _base_context(tmp_path, dry_run=True)

    result_context = engine.run(context)
    plan = result_context.get_artifact("deployment_plan")

    assert plan["overall_status"] == "DRY_RUN_COMPLETE"
    step_names = [s["name"] for s in plan["steps"]]
    assert "git_commit" in step_names
    assert next(s for s in plan["steps"] if s["name"] == "git_push")["status"] == "skipped"
    assert next(s for s in plan["steps"] if s["name"] == "aws_databricks_repository_update")["status"] == "skipped"

    target = Path(context.get_artifact("replacement_summary")["target_repo_path"])
    assert (target / ".git").exists()  # commit really happened locally
    assert not (tmp_path / "remote").exists()  # but nothing was pushed anywhere


def test_deployment_engine_full_deploy_pushes_and_updates(tmp_path: Path):
    engine = DeploymentEngine(token_store=_valid_token_store(), remote_root=str(tmp_path / "remote"))
    context = _base_context(tmp_path, dry_run=False)

    result_context = engine.run(context)
    plan = result_context.get_artifact("deployment_plan")

    assert plan["overall_status"] == "DEPLOYED"
    step_names = [s["name"] for s in plan["steps"]]
    assert step_names == [
        "validation_gate", "git_commit", "git_push",
        "repository_synchronization", "aws_databricks_repository_update",
    ]
    assert all(s["status"] == "completed" for s in plan["steps"])

    push_step = next(s for s in plan["steps"] if s["name"] == "git_push")
    update_step = next(s for s in plan["steps"] if s["name"] == "aws_databricks_repository_update")
    assert push_step["detail"]["remote_commit_hash"] == update_step["detail"]["response"]["head_commit_id"]


def test_deployment_engine_full_deploy_requires_valid_aws_token(tmp_path: Path):
    empty_store = TokenStore()  # no AWS token minted
    engine = DeploymentEngine(token_store=empty_store, remote_root=str(tmp_path / "remote"))
    context = _base_context(tmp_path, dry_run=False)

    with pytest.raises(Exception, match="No simulated token"):
        engine.run(context)


def test_deployment_engine_writes_plan_json(tmp_path: Path):
    engine = DeploymentEngine(token_store=_valid_token_store(), remote_root=str(tmp_path / "remote"))
    context = _base_context(tmp_path, dry_run=True)

    result_context = engine.run(context)
    output_path = Path(result_context.metadata["deployment_plan_path"])
    assert output_path.exists()
    assert output_path.name == "DeploymentPlan.json"




def _workspace_deployment_context(tmp_path: Path, auto_deploy: bool, dry_run: bool) -> PipelineContext:
    preview = tmp_path / "preview" / "PFL"
    preview.mkdir(parents=True)
    (preview / "job.py").write_text(
        "# Databricks notebook source\npath = 's3://bucket/customer'\n"
    )
    context = PipelineContext(config={
        "pipeline": {"dry_run": dry_run},
        "deployment": {"auto_deploy": auto_deploy},
        "source": {
            "source_mode": "workspace",
            "workspace_url": "https://x.cloud.databricks.com",
            "repo_path": "/Workspace/Users/test/pfl-repo",
        },
        "target": {
            "workspace_url": "https://x.cloud.databricks.com",
            "repo_path": "/Workspace/Users/test/pfl-repo",
        },
        "output": {"reports_dir": str(tmp_path / "reports")},
    })
    context.metadata["workspace_preview_root"] = str(tmp_path / "preview")
    context.set_artifact("validation_report", {"overall_status": "PASS"})
    context.set_artifact("replacement_summary", {
        "target_repo_path": str(tmp_path / "preview"),
        "notebooks_written": 1,
        "total_operations_applied": 1,
        "notebook_results": [{"relative_path": "PFL/job.py", "output_path": str(preview / "job.py")}],
    })
    context.set_artifact("repository", {"repo_name": "pfl-repo"})
    return context


def test_workspace_auto_deploy_false_does_not_write(monkeypatch, tmp_path: Path):
    class FakeWorkspace:
        def __init__(self, *args, **kwargs):
            self.calls = []
        def import_source(self, *args, **kwargs):
            raise AssertionError("workspace write must not occur")

    monkeypatch.setattr("repository.databricks_workspace.DatabricksWorkspaceClient", FakeWorkspace)
    context = _workspace_deployment_context(tmp_path, auto_deploy=False, dry_run=False)
    result = DeploymentEngine(token_store=_valid_token_store()).run(context)
    plan = result.get_artifact("deployment_plan")
    assert plan["overall_status"] == "READY_NOT_DEPLOYED"


def test_workspace_auto_deploy_true_writes_selected_notebook(monkeypatch, tmp_path: Path):
    class FakeWorkspace:
        calls = []
        def __init__(self, *args, **kwargs):
            pass
        def import_source(self, path, content, overwrite=True):
            self.calls.append((path, content, overwrite))

    fake = FakeWorkspace()
    monkeypatch.setattr("repository.databricks_workspace.DatabricksWorkspaceClient", lambda *a, **k: fake)
    context = _workspace_deployment_context(tmp_path, auto_deploy=True, dry_run=False)
    result = DeploymentEngine(token_store=_valid_token_store()).run(context)
    plan = result.get_artifact("deployment_plan")
    assert plan["overall_status"] == "DEPLOYED"
    assert fake.calls[0][0] == "/Workspace/Users/test/pfl-repo/PFL/job"
    assert "s3://bucket/customer" in fake.calls[0][1]
# ---------------------------------------------------------------------------
# Full pipeline integration against the real demo repo
# ---------------------------------------------------------------------------

def test_deployment_engine_full_pipeline_against_real_demo_repo(tmp_path: Path):
    from auth.auth_manager import AuthenticationManager
    from config.config_manager import ConfigurationManager
    from orchestrator.orchestrator import Orchestrator
    from parser.parser_engine import ParserEngine
    from replacement.replacement_engine import ReplacementEngine
    from repository.repository_manager import RepositoryManager, _PROJECT_ROOT
    from rules.rule_repository import RuleRepository
    from rule_service.rule_service import RuleService
    from transformation.transformation_planner import TransformationPlanner
    from validation.validation_engine import ValidationEngine

    real_source = _PROJECT_ROOT / "ucmp-demo" / "Loan-Platform"
    if not real_source.exists():
        pytest.skip("ucmp-demo/Loan-Platform not present in this checkout")

    env = {
        "UCMP__SOURCE__REPO_PATH": str(real_source),
        "UCMP__TARGET__REPO_PATH": str(tmp_path / "migrated"),
        "UCMP__OUTPUT__KNOWLEDGE_MODEL_DIR": str(tmp_path / "knowledge_model"),
        "UCMP__OUTPUT__REPORTS_DIR": str(tmp_path / "reports"),
        "UCMP__PIPELINE__DRY_RUN": "false",
    }
    config_manager = ConfigurationManager(config_path=None, env=env)
    auth_manager = AuthenticationManager()
    repository_manager = RepositoryManager(
        token_store=auth_manager.token_store, staging_dir=str(tmp_path / "staging")
    )
    parser_engine = ParserEngine()
    rule_repository = RuleRepository()
    rule_service = RuleService(rule_repository=rule_repository)
    planner = TransformationPlanner()
    replacement_engine = ReplacementEngine()
    validation_engine = ValidationEngine()
    deployment_engine = DeploymentEngine(
        token_store=auth_manager.token_store, remote_root=str(tmp_path / "remote")
    )

    orchestrator = Orchestrator(stages=[
        config_manager, auth_manager, repository_manager, parser_engine,
        rule_repository, rule_service, planner, replacement_engine,
        validation_engine, deployment_engine,
    ])
    context = orchestrator.run(PipelineContext())

    assert context.summary()["overall_status"] == "SUCCESS"
    plan = context.get_artifact("deployment_plan")
    assert plan["overall_status"] == "DEPLOYED"

    # Confirm with a real, independent git command against the simulated remote
    remote_path = tmp_path / "remote" / "Loan-Platform.git"
    log_result = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(remote_path), capture_output=True, text=True
    )
    assert log_result.returncode == 0
    assert "UCMP migration: Loan-Platform" in log_result.stdout
