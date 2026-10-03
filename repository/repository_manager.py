"""
repository.repository_manager
==============================
`RepositoryManager` is the fourth pipeline stage. It:

  1. Requires a valid simulated Azure token to already exist (produced by
     Module 3's AuthenticationManager) — this is the first stage that
     actually *consumes* that token, even though it never sends it
     anywhere.
  2. Simulates cloning the Azure Databricks source repo (config
     `source.repo_path`) into a local staging directory via
     `SimulatedGitClient`.
  3. Scans the staged tree, classifies every file as a notebook (Bronze /
     Silver / Gold / Common / Jobs / SQL) or a config asset (Config/*),
     and builds a `RepositoryInventory`.
  4. Validates that the expected medallion folder structure is present —
     fails loudly if e.g. Bronze or Silver is entirely missing.
  5. Publishes the inventory to `context.artifacts["repository"]` for the
     Parser Engine (Module 5) to consume.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from auth.token_store import TokenStore
from common.exceptions import AuthenticationError, RepositoryError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from repository.databricks_workspace import DatabricksWorkspaceClient, WorkspaceObject
from repository.git_ops import SimulatedGitClient
from repository.inventory import (
    ConfigAsset,
    NotebookFile,
    RepositoryInventory,
    compute_sha256,
    detect_notebook_language,
)

logger = get_logger(__name__)

# Categories the demo repo (and any real Loan-Platform-shaped repo) is expected
# to contain. Config isn't a notebook category but IS a required top-level folder.
REQUIRED_NOTEBOOK_CATEGORIES = ["Bronze", "Silver", "Gold", "Common", "Jobs"]
NOTEBOOK_EXTENSIONS = {".py", ".sql", ".scala"}
CONFIG_CATEGORY = "Config"

# Project root: two levels up from this file (ucmp-core/repository/ -> project root),
# so config paths like "ucmp-demo/Loan-Platform" resolve consistently regardless of cwd.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RepositoryManager(PipelineStage):
    """
    Syncs and inventories the Azure Databricks source repository.

    Parameters
    ----------
    token_store:
        The `TokenStore` populated by AuthenticationManager (Module 3).
        Required so RepositoryManager can prove it only proceeds once a
        valid simulated Azure credential exists — mirroring how a real
        Repository Manager would need an auth'd git/REST client.
    staging_dir:
        Where the simulated clone is written. Defaults to
        `<project_root>/ucmp-demo/output/_staging/<repo_name>`.
    """

    name = "RepositoryManager"

    def __init__(self, token_store: TokenStore, staging_dir: Optional[str] = None):
        self._token_store = token_store
        self._staging_dir_override = staging_dir
        self._git_client = SimulatedGitClient()

    def run(self, context: PipelineContext) -> PipelineContext:
        if not context.config:
            raise RepositoryError(
                "RepositoryManager requires context.config to be populated "
                "(run ConfigurationManager first)"
            )

        source_cfg = context.config["source"]
        source_mode = str(source_cfg.get("source_mode", "local_repo")).lower()

        if source_mode == "workspace":
            # Real workspace mode authenticates through the Databricks execution
            # context / native SDK inside Databricks. The simulated Azure token
            # produced by AuthenticationManager is deliberately not used as a
            # workspace credential.
            logger.info(
                "RepositoryManager using real Databricks workspace discovery; "
                "no user-created PAT is required"
            )
            inventory = self._sync_databricks_workspace(source_cfg)
        elif source_mode == "local_repo":
            # Preserve the legacy simulated-token gate for local/demo mode.
            token = self._token_store.require_valid("azure_databricks")
            logger.info(
                "RepositoryManager proceeding with simulated Azure token for principal '%s'",
                token.principal,
            )
            source_repo_path = self._resolve_path(source_cfg["repo_path"])
            repo_name = source_repo_path.name
            staging_path = self._resolve_staging_path(repo_name)

            self._git_client.clone(source_repo_path, staging_path)
            inventory = self._build_inventory(repo_name, source_repo_path, staging_path)
        else:
            raise RepositoryError(
                f"Unsupported source.source_mode '{source_mode}'. "
                "Expected 'local_repo' or 'workspace'."
            )

        if source_mode == "local_repo":
            self._validate_structure(inventory)

        context.set_artifact("repository", inventory.to_dict())
        context.metadata["repository_synced"] = True
        context.metadata["staged_repo_path"] = inventory.staged_path

        logger.info(
            "Repository inventory complete: %d notebook(s) across categories %s, "
            "%d config asset(s)",
            inventory.notebook_count,
            inventory.categories_found,
            len(inventory.config_assets),
        )
        return context

    def _sync_databricks_workspace(self, source_cfg: dict) -> RepositoryInventory:
        """Export notebooks from a real Databricks workspace into local staging.

        This is intentionally a discovery-only adapter. It does not modify the
        Databricks workspace and leaves all existing parser/transformation stages
        unchanged.
        """
        workspace_url = str(source_cfg.get("workspace_url", "")).strip()

        configured_root = str(source_cfg.get("workspace_path", "/"))
        client = DatabricksWorkspaceClient(workspace_url)
        objects = client.list_recursive(configured_root)

        repo_name = configured_root.strip("/").replace("/", "_") or "workspace"
        staging_path = self._resolve_staging_path(repo_name)
        if staging_path.exists():
            import shutil
            shutil.rmtree(staging_path)
        staging_path.mkdir(parents=True, exist_ok=True)

        inventory = RepositoryInventory(
            repo_name=repo_name,
            source_path=f"databricks://{workspace_url}{configured_root}",
            staged_path=str(staging_path),
        )

        for obj in objects:
            if obj.object_type.upper() != "NOTEBOOK":
                continue

            relative = obj.path.strip("/")
            if configured_root.strip("/"):
                prefix = configured_root.strip("/") + "/"
                if relative.startswith(prefix):
                    relative = relative[len(prefix):]
            if not relative:
                relative = Path(obj.path).name

            language = self._workspace_language(obj.language, obj.path)
            extension = {
                "python": ".py", "sql": ".sql", "scala": ".scala"
            }.get(language.value, ".py")
            relative_path = str(Path(relative).with_suffix(extension))
            output_path = staging_path / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)

            content = client.export_source(obj.path)
            output_path.write_text(content, encoding="utf-8")

            inventory.notebooks.append(
                NotebookFile(
                    relative_path=relative_path,
                    absolute_path=str(output_path),
                    category=relative_path.split("/")[0] if "/" in relative_path else "Root",
                    language=language,
                    size_bytes=len(content.encode("utf-8")),
                    line_count=len(content.splitlines()),
                    sha256=compute_sha256(output_path),
                )
            )

        inventory.categories_found = sorted({nb.category for nb in inventory.notebooks})
        logger.info(
            "Databricks workspace discovery complete: %d notebook(s) exported to %s",
            inventory.notebook_count, staging_path,
        )
        return inventory

    @staticmethod
    def _workspace_language(language: Optional[str], path: str):
        value = (language or "").lower()
        if value == "python":
            from repository.inventory import NotebookLanguage
            return NotebookLanguage.PYTHON
        if value == "sql":
            from repository.inventory import NotebookLanguage
            return NotebookLanguage.SQL
        if value == "scala":
            from repository.inventory import NotebookLanguage
            return NotebookLanguage.SCALA
        # Databricks workspace list normally supplies language. Keep a safe
        # fallback for mocked/test responses.
        suffix = Path(path).suffix.lower()
        from repository.inventory import NotebookLanguage
        return {".py": NotebookLanguage.PYTHON, ".sql": NotebookLanguage.SQL, ".scala": NotebookLanguage.SCALA}.get(
            suffix, NotebookLanguage.UNKNOWN
        )

    # -- internals --------------------------------------------------------

    def _resolve_path(self, configured_path: str) -> Path:
        path = Path(configured_path)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        return path.resolve()

    def _resolve_staging_path(self, repo_name: str) -> Path:
        if self._staging_dir_override:
            base = self._resolve_path(self._staging_dir_override)
            return base
        return _PROJECT_ROOT / "ucmp-demo" / "output" / "_staging" / repo_name

    def _build_inventory(
        self, repo_name: str, source_path: Path, staging_path: Path
    ) -> RepositoryInventory:
        inventory = RepositoryInventory(
            repo_name=repo_name, source_path=str(source_path), staged_path=str(staging_path)
        )

        categories_found: List[str] = []
        for file_path in self._git_client.list_tracked_files(staging_path):
            relative = file_path.relative_to(staging_path)
            top_level_category = relative.parts[0] if relative.parts else "unknown"

            if top_level_category == CONFIG_CATEGORY:
                inventory.config_assets.append(
                    ConfigAsset(
                        relative_path=str(relative),
                        absolute_path=str(file_path),
                        size_bytes=file_path.stat().st_size,
                        sha256=compute_sha256(file_path),
                    )
                )
                continue

            if file_path.suffix not in NOTEBOOK_EXTENSIONS:
                continue  # skip anything that isn't a notebook or a config asset

            language = detect_notebook_language(file_path)
            line_count = self._count_lines(file_path)

            inventory.notebooks.append(
                NotebookFile(
                    relative_path=str(relative),
                    absolute_path=str(file_path),
                    category=top_level_category,
                    language=language,
                    size_bytes=file_path.stat().st_size,
                    line_count=line_count,
                    sha256=compute_sha256(file_path),
                )
            )
            if top_level_category not in categories_found:
                categories_found.append(top_level_category)

        inventory.categories_found = sorted(categories_found)
        return inventory

    @staticmethod
    def _count_lines(path: Path) -> int:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)

    def _validate_structure(self, inventory: RepositoryInventory) -> None:
        missing = [
            category
            for category in REQUIRED_NOTEBOOK_CATEGORIES
            if category not in inventory.categories_found
        ]
        if missing:
            raise RepositoryError(
                f"Source repository '{inventory.repo_name}' is missing required "
                f"categories: {missing}. Found: {inventory.categories_found}"
            )
        if inventory.notebook_count == 0:
            raise RepositoryError(
                f"Source repository '{inventory.repo_name}' contains no notebooks"
            )
