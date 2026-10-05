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
            resolved = self._resolve(source_relative_path, raw_reference, {})
            dependencies.append(
                NotebookDependency(
                    source_notebook=source_relative_path,
                    raw_reference=raw_reference,
                    resolved_target=resolved,
                    dependency_type="run_magic",
                    line_number=magic.line_number,
                )
            )

        assignments = {}
        if ast_findings is not None:
            for assignment in ast_findings.assignments:
                assignments[assignment.target.strip()] = assignment.value_snippet.strip()

        # Re-process magic commands with assignment-aware resolution so forms
        # such as `%run $workspace_prefix/PFL/Common/utils` can be matched
        # without requiring the prefix itself to be statically known.
        for dependency in dependencies:
            if dependency.dependency_type == "run_magic":
                dependency.resolved_target = self._resolve(source_relative_path, dependency.raw_reference, assignments)

        if ast_findings is not None:
            for call in ast_findings.calls:
                if call.category != "notebook_reference" or not call.notebook_reference_target:
                    continue
                raw_reference = call.notebook_reference_target
                resolved = self._resolve(source_relative_path, raw_reference, assignments)
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

    def _resolve(self, source_relative_path: str, raw_reference: str, assignments: Optional[Dict[str, str]] = None) -> Optional[str]:
        assignments = assignments or {}
        reference = str(raw_reference or "").strip().replace("\\", "/")
        # Resolve simple variable references and retain the static notebook
        # suffix when a dynamic prefix cannot be evaluated.
        for token in sorted(assignments, key=len, reverse=True):
            value = assignments[token]
            if reference in {token, f"${token}", f"${{{token}}}"}:
                reference = self._evaluate_assignment(value, assignments)
                break
            reference = reference.replace(f"${{{token}}}", self._evaluate_assignment(value, assignments))
            reference = reference.replace(f"${token}", self._evaluate_assignment(value, assignments))
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
        direct = self._by_stem.get(self._stem_key(normalized))
        if direct:
            return direct

        # Dynamic prefixes (workspace root, environment prefix, etc.) may be
        # unavailable statically. Match the longest known notebook suffix.
        normalized_lower = normalized.lower()
        candidates = [(key, path) for key, path in self._by_stem.items() if normalized_lower.endswith(key)]
        if candidates:
            candidates.sort(key=lambda item: len(item[0]), reverse=True)
            return candidates[0][1]
        return None

    @classmethod
    def _evaluate_assignment(cls, expression: str, assignments: Dict[str, str]) -> str:
        value = str(expression or "").strip()
        if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
            value = value[1:-1]
        if value.startswith("f'") or value.startswith('f"'):
            value = value[2:-1] if value[-1:] in {"'", '"'} else value[2:]
        for token in sorted(assignments, key=len, reverse=True):
            nested = cls._evaluate_assignment(assignments[token], {}) if token not in assignments.get(token, '') else ''
            if nested:
                value = value.replace(f"{{{token}}}", nested)
                value = value.replace(f"${token}", nested)
        return value

    @staticmethod
    def _stem_key(path_str: str) -> str:
        """Extension-less, lowercased path used as the matching key, e.g.
        'Common/utils.py' and 'Common/utils' both map to 'common/utils'."""
        pure = PurePosixPath(path_str)
        stem_path = pure.parent / pure.stem
        return str(stem_path).lower()
