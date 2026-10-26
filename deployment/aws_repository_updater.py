"""
deployment.aws_repository_updater
====================================
Simulates the two remaining deployment steps that genuinely cannot be
done locally without a real cloud account: "Repository Synchronization"
(the AWS Databricks workspace noticing the new commit) and "AWS
Databricks Repository Update" (calling the Repos REST API to point the
workspace's Repos folder at that commit). Both are pure data - a
constructed request/response shape logged for the deployment plan - and
both consume the simulated AWS token from Module 3, masked exactly as
that module already handles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from common.logging_config import get_logger

if TYPE_CHECKING:
    from auth.credentials import SimulatedToken

logger = get_logger(__name__)


class RepositorySynchronizer:
    """Simulates the AWS Databricks workspace's Repos integration picking up the new commit."""

    def synchronize(self, workspace_url: str, commit_hash: str) -> Dict:
        logger.info(
            "Simulating repository synchronization: workspace=%s commit=%s",
            workspace_url, commit_hash[:8],
        )
        return {"workspace_url": workspace_url, "synced_commit_hash": commit_hash, "status": "SYNCED"}


class AWSDatabricksRepositoryUpdater:
    """Simulates a PATCH call to the Databricks Repos API to update the tracked commit."""

    def update(
        self,
        token: "SimulatedToken",
        workspace_url: str,
        repo_path_in_workspace: str,
        commit_hash: str,
    ) -> Dict:
        request = {
            "method": "PATCH",
            "url": f"{workspace_url}/api/2.0/repos/{{repo_id}}",
            "headers": {"Authorization": f"Bearer {token.masked()}"},
            "body": {"path": repo_path_in_workspace, "branch": "main"},
        }
        response = {
            "status_code": 200,
            "head_commit_id": commit_hash,
            "path": repo_path_in_workspace,
        }

        logger.info(
            "Simulating AWS Databricks Repos API update: %s %s (token=%s)",
            request["method"], request["url"], token.masked(),
        )
        return {"request": request, "response": response, "status": "UPDATED"}
