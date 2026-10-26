"""Targeted Azure->AWS notebook migration analysis.

This module adds the user-driven migration behavior on top of the existing
UCMP findings. It deliberately does not replace the existing parsers/rules.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


ABFSS_RE = re.compile(
    r"abfss://(?P<container>[A-Za-z0-9_-]+|\{[A-Za-z_][A-Za-z0-9_]*\})@"
    r"(?P<account>[A-Za-z0-9_.-]+|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\{[A-Za-z_][A-Za-z0-9_]*\})"
    r"\.dfs\.core\.windows\.net"
    r"(?:/(?P<path>[^\s\"')]+))?"
)


RUN_RE = re.compile(
    r"(?m)^"
    r"(?P<prefix>\s*(?:#\s*MAGIC\s*)?%run\s+)"
    r"(?:"
    r"(?P<quote>[\"'])(?P<qpath>[^\"']+)(?P=quote)"
    r"|"
    r"(?P<upath>[^\s\"']+)"
    r")"
)
ANY_RUN_LINE_RE = re.compile(
    r"(?m)^(?P<line>\s*(?:#\s*MAGIC\s*)?%run\b.*)$"
)

ORPHAN_RUN_LINE_RE = re.compile(
    r"^\s*(?:#\s*MAGIC\s*)?%run\s*$"
)

MAGIC_CONTINUATION_RE = re.compile(
    r"^\s*#\s*MAGIC\s+(?P<value>.+?)\s*$"
)

CONFIG_IDENTIFIER_RENAMES = {
    "output_container_path": "output_bucket_name",
}


DYNAMIC_RUN_RE = re.compile(
    r"(?P<prefix>\s*(?:#\s*MAGIC\s*)?%run\s+)(?P<quote>[\"']?)"
    r"(?P<dynamic>\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)"
    r"(?P<path>/[A-Za-z0-9_. -]+(?:/[A-Za-z0-9_. -]+)*)"
    r"(?P=quote)"
)


VAR_PATH_RE = re.compile(
    r"^(?P<indent>\s*)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"(?P<quote>[\"'])(?P<path>/workspace/[^\"']+)(?P=quote)\s*$",
    re.IGNORECASE,
)


ASSIGN_RE = re.compile(
    r"^(?P<indent>\s*)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"dbutils\.widgets\.get\(\s*[\"'](?P<widget>[^\"']+)[\"']\s*\)\s*$"
)


NOTEBOOK_RUN_RE = re.compile(
    r"dbutils\.notebook\.run\s*\(\s*"
    r"(?P<quote>[\"'])"
    r"(?P<path>/Workspace/[^\"']+)"
    r"(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class MigrationEdit:
    notebook: str
    edit_type: str
    original_value: str
    resolved_value: str
    line_number: int
    requires_manual_review: bool = False
    notes: str = ""
    construct_type: str = ""

    def to_dict(self) -> dict:
        return {
            "notebook": self.notebook,
            "edit_type": self.edit_type,
            "original_value": self.original_value,
            "resolved_value": self.resolved_value,
            "line_number": self.line_number,
            "requires_manual_review": self.requires_manual_review,
            "notes": self.notes,
            "construct_type": self.construct_type,
        }


@dataclass
class NotebookMigrationAnalysis:
    notebook: str
    edits: List[MigrationEdit] = field(default_factory=list)
    review_items: List[dict] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.edits)

    @property
    def requires_review(self) -> bool:
        return any(e.requires_manual_review for e in self.edits) or bool(self.review_items)

    def to_dict(self) -> dict:
        return {
            "notebook": self.notebook,
            "changed": self.changed,
            "requires_review": self.requires_review,
            "edits": [e.to_dict() for e in self.edits],
            "review_items": self.review_items,
        }


class MigrationAnalyzer:
    """Analyze only the migration-specific transformations agreed for v1."""

    def __init__(
        self,
        container_bucket_mapping: Optional[Dict[str, str]] = None,
        workspace_root: str = "${WORKSPACE_ROOT}",
        referred_notebook_path_root: str = "${TARGET_WORKSPACE_ROOT}",
        source_repo_path: str = "",
        bucket_variable: str = "bucket_name",
    ):
        self.mapping = {
            str(k).lower(): str(v)
            for k, v in (container_bucket_mapping or {}).items()
        }
        self.workspace_root = workspace_root or "${WORKSPACE_ROOT}"
        self.referred_notebook_path_root = (
            referred_notebook_path_root or "${TARGET_WORKSPACE_ROOT}"
        ).rstrip("/")
        self.source_repo_path = str(source_repo_path or "").strip().rstrip("/")
        self.bucket_variable = bucket_variable or "bucket_name"

    def analyze(self, notebook: str, text: str) -> NotebookMigrationAnalysis:
        result = NotebookMigrationAnalysis(notebook=notebook)
        for i, line in enumerate(text.splitlines(), 1):
            if "%run" in line:
                logger.debug("DEBUG %%run candidate line %s: %r", i, line)

        assignments = self._widget_assignments(text)
        bucket_config = (
            f'{self.bucket_variable} = dbutils.widgets.get("{self.bucket_variable}")'
        )
        env_variable = "env"
        env_config = 'env = os.getenv("env")'

        # ------------------------------------------------------------
        # ABFSS storage paths
        # ------------------------------------------------------------
        for line_no, line in enumerate(text.splitlines(), 1):
            for match in ABFSS_RE.finditer(line):
                container = match.group("container")
                account = match.group("account")
                path = match.group("path") or ""

                container_var = self._placeholder_name(container)
                account_var = self._placeholder_name(account)

                container_configured = bool(container_var and container_var in assignments)

                account_is_template = bool(
                    re.fullmatch(
                        r"\$?\{[A-Za-z_][A-Za-z0-9_]*\}",
                        account,
                    )
                )
                account_configured = bool(account_var and account_var in assignments) or account_is_template

                logger.debug(
                    "ABFSS config: container=%r account=%r container_var=%r "
                    "account_var=%r container_configured=%s account_is_template=%s "
                    "account_configured=%s assignments=%s",
                    container,
                    account,
                    container_var,
                    account_var,
                    container_configured,
                    account_is_template,
                    account_configured,
                    list(assignments.keys()),
                )

                mapping = None if container_configured else self.mapping.get(container.lower())

                review = False
                notes = []
                suffix = f"/{path}" if path else ""

                if container_configured and account_configured:
                    notes.append(
                        f"Source variables '{container_var}' and '{account_var}' "
                        "feed this ABFSS path."
                    )
                    replacement = f"s3://{{{self.bucket_variable}}}{suffix}"

                elif not container_configured and account_configured:
                    notes.append(
                        f"Source variable '{account_var}' feeds this ABFSS path; "
                        f"container '{container}' is hardcoded."
                    )
                    replacement = f"s3://{{{self.bucket_variable}}}{suffix}"

                elif not container_configured and not account_configured and mapping:
                    replacement = f"s3://{mapping}{suffix}"
                    notes.append(
                        f"Container-to-bucket mapping used: {container} -> {mapping}."
                    )

                else:
                    replacement = f"s3://{container}{suffix}"
                    review = True
                    notes.append(
                        f"No container-to-bucket mapping found for '{container}'; "
                        "mechanical S3 placeholder applied and manual verification required."
                    )

                if (
                    container_configured or account_configured
                ) and bucket_config not in text:
                    notes.append(
                        f"Target bucket configuration added using "
                        f"'{self.bucket_variable}'."
                    )

                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="storage_path",
                        original_value=match.group(0),
                        resolved_value=replacement,
                        line_number=line_no,
                        requires_manual_review=review,
                        notes=" ".join(notes),
                        construct_type="abfss_path",
                    )
                )

                for var in (container_var, account_var):
                    if var and var in assignments:
                        original_line = assignments[var]["line"]
                        commented = self._comment_line(original_line)

                        result.edits.append(
                            MigrationEdit(
                                notebook=notebook,
                                edit_type="comment_source_config",
                                original_value=original_line,
                                resolved_value=commented,
                                line_number=assignments[var]["line_number"],
                                notes=(
                                    f"Commented because '{var}' is used by a "
                                    "migrated ABFSS path."
                                ),
                                construct_type="source_storage_config",
                            )
                        )

        result.edits = self._dedupe_edits(result.edits)

        if any(
            e.edit_type == "storage_path"
            and "Target bucket configuration added" in e.notes
            for e in result.edits
        ):
            insert_at = self._bucket_insert_location(result.edits, text)

            result.edits.append(
                MigrationEdit(
                    notebook=notebook,
                    edit_type="add_target_config",
                    original_value="",
                    resolved_value=bucket_config,
                    line_number=insert_at,
                    notes="Added target bucket configuration for migrated storage paths.",
                    construct_type="target_storage_config",
                )
            )
    

    # ------------------------------------------------------------
        # %run workspace paths
        #
        # Handles:
        #   %run /Workspace/...
        #   # MAGIC %run /Workspace/...
        #   %run "/Workspace/path with spaces"
        #   # MAGIC %run "../relative/path"
        #
        # Also flags malformed/orphan cases:
        #   # MAGIC %run
        #   # MAGIC %run 
        #
        # Also handles split Databricks magic:
        #   # MAGIC %run
        #   # MAGIC /Workspace/Some/Notebook
        # ------------------------------------------------------------

        matched_run_lines = set()

        # Pre-detect dynamic %run lines so normal RUN_RE does not incorrectly
        # classify ${workspace_root}/Notebook as unsupported.
        dynamic_run_lines = set()
        for dynamic_match in DYNAMIC_RUN_RE.finditer(text):
            dynamic_line_number = text.count("\n", 0, dynamic_match.start()) + 1
            dynamic_run_lines.add(dynamic_line_number)

        # Normal single-line %run handling.
        for match in RUN_RE.finditer(text):
            raw = match.group("qpath") or match.group("upath")
            path_group = "qpath" if match.group("qpath") is not None else "upath"
            line_number = text.count("\n", 0, match.start(path_group)) + 1

            # Dynamic %run is handled below.
            if line_number in dynamic_run_lines:
                continue

            matched_run_lines.add(line_number)

            if re.match(r"(?i)^/workspace/", raw):
                relative = re.sub(r"(?i)^/workspace/", "", raw)
                target = f"{self.workspace_root.rstrip('/')}/{relative}"

                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="workspace_run_path",
                        original_value=raw,
                        resolved_value=target,
                        line_number=line_number,
                        notes=(
                            "Converted hardcoded source workspace %run reference "
                            "to the configured target workspace root."
                        ),
                        construct_type="workspace_notebook_path",
                    )
                )

            elif raw.startswith("./") or raw.startswith("../"):
                result.review_items.append(
                    {
                        "notebook": notebook,
                        "line_number": line_number,
                        "construct_type": "workspace_notebook_path",
                        "original_value": raw,
                        "notes": (
                            "Relative %run dependency detected. Manual review required "
                            "unless source workspace location is available for normalization."
                        ),
                        "requires_manual_review": True,
                    }
                )

            else:
                result.review_items.append(
                    {
                        "notebook": notebook,
                        "line_number": line_number,
                        "construct_type": "workspace_notebook_path",
                        "original_value": raw,
                        "notes": (
                            "Unsupported %run path form detected. Manual review required."
                        ),
                        "requires_manual_review": True,
                    }
                )

        # Split Databricks magic handling.
        #
        # Example:
        #   # MAGIC %run
        #   # MAGIC /Workspace/Users/x/repo/Notebook
        lines = text.splitlines()

        for idx, line in enumerate(lines):
            line_number = idx + 1

            if line_number in matched_run_lines:
                continue

            if not ORPHAN_RUN_LINE_RE.match(line):
                continue

            if idx + 1 >= len(lines):
                continue

            next_line = lines[idx + 1]
            next_line_number = idx + 2

            next_match = MAGIC_CONTINUATION_RE.match(next_line)

            if next_match:
                raw_candidate = next_match.group("value").strip()
            else:
                raw_candidate = next_line.strip()

            # Strip matching quotes if present.
            if (
                len(raw_candidate) >= 2
                and raw_candidate[0] == raw_candidate[-1]
                and raw_candidate[0] in ("'", '"')
            ):
                raw_candidate = raw_candidate[1:-1]

            # Only treat the next MAGIC line as a %run path if it looks like one.
            if not (
                re.match(r"(?i)^/workspace/", raw_candidate)
                or raw_candidate.startswith("./")
                or raw_candidate.startswith("../")
                or raw_candidate.startswith("$")
            ):
                continue

            matched_run_lines.add(line_number)
            matched_run_lines.add(next_line_number)

            if re.match(r"(?i)^/workspace/", raw_candidate):
                relative = re.sub(r"(?i)^/workspace/", "", raw_candidate)
                target = f"{self.workspace_root.rstrip('/')}/{relative}"

                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="workspace_run_path",
                        original_value=raw_candidate,
                        resolved_value=target,
                        line_number=next_line_number,
                        notes=(
                            "Converted split Databricks magic %run workspace reference "
                            "to the configured target workspace root."
                        ),
                        construct_type="workspace_notebook_path",
                    )
                )

            elif raw_candidate.startswith("./") or raw_candidate.startswith("../"):
                result.review_items.append(
                    {
                        "notebook": notebook,
                        "line_number": next_line_number,
                        "construct_type": "workspace_notebook_path",
                        "original_value": raw_candidate,
                        "notes": (
                            "Relative split Databricks magic %run dependency detected. "
                            "Manual review required unless source workspace location is "
                            "available for normalization."
                        ),
                        "requires_manual_review": True,
                    }
                )

            else:
                result.review_items.append(
                    {
                        "notebook": notebook,
                        "line_number": next_line_number,
                        "construct_type": "workspace_notebook_path",
                        "original_value": raw_candidate,
                        "notes": (
                            "Unsupported split Databricks magic %run path form detected. "
                            "Manual review required."
                        ),
                        "requires_manual_review": True,
                    }
                )

        # Dynamic %run paths.
        #
        # Example:
        #   %run ${workspace_root}/Folder/Notebook
        #   # MAGIC %run ${workspace_root}/Folder/Notebook
        for line_no, line in enumerate(text.splitlines(), 1):
            match = DYNAMIC_RUN_RE.search(line)

            if not match:
                continue

            raw = match.group("dynamic") + match.group("path")

            if re.match(r"(?i)^/workspace/", raw):
                continue

            matched_run_lines.add(line_no)

            target = f"{self.workspace_root.rstrip('/')}{match.group('path')}"

            result.edits.append(
                MigrationEdit(
                    notebook=notebook,
                    edit_type="workspace_run_path",
                    original_value=raw,
                    resolved_value=target,
                    line_number=line_no,
                    notes=(
                        "Resolved dynamic workspace prefix while preserving the stable "
                        "notebook path suffix under the configured workspace root."
                    ),
                    construct_type="workspace_notebook_path",
                )
            )

        # Catch malformed or unsupported %run lines that were not parsed above.
        #
        # This prevents silent success for:
        #   # MAGIC %run
        #   # MAGIC %run 
        #   %run
        for match in ANY_RUN_LINE_RE.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1

            if line_number in matched_run_lines:
                continue

            line = match.group("line").strip()

            result.review_items.append(
                {
                    "notebook": notebook,
                    "line_number": line_number,
                    "construct_type": "workspace_notebook_path",
                    "original_value": line,
                    "notes": (
                        "A %run command was detected but could not be parsed as a "
                        "supported notebook path. Manual review required."
                    ),
                    "requires_manual_review": True,
                }
            )

        # ------------------------------------------------------------
        # dbutils.notebook.run() workspace paths
        # ------------------------------------------------------------
        for match in NOTEBOOK_RUN_RE.finditer(text):
            raw = match.group("path")
            relative = re.sub(r"(?i)^/workspace/", "", raw)
            target = f"{self.workspace_root.rstrip('/')}/{relative}"
            line_number = text.count("\n", 0, match.start("path")) + 1

            result.edits.append(
                MigrationEdit(
                    notebook=notebook,
                    edit_type="workspace_notebook_run_path",
                    original_value=raw,
                    resolved_value=target,
                    line_number=line_number,
                    notes=(
                        "Converted hardcoded source workspace notebook reference "
                        "to the configured target workspace root."
                    ),
                    construct_type="workspace_notebook_path",
                )
            )

        

        # ------------------------------------------------------------
        # Workspace paths stored in variables
        # ------------------------------------------------------------
        for line_no, line in enumerate(text.splitlines(), 1):
            match = VAR_PATH_RE.match(line)

            if not match:
                continue

            raw = match.group("path")
            relative = re.sub(r"(?i)^/workspace/", "", raw)
            target = f"{self.workspace_root.rstrip('/')}/{relative}"

            result.edits.append(
                MigrationEdit(
                    notebook=notebook,
                    edit_type="workspace_variable_path",
                    original_value=raw,
                    resolved_value=target,
                    line_number=line_no,
                    notes=(
                        f"Transformed workspace path stored in variable "
                        f"'{match.group('name')}'."
                    ),
                    construct_type="workspace_notebook_path",
                )
            )

        # ------------------------------------------------------------
        # Referred notebook/repository paths
        #
        # Rewrites source repo prefixes to target repo prefixes.
        # Example:
        #   /Workspace/pfl-repo-dbx-datalake/X
        # becomes:
        #   ${TARGET_WORKSPACE_ROOT}/pfl-repo-dbx-datalake/X
        # ------------------------------------------------------------
        repo_name = Path(self.source_repo_path).name if self.source_repo_path else ""

        if repo_name:
            source_prefixes = {
                f"/Workspace/{repo_name}/",
                f"{self.source_repo_path}/" if self.source_repo_path else "",
            }
            source_prefixes.discard("")

            target_prefix = f"{self.referred_notebook_path_root}/{repo_name}/"

            for line_no, line in enumerate(text.splitlines(), 1):
                for source_prefix in sorted(source_prefixes, key=len, reverse=True):
                    if source_prefix in line:
                        result.edits.append(
                            MigrationEdit(
                                notebook=notebook,
                                edit_type="referred_notebook_path",
                                original_value=source_prefix,
                                resolved_value=target_prefix,
                                line_number=line_no,
                                notes=(
                                    "Replaced the hardcoded source workspace repository "
                                    "prefix with the configured target workspace "
                                    "repository root."
                                ),
                                construct_type="workspace_notebook_path",
                            )
                        )
        # Add or normalize the environment declaration only when a generated
        # target path actually depends on {env}. Environment selection comes
        # from the process environment, not a Databricks widget.
        if any("{env}" in str(edit.resolved_value) for edit in result.edits):
            insert_at = self._env_insert_location(assignments, result.edits)
            env_widget = re.compile(
                r"^(?P<indent>\s*)env\s*=\s*dbutils\.widgets\.get\(\s*([\"'])env\2\s*\)\s*$"
            )
            env_os_declaration = re.compile(
                r"^\s*env\s*=\s*(?:os\.getenv\(|os\.environ\.get\()"
            )
            env_assignment = None
            for line_number, line in enumerate(text.splitlines(), 1):
                if env_widget.match(line):
                    env_assignment = (line_number, line)
                    break

            has_os_import = bool(re.search(r"(?m)^\s*(?:import\s+os\b|from\s+os\s+import\b)", text))
            has_env_os_declaration = any(
                env_os_declaration.match(line) for line in text.splitlines()
            )

            # `os.getenv` requires the os module. Insert its import separately
            # so the config cell stays valid and the declaration is idempotent.
            if not has_os_import:
                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="add_target_config",
                        original_value="",
                        resolved_value="import os",
                        line_number=insert_at,
                        notes="Added the os import required by environment lookup.",
                        construct_type="target_environment_config",
                    )
                )

            if env_assignment:
                line_number, original_line = env_assignment
                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="env_config_replace",
                        original_value=original_line,
                        resolved_value=env_config,
                        line_number=line_number,
                        notes="Replaced the env Databricks widget lookup with os.getenv.",
                        construct_type="target_environment_config",
                    )
                )
            elif has_env_os_declaration:
                existing_env_line = next(
                    line for line in text.splitlines() if env_os_declaration.match(line)
                )
                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="env_config_existing",
                        original_value=existing_env_line,
                        resolved_value=existing_env_line,
                        line_number=next(
                            i for i, line in enumerate(text.splitlines(), 1)
                            if env_os_declaration.match(line)
                        ),
                        notes="Environment declaration already uses os.getenv/os.environ.get.",
                        construct_type="target_environment_config",
                    )
                )
            else:
                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="add_target_config",
                        original_value="",
                        resolved_value=env_config,
                        line_number=insert_at,
                        notes="Added target environment configuration using os.getenv.",
                        construct_type="target_environment_config",
                    )
                )

        # ------------------------------------------------------------
        # Config identifier renames
        #
        # Azure/source naming:
        #   output_container_path
        #
        # AWS/target naming:
        #   output_bucket_name
        # ------------------------------------------------------------
        for old_name, new_name in CONFIG_IDENTIFIER_RENAMES.items():
            match = re.search(rf"\b{re.escape(old_name)}\b", text)

            if not match:
                continue

            line_number = text.count("\n", 0, match.start()) + 1

            result.edits.append(
                MigrationEdit(
                    notebook=notebook,
                    edit_type="config_identifier_rename",
                    original_value=old_name,
                    resolved_value=new_name,
                    line_number=line_number,
                    notes=(
                        f"Renamed source config identifier '{old_name}' "
                        f"to target config identifier '{new_name}'."
                    ),
                    construct_type="config_identifier",
                )
            )

        result.edits = self._dedupe_edits(result.edits)
        return result

    @staticmethod
    def _env_insert_location(
        assignments: Dict[str, dict],
        edits: List[MigrationEdit],
    ) -> int:
        """
        Insert env widget declaration after existing dbutils.widgets.get(...)
        assignments if present.

        Example target placement:

            config_id = dbutils.widgets.get('config_id')
            business_date = dbutils.widgets.get('business_date')
            raw_sa_name = dbutils.widgets.get('raw_sa_name')
            env = dbutils.widgets.get('env')
        """

        if assignments:
            return max(
                item["line_number"]
                for item in assignments.values()
            ) + 1

        workspace_lines = [
            e.line_number
            for e in edits
            if e.construct_type == "workspace_notebook_path"
        ]

        if workspace_lines:
            return max(1, min(workspace_lines) - 1)

        return 1
    

    @staticmethod
    def _placeholder_name(value: str) -> Optional[str]:
        if value.startswith("${") and value.endswith("}"):
            return value[2:-1]

        if value.startswith("{") and value.endswith("}"):
            return value[1:-1]

        return None

    @staticmethod
    def _widget_assignments(text: str) -> Dict[str, dict]:
        result = {}

        for line_number, line in enumerate(text.splitlines(), 1):
            match = ASSIGN_RE.match(line)

            if match:
                result[match.group("name")] = {
                    "line": line,
                    "line_number": line_number,
                }

        return result

    @staticmethod
    def _comment_line(line: str) -> str:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]

        return f"{indent}# UCMP SOURCE CONFIG COMMENTED: {stripped}"

    @staticmethod
    def _bucket_insert_location(edits: List[MigrationEdit], text: str) -> int:
        return min(
            (
                e.line_number
                for e in edits
                if e.edit_type == "storage_path"
            ),
            default=1,
        )

    @staticmethod
    def _dedupe_edits(edits: List[MigrationEdit]) -> List[MigrationEdit]:
        seen = set()
        output = []

        for edit in edits:
            key = (
                edit.edit_type,
                edit.original_value,
                edit.resolved_value,
                edit.line_number,
            )

            if key in seen:
                continue

            seen.add(key)
            output.append(edit)

        return output