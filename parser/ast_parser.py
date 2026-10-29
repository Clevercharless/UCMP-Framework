"""
parser.ast_parser
===================
Structural parsing of Python notebook source using the standard library AST.

In addition to general Python structure, this parser identifies common database
connections, Spark JDBC write chains, Databricks secret retrieval calls, and
credential arguments. Credential values are never copied into findings.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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
    category: str
    snippet: str
    line_number: int
    notebook_reference_target: Optional[str] = None

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
    database_connections: List[Dict] = field(default_factory=list)
    secret_references: List[Dict] = field(default_factory=list)
    credential_findings: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "imports": [f.to_dict() for f in self.imports],
            "assignments": [f.to_dict() for f in self.assignments],
            "function_defs": [f.to_dict() for f in self.function_defs],
            "calls": [f.to_dict() for f in self.calls],
            "database_connections": self.database_connections,
            "secret_references": self.secret_references,
            "credential_findings": self.credential_findings,
        }


_MAX_SNIPPET_LEN = 160
_CREDENTIAL_NAMES = {"password", "passwd", "pwd", "token", "secret", "secret_key", "access_key", "client_secret"}


class ASTParser:
    """Parses Python notebook source into structured findings."""

    def parse(self, source: str, relative_path: str) -> ASTFindings:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ParserError(f"Notebook '{relative_path}' is not valid Python: {exc}") from exc

        findings = ASTFindings()
        assignments_by_name: Dict[str, ast.AST] = {}

        # Collect simple assignments first so credential references can be linked
        # to a variable assigned from dbutils.secrets.get(), regardless of AST walk order.
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if value is not None:
                    for target in targets:
                        if isinstance(target, ast.Name):
                            assignments_by_name[target.id] = value

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    findings.imports.append(ImportFinding(module=alias.name, line_number=node.lineno))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    findings.imports.append(ImportFinding(module=f"{module}.{alias.name}", line_number=node.lineno))
            elif isinstance(node, ast.FunctionDef):
                findings.function_defs.append(FunctionDefFinding(name=node.name, line_number=node.lineno, arg_count=len(node.args.args)))
            elif isinstance(node, ast.Assign):
                findings.assignments.append(self._assignment_finding(node))
                self._collect_assignment_credentials(node.targets, node.value, node.lineno, findings, assignments_by_name)
            elif isinstance(node, ast.AnnAssign):
                findings.assignments.append(self._ann_assignment_finding(node))
                if node.value is not None:
                    self._collect_assignment_credentials([node.target], node.value, node.lineno, findings, assignments_by_name)
            elif isinstance(node, ast.Call):
                call_finding = self._classify_call(node)
                if call_finding is not None:
                    findings.calls.append(call_finding)
                self._collect_secret_reference(node, findings)
                self._collect_mysql_connector(node, findings, assignments_by_name)
                self._collect_credential_arguments(node, findings, assignments_by_name)
                self._collect_spark_jdbc_write(node, findings, assignments_by_name)

        # Capture standalone JDBC URL assignments, too (not only Spark .option chains).
        existing_urls = {item.get("url") for item in findings.database_connections if item.get("url")}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                url = self._string_value(node.value)
                if url and url.lower().startswith("jdbc:") and url not in existing_urls:
                    findings.database_connections.append({
                        "connection_type": self._jdbc_type(url),
                        "detection_method": "jdbc_url_assignment",
                        "line_number": node.lineno,
                        "url": self._redact_connection_string(url),
                    })
                    existing_urls.add(url)

        # De-duplicate findings produced by nested AST calls.
        findings.secret_references = self._dedupe_dicts(findings.secret_references, ("line_number", "api", "scope", "key"))
        findings.credential_findings = self._dedupe_dicts(findings.credential_findings, ("line_number", "credential_type", "variable", "source_is_secret_reference"))
        findings.database_connections = self._dedupe_dicts(findings.database_connections, ("connection_type", "detection_method", "line_number", "url", "host", "database"))
        return findings

    def _assignment_finding(self, node: ast.Assign) -> AssignmentFinding:
        targets = [self._safe_unparse(t) for t in node.targets]
        target_str = ", ".join(targets)
        value_snippet = "[REDACTED]" if any(self._is_credential_name(target) for target in targets) else self._redact_snippet(self._safe_unparse(node.value))[:_MAX_SNIPPET_LEN]
        return AssignmentFinding(target=target_str, value_snippet=value_snippet, line_number=node.lineno)

    def _ann_assignment_finding(self, node: ast.AnnAssign) -> AssignmentFinding:
        target = self._safe_unparse(node.target)
        value_snippet = "[REDACTED]" if self._is_credential_name(target) else (self._redact_snippet(self._safe_unparse(node.value))[:_MAX_SNIPPET_LEN] if node.value else "")
        return AssignmentFinding(target=target, value_snippet=value_snippet, line_number=node.lineno)

    def _collect_assignment_credentials(self, targets, value_node: ast.AST, line_number: int, findings: ASTFindings, assignments: Dict[str, ast.AST]) -> None:
        for target in targets:
            if not isinstance(target, ast.Name) or not self._is_credential_name(target.id):
                continue
            source_api = self._call_name(value_node.func) if isinstance(value_node, ast.Call) else None
            source_is_secret = bool(source_api and ("dbutils.secrets.get" in source_api.lower() or ".secrets.get" in source_api.lower()))
            literal = isinstance(value_node, ast.Constant) and isinstance(value_node.value, str)
            findings.credential_findings.append({
                "credential_type": target.id.lower(),
                "line_number": line_number,
                "variable": target.id,
                "literal_value_redacted": "[REDACTED]" if literal and value_node.value else None,
                "is_hardcoded_literal": literal and bool(value_node.value),
                "source_is_secret_reference": source_is_secret,
                "source_api": source_api if source_is_secret else None,
            })

    def _classify_call(self, node: ast.Call) -> Optional[CallFinding]:
        snippet = self._redact_snippet(self._safe_unparse(node))[:_MAX_SNIPPET_LEN]
        lowered = snippet.lower()
        call_name = self._call_name(node.func).lower()
        if "dbutils.notebook.run" in lowered:
            return CallFinding(category="notebook_reference", snippet=snippet, line_number=node.lineno, notebook_reference_target=self._first_string_arg(node))
        if call_name.endswith("mysql.connector.connect"):
            return CallFinding(category="database_connection", snippet=snippet, line_number=node.lineno)
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
        if self._call_has_resolvable_name(node):
            return CallFinding(category="function_call", snippet=snippet, line_number=node.lineno)
        return None

    def _collect_secret_reference(self, node: ast.Call, findings: ASTFindings) -> None:
        name = self._call_name(node.func).lower()
        if name not in {"dbutils.secrets.get", "dbutils.secrets.getbytes"} and not name.endswith(".secrets.get") and not name.endswith(".secrets.getbytes"):
            return
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        findings.secret_references.append({
            "api": name,
            "line_number": node.lineno,
            "scope": self._string_value(kwargs.get("scope")),
            "key": self._string_value(kwargs.get("key")),
            "scope_is_literal": isinstance(kwargs.get("scope"), ast.Constant) and isinstance(kwargs["scope"].value, str),
            "key_is_literal": isinstance(kwargs.get("key"), ast.Constant) and isinstance(kwargs["key"].value, str),
        })

    def _collect_mysql_connector(self, node: ast.Call, findings: ASTFindings, assignments: Dict[str, ast.AST]) -> None:
        name = self._call_name(node.func).lower()
        if not (name.endswith("mysql.connector.connect") or name == "connect" and self._safe_unparse(node.func).lower().endswith("mysql.connector.connect")):
            return
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        password_node = kwargs.get("password") or kwargs.get("passwd")
        findings.database_connections.append({
            "connection_type": "mysql",
            "detection_method": "mysql_connector_connect",
            "line_number": node.lineno,
            "host": self._safe_config_value(kwargs.get("host")),
            "database": self._safe_config_value(kwargs.get("database")),
            "username": self._safe_config_value(kwargs.get("user")),
            "password_argument_present": password_node is not None,
            "password_is_variable": isinstance(password_node, ast.Name),
        })
        if password_node is not None:
            self._add_credential_finding(password_node, "password", node.lineno, findings, assignments)

    def _collect_spark_jdbc_write(self, node: ast.Call, findings: ASTFindings, assignments: Dict[str, ast.AST]) -> None:
        # Only inspect outer .save() calls. The nested AST represents the whole
        # chained .format(...).option(...).save() expression, including multiline chains.
        if not isinstance(node.func, ast.Attribute) or node.func.attr.lower() != "save":
            return
        chain_calls = list(self._calls_in_chain(node))
        format_jdbc = any(
            isinstance(call.func, ast.Attribute) and call.func.attr == "format"
            and call.args and self._string_value(call.args[0]) and self._string_value(call.args[0]).lower() == "jdbc"
            for call in chain_calls
        )
        options: Dict[str, ast.AST] = {}
        for call in chain_calls:
            if isinstance(call.func, ast.Attribute) and call.func.attr == "option" and len(call.args) >= 2:
                option_name = self._string_value(call.args[0])
                if option_name:
                    options[option_name.lower()] = call.args[1]
        url = self._string_value(options.get("url"))
        driver = self._string_value(options.get("driver"))
        looks_jdbc = format_jdbc or bool(url and url.lower().startswith("jdbc:")) or bool(driver and "jdbc" in driver.lower())
        if not looks_jdbc:
            return
        findings.database_connections.append({
            "connection_type": self._jdbc_type(url or "", driver),
            "detection_method": "spark_jdbc_write",
            "line_number": node.lineno,
            "driver": driver,
            "url": self._redact_connection_string(url) if url else None,
            "table": self._safe_config_value(options.get("dbtable")),
            "username": self._safe_config_value(options.get("user")),
            "write_mode": self._chain_string_arg(chain_calls, "mode"),
            "password_argument_present": "password" in options,
            "password_is_variable": isinstance(options.get("password"), ast.Name),
        })
        if "password" in options:
            self._add_credential_finding(options["password"], "password", node.lineno, findings, assignments)

    def _collect_credential_arguments(self, node: ast.Call, findings: ASTFindings, assignments: Dict[str, ast.AST]) -> None:
        for keyword in node.keywords:
            if keyword.arg and keyword.arg.lower() in _CREDENTIAL_NAMES:
                self._add_credential_finding(keyword.value, keyword.arg.lower(), node.lineno, findings, assignments)
        if isinstance(node.func, ast.Attribute) and node.func.attr.lower() == "option" and len(node.args) >= 2:
            option_name = self._string_value(node.args[0])
            if option_name and option_name.lower() in _CREDENTIAL_NAMES:
                self._add_credential_finding(node.args[1], option_name.lower(), node.lineno, findings, assignments)

    def _add_credential_finding(self, value_node: ast.AST, credential_type: str, line_number: int, findings: ASTFindings, assignments: Dict[str, ast.AST]) -> None:
        variable = value_node.id if isinstance(value_node, ast.Name) else None
        literal = isinstance(value_node, ast.Constant) and isinstance(value_node.value, str)
        source_is_secret = False
        source_api = None
        if variable and variable in assignments:
            source_node = assignments[variable]
            if isinstance(source_node, ast.Call):
                source_api = self._call_name(source_node.func)
                source_is_secret = "dbutils.secrets.get" in source_api.lower() or ".secrets.get" in source_api.lower()
        findings.credential_findings.append({
            "credential_type": credential_type,
            "line_number": line_number,
            "variable": variable,
            "literal_value_redacted": "[REDACTED]" if literal and value_node.value else None,
            "is_hardcoded_literal": literal and bool(value_node.value),
            "source_is_secret_reference": source_is_secret,
            "source_api": source_api if source_is_secret else None,
        })

    @staticmethod
    def _calls_in_chain(node: ast.Call):
        current = node
        while isinstance(current, ast.Call):
            yield current
            func = current.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
                current = func.value
            else:
                break

    @staticmethod
    def _chain_string_arg(calls, method_name: str) -> Optional[str]:
        for call in calls:
            if isinstance(call.func, ast.Attribute) and call.func.attr == method_name and call.args:
                return ASTParser._string_value(call.args[0])
        return None

    @staticmethod
    def _jdbc_type(url: str, driver: Optional[str] = None) -> str:
        lowered = (url or "").lower()
        driver_lower = (driver or "").lower()
        for name in ("mysql", "postgresql", "postgres", "sqlserver", "oracle", "mariadb", "redshift", "db2", "snowflake"):
            if f"jdbc:{name}:" in lowered or name in driver_lower:
                return "postgresql" if name == "postgres" else name
        return "jdbc_unknown"

    @staticmethod
    def _redact_connection_string(value: str) -> str:
        # Do not persist credential-like URL parameters or user-info in reports.
        import re
        value = re.sub(r"(?i)(password|passwd|pwd|token|secret)=([^;&\s]+)", r"\1=[REDACTED]", value)
        value = re.sub(r"(://)[^/@:\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        return value

    @staticmethod
    def _redact_snippet(value: str) -> str:
        """Redact inline credential literals from AST snippets before reporting."""
        import re
        value = re.sub(
            r"(?i)(password|passwd|pwd|token|client_secret|access_key)\s*=\s*(['\"])(.*?)\2",
            r"\1=\2[REDACTED]\2",
            value,
        )
        value = re.sub(
            r"(?i)(\.option\(\s*['\"](?:password|passwd|pwd|token|client_secret|access_key)['\"]\s*,\s*)(['\"])(.*?)\2",
            r"\1\2[REDACTED]\2",
            value,
        )
        return ASTParser._redact_connection_string(value)

    @staticmethod
    def _is_credential_name(name: str) -> bool:
        lowered = name.lower()
        return any(term in lowered for term in ("password", "passwd", "pwd", "token", "secret", "access_key", "client_secret"))

    @staticmethod
    def _safe_config_value(node: Optional[ast.AST]) -> Optional[str]:
        if node is None:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return f"<variable:{node.id}>"
        return f"<expression:{type(node).__name__}>"

    @staticmethod
    def _string_value(node: Optional[ast.AST]) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _dedupe_dicts(items: List[Dict], keys) -> List[Dict]:
        result = []
        seen = set()
        for item in items:
            marker = tuple(item.get(key) for key in keys)
            if marker not in seen:
                seen.add(marker)
                result.append(item)
        return result

    @staticmethod
    def _call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = ASTParser._call_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

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
    def _safe_unparse(node: Optional[ast.AST]) -> str:
        if node is None:
            return ""
        try:
            return ast.unparse(node)
        except Exception:  # noqa: BLE001
            return "<unparseable>"
