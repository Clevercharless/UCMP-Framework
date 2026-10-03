"""
deployment.git_push_service
==============================
Simulates "Git Push" and "Repository Synchronization" by pushing to a
real local BARE git repository that stands in for the git backing store
behind AWS Databricks Repos (which is itself just a git remote under the
hood). Genuinely exercises git push end to end - the only thing
"simulated" is that the remote lives on the local filesystem instead of
at a real Azure DevOps/GitHub/CodeCommit URL.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict

from common.exceptions import DeploymentError
from common.logging_config import get_logger

logger = get_logger(__name__)

_REMOTE_NAME = "aws-databricks-repos"


class GitPushService:
    """Pushes a local migrated repo to a local bare 'remote' simulating AWS Databricks Repos."""

    def __init__(self, remote_root: Path):
        self._remote_root = remote_root

    def ensure_remote_exists(self, repo_name: str) -> Path:
        remote_path = self._remote_root / f"{repo_name}.git"
        if not remote_path.exists():
            remote_path.parent.mkdir(parents=True, exist_ok=True)
            self._run(["git", "init", "--bare", "-q", str(remote_path)], self._remote_root)
            self._run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], remote_path)
            logger.info("Initialized simulated AWS Databricks Repos backing store at %s", remote_path)
        return remote_path

    def push(self, local_repo_path: Path, remote_path: Path, branch: str = "main") -> Dict:
        self._run(["git", "remote", "remove", _REMOTE_NAME], local_repo_path, allow_failure=True)
        self._run(["git", "remote", "add", _REMOTE_NAME, str(remote_path)], local_repo_path)
        self._run(["git", "push", "-q", _REMOTE_NAME, branch], local_repo_path)

        remote_commit_hash = self._run(
            ["git", "rev-parse", branch], remote_path
        ).stdout.strip()

        logger.info(
            "Pushed to simulated remote %s; remote %s now at %s",
            remote_path, branch, remote_commit_hash[:8],
        )
        return {
            "pushed": True, "remote_name": _REMOTE_NAME, "remote_path": str(remote_path),
            "branch": branch, "remote_commit_hash": remote_commit_hash,
        }

    @staticmethod
    def _run(args, cwd: Path, allow_failure: bool = False) -> subprocess.CompletedProcess:
        result = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
        if result.returncode != 0 and not allow_failure:
            raise DeploymentError(
                f"git command failed: {' '.join(args)} (cwd={cwd})\n{result.stderr.strip()}"
            )
        return result
