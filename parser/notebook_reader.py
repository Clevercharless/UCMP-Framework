"""
parser.notebook_reader
========================
Reads a Databricks-exported notebook file (`.py`, `.sql`, or `.scala`) and
splits it into cells along the `COMMAND ----------` separator that
Databricks inserts on export. This is the ONLY module that touches the
filesystem directly — every other Parser Engine component operates on the
`NotebookSource` object this produces.

Databricks export format (for any language) looks like:

    # Databricks notebook source
    <cell 0 content>
    # COMMAND ----------
    <cell 1 content>
    # COMMAND ----------
    ...

with the comment marker (`#`, `--`, or `//`) matching the notebook's
language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from common.exceptions import ParserError
from repository.inventory import NotebookLanguage, detect_notebook_language

_HEADER_PATTERNS = {
    NotebookLanguage.PYTHON: "# Databricks notebook source",
    NotebookLanguage.SQL: "-- Databricks notebook source",
    NotebookLanguage.SCALA: "// Databricks notebook source",
}

_COMMAND_SEPARATOR_RE = {
    NotebookLanguage.PYTHON: re.compile(r"^#\s*COMMAND\s*-+\s*$"),
    NotebookLanguage.SQL: re.compile(r"^--\s*COMMAND\s*-+\s*$"),
    NotebookLanguage.SCALA: re.compile(r"^//\s*COMMAND\s*-+\s*$"),
}


@dataclass
class NotebookCell:
    """A single cell (delimited by `COMMAND ----------`) within a notebook."""

    index: int
    start_line: int  # 1-indexed line number of the first line of this cell in the file
    raw_text: str

    @property
    def lines(self) -> List[str]:
        return self.raw_text.splitlines()


@dataclass
class NotebookSource:
    """The full parsed structure of one notebook file, ready for downstream parsing."""

    relative_path: str
    absolute_path: str
    language: NotebookLanguage
    full_text: str
    cells: List[NotebookCell] = field(default_factory=list)

    @property
    def cell_count(self) -> int:
        return len(self.cells)


class NotebookReader:
    """Reads a notebook file from disk and splits it into cells."""

    def read(self, relative_path: str, absolute_path: str) -> NotebookSource:
        path = Path(absolute_path)
        if not path.exists():
            raise ParserError(f"Notebook file does not exist: {absolute_path}")

        text = path.read_text(encoding="utf-8", errors="ignore")
        language = detect_notebook_language(path)

        if language == NotebookLanguage.UNKNOWN:
            raise ParserError(
                f"Notebook '{relative_path}' does not have a recognized "
                f"'Databricks notebook source' export header; cannot determine language"
            )

        cells = self._split_cells(text, language)
        return NotebookSource(
            relative_path=relative_path,
            absolute_path=absolute_path,
            language=language,
            full_text=text,
            cells=cells,
        )

    def read_content(self, relative_path: str, content: str, language_hint: NotebookLanguage | None = None) -> NotebookSource:
        """Read exported notebook source without creating a local staging file."""
        text = str(content or "")
        first = text.splitlines()[0].strip() if text.splitlines() else ""
        language = next((lang for lang, header in _HEADER_PATTERNS.items() if first.startswith(header)), NotebookLanguage.UNKNOWN)
        if language == NotebookLanguage.UNKNOWN and language_hint is not None:
            language = language_hint
        if language == NotebookLanguage.UNKNOWN:
            raise ParserError(
                f"Notebook '{relative_path}' does not have a recognized "
                "'Databricks notebook source' export header; cannot determine language"
            )
        return NotebookSource(
            relative_path=relative_path, absolute_path="", language=language,
            full_text=text, cells=self._split_cells(text, language),
        )

    @staticmethod
    def _split_cells(text: str, language: NotebookLanguage) -> List[NotebookCell]:
        separator_re = _COMMAND_SEPARATOR_RE.get(language, _COMMAND_SEPARATOR_RE[NotebookLanguage.PYTHON])
        lines = text.splitlines()

        cells: List[NotebookCell] = []
        current_lines: List[str] = []
        current_start = 1
        cell_index = 0

        for line_no, line in enumerate(lines, start=1):
            if separator_re.match(line.strip()):
                cells.append(
                    NotebookCell(
                        index=cell_index,
                        start_line=current_start,
                        raw_text="\n".join(current_lines).strip("\n"),
                    )
                )
                cell_index += 1
                current_lines = []
                current_start = line_no + 1
                continue
            current_lines.append(line)

        # Final cell (everything after the last separator, or the whole file
        # if there were no separators at all)
        cells.append(
            NotebookCell(
                index=cell_index,
                start_line=current_start,
                raw_text="\n".join(current_lines).strip("\n"),
            )
        )
        return cells
