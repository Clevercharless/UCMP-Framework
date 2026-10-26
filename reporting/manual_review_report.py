
"""
reporting.manual_review_report
=================================
Manual Review Report: consolidated checklist for human reviewers.

Combines:
- Transformation-plan operations requiring manual review.
- Knowledge Model manual_review_items.
- Validation warnings.
- Database / JDBC connection findings.
- Secret references.
- Credential findings.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from reporting.markdown_utils import heading, kv_block, table


def _safe_value(value: Any) -> str:
    """Convert a value to text and redact common credential patterns."""
    if value is None:
        return "-"

    text = str(value)

    # Redact credentials embedded in URLs:
    # protocol://username:password@host
    text = re.sub(
        r"(://[^:/@\s]+:)[^@\s]+(@)",
        r"\1[REDACTED]\2",
        text,
    )

    # Redact common sensitive key/value pairs.
    text = re.sub(
        r"(?i)\b(password|passwd|pwd|token|secret|client_secret|"
        r"api_key|apikey|access_key|secret_key)\b"
        r"(\s*[=:]\s*)"
        r"(['\"]?)[^,\s;'\"&]+",
        r"\1\2[REDACTED]",
        text,
    )

    return text


def _field(item: Dict[str, Any], *keys: str) -> str:
    """Return the first available, non-empty field."""
    for key in keys:
        value = item.get(key)

        if value is not None and value != "":
            return _safe_value(value)

    return "-"


def _render_database_connections(
    connections: List[Dict[str, Any]],
) -> List[str]:
    lines = [
        "",
        heading("Database / JDBC Connections", 2),
        (
            "Review these detected connections and verify that the target "
            "environment has the required connectivity and configuration."
        ),
        "",
    ]

    if not connections:
        lines.append("No database connection findings were recorded.")
        return lines

    lines.append(
        table(
            [
                "Notebook",
                "Connection Type",
                "Line",
                "Detection Method",
                "Connection Reference",
            ],
            [
                [
                    _field(item, "notebook", "relative_path"),
                    _field(item, "connection_type", "type"),
                    _field(item, "line_number"),
                    _field(item, "detection_method"),
                    _field(item, "url", "connection_string", "value"),
                ]
                for item in connections
            ],
        )
    )

    return lines


def _render_secret_references(
    references: List[Dict[str, Any]],
) -> List[str]:
    lines = [
        "",
        heading("Secret References", 2),
        (
            "Review secret references and ensure that the required secrets "
            "are available through the target platform's approved "
            "secret-management configuration."
        ),
        "",
    ]

    if not references:
        lines.append("No secret references were recorded.")
        return lines

    lines.append(
        table(
            [
                "Notebook",
                "Line",
                "API",
                "Scope",
                "Secret Key",
                "Detection Method",
            ],
            [
                [
                    _field(item, "notebook", "relative_path"),
                    _field(item, "line_number"),
                    _field(item, "api"),
                    _field(item, "scope"),
                    _field(item, "key", "secret_key", "secret_name"),
                    _field(item, "detection_method"),
                ]
                for item in references
            ],
        )
    )

    return lines


def _render_credential_findings(
    findings: List[Dict[str, Any]],
) -> List[str]:
    lines = [
        "",
        heading("Credential Findings", 2),
        (
            "Inspect these findings to determine whether credentials are "
            "embedded in source code or require secure configuration. "
            "Raw credential values are intentionally excluded."
        ),
        "",
    ]

    if not findings:
        lines.append("No credential findings were recorded.")
        return lines

    lines.append(
        table(
            [
                "Notebook",
                "Line",
                "Finding Type",
                "Detection Method",
                "Review Detail",
            ],
            [
                [
                    _field(item, "notebook", "relative_path"),
                    _field(item, "line_number"),
                    _field(item, "finding_type", "credential_type", "type"),
                    _field(item, "detection_method"),
                    _field(item, "reason", "description", "message"),
                ]
                for item in findings
            ],
        )
    )

    return lines


def build_manual_review_report(
    knowledge_model: Dict,
    transformation_plan: Dict,
    validation_report: Dict,
) -> str:
    # Transformation operations requiring manual review.
    plan_items = [
        {
            "notebook": nb.get("relative_path", "-"),
            "construct_type": op.get("construct_type", "-"),
            "value": op.get("original_value", "-"),
            "reason": op.get("notes", "-"),
        }
        for nb in transformation_plan.get("notebook_plans", [])
        for op in nb.get("operations", [])
        if op.get("requires_manual_review")
        and op.get("operation_type") != "keep_business_logic"
    ]

    # Existing parser-level and validation findings.
    manual_review_items = knowledge_model.get("manual_review_items", [])

    validation_warnings = [
        finding
        for finding in validation_report.get("findings", [])
        if finding.get("severity") == "warning"
    ]

    # Additional Knowledge Model findings.
    database_connections = knowledge_model.get("database_connections", [])
    secret_references = knowledge_model.get("secret_references", [])
    credential_findings = knowledge_model.get("credential_findings", [])

    lines = [
        heading("Manual Review Report", 1),
        kv_block(
            [
                ("Repository", knowledge_model.get("repo_name", "-")),
                ("Transformation items requiring manual review", len(plan_items)),
                ("Knowledge Model manual review items", len(manual_review_items)),
                ("Validation warnings", len(validation_warnings)),
                ("Database / JDBC connection findings", len(database_connections)),
                ("Secret references detected", len(secret_references)),
                ("Credential findings detected", len(credential_findings)),
            ]
        ),
        "",
        heading("Action Checklist: Constructs Requiring Manual Rewrite", 2),
        (
            "These are the transformation items requiring engineering review "
            "before the migration is considered production-ready."
        ),
        "",
        table(
            ["Notebook", "Construct Type", "Value", "Reason"],
            [
                [
                    _safe_value(item["notebook"]),
                    _safe_value(item["construct_type"]),
                    _safe_value(item["value"]),
                    _safe_value(item["reason"]),
                ]
                for item in plan_items
            ],
        ),
    ]

    if manual_review_items:
        lines.extend(
            [
                "",
                heading("Parser-Level Flags", 2),
                table(
                    ["Notebook", "Reason", "Detail"],
                    [
                        [
                            _safe_value(item.get("notebook")),
                            _safe_value(item.get("reason")),
                            _safe_value(item.get("detail")),
                        ]
                        for item in manual_review_items
                    ],
                ),
            ]
        )

    if validation_warnings:
        lines.extend(
            [
                "",
                heading("Validation Warnings", 2),
                table(
                    ["Notebook", "Category", "Message", "Detail"],
                    [
                        [
                            _safe_value(item.get("notebook")),
                            _safe_value(item.get("category")),
                            _safe_value(item.get("message")),
                            _safe_value(item.get("detail")),
                        ]
                        for item in validation_warnings
                    ],
                ),
            ]
        )

    lines.extend(_render_database_connections(database_connections))
    lines.extend(_render_secret_references(secret_references))
    lines.extend(_render_credential_findings(credential_findings))

    return "\n".join(lines)
