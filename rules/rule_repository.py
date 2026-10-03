"""
rules.rule_repository
=======================
`RuleRepository` is the sixth pipeline stage. It loads every `*_rules.yaml`
file from the configured rules directory (`context.config["rules"]["rules_dir"]`),
validates each rule against the schema in `rule_models.py`, and exposes the
loaded rules — grouped by category — for the Rule Service (Module 7) to
query.

Per the spec: "It never contains business logic." This module does not
decide which rules apply to which notebooks, does not resolve priority
conflicts between rules, and does not know anything about the Migration
Knowledge Model. It only loads, validates, and serves data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml

from common.exceptions import RuleRepositoryError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from rules.rule_models import MigrationRule, validate_and_build_rule

logger = get_logger(__name__)

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RULE_FILE_SUFFIX = "_rules.yaml"


class RuleRepository(PipelineStage):
    """Loads and validates all externalized YAML migration rule files."""

    name = "RuleRepository"

    def __init__(self, rules_dir: Optional[str] = None):
        self._rules_dir_override = rules_dir
        self._rules_by_category: Dict[str, List[MigrationRule]] = {}
        self._all_rules: List[MigrationRule] = []

    @property
    def all_rules(self) -> List[MigrationRule]:
        return list(self._all_rules)

    def get_rules(self, category: str) -> List[MigrationRule]:
        """Direct programmatic access for Rule Service (Module 7), sorted by priority."""
        return list(self._rules_by_category.get(category, []))

    def run(self, context: PipelineContext) -> PipelineContext:
        if not context.config:
            raise RuleRepositoryError(
                "RuleRepository requires context.config to be populated "
                "(run ConfigurationManager first)"
            )

        rules_dir = self._resolve_rules_dir(context)
        rule_files = self._discover_rule_files(rules_dir)

        all_rules: List[MigrationRule] = []
        for rule_file in rule_files:
            all_rules.extend(self._load_rule_file(rule_file))

        self._all_rules = all_rules
        self._rules_by_category = self._group_by_category(all_rules)

        context.set_artifact(
            "rule_repository",
            {
                "rules_dir": str(rules_dir),
                "source_files": [f.name for f in rule_files],
                "rule_count": len(all_rules),
                "categories": sorted(self._rules_by_category.keys()),
                "rules_by_category": {
                    category: [r.to_dict() for r in rules]
                    for category, rules in self._rules_by_category.items()
                },
            },
        )
        context.metadata["rules_loaded"] = True

        logger.info(
            "Loaded %d rule(s) from %d file(s) across categories: %s",
            len(all_rules),
            len(rule_files),
            sorted(self._rules_by_category.keys()),
        )
        return context

    # -- internals --------------------------------------------------------

    def _resolve_rules_dir(self, context: PipelineContext) -> Path:
        configured = self._rules_dir_override or context.config["rules"]["rules_dir"]
        path = Path(configured)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        return path.resolve()

    def _discover_rule_files(self, rules_dir: Path) -> List[Path]:
        if not rules_dir.exists():
            raise RuleRepositoryError(f"Rules directory does not exist: {rules_dir}")
        if not rules_dir.is_dir():
            raise RuleRepositoryError(f"Rules path is not a directory: {rules_dir}")

        rule_files = sorted(rules_dir.glob(f"*{_RULE_FILE_SUFFIX}"))
        if not rule_files:
            raise RuleRepositoryError(
                f"No '*{_RULE_FILE_SUFFIX}' files found in rules directory: {rules_dir}"
            )
        return rule_files

    def _load_rule_file(self, rule_file: Path) -> List[MigrationRule]:
        try:
            raw_text = rule_file.read_text(encoding="utf-8")
            raw_entries = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise RuleRepositoryError(f"Invalid YAML in {rule_file.name}: {exc}") from exc
        except OSError as exc:
            raise RuleRepositoryError(f"Could not read {rule_file}: {exc}") from exc

        if raw_entries is None:
            raise RuleRepositoryError(f"Rule file {rule_file.name} is empty")
        if not isinstance(raw_entries, list):
            raise RuleRepositoryError(
                f"Rule file {rule_file.name} must contain a top-level list of rules, "
                f"got {type(raw_entries).__name__}"
            )

        rules = [
            validate_and_build_rule(entry, source_file=rule_file.name) for entry in raw_entries
        ]
        self._check_unique_ids(rules, rule_file.name)
        return rules

    @staticmethod
    def _check_unique_ids(rules: List[MigrationRule], source_file: str) -> None:
        seen = set()
        for rule in rules:
            if rule.rule_id in seen:
                raise RuleRepositoryError(
                    f"Duplicate rule_id '{rule.rule_id}' within {source_file}"
                )
            seen.add(rule.rule_id)

    @staticmethod
    def _group_by_category(rules: List[MigrationRule]) -> Dict[str, List[MigrationRule]]:
        grouped: Dict[str, List[MigrationRule]] = {}
        for rule in rules:
            grouped.setdefault(rule.category, []).append(rule)
        for category_rules in grouped.values():
            category_rules.sort(key=lambda r: r.priority)
        return grouped
