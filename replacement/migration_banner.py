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
    """Build a Python/SQL/Scala comment-only migration banner.
    """
    prefix = _COMMENT_PREFIX_BY_LANGUAGE.get(language, "#")
    separator = f"{prefix} COMMAND ----------"

    lines = [
        separator, "",
        f"{prefix} {BANNER_START_MARKER}",
        f"{prefix} UCMP Migration Notes",
        f"{prefix}",
        f"{prefix} This notebook was migrated from Azure Databricks to "
        f"AWS Databricks by the Universal Cloud Migration Platform (UCMP).",
        f"{prefix}",
        f"{prefix} Automatic replacements applied: {applied_count}",
    ]

    if manual_review_ops:
        lines.append(f"{prefix}")
        lines.append(f"{prefix} Manual review required "
                     f"({len(manual_review_ops)} items(s)):")
        for op in manual_review_ops:
            value = (op.get("original_value") or "").strip()
            note = (op.get("notes") or "").strip().splitlines()[0] if op.get("notes") else ""
            lines.append(f"{prefix}- `{value}` — {note}")
    else:
        lines.append(f"{prefix}")
        lines.append(f"{prefix} Manual review required: none")

    lines.append("")  # trailing blank line before the next COMMAND separator
    lines.append(f"{prefix} {BANNER_END_MARKER}")
    return "\n".join(lines)
