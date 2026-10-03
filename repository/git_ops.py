"""
repository.git_ops
===================
`SimulatedGitClient` models the "clone the Azure Repo locally" step of an
enterprise migration without requiring a real Azure DevOps / GitHub remote.
It copies a source folder tree into a local staging directory and logs the
operation the way a real `git clone` would be logged in a CI pipeline.

No real `git` binary is invoked here — this is intentionally a pure
filesystem operation dressed up with git-shaped logging, so the whole demo
runs with zero external dependencies. (Deployment Engine, built later,
will have its own simulated git commit/push for the *output* side of the
pipeline; this module only handles the *input* side.)
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import List

from common.exceptions import RepositoryError
from common.logging_config import get_logger

logger = get_logger(__name__)


class SimulatedGitClient:
    """Simulates `git clone`-style repository synchronization to a local staging path."""

    def clone(self, source_path: Path, staging_path: Path) -> None:
        """
        Simulate cloning `source_path` into `staging_path`. In a real
        pipeline this would be `git clone <azure-repos-url> staging_path`;
        here it's a local recursive copy, refreshed on every run so the
        staging area always reflects the current source state.
        """
        if not source_path.exists():
            raise RepositoryError(f"Source repository path does not exist: {source_path}")
        if not source_path.is_dir():
            raise RepositoryError(f"Source repository path is not a directory: {source_path}")

        logger.info("Simulating: git clone %s %s", source_path, staging_path)
        start = time.time()

        if staging_path.exists():
            shutil.rmtree(staging_path)
        shutil.copytree(source_path, staging_path)

        elapsed = round(time.time() - start, 4)
        file_count = sum(1 for _ in staging_path.rglob("*") if _.is_file())
        logger.info(
            "Simulated clone complete: %d file(s) staged in %ss at %s",
            file_count,
            elapsed,
            staging_path,
        )

    def list_tracked_files(self, staging_path: Path) -> List[Path]:
        """Simulates `git ls-files` — every regular file currently in the staged tree."""
        if not staging_path.exists():
            raise RepositoryError(f"Staging path does not exist: {staging_path}")
        return [p for p in staging_path.rglob("*") if p.is_file()]
