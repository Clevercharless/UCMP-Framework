"""
reporting.dependency_report
=============================
Dependency Report: the notebook-to-notebook %run / dbutils.notebook.run
dependency graph the Parser Engine built (Module 5) - node/edge counts,
cyclicality, topological execution order, and any unresolved references.
"""

from __future__ import annotations

from typing import Dict

from reporting.markdown_utils import bullet_list, heading, kv_block, table


def build_dependency_report(knowledge_model: Dict) -> str:
    edges = knowledge_model["dependencies"]["edges"]
    graph_summary = knowledge_model["dependencies"]["graph_summary"]
    resolved_edges = [e for e in edges if e["is_resolved"]]

    scope = knowledge_model.get("migration_scope", {})
    lines = [
        heading("Dependency Report", 1),
        kv_block([
            ("Requested notebooks", len(scope.get("requested_notebooks", []))),
            ("Requested notebooks found", len(scope.get("found_notebooks", []))),
            ("Requested notebooks missing", len(scope.get("missing_notebooks", []))),
        ]) if scope else "",
        kv_block([
            ("Nodes (notebooks)", graph_summary["node_count"]),
            ("Edges (dependencies)", graph_summary["edge_count"]),
            ("Acyclic", graph_summary["is_acyclic"]),
            ("Unresolved references", len(graph_summary["unresolved_references"])),
        ]),
        "",
    ]

    if not graph_summary["is_acyclic"]:
        lines.append(heading("Cycles Detected", 2))
        lines.append(bullet_list(" -> ".join(cycle) for cycle in graph_summary["cycles"]))
        lines.append("")

    lines.append(heading("Resolved Dependencies", 2))
    lines.append(
        table(
            ["Source Notebook", "Type", "Target Notebook"],
            [[e["source_notebook"], e["dependency_type"], e["resolved_target"]] for e in resolved_edges],
        )
    )

    if graph_summary["unresolved_references"]:
        lines.append("")
        lines.append(heading("Unresolved References", 2))
        lines.append(
            table(
                ["Source Notebook", "Type", "Raw Reference"],
                [
                    [u["source_notebook"], u["dependency_type"], u["raw_reference"]]
                    for u in graph_summary["unresolved_references"]
                ],
            )
        )

    if graph_summary["topological_order"]:
        lines.append("")
        lines.append(heading("Topological Execution Order", 2))
        lines.append(
            bullet_list(
                f"{i}. {path}" for i, path in enumerate(graph_summary["topological_order"], start=1)
            )
        )

    return "\n".join(lines)
