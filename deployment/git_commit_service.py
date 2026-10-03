"""
deployment.git_commit_service
================================
Simulates "Git Commit" using REAL local git commands (git is in the
approved Simulation Mode toolset per spec) against the migrated output
directory. This is genuinely a git repository with a real commit history
- just with no external remote involved, keeping everything local and
free. No network access, no real Azure DevOps / GitHub / AWS CodeCommit
account required.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

from common.exceptions import DeploymentError
from common.logging_config import get_logger

logger = get_logger(__name__)

_BOT_NAME = "UCMP Migration Bot"
_BOT_EMAIL = "ucmp-bot@ucmp.local"


class GitCommitService:
    """Initializes (if needed) and commits the migrated repo using real local git."""

    def __init__(self):
        if shutil.which("git") is None:
            raise DeploymentError(
                "git is not available on PATH; Deployment Engine requires git for "
                "the (local-only) commit simulation"
            )

    def commit(self, repo_path: Path, message: str) -> Dict:
        is_fresh_repo = not (repo_path / ".git").exists()

        if is_fresh_repo:
            self._run(["git", "init", "-q"], repo_path)
            self._run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], repo_path)

        self._run(["git", "config", "user.email", _BOT_EMAIL], repo_path)
        self._run(["git", "config", "user.name", _BOT_NAME], repo_path)
        self._run(["git", "add", "-A"], repo_path)

        status = self._run(["git", "status", "--porcelain"], repo_path)
        if not status.stdout.strip():
            head_hash = self._current_head_hash(repo_path)
            logger.info("Nothing to commit in %s (working tree clean)", repo_path)
            return {
                "committed": False, "commit_hash": head_hash,
                "message": message, "reason": "working tree clean, no changes to commit",
            }

        self._run(["git", "commit", "-q", "-m", message], repo_path)
        commit_hash = self._current_head_hash(repo_path)

        logger.info("Committed %s to local git repo at %s (%s)", commit_hash[:8], repo_path, message)
        return {"committed": True, "commit_hash": commit_hash, "message": message, "reason": None}

    def _current_head_hash(self, repo_path: Path) -> Optional[str]:
        try:
            result = self._run(["git", "rev-parse", "HEAD"], repo_path)
            return result.stdout.strip()
        except DeploymentError:
            return None  # no commits yet

    @staticmethod
    def _run(args, cwd: Path) -> subprocess.CompletedProcess:
        result = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
        if result.returncode != 0:
            raise DeploymentError(
                f"git command failed: {' '.join(args)} (cwd={cwd})\n{result.stderr.strip()}"
            )
        return result
