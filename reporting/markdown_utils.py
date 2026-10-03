"""
reporting.markdown_utils
==========================
Small, dependency-free Markdown formatting helpers shared by every report
builder in this module. Kept intentionally minimal - these reports are
meant to be read in any plain-text viewer or GitHub-style renderer, not
processed by a Markdown engine with extensions.
"""

from __future__ import annotations

from typing import Iterable, Sequence


def heading(text: str, level: int = 1) -> str:
    return f"{'#' * level} {text}\n"


def table(headers: Sequence[str], rows: Iterable[Sequence]) -> str:
    if not headers:
        return ""
    lines = [
        "| " + " | ".join(str(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def bullet_list(items: Iterable[str]) -> str:
    lines = [f"- {item}" for item in items]
    return "\n".join(lines) + ("\n" if lines else "")


def kv_block(pairs: Sequence[tuple]) -> str:
    lines = [f"**{key}:** {value}" for key, value in pairs]
    return "  \n".join(lines) + "\n"


def _cell(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")
