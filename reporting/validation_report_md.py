"""
reporting.validation_report_md
================================
Validation Report (Markdown): a human-readable rendering of the
ValidationReport artifact the Validation Engine (Module 10) already
computed and wrote as JSON. This module adds no new logic or findings -
it only formats the existing PASS/FAIL result and findings for a reviewer
who doesn't want to read raw JSON.
"""

from __future__ import annotations

from typing import Dict

from reporting.markdown_utils import heading, kv_block, table


def build_validation_report_md(validation_report: Dict) -> str:
    summary = validation_report["summary"]
    findings = validation_report["findings"]

    lines = [
        heading("Validation Report", 1),
        kv_block([
            ("Repository", validation_report["repo_name"]),
            ("Overall Status", f"**{validation_report['overall_status']}**"),
            ("Errors", summary["error_count"]),
            ("Warnings", summary["warning_count"]),
            ("Info", summary["info_count"]),
        ]),
        "",
        heading("Findings by Category", 2),
        table(
            ["Category", "Errors", "Warnings", "Info"],
            [
                [category, counts["error"], counts["warning"], counts["info"]]
                for category, counts in sorted(summary["by_category"].items())
            ],
        ),
    ]

    for severity, label in [("error", "Errors"), ("warning", "Warnings")]:
        matching = [f for f in findings if f["severity"] == severity]
        if not matching:
            continue
        lines.append("")
        lines.append(heading(label, 2))
        lines.append(
            table(
                ["Category", "Notebook", "Message", "Detail"],
                [
                    [f["category"], f["notebook"] or "-", f["message"], f["detail"] or "-"]
                    for f in matching
                ],
            )
        )

    return "\n".join(lines)
