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
            self._active_migration_cfg = context.config.get("migration", {}) or {}
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

        # An explicit migration scope makes repository category layout optional.
        # The parser will use migration.notebook_list as the authoritative scope.
        # Keep the legacy structural validation only for unrestricted local-repo
        # migrations so existing demo/test behavior remains intact.
        migration_cfg = context.config.get("migration", {}) or {}
        explicit_scope = bool(
            migration_cfg.get("notebook_list")
            or migration_cfg.get("notebook_list_file")
        )
        if source_mode == "local_repo" and not explicit_scope:
            self._validate_structure(inventory)
        elif explicit_scope:
            logger.info(
                "Explicit migration scope detected; skipping legacy Bronze/Silver/Gold/"
                "Common/Jobs repository structure validation."
            )

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
        """Discover workspace metadata and export only explicitly selected notebooks.

        Real workspace mode deliberately avoids git clone and full-repository staging.
        The workspace API is used for metadata discovery, while notebook source is
        fetched only for migration.notebook_list entries.
        """
        workspace_url = str(source_cfg.get("workspace_url", "")).strip()
        configured_root = str(source_cfg.get("workspace_path", source_cfg.get("repo_path", "/"))).strip() or "/"
        client = DatabricksWorkspaceClient(workspace_url or None)

        migration_cfg = getattr(self, "_active_migration_cfg", {}) or {}
        requested = list(migration_cfg.get("notebook_list") or [])
        if not requested and migration_cfg.get("notebook_list_file"):
            requested = self._load_notebook_list_file(str(migration_cfg["notebook_list_file"]))
        if not requested:
            raise RepositoryError(
                "Workspace mode requires migration.notebook_list. Full workspace migration is "
                "intentionally disabled to avoid cloning/staging the entire workspace."
            )

        objects = client.list_recursive(configured_root)
        notebook_objects = [
            o for o in objects
            if str(o.object_type).upper() == "NOTEBOOK"
            or (str(o.object_type).upper() == "FILE" and Path(o.path).suffix.lower() in {".py", ".sql", ".scala"})
        ]
        known_paths = []
        object_by_normalized = {}
        root_norm = configured_root.strip("/").lower()
        for obj in notebook_objects:
            full = obj.path.strip("/")
            relative = full
            prefix = configured_root.strip("/") + "/"
            if configured_root.strip("/") and full.lower().startswith(prefix.lower()):
                relative = full[len(prefix):]
            known_paths.append(relative)
            object_by_normalized[self._normalize_workspace_path(full, configured_root)] = obj
            object_by_normalized[self._normalize_workspace_path(relative, configured_root)] = obj

        selected = []
        missing = []
        for requested_path in requested:
            key = self._normalize_workspace_path(requested_path, configured_root)
            obj = object_by_normalized.get(key)
            if obj is None:
                missing.append(requested_path)
            else:
                selected.append(obj)

        if missing:
            logger.warning("%d requested workspace notebook(s) were not found: %s", len(missing), missing)

        inventory = RepositoryInventory(
            repo_name=Path(configured_root.rstrip("/")).name or "workspace",
            source_path=f"databricks://{workspace_url}{configured_root}",
            staged_path="",
            workspace_mode=True,
            all_notebook_paths=sorted(set(known_paths)),
        )

        for obj in selected:
            full = obj.path.strip("/")
            prefix = configured_root.strip("/") + "/"
            relative = full[len(prefix):] if configured_root.strip("/") and full.lower().startswith(prefix.lower()) else full
            language = self._workspace_language(obj.language, obj.path)
            content = client.export_source(obj.path)
            inventory.notebooks.append(
                NotebookFile(
                    relative_path=relative,
                    absolute_path="",
                    category=relative.split("/")[0] if "/" in relative else "Root",
                    language=language,
                    size_bytes=len(content.encode("utf-8")),
                    line_count=len(content.splitlines()),
                    sha256=__import__("hashlib").sha256(content.encode("utf-8")).hexdigest(),
                    source_content=content,
                    workspace_object_type=str(obj.object_type).upper(),
                )
            )

        inventory.categories_found = sorted({nb.category for nb in inventory.notebooks})
        logger.info(
            "Databricks workspace discovery complete: discovered %d notebook path(s); "
            "exported %d selected notebook(s); no clone/staging performed",
            len(inventory.all_notebook_paths), inventory.notebook_count,
        )
        return inventory

    @staticmethod
    def _load_notebook_list_file(path_value: str) -> list[str]:
        path = Path(path_value)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        if not path.exists():
            raise RepositoryError(f"Migration notebook list file does not exist: {path}")
        suffix = path.suffix.lower()
        values = []
        if suffix in {".txt", ".csv"}:
            import csv
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.reader(fh):
                    if row and row[0].strip() and row[0].strip().lower() not in {"notebook path", "path"}:
                        values.append(row[0].strip())
        elif suffix in {".xlsx", ".xlsm"}:
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            header = [str(v).strip() if v is not None else "" for v in (rows[0] if rows else [])]
            idx = header.index("Notebook Path") if "Notebook Path" in header else 0
            values = [str(row[idx]).strip() for row in rows[1:] if len(row) > idx and row[idx]]
        else:
            raise RepositoryError(f"Unsupported migration notebook list format: {suffix}")
        return list(dict.fromkeys(values))

    @staticmethod
    def _normalize_workspace_path(path: str, configured_root: str) -> str:
        value = str(path or "").strip().replace("\\", "/").strip("/").lower()
        root = str(configured_root or "/").strip().strip("/").lower()
        if root and value.startswith(root + "/"):
            value = value[len(root) + 1:]
        return value.rsplit(".py", 1)[0] if value.endswith(".py") else value.rsplit(".sql", 1)[0] if value.endswith(".sql") else value.rsplit(".scala", 1)[0] if value.endswith(".scala") else value

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
