"""
parser.regex_parser
=====================
Line-by-line regex scanning for Azure-specific constructs that will need
translating during migration: ADLS Gen2 paths (`abfss://`), Azure Blob
Storage URLs, Azure Databricks workspace URLs, Azure Key Vault references,
DBFS mount paths, Azure SDK imports, and other hardcoded cloud-specific
URLs (e.g. Azure SQL JDBC connection strings).

This is deliberately regex-based rather than AST-based: these constructs
appear as string literals, f-string fragments, and comments, and need to
be found regardless of the surrounding Python/SQL syntax.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List


class AzureConstructType(str, Enum):
    ABFSS_PATH = "abfss_path"
    BLOB_STORAGE = "blob_storage"
    WORKSPACE_URL = "workspace_url"
    KEY_VAULT = "key_vault"
    MOUNT_PATH = "mount_path"
    AZURE_SDK_IMPORT = "azure_sdk_import"
    HARDCODED_URL = "hardcoded_url"


@dataclass
class AzureConstruct:
    """A single Azure-specific construct found in notebook source text."""

    construct_type: AzureConstructType
    value: str
    line_number: int

    def to_dict(self) -> dict:
        return {
            "construct_type": self.construct_type.value,
            "value": self.value,
            "line_number": self.line_number,
        }


# Order matters: more specific patterns are checked before the generic
# hardcoded-URL catch-all, so e.g. a *.blob.core.windows.net URL is tagged
# BLOB_STORAGE rather than the generic HARDCODED_URL.
_PATTERNS: List[tuple] = [
    (AzureConstructType.ABFSS_PATH, re.compile(r"abfss://[^\s\"')]+")),
    (AzureConstructType.BLOB_STORAGE, re.compile(r"https?://[a-zA-Z0-9\-]+\.blob\.core\.windows\.net[^\s\"')]*")),
    (AzureConstructType.WORKSPACE_URL, re.compile(r"https?://[a-zA-Z0-9\-]+\.azuredatabricks\.net[^\s\"')]*")),
    (AzureConstructType.KEY_VAULT, re.compile(r"https?://[a-zA-Z0-9\-]+\.vault\.azure\.net[^\s\"')]*")),
    (AzureConstructType.MOUNT_PATH, re.compile(r"/mnt/[a-zA-Z0-9_\-/{}]+")),
    (AzureConstructType.AZURE_SDK_IMPORT, re.compile(r"^\s*(?:from|import)\s+azure\.[a-zA-Z0-9_.]+")),
    (AzureConstructType.HARDCODED_URL, re.compile(r"jdbc:sqlserver://[^\s\"')]+")),
    (AzureConstructType.HARDCODED_URL, re.compile(r"https?://[a-zA-Z0-9\-]+\.database\.windows\.net[^\s\"')]*")),
]


@dataclass
class GeneralConstruct:
    """Non-Azure migration construct found in raw source text."""

    category: str
    value: str
    line_number: int

    def to_dict(self) -> dict:
        return {"category": self.category, "value": self.value, "line_number": self.line_number}


class RegexParser:
    """Scans raw notebook text line-by-line for Azure-specific constructs."""

    def parse(self, full_text: str) -> List[AzureConstruct]:
        findings: List[AzureConstruct] = []
        seen_on_line: set = set()  # (line_no, construct_type, value) dedup guard

        for line_number, line in enumerate(full_text.splitlines(), start=1):
            for construct_type, pattern in _PATTERNS:
                for match in pattern.finditer(line):
                    value = match.group(0).strip()
                    key = (line_number, construct_type, value)
                    if key in seen_on_line:
                        continue
                    seen_on_line.add(key)
                    findings.append(
                        AzureConstruct(construct_type=construct_type, value=value, line_number=line_number)
                    )
        return findings

    def parse_general_constructs(self, full_text: str) -> List[GeneralConstruct]:
        """Detect JDBC URLs and secret API calls across the full source, including multiline calls.

        This complements AST analysis: regex scanning can find URL strings in comments,
        SQL snippets, and other text that is not represented as a Python call node.
        Sensitive URL parameters are redacted before returning findings.
        """
        findings: List[GeneralConstruct] = []
        seen = set()

        jdbc_pattern = re.compile(r"jdbc:[a-zA-Z0-9_-]+:[^\s\"'`)]+", re.IGNORECASE)
        for match in jdbc_pattern.finditer(full_text):
            value = match.group(0).rstrip(".,;")
            value = re.sub(r"(?i)(password|passwd|pwd|token|secret)=([^;&\s]+)", r"\1=[REDACTED]", value)
            value = re.sub(r"(://)[^/@:\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
            line_number = full_text.count("\n", 0, match.start()) + 1
            key = ("jdbc_url", value, line_number)
            if key not in seen:
                seen.add(key)
                findings.append(GeneralConstruct("jdbc_url", value, line_number))

        secret_pattern = re.compile(r"(?:dbutils\s*\.\s*secrets\s*\.\s*(?:get|getBytes))\s*\(", re.IGNORECASE)
        for match in secret_pattern.finditer(full_text):
            line_number = full_text.count("\n", 0, match.start()) + 1
            # Never include the complete call or any secret value in this finding.
            key = ("secret_retrieval_api", "dbutils.secrets.get", line_number)
            if key not in seen:
                seen.add(key)
                findings.append(GeneralConstruct("secret_retrieval_api", "dbutils.secrets.get", line_number))

        return sorted(findings, key=lambda item: (item.line_number, item.category, item.value))
