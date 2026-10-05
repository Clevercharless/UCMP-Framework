"""
deployment.deployment_engine
===============================
DeploymentEngine is the eleventh pipeline stage. It:

  1. Enforces the validation gate: if the ValidationReport (Module 10)
     overall_status is FAIL, deployment is ABORTED - no git operations
     happen at all. This mirrors a real CI/CD gate and is a deliberate
     business rule, not a technical limitation.
  2. Commits the migrated repo locally (real git).
  3. If pipeline.dry_run is True (the demo default), stops here -
     DRY_RUN_COMPLETE. This is the standard "build and verify the
     artifact, don't actually ship it" dry-run semantics.
  4. Otherwise, pushes to a simulated AWS Databricks Repos backing store
     (a local bare git repo), simulates repository synchronization, and
     simulates the AWS Databricks Repos API update - consuming the AWS
     token minted by Module 3's AuthenticationManager.
  5. Writes DeploymentPlan.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from auth.token_store import TokenStore
from common.exceptions import DeploymentError
from common.logging_config import get_logger
from deployment.aws_repository_updater import AWSDatabricksRepositoryUpdater, RepositorySynchronizer
from deployment.deployment_plan import DeploymentPlan, DeploymentStep
from deployment.git_commit_service import GitCommitService
from deployment.git_push_service import GitPushService
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REMOTE_ROOT = _PROJECT_ROOT / "ucmp-demo" / "output" / "_aws_databricks_remote"
_REQUIRED_ARTIFACTS = ["validation_report", "replacement_summary", "repository"]


class DeploymentEngine(PipelineStage):
    """Simulates git commit/push, repository sync, and AWS Databricks Repos update."""

    name = "DeploymentEngine"

    def __init__(self, token_store: TokenStore, remote_root: Optional[str] = None):
        self._token_store = token_store
        self._git_commit_service = GitCommitService()
        remote_root_path = Path(remote_root) if remote_root else _DEFAULT_REMOTE_ROOT
        self._git_push_service = GitPushService(remote_root=remote_root_path)
        self._repo_synchronizer = RepositorySynchronizer()
        self._aws_updater = AWSDatabricksRepositoryUpdater()

    def run(self, context: PipelineContext) -> PipelineContext:
        missing = [key for key in _REQUIRED_ARTIFACTS if not context.get_artifact(key)]
        if missing:
            raise DeploymentError(
                f"DeploymentEngine requires the following artifacts to be populated first: {missing}"
            )
        if not context.config:
            raise DeploymentError("DeploymentEngine requires context.config")

        validation_report = context.get_artifact("validation_report")
        replacement_summary = context.get_artifact("replacement_summary")
        repository = context.get_artifact("repository")

        repo_name = repository["repo_name"]
        source_cfg = context.config.get("source", {}) or {}
        target_cfg = context.config.get("target", {}) or {}
        source_mode = str(source_cfg.get("source_mode", "local_repo")).strip().lower()
        target_root = Path(replacement_summary["target_repo_path"])
        validation_status = validation_report["overall_status"]
        deployment_cfg = context.config.get("deployment", {}) or {}
        auto_deploy = bool(deployment_cfg.get("auto_deploy", False))
        dry_run = bool(context.config.get("pipeline", {}).get("dry_run", True))

        if validation_status == "FAIL":
            plan = self._build_aborted_plan(repo_name, validation_status)
            return self._finalize(context, plan)

        steps = [
            DeploymentStep(
                name="validation_gate", status="completed",
                detail={"validation_status": validation_status},
                notes="Validation passed; deployment gate evaluated.",
            )
        ]

        if source_mode == "workspace":
            # Workspace mode never performs Git commit/push. The transformed selected
            # notebooks are held in the replacement preview and are written back only
            # when both auto_deploy=true and dry_run=false.
            if not auto_deploy:
                steps.append(DeploymentStep(
                    name="workspace_write",
                    status="skipped",
                    notes="auto_deploy=false: transformed notebooks were not written to the workspace.",
                ))
                plan = DeploymentPlan(
                    repo_name=repo_name,
                    deployment_mode="workspace_preview",
                    validation_gate_status=validation_status,
                    overall_status="READY_NOT_DEPLOYED",
                    steps=steps,
                )
                return self._finalize(context, plan)

            if dry_run:
                steps.append(DeploymentStep(
                    name="workspace_write",
                    status="skipped",
                    notes="dry_run=true: workspace write-back skipped even though auto_deploy=true.",
                ))
                plan = DeploymentPlan(
                    repo_name=repo_name,
                    deployment_mode="workspace_dry_run",
                    validation_gate_status=validation_status,
                    overall_status="DRY_RUN_COMPLETE",
                    steps=steps,
                )
                return self._finalize(context, plan)

            preview_root = Path(context.metadata.get("workspace_preview_root", ""))
            if not preview_root.exists():
                raise DeploymentError("Workspace deployment preview does not exist.")

            from repository.databricks_workspace import DatabricksWorkspaceClient
            target_url = str(target_cfg.get("workspace_url", "") or "").strip()
            if not target_url or "simulated.cloud.databricks.com" in target_url:
                target_url = str(source_cfg.get("workspace_url", "") or "").strip()
            target_repo_root = str(
                target_cfg.get("repo_path")
                or source_cfg.get("repo_path")
                or ""
            ).rstrip("/")
            if not target_repo_root:
                raise DeploymentError("Target workspace repo_path is required for workspace deployment.")

            client = DatabricksWorkspaceClient(target_url or None)
            deployed = []
            for result in replacement_summary.get("notebook_results", []):
                relative_path = str(result["relative_path"])
                preview_file = preview_root / relative_path
                if not preview_file.exists():
                    raise DeploymentError(
                        f"Transformed preview for '{relative_path}' was not found."
                    )
                content = preview_file.read_text(encoding="utf-8", errors="ignore")
                workspace_path = self._workspace_notebook_path(target_repo_root, relative_path)
                # Only notebooks present in the transformation plan/replacement summary
                # are deployed. Dependencies discovered by analysis are never auto-added.
                client.import_source(workspace_path, content, overwrite=True)
                deployed.append(workspace_path)

            steps.append(DeploymentStep(
                name="workspace_write",
                status="completed",
                detail={"notebooks_written": deployed},
                notes="Selected migration notebooks written directly to the Databricks workspace. No Git operations performed.",
            ))
            plan = DeploymentPlan(
                repo_name=repo_name,
                deployment_mode="workspace",
                validation_gate_status=validation_status,
                overall_status="DEPLOYED",
                steps=steps,
            )
            return self._finalize(context, plan)

        # Legacy local_repo mode retains the existing Git-based deployment behavior.
        commit_result = self._git_commit_service.commit(
            target_root,
            message=self._commit_message(repo_name, replacement_summary, validation_report),
        )
        steps.append(DeploymentStep(name="git_commit", status="completed", detail=commit_result))

        if dry_run:
            steps.append(DeploymentStep(
                name="git_push", status="skipped", notes="Dry run mode: push skipped",
            ))
            steps.append(DeploymentStep(
                name="repository_synchronization", status="skipped", notes="Dry run mode: skipped",
            ))
            steps.append(DeploymentStep(
                name="aws_databricks_repository_update", status="skipped", notes="Dry run mode: skipped",
            ))
            plan = DeploymentPlan(
                repo_name=repo_name, deployment_mode="dry_run",
                validation_gate_status=validation_status, overall_status="DRY_RUN_COMPLETE", steps=steps,
            )
            return self._finalize(context, plan)

        remote_path = self._git_push_service.ensure_remote_exists(repo_name)
        push_result = self._git_push_service.push(target_root, remote_path)
        steps.append(DeploymentStep(name="git_push", status="completed", detail=push_result))

        target_config = context.config["target"]
        sync_result = self._repo_synchronizer.synchronize(
            workspace_url=target_config["workspace_url"],
            commit_hash=push_result["remote_commit_hash"],
        )
        steps.append(DeploymentStep(
            name="repository_synchronization", status="completed", detail=sync_result,
        ))

        token = self._token_store.require_valid("aws_databricks")
        update_result = self._aws_updater.update(
            token=token,
            workspace_url=target_config["workspace_url"],
            repo_path_in_workspace=target_config["repo_path"],
            commit_hash=push_result["remote_commit_hash"],
        )
        steps.append(DeploymentStep(
            name="aws_databricks_repository_update", status="completed", detail=update_result,
        ))

        plan = DeploymentPlan(
            repo_name=repo_name, deployment_mode="full",
            validation_gate_status=validation_status,
            overall_status="DEPLOYED", steps=steps,
        )
        return self._finalize(context, plan)

    @staticmethod
    def _workspace_notebook_path(target_root: str, relative_path: str) -> str:
        rel = str(relative_path).replace("\\", "/").lstrip("/")
        suffix = Path(rel).suffix.lower()
        if suffix in {".py", ".sql", ".scala"}:
            rel = rel[:-len(suffix)]
        return f"{target_root.rstrip('/')}/{rel}"

    # -- internals --------------------------------------------------------

    @staticmethod
    def _build_aborted_plan(repo_name: str, validation_status: str) -> DeploymentPlan:
        return DeploymentPlan(
            repo_name=repo_name, deployment_mode="aborted",
            validation_gate_status=validation_status, overall_status="ABORTED",
            steps=[
                DeploymentStep(
                    name="validation_gate", status="aborted",
                    detail={"validation_status": validation_status},
                    notes="Deployment aborted: validation report status is FAIL. "
                    "No git operations were performed.",
                )
            ],
        )

    @staticmethod
    def _commit_message(repo_name: str, replacement_summary: Dict, validation_report: Dict) -> str:
        return (
            f"UCMP migration: {repo_name} "
            f"({replacement_summary['notebooks_written']} notebooks, "
            f"{replacement_summary['total_operations_applied']} operations applied, "
            f"validation={validation_report['overall_status']})"
        )

    def _finalize(self, context: PipelineContext, plan: DeploymentPlan) -> PipelineContext:
        output_path = self._write_plan(context, plan.to_dict())
        context.set_artifact("deployment_plan", plan.to_dict())
        context.metadata["deployment_complete"] = True
        context.metadata["deployment_status"] = plan.overall_status
        context.metadata["deployment_plan_path"] = str(output_path)

        logger.info(
            "Deployment engine finished: overall_status=%s (mode=%s, %d step(s))",
            plan.overall_status, plan.deployment_mode, len(plan.steps),
        )
        return context

    def _write_plan(self, context: PipelineContext, plan_dict: Dict) -> Path:
        output_dir_config = context.config["output"]["reports_dir"]
        output_dir = Path(output_dir_config)
        if not output_dir.is_absolute():
            output_dir = _PROJECT_ROOT / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "DeploymentPlan.json"
        output_path.write_text(json.dumps(plan_dict, indent=2, default=str), encoding="utf-8")
        return output_path
