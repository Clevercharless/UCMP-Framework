"""
reporting.transformation_report
==================================
Transformation Report: what the Transformation Planner (Module 8) decided
to do - operations by type, and a per-notebook breakdown of what changed
versus what's preserved.
"""

from __future__ import annotations

from typing import Dict

from reporting.markdown_utils import heading, kv_block, table


def build_transformation_report(transformation_plan: Dict) -> str:
    summary = transformation_plan["summary"]
    notebook_plans = transformation_plan["notebook_plans"]

    lines = [
        heading("Transformation Report", 1),
        kv_block([
            ("Repository", transformation_plan["repo_name"]),
            ("Notebooks planned", summary["notebook_count"]),
            ("Total operations", summary["total_operations"]),
            ("Notebooks needing manual review", summary["notebooks_with_manual_review"]),
        ]),
        "",
        heading("Operations by Type", 2),
        table(["Operation Type", "Count"], sorted(summary["by_operation_type"].items())),
        "",
        heading("Per-Notebook Plan Summary", 2),
        table(
            ["Notebook", "Category", "Classification", "Operations", "Manual Review"],
            [
                [nb["relative_path"], nb["category"], nb.get("classification", "NO_CHANGE"), nb["operation_count"],
                 "YES" if nb["requires_manual_review"] else "no"]
                for nb in notebook_plans
            ],
        ),
        "",
        heading("Transformation Details", 2),
        table(
            ["Notebook", "Type", "Before", "After", "Review", "Notes"],
            [
                [nb["relative_path"], op["operation_type"], op.get("original_value") or "-",
                 op.get("resolved_value") or "-", "YES" if op.get("requires_manual_review") else "no",
                 op.get("notes") or "-"]
                for nb in notebook_plans for op in nb["operations"]
                if op["operation_type"] != "keep_business_logic"
            ],
        ),
    ]
    return "\n".join(lines)
