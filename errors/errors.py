"""
repository.repository_manager
=============================

Repository/workspace discovery and migration-scope preparation for UCMP.

Responsibilities
----------------
1. Discover source notebooks.
2. Support real Databricks workspace mode.
3. Resolve the user-provided migration notebook list.
4. Export only selected notebooks in workspace mode.
5. Build a workspace inventory for dependency analysis.
6. Preserve local-repository behavior for legacy/demo execution.

Important
---------
Workspace mode does NOT:
    - clone the complete repository
    - require Bronze/Silver/Gold/Common/Jobs folders
    - automatically add dependencies to migration scope
    - deploy transformed notebooks
    - perform Git commit/push

Deployment is handled by DeploymentEngine.
"""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from common.exceptions import RepositoryError
from common.logging_config import get_logger
from config.schema import UCMPConfig
from repository.databricks_workspace import (
    DatabricksWorkspaceClient,
    WorkspaceObject,
)
from repository.inventory import NotebookMetadata, RepositoryInventory


logger = get_logger(__name__)


class RepositoryManager:
    """
    Prepare the repository/workspace for migration.

    Workspace mode
    --------------
    Discovery is performed directly against the configured Databricks
    workspace.

    Only notebooks explicitly present in:

        migration.notebook_list

    or, when that list is empty:

        migration.notebook_list_file

    are exported for migration.

    Discovery of other notebooks is retained as metadata so that
    dependency analysis can determine whether referenced notebooks
    exist and whether they were selected for migration.
    """

    NOTEBOOK_EXTENSIONS = {
        ".py",
        ".sql",
        ".scala",
        ".r",
    }

    NOTEBOOK_OBJECT_TYPES = {
        "NOTEBOOK",
        "FILE",
    }

    CONFIG_EXTENSIONS = {
        ".yaml",
        ".yml",
        ".json",
        ".conf",
        ".ini",
        ".properties",
    }

    def __init__(
        self,
        config: UCMPConfig,
        context=None,
    ):
        self.config = config
        self.context = context

        self._workspace_client: Optional[DatabricksWorkspaceClient] = None

        self._workspace_objects: Dict[str, WorkspaceObject] = {}

        self._selected_notebook_paths: List[str] = []

        self._known_notebook_paths: List[str] = []

        self._workspace_preview_root: Optional[str] = None

        self._temporary_paths: List[str] = []

    # =================================================================
    # Public API
    # =================================================================

    def run(self) -> RepositoryInventory:
        """
        Execute repository preparation.

        Returns
        -------
        RepositoryInventory
            Inventory consumed by ParserEngine and subsequent stages.
        """

        source = self.config.source

        source_mode = str(
            getattr(source, "source_mode", None)
            or self._get_config_value(
                "source",
                "source_mode",
                default="local_repo",
            )
        ).strip().lower()

        if source_mode == "workspace":
            return self._run_workspace_mode()

        return self._run_local_repository_mode()

    # =================================================================
    # Workspace mode
    # =================================================================

    def _run_workspace_mode(self) -> RepositoryInventory:
        """
        Discover the real Databricks workspace and export only the
        notebooks explicitly selected for migration.
        """

        source = self.config.source

        workspace_url = self._get_source_value(
            "workspace_url",
            default="",
        )

        configured_root = self._get_source_value(
            "workspace_path",
            default="",
        )

        if not configured_root:
            configured_root = self._get_source_value(
                "repo_path",
                default="",
            )

        configured_root = self._normalize_workspace_path(
            configured_root or "/"
        )

        if not workspace_url:
            raise RepositoryError(
                "source.workspace_url is required when "
                "source.source_mode='workspace'"
            )

        logger.info(
            "RepositoryManager running in real Databricks workspace mode"
        )

        logger.info(
            "Workspace root: %s",
            configured_root,
        )

        # -------------------------------------------------------------
        # Authenticate / initialize workspace client.
        #
        # The client itself decides whether to use:
        #   - explicit token
        #   - notebook execution context
        #   - native Databricks SDK authentication
        # -------------------------------------------------------------

        access_token = self._get_source_value(
            "access_token",
            default=None,
        )

        self._workspace_client = DatabricksWorkspaceClient(
            workspace_url=workspace_url,
            access_token=access_token,
        )

        # -------------------------------------------------------------
        # Discover the workspace.
        #
        # This is discovery only. It is NOT migration scope.
        # -------------------------------------------------------------

        logger.info(
            "Discovering Databricks workspace recursively: %s",
            configured_root,
        )

        workspace_objects = self._workspace_client.list_recursive(
            configured_root
        )

        if not workspace_objects:
            raise RepositoryError(
                f"No workspace objects were discovered under "
                f"'{configured_root}'"
            )

        normalized_objects = self._index_workspace_objects(
            workspace_objects
        )

        self._workspace_objects = normalized_objects

        logger.info(
            "Discovered %d workspace object(s)",
            len(normalized_objects),
        )

        # -------------------------------------------------------------
        # Build complete notebook inventory.
        #
        # These notebooks are known to exist in source workspace.
        # They are NOT automatically migrated.
        # -------------------------------------------------------------

        notebook_objects = [
            obj
            for obj in normalized_objects.values()
            if self._is_notebook_object(obj)
        ]

        self._known_notebook_paths = sorted(
            {
                self._relative_workspace_path(
                    obj.path,
                    configured_root,
                )
                for obj in notebook_objects
            }
        )

        logger.info(
            "Discovered %d source notebook(s)",
            len(self._known_notebook_paths),
        )

        # -------------------------------------------------------------
        # Resolve explicit migration scope.
        # -------------------------------------------------------------

        requested_paths = self._load_requested_notebook_list()

        if not requested_paths:
            raise RepositoryError(
                "No migration notebooks were provided. "
                "Set migration.notebook_list or provide "
                "migration.notebook_list_file."
            )

        self._selected_notebook_paths = (
            self._resolve_selected_workspace_notebooks(
                requested_paths=requested_paths,
                workspace_root=configured_root,
                workspace_objects=normalized_objects,
            )
        )

        if not self._selected_notebook_paths:
            raise RepositoryError(
                "The migration notebook list was provided, but no "
                "selected notebooks could be resolved in the source "
                "Databricks workspace."
            )

        logger.info(
            "Selected %d notebook(s) for migration",
            len(self._selected_notebook_paths),
        )

        # -------------------------------------------------------------
        # Export only selected notebooks.
        #
        # IMPORTANT:
        # Do not create output/_staging and do not clone the complete
        # repository.
        # -------------------------------------------------------------

        selected_objects = []

        for selected_path in self._selected_notebook_paths:

            object_key = self._normalize_workspace_path(
                selected_path
            )

            obj = normalized_objects.get(object_key)

            if obj is None:
                raise RepositoryError(
                    "Selected notebook disappeared from workspace "
                    f"inventory: '{selected_path}'"
                )

            selected_objects.append(obj)

        export_root = self._create_workspace_selection_temp_dir()

        exported_notebooks = self._export_selected_notebooks(
            selected_objects=selected_objects,
            export_root=export_root,
            workspace_root=configured_root,
        )

        if not exported_notebooks:
            raise RepositoryError(
                "Migration scope contains notebooks, but none could "
                "be exported from the source workspace."
            )

        # -------------------------------------------------------------
        # Build repository inventory.
        # -------------------------------------------------------------

        inventory = RepositoryInventory(
            source_root=configured_root,
            staged_path="",
            notebooks=exported_notebooks,
            known_notebook_paths=self._known_notebook_paths,
        )

        # Store useful runtime metadata for downstream components.
        self._set_context_metadata(
            "repository_manager.workspace_mode",
            True,
        )

        self._set_context_metadata(
            "repository_manager.workspace_root",
            configured_root,
        )

        self._set_context_metadata(
            "repository_manager.selected_notebook_paths",
            list(self._selected_notebook_paths),
        )

        self._set_context_metadata(
            "repository_manager.known_notebook_paths",
            list(self._known_notebook_paths),
        )

        self._set_context_metadata(
            "repository_manager.workspace_objects",
            normalized_objects,
        )

        self._set_context_metadata(
            "repository_manager.selected_export_root",
            export_root,
        )

        logger.info(
            "Workspace preparation completed successfully: "
            "%d notebook(s) exported for migration",
            len(exported_notebooks),
        )

        return inventory

    # =================================================================
    # Workspace discovery helpers
    # =================================================================

    def _index_workspace_objects(
        self,
        objects: Sequence[WorkspaceObject],
    ) -> Dict[str, WorkspaceObject]:
        """
        Index workspace objects using normalized workspace paths.
        """

        result: Dict[str, WorkspaceObject] = {}

        for obj in objects:

            if not obj.path:
                continue

            normalized = self._normalize_workspace_path(
                obj.path
            )

            result[normalized] = obj

        return result

    @staticmethod
    def _normalize_workspace_path(path: str) -> str:
        """
        Normalize Databricks workspace paths.

        Handles:
            /Workspace/Users/...
            /PFL/Delta-Lake/...
            trailing slashes
            Windows separators
            case differences

        Extensions are intentionally NOT removed here because this
        helper is used for actual workspace objects as well.

        Extension-insensitive comparison is handled separately.
        """

        value = str(path or "").strip()

        value = value.replace("\\", "/")

        value = "/" + value.strip("/")

        return value.lower()

    @classmethod
    def _workspace_path_without_extension(
        cls,
        path: str,
    ) -> str:
        """
        Return normalized workspace path without a notebook extension.

        Databricks workspace notebook paths are normally extensionless,
        while exported source files may use .py/.sql/.scala.
        """

        normalized = cls._normalize_workspace_path(path)

        suffix = Path(normalized).suffix.lower()

        if suffix in cls.NOTEBOOK_EXTENSIONS:
            normalized = normalized[: -len(suffix)]

        return normalized

    @classmethod
    def _workspace_paths_equivalent(
        cls,
        left: str,
        right: str,
    ) -> bool:
        """
        Determine whether two workspace paths refer to the same
        notebook, accounting for notebook extensions.
        """

        return (
            cls._workspace_path_without_extension(left)
            == cls._workspace_path_without_extension(right)
        )

    def _relative_workspace_path(
        self,
        object_path: str,
        workspace_root: str,
    ) -> str:
        """
        Convert an absolute workspace object path to a path relative
        to the configured workspace root.

        Example:

            root:
            /Workspace/Users/user/repo

            object:
            /Workspace/Users/user/repo/PFL/a.py

            result:
            PFL/a.py
        """

        object_norm = self._normalize_workspace_path(
            object_path
        )

        root_norm = self._normalize_workspace_path(
            workspace_root
        )

        if object_norm == root_norm:
            return ""

        prefix = root_norm.rstrip("/") + "/"

        if object_norm.startswith(prefix):
            return object_norm[len(prefix) :]

        # If the object is outside configured root, preserve the
        # normalized path rather than inventing a relative path.
        return object_norm.strip("/")

    def _resolve_requested_workspace_path(
        self,
        requested_path: str,
        workspace_root: str,
    ) -> str:
        """
        Convert a user-provided migration-list path into an absolute
        Databricks workspace path.

        Supported examples:

            /PFL/Delta-Lake/notebook

            PFL/Delta-Lake/notebook

            /Workspace/Users/user/repo/PFL/Delta-Lake/notebook

            /PFL/Delta-Lake/notebook.py
        """

        value = str(requested_path or "").strip()

        if not value:
            return ""

        value = value.replace("\\", "/")

        # -------------------------------------------------------------
        # Full workspace path.
        # -------------------------------------------------------------

        if value.lower().startswith("/workspace/"):
            return self._normalize_workspace_path(
                value
            )

        # -------------------------------------------------------------
        # Relative path.
        #
        # /PFL/... is interpreted relative to configured root unless
        # configured root itself is "/" .
        # -------------------------------------------------------------

        value = value.strip("/")

        root = self._normalize_workspace_path(
            workspace_root
        )

        if root == "/":
            return "/" + value.lower()

        return (
            root.rstrip("/")
            + "/"
            + value.lower()
        )

    # =================================================================
    # Migration-list loading
    # =================================================================

    def _load_requested_notebook_list(self) -> List[str]:
        """
        Load migration notebook list.

        Priority:

        1. migration.notebook_list
        2. migration.notebook_list_file

        Inline list is authoritative when non-empty.
        """

        migration_cfg = self._get_migration_config()

        inline_list = migration_cfg.get(
            "notebook_list",
            [],
        )

        if inline_list:
            if not isinstance(inline_list, (list, tuple)):
                raise RepositoryError(
                    "migration.notebook_list must be a list"
                )

            values = [
                str(item).strip()
                for item in inline_list
                if str(item).strip()
            ]

            logger.info(
                "Using migration.notebook_list with %d notebook(s)",
                len(values),
            )

            return values

        list_file = str(
            migration_cfg.get(
                "notebook_list_file",
                "",
            )
            or ""
        ).strip()

        if not list_file:
            return []

        logger.info(
            "Using migration notebook list file: %s",
            list_file,
        )

        return self._read_notebook_list_file(
            list_file
        )

    def _read_notebook_list_file(
        self,
        path: str,
    ) -> List[str]:
        """
        Read notebook paths from CSV/TXT/XLSX/XLSM.

        CSV:
            Uses migration.notebook_path_column when present.

        TXT:
            One notebook path per line.

        XLSX/XLSM:
            Uses openpyxl and migration.notebook_path_column.
        """

        file_path = Path(path)

        if not file_path.exists():
            raise RepositoryError(
                f"Migration notebook list file does not exist: "
                f"{path}"
            )

        suffix = file_path.suffix.lower()

        if suffix in {".txt", ".list"}:
            return self._read_text_notebook_list(
                file_path
            )

        if suffix == ".csv":
            return self._read_csv_notebook_list(
                file_path
            )

        if suffix in {".xlsx", ".xlsm"}:
            return self._read_excel_notebook_list(
                file_path
            )

        raise RepositoryError(
            f"Unsupported migration notebook list format: "
            f"'{suffix}'. Supported formats are TXT, CSV, XLSX and XLSM."
        )

    @staticmethod
    def _read_text_notebook_list(
        path: Path,
    ) -> List[str]:
        values: List[str] = []

        with path.open(
            "r",
            encoding="utf-8-sig",
        ) as handle:

            for line in handle:
                value = line.strip()

                if value:
                    values.append(value)

        return values

    def _read_csv_notebook_list(
        self,
        path: Path,
    ) -> List[str]:
        migration_cfg = self._get_migration_config()

        configured_column = str(
            migration_cfg.get(
                "notebook_path_column",
                "Notebook Path",
            )
            or "Notebook Path"
        ).strip()

        values: List[str] = []

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:

            reader = csv.DictReader(handle)

            if not reader.fieldnames:
                raise RepositoryError(
                    f"CSV notebook list has no header: {path}"
                )

            actual_column = self._find_column(
                reader.fieldnames,
                configured_column,
            )

            if actual_column is None:
                raise RepositoryError(
                    f"Column '{configured_column}' was not found "
                    f"in migration notebook list CSV. "
                    f"Available columns: {reader.fieldnames}"
                )

            for row in reader:
                value = str(
                    row.get(actual_column, "")
                    or ""
                ).strip()

                if value:
                    values.append(value)

        return values

    def _read_excel_notebook_list(
        self,
        path: Path,
    ) -> List[str]:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise RepositoryError(
                "openpyxl is required to read XLSX/XLSM migration "
                "notebook lists."
            ) from exc

        migration_cfg = self._get_migration_config()

        configured_column = str(
            migration_cfg.get(
                "notebook_path_column",
                "Notebook Path",
            )
            or "Notebook Path"
        ).strip()

        workbook = load_workbook(
            filename=path,
            read_only=True,
            data_only=True,
        )

        try:
            worksheet = workbook.active

            rows = worksheet.iter_rows(
                values_only=True
            )

            try:
                headers = next(rows)
            except StopIteration:
                return []

            header_names = [
                str(value or "").strip()
                for value in headers
            ]

            column_index = None

            for index, header in enumerate(header_names):
                if header.lower() == configured_column.lower():
                    column_index = index
                    break

            if column_index is None:
                raise RepositoryError(
                    f"Column '{configured_column}' was not found "
                    f"in migration notebook list Excel file. "
                    f"Available columns: {header_names}"
                )

            values: List[str] = []

            for row in rows:

                if column_index >= len(row):
                    continue

                value = str(
                    row[column_index] or ""
                ).strip()

                if value:
                    values.append(value)

            return values

        finally:
            workbook.close()

    @staticmethod
    def _find_column(
        columns: Iterable[str],
        requested: str,
    ) -> Optional[str]:
        requested_lower = str(
            requested or ""
        ).strip().lower()

        for column in columns:
            if str(column).strip().lower() == requested_lower:
                return column

        return None

    # =================================================================
    # Migration selection
    # =================================================================

    def _resolve_selected_workspace_notebooks(
        self,
        requested_paths: Sequence[str],
        workspace_root: str,
        workspace_objects: Dict[str, WorkspaceObject],
    ) -> List[str]:
        """
        Resolve user-requested notebook paths against discovered
        workspace objects.

        No dependency is automatically added.

        If a requested notebook is missing, fail the repository stage
        rather than silently processing zero notebooks.
        """

        selected: List[str] = []

        missing: List[str] = []

        for requested in requested_paths:

            absolute_requested = (
                self._resolve_requested_workspace_path(
                    requested_path=requested,
                    workspace_root=workspace_root,
                )
            )

            if not absolute_requested:
                continue

            matched_object = self._find_equivalent_workspace_object(
                absolute_requested,
                workspace_objects,
            )

            if matched_object is None:
                missing.append(requested)
                continue

            selected_path = matched_object.path

            if selected_path not in selected:
                selected.append(selected_path)

        if missing:
            logger.error(
                "%d requested notebook(s) were not found in source "
                "Databricks workspace:",
                len(missing),
            )

            for path in missing:
                logger.error(
                    "  Missing migration notebook: %s",
                    path,
                )

            raise RepositoryError(
                "One or more notebooks in migration.notebook_list "
                "were not found in the source Databricks workspace. "
                f"Missing: {missing}"
            )

        return selected

    def _find_equivalent_workspace_object(
        self,
        requested_path: str,
        workspace_objects: Dict[str, WorkspaceObject],
    ) -> Optional[WorkspaceObject]:
        """
        Find a workspace object using extension-insensitive path
        comparison.

        This is important because:

            Databricks:
                /PFL/Delta-Lake/notebook

            Exported source:
                /PFL/Delta-Lake/notebook.py

        represent the same notebook.
        """

        requested_normalized = (
            self._workspace_path_without_extension(
                requested_path
            )
        )

        # Fast path.
        direct = workspace_objects.get(
            self._normalize_workspace_path(
                requested_path
            )
        )

        if direct is not None:
            return direct

        # Extension-insensitive comparison.
        for object_path, obj in workspace_objects.items():

            normalized_object = (
                self._workspace_path_without_extension(
                    object_path
                )
            )

            if normalized_object == requested_normalized:
                return obj

        return None

    # =================================================================
    # Workspace export
    # =================================================================

    def _create_workspace_selection_temp_dir(self) -> str:
        """
        Create a process-local temporary directory.

        This directory is NOT:
            output/_staging
            Git working tree
            workspace deployment directory
        """

        path = tempfile.mkdtemp(
            prefix="ucmp_workspace_selected_"
        )

        self._temporary_paths.append(path)

        return path

    def _export_selected_notebooks(
        self,
        selected_objects: Sequence[WorkspaceObject],
        export_root: str,
        workspace_root: str,
    ) -> List[NotebookMetadata]:
        """
        Export only selected workspace notebooks.

        The Databricks workspace client returns notebook source.
        The source is written to a temporary local directory so the
        existing parser/replacement pipeline can operate on files.
        """

        if self._workspace_client is None:
            raise RepositoryError(
                "Databricks workspace client is not initialized."
            )

        notebooks: List[NotebookMetadata] = []

        for workspace_object in selected_objects:

            relative_path = self._relative_workspace_path(
                workspace_object.path,
                workspace_root,
            )

            if not relative_path:
                raise RepositoryError(
                    "Selected workspace object resolved to the "
                    "workspace root instead of a notebook: "
                    f"{workspace_object.path}"
                )

            local_relative_path = self._workspace_object_to_local_path(
                workspace_object,
                relative_path,
            )

            destination = (
                Path(export_root)
                / local_relative_path
            )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            try:
                source_text = self._workspace_client.export_source(
                    workspace_object.path
                )
            except Exception as exc:
                raise RepositoryError(
                    "Failed to export selected notebook from "
                    f"Databricks workspace: "
                    f"{workspace_object.path}: {exc}"
                ) from exc

            try:
                destination.write_text(
                    source_text,
                    encoding="utf-8",
                )
            except Exception as exc:
                raise RepositoryError(
                    f"Failed to write exported notebook "
                    f"'{destination}': {exc}"
                ) from exc

            metadata = NotebookMetadata(
                relative_path=local_relative_path,
                absolute_path=str(destination),
                language=(
                    workspace_object.language
                    or self._infer_language_from_path(
                        workspace_object.path
                    )
                ),
                size=len(source_text.encode("utf-8")),
            )

            notebooks.append(metadata)

            logger.info(
                "Selected notebook exported: %s -> %s",
                workspace_object.path,
                destination,
            )

        return notebooks

    @classmethod
    def _workspace_object_to_local_path(
        cls,
        workspace_object: WorkspaceObject,
        relative_path: str,
    ) -> str:
        """
        Convert a Databricks workspace notebook into a local source
        filename.

        Databricks notebook:
            /PFL/Delta-Lake/notebook

        Python notebook:
            PFL/Delta-Lake/notebook.py
        """

        relative = str(
            relative_path or ""
        ).replace("\\", "/").strip("/")

        suffix = Path(relative).suffix.lower()

        if suffix in cls.NOTEBOOK_EXTENSIONS:
            return relative

        language = str(
            workspace_object.language
            or ""
        ).upper()

        language_to_extension = {
            "PYTHON": ".py",
            "SQL": ".sql",
            "SCALA": ".scala",
            "R": ".r",
        }

        extension = language_to_extension.get(
            language,
            ".py",
        )

        return relative + extension

    @classmethod
    def _infer_language_from_path(
        cls,
        path: str,
    ) -> str:
        suffix = Path(
            str(path or "")
        ).suffix.lower()

        mapping = {
            ".py": "PYTHON",
            ".sql": "SQL",
            ".scala": "SCALA",
            ".r": "R",
        }

        return mapping.get(
            suffix,
            "PYTHON",
        )

    @classmethod
    def _is_notebook_object(
        cls,
        obj: WorkspaceObject,
    ) -> bool:
        """
        Determine whether a workspace object is a notebook.

        Databricks API generally returns object_type=NOTEBOOK.

        FILE is accepted only when its extension clearly represents
        a notebook source file.
        """

        object_type = str(
            obj.object_type or ""
        ).upper()

        if object_type == "NOTEBOOK":
            return True

        if object_type == "FILE":
            suffix = Path(
                str(obj.path or "")
            ).suffix.lower()

            return suffix in cls.NOTEBOOK_EXTENSIONS

        return False

    # =================================================================
    # Local repository mode
    # =================================================================

    def _run_local_repository_mode(
        self,
    ) -> RepositoryInventory:
        """
        Preserve legacy local repository behavior.

        This mode is used for:
            - local repositories
            - Git clones
            - demo repositories
            - existing UCMP local-repo workflows

        The workspace-specific selected-notebook behavior is NOT
        applied here unless the existing local pipeline explicitly
        provides it.
        """

        source = self.config.source

        repo_path = self._get_source_value(
            "repo_path",
            default="",
        )

        if not repo_path:
            raise RepositoryError(
                "source.repo_path is required when "
                "source.source_mode is not 'workspace'"
            )

        source_path = Path(
            os.path.expanduser(
                str(repo_path)
            )
        )

        if not source_path.exists():
            raise RepositoryError(
                f"Source repository path does not exist: "
                f"{source_path}"
            )

        if not source_path.is_dir():
            raise RepositoryError(
                f"Source repository path is not a directory: "
                f"{source_path}"
            )

        logger.info(
            "RepositoryManager running in local repository mode"
        )

        logger.info(
            "Source repository: %s",
            source_path,
        )

        # -------------------------------------------------------------
        # Do NOT impose Bronze/Silver/Gold/Common/Jobs structure.
        #
        # The real PFL repository is not required to follow that
        # artificial demo layout.
        # -------------------------------------------------------------

        inventory = self._build_local_inventory(
            source_path
        )

        self._set_context_metadata(
            "repository_manager.workspace_mode",
            False,
        )

        self._set_context_metadata(
            "repository_manager.selected_notebook_paths",
            [],
        )

        self._set_context_metadata(
            "repository_manager.known_notebook_paths",
            [
                notebook.relative_path
                for notebook in inventory.notebooks
            ],
        )

        logger.info(
            "Local repository preparation completed: "
            "%d notebook(s) discovered",
            len(inventory.notebooks),
        )

        return inventory

    def _build_local_inventory(
        self,
        source_path: Path,
    ) -> RepositoryInventory:
        """
        Build an inventory from an existing local repository.
        """

        notebooks: List[NotebookMetadata] = []

        for file_path in source_path.rglob("*"):

            if not file_path.is_file():
                continue

            if self._is_ignored_path(
                file_path,
                source_path,
            ):
                continue

            if file_path.suffix.lower() not in (
                self.NOTEBOOK_EXTENSIONS
            ):
                continue

            relative_path = str(
                file_path.relative_to(
                    source_path
                )
            ).replace("\\", "/")

            try:
                size = file_path.stat().st_size
            except OSError:
                size = None

            notebooks.append(
                NotebookMetadata(
                    relative_path=relative_path,
                    absolute_path=str(file_path),
                    language=self._infer_language_from_path(
                        relative_path
                    ),
                    size=size,
                )
            )

        notebooks.sort(
            key=lambda item: item.relative_path.lower()
        )

        return RepositoryInventory(
            source_root=str(source_path),
            staged_path=str(source_path),
            notebooks=notebooks,
            known_notebook_paths=[
                notebook.relative_path
                for notebook in notebooks
            ],
        )

    @staticmethod
    def _is_ignored_path(
        path: Path,
        root: Path,
    ) -> bool:
        """
        Ignore common repository metadata/build directories.
        """

        try:
            relative_parts = {
                part.lower()
                for part in path.relative_to(root).parts
            }
        except ValueError:
            relative_parts = {
                part.lower()
                for part in path.parts
            }

        ignored = {
            ".git",
            ".idea",
            ".vscode",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
        }

        return bool(
            relative_parts.intersection(ignored)
        )

    # =================================================================
    # Configuration helpers
    # =================================================================

    def _get_migration_config(self) -> Dict:
        """
        Return migration configuration as a plain dictionary.
        """

        migration = getattr(
            self.config,
            "migration",
            None,
        )

        if migration is not None:

            if hasattr(
                migration,
                "__dict__",
            ):
                return dict(
                    migration.__dict__
                )

            if isinstance(
                migration,
                dict,
            ):
                return migration

        # Fallback for configuration objects that do not expose a
        # migration dataclass yet.
        config_dict = getattr(
            self.config,
            "__dict__",
            {},
        )

        value = config_dict.get(
            "migration",
            {},
        )

        if isinstance(value, dict):
            return value

        if hasattr(
            value,
            "__dict__",
        ):
            return dict(
                value.__dict__
            )

        return {}

    def _get_source_value(
        self,
        key: str,
        default=None,
    ):
        """
        Read a source configuration value while supporting both
        dataclass and dictionary configurations.
        """

        source = getattr(
            self.config,
            "source",
            None,
        )

        if source is not None:

            value = getattr(
                source,
                key,
                None,
            )

            if value is not None:
                return value

            if isinstance(
                source,
                dict,
            ):
                return source.get(
                    key,
                    default,
                )

        return self._get_config_value(
            "source",
            key,
            default,
        )

    def _get_config_value(
        self,
        section: str,
        key: str,
        default=None,
    ):
        """
        Generic configuration fallback.
        """

        config_dict = getattr(
            self.config,
            "__dict__",
            {},
        )

        section_value = config_dict.get(
            section
        )

        if isinstance(
            section_value,
            dict,
        ):
            return section_value.get(
                key,
                default,
            )

        if hasattr(
            section_value,
            key,
        ):
            return getattr(
                section_value,
                key,
            )

        return default

    # =================================================================
    # Context metadata
    # =================================================================

    def _set_context_metadata(
        self,
        key: str,
        value,
    ) -> None:
        """
        Store runtime metadata in PipelineContext when available.

        The method is intentionally defensive because older UCMP
        PipelineContext implementations may expose different metadata
        containers.
        """

        if self.context is None:
            return

        # -------------------------------------------------------------
        # Preferred metadata dictionary.
        # -------------------------------------------------------------

        metadata = getattr(
            self.context,
            "metadata",
            None,
        )

        if isinstance(
            metadata,
            dict,
        ):
            metadata[key] = value
            return

        # -------------------------------------------------------------
        # Runtime metadata dictionary.
        # -------------------------------------------------------------

        runtime_metadata = getattr(
            self.context,
            "runtime_metadata",
            None,
        )

        if isinstance(
            runtime_metadata,
            dict,
        ):
            runtime_metadata[key] = value
            return

        # -------------------------------------------------------------
        # Create metadata dictionary when possible.
        # -------------------------------------------------------------

        try:
            setattr(
                self.context,
                "metadata",
                {
                    key: value,
                },
            )
        except Exception:
            logger.debug(
                "Unable to store repository metadata '%s'",
                key,
                exc_info=True,
            )

    # =================================================================
    # Cleanup
    # =================================================================

    def cleanup(self) -> None:
        """
        Remove process-local temporary workspace exports.
        """

        for path in list(
            self._temporary_paths
        ):

            try:
                shutil.rmtree(
                    path,
                    ignore_errors=True,
                )
            except Exception:
                logger.debug(
                    "Failed to cleanup temporary repository path: %s",
                    path,
                    exc_info=True,
                )

        self._temporary_paths.clear()

    def __del__(self):
        """
        Best-effort cleanup.

        Explicit cleanup is preferred.
        """

        try:
            self.cleanup()
        except Exception:
            pass
