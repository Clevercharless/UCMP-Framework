"""
validation.banner_utils
=========================
Shared helper used by every validator that scans migrated notebook
CONTENT (Azure Residue, Unsupported SDK, Hardcoded Secret) rather than
structure (Syntax). The Replacement Engine's inserted "UCMP Migration
Notes" banner intentionally quotes flagged construct values in its own
markdown documentation - that text must never be mistaken for the
construct still being present in real code, so these validators strip
the banner block before scanning.
"""

from __future__ import annotations

from typing import List

from replacement.migration_banner import BANNER_END_MARKER, BANNER_START_MARKER


def strip_banner(text: str) -> str:
    """Removes the UCMP-inserted migration notes cell, leaving only real code/markdown."""
    lines = text.splitlines()
    output: List[str] = []
    inside_banner = False
    for line in lines:
        if BANNER_START_MARKER in line:
            inside_banner = True
            continue
        if BANNER_END_MARKER in line:
            inside_banner = False
            continue
        if not inside_banner:
            output.append(line)
    return "\n".join(output)
