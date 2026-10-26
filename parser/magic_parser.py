"""
parser.magic_parser
=====================
Detects Databricks "magic" commands within notebook cells. In an exported
notebook, a magic command is rendered as one or more comment lines
prefixed with `MAGIC`, e.g. (Python export):

    # MAGIC %run "../Common/utils"

or (SQL export):

    -- MAGIC %md
    -- MAGIC ## Some heading

This parser strips the language-appropriate comment+MAGIC prefix and
extracts the magic type (`run`, `sql`, `python`, `scala`, `pip`, `sh`,
`md`) plus its argument text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from parser.notebook_reader import NotebookCell, NotebookSource
from repository.inventory import NotebookLanguage

SUPPORTED_MAGIC_TYPES = {"run", "sql", "python", "scala", "pip", "sh", "md"}

_MAGIC_LINE_PATTERNS = {
    NotebookLanguage.PYTHON: re.compile(r"^#\s*MAGIC\s?(.*)$"),
    NotebookLanguage.SQL: re.compile(r"^--\s*MAGIC\s?(.*)$"),
    NotebookLanguage.SCALA: re.compile(r"^//\s*MAGIC\s?(.*)$"),
}

_MAGIC_COMMAND_RE = re.compile(r"^%(\w+)\s*(.*)$")


@dataclass
class MagicCommand:
    """A single magic command found in a notebook cell."""

    magic_type: str  # one of SUPPORTED_MAGIC_TYPES
    argument: str  # raw remaining text on the command line, e.g. '"../Common/utils"'
    cell_index: int
    line_number: int

    def to_dict(self) -> dict:
        return {
            "magic_type": self.magic_type,
            "argument": self.argument,
            "cell_index": self.cell_index,
            "line_number": self.line_number,
        }


class MagicCommandParser:
    """Extracts magic commands from every cell of a NotebookSource."""

    def parse(self, notebook: NotebookSource) -> List[MagicCommand]:
        pattern = _MAGIC_LINE_PATTERNS.get(notebook.language, _MAGIC_LINE_PATTERNS[NotebookLanguage.PYTHON])
        commands: List[MagicCommand] = []

        for cell in notebook.cells:
            magic_lines = self._extract_magic_lines(cell, pattern)
            if not magic_lines:
                continue

            first_line_no, first_content = magic_lines[0]
            match = _MAGIC_COMMAND_RE.match(first_content.strip())
            if not match:
                continue

            magic_type = match.group(1).lower()
            if magic_type not in SUPPORTED_MAGIC_TYPES:
                continue

            # For multi-line magic blocks (e.g. %md spanning several MAGIC lines),
            # join everything after the %magic token as the argument.
            argument_parts = [match.group(2)]
            argument_parts.extend(content for _, content in magic_lines[1:])
            argument = "\n".join(part for part in argument_parts if part).strip()

            commands.append(
                MagicCommand(
                    magic_type=magic_type,
                    argument=argument,
                    cell_index=cell.index,
                    line_number=first_line_no,
                )
            )
        return commands

    @staticmethod
    def _extract_magic_lines(cell: NotebookCell, pattern: re.Pattern) -> List[tuple]:
        """Return [(absolute_line_number, content_after_MAGIC_prefix), ...] for this cell."""
        result = []
        for offset, line in enumerate(cell.lines):
            match = pattern.match(line)
            if match:
                result.append((cell.start_line + offset, match.group(1)))
        return result
