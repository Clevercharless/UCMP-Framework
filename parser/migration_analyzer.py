"""Targeted Azure->AWS notebook migration analysis.

This module adds the user-driven migration behavior on top of the existing
UCMP findings. It deliberately does not replace the existing parsers/rules.

Idempotency fix (marked "[idempotency fix]" below)
--------------------------------------------------
A path that has already been migrated (for example
``/Workspace/Deployed-Assets/{env}/PFL/...``) still starts with
``/Workspace/``, so it used to be treated as a *source* path and re-rooted
again, producing ``/Workspace/Deployed-Assets/{env}/Deployed-Assets/{env}/PFL/...``.
Every place that builds a target path from a ``/Workspace/...`` path now skips
paths that already live under a configured root (``workspace_root`` or
``referred_notebook_path_root``). The referred-repository rule is guarded too:
a source prefix such as ``/Workspace/Deployed-Assets/`` no longer matches the
start of an already-migrated ``/Workspace/Deployed-Assets/{env}/...`` path.
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
    "output_container_path": "output_container_path",
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
    r"(?P<f_prefix>[fF]?)"
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
        # [idempotency fix] An edit whose resolved value equals its original
        # (e.g. "env_config_existing") changes nothing, so it must not make a
        # notebook look "changed" on a re-run.
        return any(e.original_value != e.resolved_value for e in self.edits)

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
        enable_bucket_name_declaration: bool = False,
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
        self.enable_bucket_name_declaration = enable_bucket_name_declaration

    # ------------------------------------------------------------------
    # [idempotency fix] helpers
    # ------------------------------------------------------------------
    def _migrated_roots(self) -> List[str]:
        """Both configured roots; a path under either one was produced by a previous run."""
        roots = {
            self.workspace_root.rstrip("/"),
            self.referred_notebook_path_root.rstrip("/"),
        }
        return sorted((r for r in roots if r), key=len, reverse=True)

    def _already_target(self, path: str) -> bool:
        """
        True when ``path`` already lives under a configured target root
        (``workspace_root`` or ``referred_notebook_path_root``), i.e. it was
        produced by a previous run and must not be re-rooted.

        The comparison is case-sensitive on purpose: path case is never folded.
        """
        return any(path == root or path.startswith(root + "/") for root in self._migrated_roots())

    def _has_unmigrated_occurrence(self, line: str, source_prefix: str, target_prefix: str) -> bool:
        """
        True if ``source_prefix`` occurs in ``line`` at a place that has NOT
        already been migrated. An occurrence counts as migrated when it

        * lies inside an occurrence of ``target_prefix``, or
        * starts a path that is already under a configured root. This is what
          stops e.g. the source prefix ``/Workspace/Deployed-Assets/`` from
          matching the start of ``/Workspace/Deployed-Assets/{env}/PFL/...``.
        """
        target_spans = []
        start = 0
        while True:
            idx = line.find(target_prefix, start)
            if idx == -1:
                break
            target_spans.append((idx, idx + len(target_prefix)))
            start = idx + 1

        roots = self._migrated_roots()
        start = 0
        while True:
            idx = line.find(source_prefix, start)
            if idx == -1:
                return False
            inside_target = any(lo <= idx < hi for lo, hi in target_spans)
            starts_migrated_path = any(line.startswith(root + "/", idx) for root in roots)
            if not inside_target and not starts_migrated_path:
                return True
            start = idx + 1

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
        # env_config = 'import os\nenv = os.getenv("ENV","dev")'

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

                mapping = (
                    None
                    if container_configured
                    else self.mapping.get(container.lower())
                )

                review = False
                notes = []
                suffix = f"/{path}" if path else ""

                # Prefer the configured S3 bucket for a known literal container,
                # regardless of whether the storage account is hardcoded or dynamic.
                if not container_configured and mapping:
                    replacement = f"s3://{mapping}{suffix}"
                    notes.append(
                        f"Container-to-bucket mapping used: "
                        f"{container} -> {mapping}."
                    )

                else:
                    replacement = f"s3://{container}{suffix}"
                    review = True
                    notes.append(
                        f"No container-to-bucket mapping found for "
                        f"'{container}'; mechanical S3 placeholder "
                        "applied and manual verification required."
                    )

                if (
                    self.enable_bucket_name_declaration
                    and (container_configured or account_configured)
                    and bucket_config not in text
                ) :
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

        if self.enable_bucket_name_declaration and any(
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
                # [idempotency fix] already migrated: nothing to do. The line is
                # already in matched_run_lines so it is not reported as unparsed.
                if self._already_target(raw):
                    continue

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
                # [idempotency fix] already migrated: nothing to do.
                if self._already_target(raw_candidate):
                    continue

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
            existing_f_prefix = match.group("f_prefix") or ""
            quote = match.group("quote")
            argument_start = match.start("f_prefix")
            original_argument = text[argument_start:match.end()]

            # Already-migrated paths must not be re-rooted, but a path containing
            # {env} still needs an f-string prefix for Python interpolation.
            if self._already_target(raw):
                target = raw
            else:
                relative = re.sub(r"(?i)^/workspace/", "", raw)
                target = f"{self.workspace_root.rstrip('/')}/{relative}"

            needs_interpolation = "{env}" in target
            target_f_string = target
            if needs_interpolation:
                # Preserve deployment-time placeholders such as ${WORKSPACE_ROOT}
                # as literal text inside the Python f-string.
                target_f_string = re.sub(
                    r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
                    r"${{\1}}",
                    target_f_string,
                )
            desired_f_prefix = "f" if needs_interpolation or existing_f_prefix else ""
            replacement_argument = f"{desired_f_prefix}{quote}{target_f_string}{quote}"
            line_number = text.count("\n", 0, match.start("path")) + 1

            if original_argument != replacement_argument:
                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="workspace_notebook_run_path",
                        original_value=original_argument,
                        resolved_value=replacement_argument,
                        line_number=line_number,
                        notes=(
                            "Converted the notebook.run workspace reference to the configured "
                            "target workspace root; added/preserved an f-string when {env} "
                            "requires Python runtime interpolation."
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

            # [idempotency fix] already migrated: nothing to do.
            if self._already_target(raw):
                continue

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
                    # [idempotency fix] a no-op rewrite, or an occurrence that is
                    # already inside the target prefix, must not be rewritten again.
                    if source_prefix == target_prefix:
                        continue
                    if self._has_unmigrated_occurrence(line, source_prefix, target_prefix):
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
        result.edits.append(
            MigrationEdit(
                notebook=notebook,
                edit_type="add_target_config",
                original_value= "",
                resolved_value = 'import os\nenv = os.getenv("ENV", "dev")',
                line_number = 1,
                notes = "Added import os and env configuration.",
                construct_type = "target_environment_config",
            )
        )

        # Comment out the legacy raw_sa_name widget assignment in every notebook
        # where it is present. Do not add a duplicate edit for an already-commented line.
        raw_sa_pattern = re.compile(
            r"^(?P<indent>\s*)raw_sa_name\s*=\s*dbutils\.widgets\.get\(\s*([\"'])raw_sa_name\2\s*\)\s*$"
        )
        for line_number, line in enumerate(text.splitlines(), 1):
            if raw_sa_pattern.match(line):
                result.edits.append(
                    MigrationEdit(
                        notebook=notebook,
                        edit_type="comment_source_config",
                        original_value=line,
                        resolved_value=self._comment_line(line),
                        line_number=line_number,
                        notes="Commented out the legacy raw_sa_name widget assignment.",
                        construct_type="source_storage_config",
                    )
                )
                break

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

        return f"{indent}# {stripped}"

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
