"""
parser.sql_parser
===================
Lightweight, regex-based SQL parsing (not a full grammar — sufficient for
identifying which statement types and table names appear in a notebook,
which is all downstream modules need). Applied to:
  * Entire `.sql` notebooks (SQL-default language)
  * Individual `%sql` magic cells embedded in Python notebooks

Detects, per the spec: FROM, JOIN, MERGE, INSERT, UPDATE, DELETE,
CREATE TABLE, CREATE VIEW, and the table names each statement touches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set


class SQLStatementType(str, Enum):
    SELECT_FROM = "select_from"
    JOIN = "join"
    MERGE = "merge"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    CREATE_TABLE = "create_table"
    CREATE_VIEW = "create_view"


@dataclass
class SQLStatementFinding:
    statement_type: SQLStatementType
    table_name: str
    line_number: int

    def to_dict(self) -> dict:
        return {
            "statement_type": self.statement_type.value,
            "table_name": self.table_name,
            "line_number": self.line_number,
        }


@dataclass
class SQLFindings:
    statements: List[SQLStatementFinding] = field(default_factory=list)

    @property
    def table_dependencies(self) -> List[str]:
        seen: Set[str] = set()
        ordered: List[str] = []
        for stmt in self.statements:
            if stmt.table_name not in seen:
                seen.add(stmt.table_name)
                ordered.append(stmt.table_name)
        return ordered

    def to_dict(self) -> dict:
        return {
            "statements": [s.to_dict() for s in self.statements],
            "table_dependencies": self.table_dependencies,
        }


_IDENT = r"([a-zA-Z_][a-zA-Z0-9_.]*)"

_PATTERNS = [
    (SQLStatementType.CREATE_VIEW, re.compile(rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+{_IDENT}", re.IGNORECASE)),
    (SQLStatementType.CREATE_TABLE, re.compile(rf"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{_IDENT}", re.IGNORECASE)),
    (SQLStatementType.MERGE, re.compile(rf"\bMERGE\s+INTO\s+{_IDENT}", re.IGNORECASE)),
    (SQLStatementType.INSERT, re.compile(rf"\bINSERT\s+INTO\s+{_IDENT}", re.IGNORECASE)),
    (SQLStatementType.UPDATE, re.compile(rf"\bUPDATE\s+(?!SET\b){_IDENT}", re.IGNORECASE)),
    (SQLStatementType.DELETE, re.compile(rf"\bDELETE\s+FROM\s+{_IDENT}", re.IGNORECASE)),
    (SQLStatementType.JOIN, re.compile(rf"\b(?:INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+|LEFT\s+ANTI\s+)?JOIN\s+{_IDENT}", re.IGNORECASE)),
    (SQLStatementType.SELECT_FROM, re.compile(rf"\bFROM\s+{_IDENT}", re.IGNORECASE)),
]


class SQLParser:
    """Scans raw SQL text for statement types and the table names they reference."""

    def parse(self, sql_text: str) -> SQLFindings:
        findings = SQLFindings()
        for line_number, line in enumerate(sql_text.splitlines(), start=1):
            for statement_type, pattern in _PATTERNS:
                match = pattern.search(line)
                if match:
                    findings.statements.append(
                        SQLStatementFinding(
                            statement_type=statement_type,
                            table_name=match.group(1),
                            line_number=line_number,
                        )
                    )
        return findings
