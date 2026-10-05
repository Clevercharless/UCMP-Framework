"""
reporting.migration_summary_report
=====================================
Migration Summary Report: the executive-level view - what was migrated,
from where to where, how much was automated versus flagged, and whether
it's PASS/FAIL/DEPLOYED. Meant to be the first (and possibly only) report
a stakeholder reads; everything else is supporting detail.
"""

from __future__ import annotations

from typing import Dict

from reporting.markdown_utils import heading, kv_block


def build_migration_summary_report(
    config: Dict,
    repository: Dict,
    knowledge_model: Dict,
    rule_service_output: Dict,
    replacement_summary: Dict,
    validation_report: Dict,
    deployment_plan: Dict,
) -> str:
    rs_summary = rule_service_output["summary"]

    lines = [
        heading("Migration Summary Report", 1),
        heading(f"{repository['repo_name']}: {config['source']['platform']} -> {config['target']['platform']}", 2),
        kv_block([
            ("Source platform", config["source"]["platform"]),
            ("Source repository", config["source"]["repo_path"]),
            ("Target platform", config["target"]["platform"]),
            ("Target repository", replacement_summary["target_repo_path"]),
        ]),
        "",
        heading("Pipeline Outcome", 2),
        kv_block([
            ("Notebooks migrated", replacement_summary["notebooks_written"]),
            ("Config assets migrated", replacement_summary["config_assets_copied"]),
            ("Operations applied automatically", replacement_summary["total_operations_applied"]),
            ("Constructs auto-replaced", rs_summary["replace"]),
            ("Constructs removed", rs_summary["remove"]),
            ("Constructs flagged for manual review", rs_summary["manual_review"]),
            ("Constructs left unmatched", rs_summary["unmatched"]),
            ("Business objects preserved untouched", len(knowledge_model["business_objects"])),
        ]),
        "",
        heading("Quality Gates", 2),
        kv_block([
            ("Validation status", f"**{validation_report['overall_status']}**"),
            ("Validation errors", validation_report["summary"]["error_count"]),
            ("Validation warnings", validation_report["summary"]["warning_count"]),
            ("Deployment status", f"**{deployment_plan['overall_status']}**"),
            ("Deployment mode", deployment_plan["deployment_mode"]),
        ]),
        "",
        heading("Automation Rate", 2),
        _automation_rate_line(rs_summary),
        "",
        heading("Next Steps", 2),
        (
            f"{replacement_summary['notebooks_written']} notebook(s) and "
            f"{replacement_summary['config_assets_copied']} config asset(s) have been migrated "
            f"to `{replacement_summary['target_repo_path']}`. "
            f"See **ManualReviewReport.md** for the {rs_summary['manual_review'] + rs_summary['unmatched']} "
            f"item(s) still requiring engineering attention before this migration is production-ready."
        ),
    ]
    return "\n".join(lines)


def _automation_rate_line(rs_summary: Dict) -> str:
    total = rs_summary["total"]
    if total == 0:
        return "No transformation candidates were found.\n"
    automated = rs_summary["replace"] + rs_summary["remove"] + rs_summary["no_change"]
    rate = round(100 * automated / total, 1)
    return (
        f"{automated} of {total} constructs ({rate}%) were resolved automatically without "
        f"human intervention.\n"
    )
