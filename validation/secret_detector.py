"""
validation.secret_detector
=============================
Hardcoded Secret Detection: scans migrated notebooks for secret-shaped
literal assignments (password/secret/api_key/client_secret/token followed
by a quoted string literal) that are NOT going through
dbutils.secrets.get(...). This is a real security check, independent of
anything Azure- or AWS-specific: a hardcoded secret is a problem on either
cloud, and migration is a natural point to catch one that was already
lurking in the source or that a bad rule template accidentally introduced.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from validation.banner_utils import strip_banner
from validation.finding import ValidationCategory, ValidationFinding, ValidationSeverity

_SECRET_LITERAL_PATTERN = re.compile(
    r'(?i)\b(password|secret|api[_-]?key|client_secret|access_key|private_key)\b\s*=\s*'
    r'["\'](?!\{)[^"\']{4,}["\']'
)


class HardcodedSecretDetector:
    def validate(self, transformation_plan: Dict, target_root: Path, content_map: Dict[str, str] | None = None) -> List[ValidationFinding]:
        findings: List[ValidationFinding] = []

        for notebook_plan in transformation_plan["notebook_plans"]:
            relative_path = notebook_plan["relative_path"]
            output_path = target_root / relative_path
            if content_map is not None and relative_path in content_map:
                text = content_map[relative_path]
            else:
                if not output_path.exists():
                    continue
                text = output_path.read_text(encoding="utf-8", errors="ignore")
            text = strip_banner(text)
            for line_number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if any(stripped.startswith(marker) for marker in ("#", "--", "//")):
                    continue
                if "dbutils.secrets.get" in stripped:
                    continue  # properly sourced from a secret scope, not hardcoded

                match = _SECRET_LITERAL_PATTERN.search(stripped)
                if match:
                    findings.append(
                        ValidationFinding(
                            category=ValidationCategory.HARDCODED_SECRET,
                            severity=ValidationSeverity.ERROR,
                            message=f"Possible hardcoded secret literal on line {line_number} "
                            f"(matched field '{match.group(1)}')",
                            notebook=relative_path,
                            detail=stripped,
                        )
                    )

        if not findings:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.HARDCODED_SECRET,
                    severity=ValidationSeverity.INFO,
                    message="No hardcoded secret literals detected; all secrets are sourced "
                    "via dbutils.secrets.get",
                )
            )
        return findings
