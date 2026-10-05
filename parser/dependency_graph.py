"""
parser.dependency_graph
=========================
Builds a directed graph of notebook-to-notebook dependencies using
NetworkX. Nodes are notebook relative paths; edges represent a resolved
`%run` or `dbutils.notebook.run` reference from one notebook to another.

Provides cycle detection (a real migration risk — circular %run chains
will fail identically on either platform, so this is worth surfacing
regardless of cloud) and a topological execution order, plus a Graphviz
DOT export for the Reporting Engine's future dependency-graph diagram.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import networkx as nx

from parser.dependency_extractor import NotebookDependency


@dataclass
class DependencyGraphSummary:
    node_count: int
    edge_count: int
    is_acyclic: bool
    cycles: List[List[str]] = field(default_factory=list)
    topological_order: Optional[List[str]] = None
    unresolved_references: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "is_acyclic": self.is_acyclic,
            "cycles": self.cycles,
            "topological_order": self.topological_order,
            "unresolved_references": self.unresolved_references,
        }


class DependencyGraphBuilder:
    """Builds and analyzes a NetworkX DiGraph from resolved notebook dependencies."""

    def build(
        self, notebook_paths: List[str], dependencies: List[NotebookDependency]
    ) -> "nx.DiGraph":
        graph = nx.DiGraph()
        graph.add_nodes_from(notebook_paths)

        for dep in dependencies:
            if dep.is_resolved:
                graph.add_edge(
                    dep.source_notebook,
                    dep.resolved_target,
                    dependency_type=dep.dependency_type,
                )
        return graph

    def summarize(
        self, graph: "nx.DiGraph", dependencies: List[NotebookDependency]
    ) -> DependencyGraphSummary:
        is_acyclic = nx.is_directed_acyclic_graph(graph)
        cycles = [] if is_acyclic else [list(c) for c in nx.simple_cycles(graph)]
        topo_order = list(nx.topological_sort(graph)) if is_acyclic else None
        unresolved = [dep.to_dict() for dep in dependencies if not dep.is_resolved]

        return DependencyGraphSummary(
            node_count=graph.number_of_nodes(),
            edge_count=graph.number_of_edges(),
            is_acyclic=is_acyclic,
            cycles=cycles,
            topological_order=topo_order,
            unresolved_references=unresolved,
        )

    def to_dot(self, graph: "nx.DiGraph") -> str:
        """Graphviz DOT representation, for the future Reporting Engine's
        dependency-graph visualization."""
        lines = ["digraph NotebookDependencies {", '  rankdir="LR";']
        for node in graph.nodes:
            lines.append(f'  "{node}";')
        for source, target, attrs in graph.edges(data=True):
            dep_type = attrs.get("dependency_type", "")
            lines.append(f'  "{source}" -> "{target}" [label="{dep_type}"];')
        lines.append("}")
        return "\n".join(lines)
