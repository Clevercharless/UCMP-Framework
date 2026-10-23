"""
reporting.manual_review_report
=================================
Manual Review Report: the single consolidated checklist a human reviewer
actually needs. Pulls together everything flagged for manual attention
across the whole pipeline - the Knowledge Model's own manual_review_items
(Module 5), the Transformation Plan's manual_review/unmatched operations
(Module 8), and the Validation Report's warnings (Module 10) - rather
than making a reviewer hunt through five different JSON files.
"""

from __future__ import annotations

from typing import Dict

from reporting.markdown_utils import heading, kv_block, table


def build_manual_review_report(
    knowledge_model: Dict,
    transformation_plan: Dict,
    validation_report: Dict,
) -> str:
    plan_items = [
        {"notebook": nb["relative_path"], "construct_type": op["construct_type"],
         "value": op["original_value"], "reason": op["notes"]}
        for nb in transformation_plan["notebook_plans"]
        for op in nb["operations"]
        if op["requires_manual_review"] and op["operation_type"] != "keep_business_logic"
    ]
    validation_warnings = [f for f in validation_report["findings"] if f["severity"] == "warning"]

    lines = [
        heading("Manual Review Report", 1),
        kv_block([
            ("Repository", knowledge_model["repo_name"]),
            ("Items requiring manual review (transformation plan)", len(plan_items)),
            ("Knowledge model manual review items", len(knowledge_model["manual_review_items"])),
            ("Validation warnings (expected residue)", len(validation_warnings)),
        ]),
        "",
        heading("Action Checklist: Constructs Requiring Manual Rewrite", 2),
        "These are the items an engineer must resolve before this migration is production-ready.\n",
        table(
            ["Notebook", "Construct Type", "Value", "Reason"],
            [[i["notebook"], i["construct_type"], i["value"], i["reason"]] for i in plan_items],
        ),
    ]

    if knowledge_model["manual_review_items"]:
        lines.append("")
        lines.append(heading("Parser-Level Flags", 2))
        lines.append(
            table(
                ["Notebook", "Reason", "Detail"],
                [
                    [i["notebook"], i["reason"], i["detail"]]
                    for i in knowledge_model["manual_review_items"]
                ],
            )
        )

    if validation_warnings:
        lines.append("")
        lines.append(heading("Validation Warnings (confirmed as expected, still open)", 2))
        lines.append(
            table(
                ["Notebook", "Category", "Message", "Detail"],
                [
                    [f["notebook"] or "-", f["category"], f["message"], f["detail"] or "-"]
                    for f in validation_warnings
                ],
            )
        )

    return "\n".join(lines)
