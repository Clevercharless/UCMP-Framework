"""
reporting.deployment_report
=============================
Deployment Report: a human-readable rendering of the DeploymentPlan
artifact the Deployment Engine (Module 11) already computed and wrote as
JSON - step-by-step outcome, git commit/push hashes, and the overall
deployment status.
"""

from __future__ import annotations

from typing import Dict

from reporting.markdown_utils import heading, kv_block, table


def build_deployment_report(deployment_plan: Dict) -> str:
    lines = [
        heading("Deployment Report", 1),
        kv_block([
            ("Repository", deployment_plan["repo_name"]),
            ("Deployment Mode", deployment_plan["deployment_mode"]),
            ("Validation Gate Status", deployment_plan["validation_gate_status"]),
            ("Overall Status", f"**{deployment_plan['overall_status']}**"),
        ]),
        "",
        heading("Deployment Steps", 2),
        table(
            ["Step", "Status", "Notes"],
            [[s["name"], s["status"], s["notes"] or "-"] for s in deployment_plan["steps"]],
        ),
    ]

    commit_step = next((s for s in deployment_plan["steps"] if s["name"] == "git_commit"), None)
    push_step = next((s for s in deployment_plan["steps"] if s["name"] == "git_push"), None)

    if commit_step and commit_step["detail"].get("commit_hash"):
        lines.append("")
        lines.append(heading("Git Detail", 2))
        detail_pairs = [("Local commit hash", commit_step["detail"]["commit_hash"])]
        if push_step and push_step["status"] == "completed":
            detail_pairs.append(("Remote commit hash", push_step["detail"]["remote_commit_hash"]))
            detail_pairs.append(("Remote branch", push_step["detail"]["branch"]))
        lines.append(kv_block(detail_pairs))

    return "\n".join(lines)
