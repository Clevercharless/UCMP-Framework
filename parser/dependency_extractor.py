"""
parser.dependency_extractor
=============================
Turns raw notebook-to-notebook references — `%run "../Common/utils"` magic
commands and `dbutils.notebook.run("../Bronze/ingest_customer", ...)` calls
found by the AST parser — into resolved dependency edges pointing at real
notebooks in the repository.

References are written relative to the referencing notebook's own folder
and conventionally omit the file extension (Databricks convention), so
resolution needs to: (1) join the raw reference against the source
notebook's parent directory, (2) normalize `..`/`.` segments, and (3)
match against the known repo notebook paths by extension-less stem.
Anything that doesn't resolve is kept with `resolved_target=None` so the
Knowledge Model can flag it for manual review rather than silently
dropping it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Dict, List, Optional

from parser.ast_parser import ASTFindings
from parser.magic_parser import MagicCommand


@dataclass
class NotebookDependency:
    """A single resolved (or unresolved) notebook-to-notebook reference."""

    source_notebook: str
    raw_reference: str
    resolved_target: Optional[str]
    dependency_type: str  # "run_magic" | "notebook_run_call"
    line_number: int
    target_in_migration_list: Optional[bool] = None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_target is not None

    def to_dict(self) -> dict:
        return {
            "source_notebook": self.source_notebook,
            "raw_reference": self.raw_reference,
            "resolved_target": self.resolved_target,
            "dependency_type": self.dependency_type,
            "is_resolved": self.is_resolved,
            "line_number": self.line_number,
            "target_in_migration_list": self.target_in_migration_list,
        }


class DependencyExtractor:
    """
    Extracts and resolves notebook dependencies. Must be constructed with
    the full list of known repo notebook relative paths (from Module 4's
    RepositoryInventory) so raw references can be matched to real files.
    """

    def __init__(self, known_notebook_paths: List[str]):
        self._known_paths = list(known_notebook_paths)
        self._by_stem: Dict[str, str] = {
            self._stem_key(path): path for path in known_notebook_paths
        }

    def extract(
        self,
        source_relative_path: str,
        magic_commands: List[MagicCommand],
        ast_findings: Optional[ASTFindings],
    ) -> List[NotebookDependency]:
        dependencies: List[NotebookDependency] = []

        for magic in magic_commands:
            if magic.magic_type != "run":
                continue
            raw_reference = magic.argument.strip().strip('"').strip("'")
            resolved = self._resolve(source_relative_path, raw_reference)
            dependencies.append(
                NotebookDependency(
                    source_notebook=source_relative_path,
                    raw_reference=raw_reference,
                    resolved_target=resolved,
                    dependency_type="run_magic",
                    line_number=magic.line_number,
                )
            )

        if ast_findings is not None:
            assignments = {}
            for assignment in ast_findings.assignments:
                value = assignment.value_snippet.strip()
                if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                    assignments[assignment.target.strip()] = value[1:-1]
            for call in ast_findings.calls:
                if call.category != "notebook_reference" or not call.notebook_reference_target:
                    continue
                raw_reference = call.notebook_reference_target
                raw_reference = assignments.get(raw_reference, raw_reference)
                resolved = self._resolve(source_relative_path, raw_reference)
                dependencies.append(
                    NotebookDependency(
                        source_notebook=source_relative_path,
                        raw_reference=raw_reference,
                        resolved_target=resolved,
                        dependency_type="notebook_run_call",
                        line_number=call.line_number,
                    )
                )

        return dependencies

    # -- internals --------------------------------------------------------

    def _resolve(self, source_relative_path: str, raw_reference: str) -> Optional[str]:
        reference = str(raw_reference or "").strip().replace("\\", "/")
        # Workspace-absolute references are resolved against the inventory's
        # workspace-relative paths. Support both the historical /workspace/
        # convention and ordinary Databricks absolute paths such as /PFL/....
        if reference.startswith("/workspace/"):
            joined = reference[len("/workspace/"): ]
        elif reference.startswith("/"):
            joined = reference.lstrip("/")
        else:
            source_dir = PurePosixPath(source_relative_path).parent
            joined = (source_dir / reference).as_posix()
        normalized = os.path.normpath(joined).replace(os.sep, "/").lstrip("/")
        return self._by_stem.get(self._stem_key(normalized))

    @staticmethod
    def _stem_key(path_str: str) -> str:
        """Extension-less, lowercased path used as the matching key, e.g.
        'Common/utils.py' and 'Common/utils' both map to 'common/utils'."""
        pure = PurePosixPath(path_str)
        stem_path = pure.parent / pure.stem
        return str(stem_path).lower()
