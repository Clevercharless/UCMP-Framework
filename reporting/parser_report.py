from __future__ import annotations

import re
from typing import Any, Dict, List

from reporting.markdown_utils import bullet_list, heading, kv_block, table


def _safe_value(value: Any) -> str:
    """Convert values to text and redact common credential patterns."""
    if value is None or value == "":
        return "-"

    text = str(value)

    # Redact passwords embedded in URLs.
    text = re.sub(
        r"(://[^:/@\s]+:)[^@\s]+(@)",
        r"\1[REDACTED]\2",
        text,
    )

    # Redact common sensitive key/value pairs.
    text = re.sub(
        r"""(?i)\b(password|passwd|pwd|token|secret|client_secret|
        api_key|apikey|access_key|secret_key)\b
        (\s*[=:]\s*)
        (['"]?)[^,\s;'"&]+""",
        lambda match: (
            match.group(1) + match.group(2) + "[REDACTED]"
        ),
        text,
        flags=re.VERBOSE,
    )

    return text


def _field(item: Dict[str, Any], *keys: str) -> str:
    """Return the first available non-empty field."""
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
            "Database connection references detected during parsing. "
            "Review the connection configuration and target connectivity."
        ),
        "",
    ]

    if not connections:
        lines.append("No database connection findings recorded.")
        return lines

    lines.append(
        table(
            [
                "Notebook",
                "Connection Type",
                "Line Number",
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
            "Secret references detected in source code. Verify that the "
            "required secrets and scopes are configured in the target "
            "environment."
        ),
        "",
    ]

    if not references:
        lines.append("No secret references recorded.")
        return lines

    lines.append(
        table(
            [
                "Notebook",
                "Line Number",
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
            "Credential-related findings identified during parsing. "
            "Raw credential values are intentionally not displayed."
        ),
        "",
    ]

    if not findings:
        lines.append("No credential findings recorded.")
        return lines

    lines.append(
        table(
            [
                "Notebook",
                "Line Number",
                "Finding Type",
                "Detection Method",
                "Description",
            ],
            [
                [
                    _field(item, "notebook", "relative_path"),
                    _field(item, "line_number"),
                    _field(
                        item,
                        "finding_type",
                        "credential_type",
                        "type",
                    ),
                    _field(item, "detection_method"),
                    _field(item, "description", "reason", "message"),
                ]
                for item in findings
            ],
        )
    )

    return lines


def _render_general_constructs(
    constructs: List[Dict[str, Any]],
) -> List[str]:
    lines = [
        "",
        heading("General Constructs Found", 2),
        "Additional constructs detected during parsing.",
        "",
    ]

    if not constructs:
        lines.append("No general constructs recorded.")
        return lines

    lines.append(
        table(
            [
                "Construct Type",
                "Value",
                "Notebook",
                "Line Number",
            ],
            [
                [
                    _field(item, "construct_type", "type"),
                    _field(item, "value", "name"),
                    _field(
                        item,
                        "notebook",
                        "relative_path",
                        "file_path",
                    ),
                    _field(item, "line_number", "lineno"),
                ]
                for item in constructs
            ],
        )
    )

    return lines


def build_parser_report(knowledge_model: Dict) -> str:
    # Existing Knowledge Model fields.
    metadata = knowledge_model.get("notebook_metadata", [])
    azure_constructs = knowledge_model.get("azure_constructs", [])
    business_objects = knowledge_model.get("business_objects", [])

    # Additional findings already stored in the Knowledge Model.
    database_connections = knowledge_model.get(
        "database_connections", []
    )
    secret_references = knowledge_model.get("secret_references", [])
    credential_findings = knowledge_model.get("credential_findings", [])
    general_constructs = knowledge_model.get("general_constructs", [])

    # Notebook summaries.
    by_category: Dict[str, int] = {}
    by_language: Dict[str, int] = {}

    for notebook in metadata:
        category = notebook.get("category", "Unknown")
        language = notebook.get("language", "Unknown")

        by_category[category] = by_category.get(category, 0) + 1
        by_language[language] = by_language.get(language, 0) + 1

    lines = [
        heading("Parser Report", 1),
        kv_block(
            [
                ("Repository", knowledge_model.get("repo_name", "-")),
                ("Notebooks parsed", len(metadata)),
                ("Unique Azure constructs found", len(azure_constructs)),
                ("Business objects preserved", len(business_objects)),
                (
                    "Changed notebooks",
                    sum(
                        1
                        for notebook in metadata
                        if notebook.get("migration_classification")
                        == "CHANGED"
                    ),
                ),
                (
                    "Notebooks requiring review",
                    sum(
                        1
                        for notebook in metadata
                        if notebook.get("review_required")
                    ),
                ),
                (
                    "Database / JDBC connections",
                    len(database_connections),
                ),
                ("Secret references", len(secret_references)),
                ("Credential findings", len(credential_findings)),
                ("General constructs", len(general_constructs)),
            ]
        ),
        "",
        heading("Notebooks by Category", 2),
        table(
            ["Category", "Count"],
            sorted(by_category.items()),
        ),
        "",
        heading("Notebooks by Language", 2),
        table(
            ["Language", "Count"],
            sorted(by_language.items()),
        ),
        "",
        heading("Notebook Inventory", 2),
        table(
            [
                "Path",
                "Category",
                "Language",
                "Cells",
                "Azure Constructs",
                "Classification",
                "Review",
                "Parse Error",
            ],
            [
                [
                    notebook.get("relative_path", "-"),
                    notebook.get("category", "-"),
                    notebook.get("language", "-"),
                    notebook.get("cell_count", 0),
                    notebook.get("azure_construct_count", 0),
                    notebook.get(
                        "migration_classification", "NO_CHANGE"
                    ),
                    (
                        "YES"
                        if notebook.get("review_required")
                        else "no"
                    ),
                    notebook.get("parse_error") or "-",
                ]
                for notebook in metadata
            ],
        ),
        "",
        heading("Azure Constructs Found (by type)", 2),
        table(
            ["Construct Type", "Value", "Occurrences", "Found In"],
            [
                [
                    _safe_value(item.get("construct_type")),
                    _safe_value(item.get("value")),
                    item.get("occurrences", 0),
                    ", ".join(item.get("found_in", [])),
                ]
                for item in azure_constructs
            ],
        ),
        "",
        heading("Business Objects Preserved (untouched)", 2),
        bullet_list(
            (
                f"[{item.get('type', 'unknown')}] "
                f"{item.get('name', 'unnamed')}"
                + (
                    f" (defined in {item.get('defined_in', '-')})"
                    if item.get("type") == "shared_function"
                    else (
                        " (referenced in "
                        f"{len(item.get('referenced_in', []))} notebook(s))"
                    )
                )
            )
            for item in business_objects
        ),
    ]

    # New report sections.
    lines.extend(
        _render_database_connections(database_connections)
    )
    lines.extend(
        _render_secret_references(secret_references)
    )
    lines.extend(
        _render_credential_findings(credential_findings)
    )
    lines.extend(
        _render_general_constructs(general_constructs)
    )

    return "\n".join(lines)
