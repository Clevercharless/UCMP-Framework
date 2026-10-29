"""
parser.knowledge_model
========================
Defines `NotebookParseResult` (everything the Parser Engine learned about
one notebook) and `KnowledgeModelGenerator`, which aggregates every
notebook's results plus the dependency graph into the final
`MigrationKnowledgeModel` — serialized as `MigrationKnowledgeModel.json`.

Per the spec, the model has seven sections: Notebook Metadata,
Dependencies, Azure Constructs, Configuration References, Transformation
Candidates, Business Objects, and Manual Review Items. The
`rule_category_hint` attached to each transformation candidate deliberately
foreshadows Module 6's Rule Repository file names (storage_rules.yaml,
secret_rules.yaml, workspace_rules.yaml, library_rules.yaml) so the Rule
Service can do a direct lookup later without re-deriving the mapping.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parser.ast_parser import ASTFindings
from parser.dependency_extractor import NotebookDependency
from parser.dependency_graph import DependencyGraphSummary
from parser.magic_parser import MagicCommand
from parser.migration_analyzer import NotebookMigrationAnalysis
from parser.regex_parser import AzureConstruct, AzureConstructType, GeneralConstruct
from parser.sql_parser import SQLFindings

_RULE_CATEGORY_HINTS = {
    AzureConstructType.ABFSS_PATH: "storage_rules",
    AzureConstructType.BLOB_STORAGE: "storage_rules",
    AzureConstructType.MOUNT_PATH: "storage_rules",
    AzureConstructType.WORKSPACE_URL: "workspace_rules",
    AzureConstructType.KEY_VAULT: "secret_rules",
    AzureConstructType.AZURE_SDK_IMPORT: "library_rules",
    AzureConstructType.HARDCODED_URL: "api_rules",
}

# Construct types treated as "configuration" (environment/identity plumbing)
# rather than "transformation candidates" (data-path/code constructs).
_CONFIGURATION_CONSTRUCT_TYPES = {
    AzureConstructType.KEY_VAULT,
    AzureConstructType.WORKSPACE_URL,
    AzureConstructType.MOUNT_PATH,
}


@dataclass
class NotebookParseResult:
    """Everything the Parser Engine learned about a single notebook."""

    relative_path: str
    category: str
    language: str
    cell_count: int
    magic_commands: List[MagicCommand] = field(default_factory=list)
    azure_constructs: List[AzureConstruct] = field(default_factory=list)
    general_constructs: List[GeneralConstruct] = field(default_factory=list)
    ast_findings: Optional[ASTFindings] = None
    sql_findings: Optional[SQLFindings] = None
    parse_error: Optional[str] = None
    migration_analysis: Optional[NotebookMigrationAnalysis] = None


@dataclass
class MigrationKnowledgeModel:
    repo_name: str
    notebook_metadata: List[Dict] = field(default_factory=list)
    dependencies: Dict = field(default_factory=dict)
    azure_constructs: List[Dict] = field(default_factory=list)
    database_connections: List[Dict] = field(default_factory=list)
    secret_references: List[Dict] = field(default_factory=list)
    credential_findings: List[Dict] = field(default_factory=list)
    general_constructs: List[Dict] = field(default_factory=list)
    configuration_references: List[Dict] = field(default_factory=list)
    transformation_candidates: List[Dict] = field(default_factory=list)
    business_objects: List[Dict] = field(default_factory=list)
    manual_review_items: List[Dict] = field(default_factory=list)
    migration_scope: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "repo_name": self.repo_name,
            "notebook_metadata": self.notebook_metadata,
            "dependencies": self.dependencies,
            "azure_constructs": self.azure_constructs,
            "database_connections": self.database_connections,
            "secret_references": self.secret_references,
            "credential_findings": self.credential_findings,
            "general_constructs": self.general_constructs,
            "configuration_references": self.configuration_references,
            "transformation_candidates": self.transformation_candidates,
            "business_objects": self.business_objects,
            "manual_review_items": self.manual_review_items,
            "migration_scope": self.migration_scope,
        }


class KnowledgeModelGenerator:
    """Aggregates per-notebook parse results + the dependency graph into a MigrationKnowledgeModel."""

    def generate(
        self,
        repo_name: str,
        notebook_results: List[NotebookParseResult],
        dependencies: List[NotebookDependency],
        graph_summary: DependencyGraphSummary,
    ) -> MigrationKnowledgeModel:
        model = MigrationKnowledgeModel(repo_name=repo_name)

        model.notebook_metadata = self._build_notebook_metadata(notebook_results)
        model.dependencies = {
            "edges": [d.to_dict() for d in dependencies],
            "graph_summary": graph_summary.to_dict(),
        }

        all_constructs = [
            (result.relative_path, construct)
            for result in notebook_results
            for construct in result.azure_constructs
        ]
        model.azure_constructs = self._aggregate_constructs(all_constructs)
        model.general_constructs = self._aggregate_general_constructs(notebook_results)
        model.database_connections = self._aggregate_ast_section(notebook_results, "database_connections")
        model.secret_references = self._aggregate_ast_section(notebook_results, "secret_references")
        model.credential_findings = self._aggregate_ast_section(notebook_results, "credential_findings")
        # Regex URL detection remains available even if Python AST parsing fails or
        # the URL occurs in a comment/SQL string rather than a Python call.
        self._merge_regex_jdbc_findings(model.database_connections, notebook_results)
        self._merge_regex_secret_findings(model.secret_references, notebook_results)
        model.configuration_references = self._build_configuration_references(all_constructs)
        model.transformation_candidates = self._build_transformation_candidates(all_constructs)
        model.business_objects = self._build_business_objects(notebook_results)
        model.manual_review_items = self._build_manual_review_items(
            notebook_results, graph_summary
        )

        return model

    # -- section builders -----------------------------------------------

    def _aggregate_general_constructs(self, results: List[NotebookParseResult]) -> List[Dict]:
        output = []
        seen = set()
        for result in results:
            for finding in result.general_constructs:
                item = finding.to_dict()
                item["notebook"] = result.relative_path
                key = (item["notebook"], item["category"], item["value"], item["line_number"])
                if key not in seen:
                    seen.add(key)
                    output.append(item)
        return sorted(output, key=lambda item: (item["notebook"], item["line_number"], item["category"]))

    def _aggregate_ast_section(self, results: List[NotebookParseResult], section: str) -> List[Dict]:
        output = []
        seen = set()
        for result in results:
            if not result.ast_findings:
                continue
            for finding in getattr(result.ast_findings, section, []):
                item = dict(finding)
                item["notebook"] = result.relative_path
                key = (result.relative_path, section, tuple(sorted((k, str(v)) for k, v in item.items() if k != "notebook")))
                if key not in seen:
                    seen.add(key)
                    output.append(item)
        return sorted(output, key=lambda item: (item["notebook"], item.get("line_number", 0)))

    def _merge_regex_jdbc_findings(self, connections: List[Dict], results: List[NotebookParseResult]) -> None:
        seen = {(item.get("notebook"), item.get("url")) for item in connections}
        for result in results:
            for finding in result.general_constructs:
                if finding.category != "jdbc_url":
                    continue
                key = (result.relative_path, finding.value)
                if key in seen:
                    continue
                seen.add(key)
                jdbc_lower = finding.value.lower()
                connection_type = next((name for name in ("mysql", "postgresql", "sqlserver", "oracle", "mariadb", "redshift", "db2", "snowflake") if f"jdbc:{name}:" in jdbc_lower), "jdbc_unknown")
                connections.append({
                    "notebook": result.relative_path,
                    "connection_type": connection_type,
                    "detection_method": "regex_jdbc_url",
                    "line_number": finding.line_number,
                    "url": finding.value,
                })

    def _merge_regex_secret_findings(self, secrets: List[Dict], results: List[NotebookParseResult]) -> None:
        seen = {(item.get("notebook"), item.get("line_number")) for item in secrets}
        for result in results:
            for finding in result.general_constructs:
                if finding.category != "secret_retrieval_api":
                    continue
                key = (result.relative_path, finding.line_number)
                if key in seen:
                    continue
                seen.add(key)
                secrets.append({
                    "notebook": result.relative_path,
                    "api": "dbutils.secrets.get",
                    "line_number": finding.line_number,
                    "scope": None,
                    "key": None,
                    "detection_method": "regex_fallback",
                })

    def _build_notebook_metadata(self, results: List[NotebookParseResult]) -> List[Dict]:
        metadata = []
        for result in results:
            entry = {
                "relative_path": result.relative_path,
                "category": result.category,
                "language": result.language,
                "cell_count": result.cell_count,
                "magic_command_count": len(result.magic_commands),
                "azure_construct_count": len(result.azure_constructs),
                "general_construct_count": len(result.general_constructs),
                "database_connection_count": len(result.ast_findings.database_connections) if result.ast_findings else 0,
                "secret_reference_count": len(result.ast_findings.secret_references) if result.ast_findings else 0,
                "credential_finding_count": len(result.ast_findings.credential_findings) if result.ast_findings else 0,
                "parse_error": result.parse_error,
                "migration_classification": "CHANGED" if result.migration_analysis and result.migration_analysis.changed else "NO_CHANGE",
                "review_required": bool(result.migration_analysis and result.migration_analysis.requires_review),
            }
            if result.ast_findings is not None:
                entry["import_count"] = len(result.ast_findings.imports)
                entry["function_def_count"] = len(result.ast_findings.function_defs)
                entry["call_count"] = len(result.ast_findings.calls)
            if result.sql_findings is not None:
                entry["sql_statement_count"] = len(result.sql_findings.statements)
                entry["table_dependency_count"] = len(result.sql_findings.table_dependencies)
            metadata.append(entry)
        return metadata

    def _aggregate_constructs(self, all_constructs) -> List[Dict]:
        grouped: Dict[tuple, Dict] = {}
        for notebook_path, construct in all_constructs:
            key = (construct.construct_type, construct.value)
            if key not in grouped:
                grouped[key] = {
                    "construct_type": construct.construct_type.value,
                    "value": construct.value,
                    "occurrences": 0,
                    "found_in": [],
                }
            grouped[key]["occurrences"] += 1
            if notebook_path not in grouped[key]["found_in"]:
                grouped[key]["found_in"].append(notebook_path)
        return sorted(grouped.values(), key=lambda d: (d["construct_type"], d["value"]))

    def _build_configuration_references(self, all_constructs) -> List[Dict]:
        grouped: Dict[tuple, Dict] = {}
        for notebook_path, construct in all_constructs:
            if construct.construct_type not in _CONFIGURATION_CONSTRUCT_TYPES:
                continue
            key = (construct.construct_type, construct.value)
            if key not in grouped:
                grouped[key] = {
                    "reference_type": construct.construct_type.value,
                    "value": construct.value,
                    "occurrences": 0,
                    "found_in": [],
                }
            grouped[key]["occurrences"] += 1
            if notebook_path not in grouped[key]["found_in"]:
                grouped[key]["found_in"].append(notebook_path)
        return sorted(grouped.values(), key=lambda d: (d["reference_type"], d["value"]))

    def _build_transformation_candidates(self, all_constructs) -> List[Dict]:
        grouped: Dict[tuple, Dict] = {}
        for notebook_path, construct in all_constructs:
            key = (construct.construct_type, construct.value)
            if key not in grouped:
                grouped[key] = {
                    "construct_type": construct.construct_type.value,
                    "value": construct.value,
                    "rule_category_hint": _RULE_CATEGORY_HINTS.get(construct.construct_type, "api_rules"),
                    "occurrences": 0,
                    "found_in": [],
                }
            grouped[key]["occurrences"] += 1
            if notebook_path not in grouped[key]["found_in"]:
                grouped[key]["found_in"].append(notebook_path)
        return sorted(grouped.values(), key=lambda d: (d["rule_category_hint"], d["value"]))

    def _build_business_objects(self, results: List[NotebookParseResult]) -> List[Dict]:
        tables: Dict[str, Dict] = {}
        for result in results:
            if result.sql_findings:
                for table_name in result.sql_findings.table_dependencies:
                    entry = tables.setdefault(
                        table_name, {"name": table_name, "type": "table", "referenced_in": []}
                    )
                    if result.relative_path not in entry["referenced_in"]:
                        entry["referenced_in"].append(result.relative_path)

        functions: List[Dict] = []
        for result in results:
            if result.category != "Common" or not result.ast_findings:
                continue
            for func in result.ast_findings.function_defs:
                functions.append(
                    {
                        "name": func.name,
                        "type": "shared_function",
                        "defined_in": result.relative_path,
                        "arg_count": func.arg_count,
                    }
                )

        return sorted(tables.values(), key=lambda d: d["name"]) + sorted(
            functions, key=lambda d: d["name"]
        )

    def _build_manual_review_items(
        self, results: List[NotebookParseResult], graph_summary: DependencyGraphSummary
    ) -> List[Dict]:
        items: List[Dict] = []

        for result in results:
            if result.parse_error:
                items.append(
                    {
                        "notebook": result.relative_path,
                        "reason": "Notebook could not be fully parsed",
                        "detail": result.parse_error,
                    }
                )
            for construct in result.azure_constructs:
                if construct.construct_type == AzureConstructType.HARDCODED_URL:
                    items.append(
                        {
                            "notebook": result.relative_path,
                            "reason": "External/hardcoded connection endpoint requires manual "
                            "review for AWS-side connectivity",
                            "detail": construct.value,
                        }
                    )

        for unresolved in graph_summary.unresolved_references:
            items.append(
                {
                    "notebook": unresolved["source_notebook"],
                    "reason": "Unresolved notebook reference — target could not be matched "
                    "to a known notebook in the repository",
                    "detail": unresolved["raw_reference"],
                }
            )

        if not graph_summary.is_acyclic:
            items.append(
                {
                    "notebook": "<repository>",
                    "reason": "Circular %run / dbutils.notebook.run dependency detected",
                    "detail": str(graph_summary.cycles),
                }
            )

        return items
