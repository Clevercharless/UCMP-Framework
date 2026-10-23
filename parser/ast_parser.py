"""
parser.ast_parser
===================
Structural parsing of Python notebook source using the standard library
`ast` module. Because Databricks' export format renders magic commands as
ordinary comment lines (`# MAGIC ...`), an entire exported Python notebook
is valid, parseable Python — no preprocessing needed beyond reading the
file.

Detects, per the spec:
  * Imports
  * Assignments / variables
  * Function definitions (treated as "business objects" — reusable logic
    that must survive migration untouched)
  * Function calls, classified into: spark_read, spark_write, dbutils_call,
    delta_api, notebook_reference (dbutils.notebook.run), or generic
    function_call
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import List, Optional

from common.exceptions import ParserError


@dataclass
class ImportFinding:
    module: str
    line_number: int

    def to_dict(self) -> dict:
        return {"module": self.module, "line_number": self.line_number}


@dataclass
class AssignmentFinding:
    target: str
    value_snippet: str
    line_number: int

    def to_dict(self) -> dict:
        return {"target": self.target, "value_snippet": self.value_snippet, "line_number": self.line_number}


@dataclass
class FunctionDefFinding:
    name: str
    line_number: int
    arg_count: int

    def to_dict(self) -> dict:
        return {"name": self.name, "line_number": self.line_number, "arg_count": self.arg_count}


@dataclass
class CallFinding:
    category: str  # spark_read | spark_write | dbutils_call | delta_api | notebook_reference | function_call
    snippet: str
    line_number: int
    notebook_reference_target: Optional[str] = None  # populated only for category == notebook_reference

    def to_dict(self) -> dict:
        result = {"category": self.category, "snippet": self.snippet, "line_number": self.line_number}
        if self.notebook_reference_target is not None:
            result["notebook_reference_target"] = self.notebook_reference_target
        return result


@dataclass
class ASTFindings:
    imports: List[ImportFinding] = field(default_factory=list)
    assignments: List[AssignmentFinding] = field(default_factory=list)
    function_defs: List[FunctionDefFinding] = field(default_factory=list)
    calls: List[CallFinding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "imports": [f.to_dict() for f in self.imports],
            "assignments": [f.to_dict() for f in self.assignments],
            "function_defs": [f.to_dict() for f in self.function_defs],
            "calls": [f.to_dict() for f in self.calls],
        }


_MAX_SNIPPET_LEN = 160


class ASTParser:
    """Parses Python notebook source into structured findings."""

    def parse(self, source: str, relative_path: str) -> ASTFindings:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ParserError(f"Notebook '{relative_path}' is not valid Python: {exc}") from exc

        findings = ASTFindings()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    findings.imports.append(ImportFinding(module=alias.name, line_number=node.lineno))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    findings.imports.append(
                        ImportFinding(module=f"{module}.{alias.name}", line_number=node.lineno)
                    )
            elif isinstance(node, ast.FunctionDef):
                findings.function_defs.append(
                    FunctionDefFinding(
                        name=node.name, line_number=node.lineno, arg_count=len(node.args.args)
                    )
                )
            elif isinstance(node, ast.Assign):
                findings.assignments.append(self._assignment_finding(node))
            elif isinstance(node, ast.Call):
                call_finding = self._classify_call(node)
                if call_finding is not None:
                    findings.calls.append(call_finding)

        return findings

    # -- internals --------------------------------------------------------

    def _assignment_finding(self, node: ast.Assign) -> AssignmentFinding:
        targets = [self._safe_unparse(t) for t in node.targets]
        target_str = ", ".join(targets)
        value_snippet = self._safe_unparse(node.value)[:_MAX_SNIPPET_LEN]
        return AssignmentFinding(target=target_str, value_snippet=value_snippet, line_number=node.lineno)

    def _classify_call(self, node: ast.Call) -> Optional[CallFinding]:
        snippet = self._safe_unparse(node)[:_MAX_SNIPPET_LEN]
        lowered = snippet.lower()

        if "dbutils.notebook.run" in lowered:
            target = self._first_string_arg(node)
            return CallFinding(
                category="notebook_reference",
                snippet=snippet,
                line_number=node.lineno,
                notebook_reference_target=target,
            )
        if ".format(\"delta\")" in lowered or ".format('delta')" in lowered or "deltatable" in lowered:
            return CallFinding(category="delta_api", snippet=snippet, line_number=node.lineno)
        if ".write." in lowered and ("spark" in lowered or lowered.count(".") >= 2):
            return CallFinding(category="spark_write", snippet=snippet, line_number=node.lineno)
        if "spark.read" in lowered:
            return CallFinding(category="spark_read", snippet=snippet, line_number=node.lineno)
        if lowered.startswith("spark.sql") or ".spark.sql" in lowered:
            return CallFinding(category="spark_sql", snippet=snippet, line_number=node.lineno)
        if lowered.startswith("dbutils.") or ".dbutils." in lowered:
            return CallFinding(category="dbutils_call", snippet=snippet, line_number=node.lineno)

        # Skip trivial/no-name calls (e.g. lambda invocations) — only report
        # calls with a resolvable name to keep findings meaningful.
        if self._call_has_resolvable_name(node):
            return CallFinding(category="function_call", snippet=snippet, line_number=node.lineno)
        return None

    @staticmethod
    def _call_has_resolvable_name(node: ast.Call) -> bool:
        return isinstance(node.func, (ast.Name, ast.Attribute))

    @staticmethod
    def _first_string_arg(node: ast.Call) -> Optional[str]:
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return arg.value
            if isinstance(arg, ast.Name):
                return arg.id
        return None

    @staticmethod
    def _safe_unparse(node: ast.AST) -> str:
        try:
            return ast.unparse(node)
        except Exception:  # noqa: BLE001 - defensive; ast.unparse should not fail here
            return "<unparseable>"
