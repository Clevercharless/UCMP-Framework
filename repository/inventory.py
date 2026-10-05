"""
repository.inventory
=====================
Data model describing what the Repository Manager finds when it syncs and
scans a source repository. Kept intentionally simple (paths + metadata,
no parsed content) — actual code parsing is the Parser Engine's job
(Module 5). The Repository Manager only answers "what files exist, where,
and what kind are they."
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List


class NotebookLanguage(str, Enum):
    """Primary language of a notebook, inferred from its Databricks export header."""

    PYTHON = "python"
    SQL = "sql"
    SCALA = "scala"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NotebookFile:
    """A single Databricks notebook discovered in the source repository."""

    relative_path: str
    absolute_path: str
    category: str  # top-level folder: Bronze / Silver / Gold / Common / Jobs / SQL
    language: NotebookLanguage
    size_bytes: int
    line_count: int
    sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "absolute_path": self.absolute_path,
            "category": self.category,
            "language": self.language.value,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ConfigAsset:
    """A non-notebook infrastructure asset (e.g. Config/*.yaml, Config/*.json)."""

    relative_path: str
    absolute_path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "absolute_path": self.absolute_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass
class RepositoryInventory:
    """Full result of a Repository Manager sync + scan pass."""

    repo_name: str
    source_path: str
    staged_path: str
    notebooks: List[NotebookFile] = field(default_factory=list)
    config_assets: List[ConfigAsset] = field(default_factory=list)
    categories_found: List[str] = field(default_factory=list)
    # Workspace mode may discover many notebook paths as metadata while exporting
    # source only for the selected migration scope.
    known_notebook_paths: List[str] = field(default_factory=list)

    @property
    def notebook_count(self) -> int:
        return len(self.notebooks)

    def notebooks_by_category(self, category: str) -> List[NotebookFile]:
        return [nb for nb in self.notebooks if nb.category == category]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "source_path": self.source_path,
            "staged_path": self.staged_path,
            "notebook_count": self.notebook_count,
            "categories_found": self.categories_found,
            "known_notebook_paths": self.known_notebook_paths or [nb.relative_path for nb in self.notebooks],
            "notebooks": [nb.to_dict() for nb in self.notebooks],
            "config_assets": [asset.to_dict() for asset in self.config_assets],
        }


def compute_sha256(path: Path) -> str:
    """Content checksum, used to detect real changes across sync runs."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_notebook_language(path: Path) -> NotebookLanguage:
    """
    Infer language from a Databricks-exported notebook's source header line,
    e.g. "# Databricks notebook source" (Python) or
    "-- Databricks notebook source" (SQL).
    """
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            first_line = fh.readline().strip()
    except OSError:
        return NotebookLanguage.UNKNOWN

    if first_line.startswith("# Databricks notebook source"):
        return NotebookLanguage.PYTHON
    if first_line.startswith("-- Databricks notebook source"):
        return NotebookLanguage.SQL
    if first_line.startswith("// Databricks notebook source"):
        return NotebookLanguage.SCALA
    return NotebookLanguage.UNKNOWN
