"""Targeted Azure->AWS notebook migration analysis.

This module adds the user-driven migration behavior on top of the existing
UCMP findings.  It deliberately does not replace the existing parsers/rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, List, Optional


ABFSS_RE = re.compile(
    r"abfss://(?P<container>[A-Za-z0-9_-]+|\{[A-Za-z_][A-Za-z0-9_]*\})@"
    r"(?P<account>[A-Za-z0-9_.-]+|\{[A-Za-z_][A-Za-z0-9_]*\})\.dfs\.core\.windows\.net/"
    r"(?P<path>[^\s\"')]+)"
)
RUN_RE = re.compile(r"(?P<prefix>%run\s+)(?P<quote>[\"']?)(?P<path>/workspace/[^\"'\s]+)(?P=quote)")
VAR_PATH_RE = re.compile(r"^(?P<indent>\s*)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<quote>[\"'])(?P<path>/workspace/[^\"']+)(?P=quote)\s*$")
ASSIGN_RE = re.compile(
    r"^(?P<indent>\s*)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"dbutils\.widgets\.get\(\s*[\"'](?P<widget>[^\"']+)[\"']\s*\)\s*$"
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

    def __init__(self, container_bucket_mapping: Optional[Dict[str, str]] = None,
                 workspace_root: str = "${WORKSPACE_ROOT}",
                 bucket_variable: str = "bucket"):
        self.mapping = {str(k).lower(): str(v) for k, v in (container_bucket_mapping or {}).items()}
        self.workspace_root = workspace_root or "${WORKSPACE_ROOT}"
        self.bucket_variable = bucket_variable or "bucket"

    def analyze(self, notebook: str, text: str) -> NotebookMigrationAnalysis:
        result = NotebookMigrationAnalysis(notebook=notebook)
        assignments = self._widget_assignments(text)
        bucket_config = f'{self.bucket_variable} = dbutils.widgets.get("{self.bucket_variable}")'

        for line_no, line in enumerate(text.splitlines(), 1):
            for match in ABFSS_RE.finditer(line):
                container = match.group("container")
                account = match.group("account")
                path = match.group("path")
                container_var = self._placeholder_name(container)
                account_var = self._placeholder_name(account)
                container_configured = container_var in assignments
                account_configured = account_var in assignments
                mapping = None if container_configured else self.mapping.get(container.lower())

                review = False
                notes = []
                if container_configured and account_configured:
                    notes.append(f"Source variables '{container_var}' and '{account_var}' feed this ABFSS path.")
                    replacement = f"s3://{{{self.bucket_variable}}}/{path}"
                elif not container_configured and account_configured:
                    notes.append(f"Source variable '{account_var}' feeds this ABFSS path; container '{container}' is hardcoded.")
                    replacement = f"s3://{{{self.bucket_variable}}}/{path}"
                elif not container_configured and not account_configured and mapping:
                    replacement = f"s3://{mapping}/{path}"
                    notes.append(f"Container-to-bucket mapping used: {container} -> {mapping}.")
                else:
                    mechanical_account = account_var and f"{{{account_var}}}" or account
                    replacement = f"s3://{container}@{mechanical_account}/{path}"
                    review = True
                    notes.append(f"No container-to-bucket mapping found for '{container}'; mechanical transformation applied and manual verification required.")

                # The output target uses a configurable bucket variable when the source path
                # contains any source configuration.  A single config assignment is inserted
                # once per notebook by _ensure_bucket_assignment below.
                if (container_configured or account_configured) and bucket_config not in text:
                    notes.append(f"Target bucket configuration added using '{self.bucket_variable}'.")

                result.edits.append(MigrationEdit(
                    notebook=notebook,
                    edit_type="storage_path",
                    original_value=match.group(0),
                    resolved_value=replacement,
                    line_number=line_no,
                    requires_manual_review=review,
                    notes=" ".join(notes),
                    construct_type="abfss_path",
                ))

                for var in (container_var, account_var):
                    if var and var in assignments:
                        original_line = assignments[var]["line"]
                        commented = self._comment_line(original_line)
                        result.edits.append(MigrationEdit(
                            notebook=notebook,
                            edit_type="comment_source_config",
                            original_value=original_line,
                            resolved_value=commented,
                            line_number=assignments[var]["line_number"],
                            notes=f"Commented because '{var}' is used by a migrated ABFSS path.",
                            construct_type="source_storage_config",
                        ))

        # Remove duplicate edits while preserving order.
        result.edits = self._dedupe_edits(result.edits)
        if any(e.edit_type == "storage_path" and ("Target bucket configuration added" in e.notes) for e in result.edits):
            insert_at = self._bucket_insert_location(result.edits, text)
            result.edits.append(MigrationEdit(
                notebook=notebook,
                edit_type="add_target_config",
                original_value="",
                resolved_value=bucket_config,
                line_number=insert_at,
                notes="Added target bucket configuration for migrated storage paths.",
                construct_type="target_storage_config",
            ))

        for line_no, line in enumerate(text.splitlines(), 1):
            for match in RUN_RE.finditer(line):
                raw = match.group("path")
                relative = raw[len("/workspace/"):]
                target = f"{self.workspace_root}/{relative}"
                result.edits.append(MigrationEdit(
                    notebook=notebook,
                    edit_type="workspace_run_path",
                    original_value=raw,
                    resolved_value=target,
                    line_number=line_no,
                    notes="Converted source workspace-root notebook reference to configurable target workspace root.",
                    construct_type="workspace_notebook_path",
                ))

        for line_no, line in enumerate(text.splitlines(), 1):
            match = VAR_PATH_RE.match(line)
            if match:
                raw = match.group("path")
                relative = raw[len("/workspace/"):]
                target = f"{self.workspace_root}/{relative}"
                result.edits.append(MigrationEdit(
                    notebook=notebook,
                    edit_type="workspace_variable_path",
                    original_value=raw,
                    resolved_value=target,
                    line_number=line_no,
                    notes=f"Transformed workspace path stored in variable '{match.group('name')}'.",
                    construct_type="workspace_notebook_path",
                ))
        result.edits = self._dedupe_edits(result.edits)
        return result

    @staticmethod
    def _placeholder_name(value: str) -> Optional[str]:
        if value.startswith("{") and value.endswith("}"):
            return value[1:-1]
        return None

    @staticmethod
    def _widget_assignments(text: str) -> Dict[str, dict]:
        result = {}
        for line_number, line in enumerate(text.splitlines(), 1):
            match = ASSIGN_RE.match(line)
            if match:
                result[match.group("name")] = {"line": line, "line_number": line_number}
        return result

    @staticmethod
    def _comment_line(line: str) -> str:
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]
        return f"{indent}# UCMP SOURCE CONFIG COMMENTED: {stripped}"

    @staticmethod
    def _bucket_insert_location(edits: List[MigrationEdit], text: str) -> int:
        return min((e.line_number for e in edits if e.edit_type == "storage_path"), default=1)

    @staticmethod
    def _dedupe_edits(edits: List[MigrationEdit]) -> List[MigrationEdit]:
        seen = set()
        output = []
        for edit in edits:
            key = (edit.edit_type, edit.original_value, edit.resolved_value)
            if key in seen:
                continue
            seen.add(key)
            output.append(edit)
        return output
