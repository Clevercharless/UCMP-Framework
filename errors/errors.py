"""
replacement.replacement_engine
================================
`ReplacementEngine` is the ninth pipeline stage. It executes the
Transformation Plan (Module 8) against the staged notebook copies
(Module 4), producing the migrated AWS Databricks repository under the configured output mode:
`target.repo_path` for `separate` mode or `source.repo_path` for `in_place` mode.

Per the spec: "Business logic must remain untouched. Only
infrastructure-specific constructs should change." This is enforced
structurally, not by trust: the engine only ever performs exact-substring
`str.replace(original_value, resolved_value)` for operations whose
`action` is `replace` or `remove` (which erases the substring). Every
other operation type (`manual_review`, `no_change`, `unmatched`, and the
`keep_business_logic` marker itself) carries no `original_value` to
substitute, or is explicitly skipped -- so nothing outside a flagged
construct's exact text is ever modified.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Tuple

from common.exceptions import ReplacementError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from replacement.migration_banner import build_banner

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_APPLICABLE_ACTIONS = {"replace", "remove"}


class ReplacementEngine(PipelineStage):
    """Applies the Transformation Plan's operations to staged notebooks, writing the migrated repo."""

    name = "ReplacementEngine"

    def run(self, context: PipelineContext) -> PipelineContext:
        transformation_plan = context.get_artifact("transformation_plan")
        repository = context.get_artifact("repository")

        if not transformation_plan:
            raise ReplacementError(
                "ReplacementEngine requires context.artifacts['transformation_plan'] "
                "to be populated (run TransformationPlanner first)"
            )
        if not repository:
            raise ReplacementError(
                "ReplacementEngine requires context.artifacts['repository'] "
                "to be populated (run RepositoryManager first)"
            )
        if not context.config:
            raise ReplacementError("ReplacementEngine requires context.config")

        output_mode = str((context.config.get("output", {}) or {}).get("mode", "separate")).strip().lower()
        source_mode = str((context.config.get("source", {}) or {}).get("source_mode", "local_repo")).strip().lower()
        workspace_mode = output_mode == "in_place" and source_mode == "workspace"
        # Workspace mode is analyzed/transformed into a process-local preview only.
        # DeploymentEngine is the sole component allowed to write back to Databricks.
        # This prevents auto_deploy=False from modifying the workspace.
        if workspace_mode:
            import tempfile
            target_root = Path(tempfile.mkdtemp(prefix="ucmp_workspace_preview_"))
            context.metadata.workspace_preview_root = str(target_root)
        else:
            target_root = self._resolve_target_root(context)

        notebook_paths = {nb.relative_path: Path(nb.absolute_path) for nb in repository["notebooks"]}
        notebook_languages = {nb.relative_path: nb.language for nb in repository["notebooks"]}

        results: List[Dict] = []
        for notebook_plan in transformation_plan["notebook_plans"]:
            relative_path = notebook_plan["relative_path"]
            source_path = notebook_paths.get(relative_path)
            if source_path is None:
                raise ReplacementError(
                    f"Transformation plan references notebook '{relative_path}' which is "
                    f"not present in the repository inventory"
                )
            language = notebook_languages.get(relative_path, "python")
            result = self._apply_notebook_plan(
                relative_path, source_path, language, notebook_plan, target_root,
                workspace_client=None,
                workspace_target_root=None,
            )
            results.append(result)

        config_assets_copied = 0 if workspace_mode else self._copy_config_assets(repository, target_root)

        summary = self._summarize(
            results,
            config_assets_copied,
            target_root or self._resolve_workspace_target_root(context),
        )
        context.set_artifact("replacement_summary", summary)
        context.metadata["replacement_complete"] = True

        logger.info(
            "Replacement Engine wrote %d notebook(s) (%d operation(s) applied, "
            "%d notebook(s) flagged for review) + %d config asset(s) to %s",
            summary["notebooks_written"],
            summary["total_operations_applied"],
            summary["notebooks_with_manual_review"],
            summary["config_assets_copied"],
            target_root,
        )
        return context

    # -- internals --------------------------------------------------------

    def _resolve_target_root(self, context: PipelineContext) -> Path:
        output_cfg = context.config.get("output", {}) or {}
        mode = str(output_cfg.get("mode", "separate")).strip().lower()

        if mode == "in_place":
            source_cfg = context.config.get("source", {}) or {}
            configured = source_cfg.get("repo_path")
        else:
            configured = context.config["target"]["repo_path"]

        if not configured:
            raise ReplacementError(
                f"No repository path configured for output mode '{mode}'."
            )

        path = Path(str(configured))
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        return path.resolve()

    def _apply_notebook_plan(
        self,
        relative_path: str,
        source_path: Path,
        language: str,
        notebook_plan: Dict,
        target_root: Path | None,
        workspace_client=None,
        workspace_target_root: str | None = None,
    ) -> Dict:
        try:
            text = source_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            raise ReplacementError(f"Could not read staged notebook {source_path}: {exc}") from exc

        transformed_text, applied_count = self._apply_operations(text, notebook_plan["operations"])
        transformed_text, config_added = self._apply_target_config_additions(transformed_text, notebook_plan["operations"], language)
        applied_count += config_added

        manual_review_ops = [
            op for op in notebook_plan["operations"]
            if op["requires_manual_review"] and op["operation_type"] != "keep_business_logic"
        ]
        if applied_count > 0 or manual_review_ops:
            transformed_text = self._insert_banner(
                transformed_text, language, applied_count, manual_review_ops
            )

        if workspace_client is not None:
            workspace_path = self._workspace_notebook_path(workspace_target_root, relative_path)
            workspace_client.import_source(workspace_path, transformed_text, overwrite=True)
            output_path_value = workspace_path
        else:
            if target_root is None:
                raise ReplacementError("A local target root is required for non-workspace output")
            output_path = target_root / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(transformed_text, encoding="utf-8")
            output_path_value = str(output_path)

        return {
            "relative_path": relative_path,
            "output_path": output_path_value,
            "operations_applied": applied_count,
            "manual_review_count": len(manual_review_ops),
        }

    @staticmethod
    def _apply_operations(text: str, operations: List[Dict]) -> Tuple[str, int]:
        applied_count = 0
        for op in operations:
            if op["action"] not in _APPLICABLE_ACTIONS:
                continue  # manual_review / no_change / unmatched / keep -> leave untouched
            original_value = op.get("original_value")
            if not original_value or original_value not in text:
                continue

            replacement = op.get("resolved_value") or ""  # "remove" -> resolved_value is None
            text = text.replace(original_value, replacement)
            applied_count += 1
        return text, applied_count

    @staticmethod
    def _apply_target_config_additions(text: str, operations: List[Dict], language: str) -> Tuple[str, int]:
        additions = [op.get("resolved_value") for op in operations if op.get("action") == "add_config" and op.get("resolved_value")]
        if not additions:
            return text, 0
        unique = []
        for value in additions:
            if value not in unique and value not in text:
                unique.append(value)
        if not unique:
            return text, 0
        lines = text.splitlines()
        if not lines:
            return text, 0
        insert_index = 1 if lines[0].startswith(("# Databricks notebook source", "-- Databricks notebook source", "// Databricks notebook source")) else 0
        lines[insert_index:insert_index] = unique + [""]
        return "\n".join(lines), len(unique)

    @staticmethod
    def _insert_banner(text: str, language: str, applied_count: int, manual_review_ops: List[Dict]) -> str:
        lines = text.splitlines()
        if not lines:
            return text
        header, rest = lines[0], "\n".join(lines[1:])
        banner = build_banner(language, applied_count, manual_review_ops)
        return f"{header}\n\n{banner}\n{rest}"

    def _build_workspace_client(self, context: PipelineContext):
        from repository.databricks_workspace import DatabricksWorkspaceClient
        target_cfg = context.config.get("target", {}) or {}
        source_cfg = context.config.get("source", {}) or {}
        target_url = str(target_cfg.get("workspace_url", "") or "").strip()
        source_url = str(source_cfg.get("workspace_url", "") or "").strip()
        # If target URL is left at the framework's simulated default, use the
        # actual source/current workspace URL. This is useful when UCMP runs in
        # the same Databricks workspace it is migrating into.
        if not target_url or "simulated.cloud.databricks.com" in target_url:
            target_url = source_url
        return DatabricksWorkspaceClient(target_url or None)

    @staticmethod
    def _resolve_workspace_target_root(context: PipelineContext) -> str:
        target_cfg = context.config.get("target", {}) or {}
        configured = str(target_cfg.get("repo_path", "") or "").strip()
        if not configured:
            source_cfg = context.config.get("source", {}) or {}
            configured = str(source_cfg.get("repo_path", "") or "").strip()
        if not configured:
            raise ReplacementError("A target workspace repo_path is required for workspace in-place migration")
        return configured.rstrip("/") or "/"

    @staticmethod
    def _workspace_notebook_path(target_root: str, relative_path: str) -> str:
        # Workspace API notebook paths conventionally omit the local export
        # extension. The staged inventory uses .py/.sql/.scala so parser and
        # replacement logic can operate on normal source files.
        rel = str(relative_path).replace("\\", "/").lstrip("/")
        suffix = Path(rel).suffix.lower()
        if suffix in {".py", ".sql", ".scala"}:
            rel = rel[:-len(suffix)]
        return f"{target_root.rstrip('/')}/{rel}"

    def _copy_config_assets(self, repository: Dict, target_root: Path) -> int:
        count = 0
        for asset in repository.get("config_assets", []):
            source_path = Path(asset["absolute_path"])
            output_path = target_root / asset["relative_path"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # In-place mode points target_root at the source repository. The
            # config asset is already in the correct location, so do not copy
            # a file onto itself.
            if source_path.resolve() == output_path.resolve():
                count += 1
                continue
            shutil.copy2(source_path, output_path)
            count += 1
        return count

    @staticmethod
    def _summarize(results: List[Dict], config_assets_copied: int, target_root: Path) -> Dict:
        return {
            "target_repo_path": str(target_root),
            "notebooks_written": len(results),
            "total_operations_applied": sum(r["operations_applied"] for r in results),
            "notebooks_with_manual_review": sum(1 for r in results if r["manual_review_count"] > 0),
            "config_assets_copied": config_assets_copied,
            "notebook_results": results,
        }
