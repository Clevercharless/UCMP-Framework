"""
replacement.migration_banner
==============================
Builds a small "UCMP Migration Notes" cell that the Replacement Engine
inserts as the second cell of every migrated notebook (right after the
Databricks export header), summarizing what was automatically changed and
what still needs a human look. Written using the same comment-prefix and
`MAGIC`/`COMMAND` conventions as the rest of the notebook, so the output
remains a fully valid, re-parseable Databricks export.
"""

from __future__ import annotations

from typing import Dict, List

_COMMENT_PREFIX_BY_LANGUAGE = {"python": "#", "sql": "--", "scala": "//"}

BANNER_START_MARKER = "UCMP_BANNER_START"
BANNER_END_MARKER = "UCMP_BANNER_END"


def build_banner(
    language: str,
    applied_count: int,
    manual_review_ops: List[Dict],
) -> str:
    return ""
