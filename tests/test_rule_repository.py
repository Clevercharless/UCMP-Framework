"""
tests.test_rule_repository
============================
Unit tests for rules.rule_models and rules.rule_repository.RuleRepository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.exceptions import RuleRepositoryError
from orchestrator.context import PipelineContext
from rules.rule_models import RuleAction, RuleMatchType, validate_and_build_rule
from rules.rule_repository import RuleRepository


# ---------------------------------------------------------------------------
# rule_models.validate_and_build_rule
# ---------------------------------------------------------------------------

def _valid_raw_rule(**overrides) -> dict:
    base = {
        "rule_id": "test-001",
        "category": "storage",
        "match_type": "exact",
        "pattern": "abfss://x",
        "action": "replace",
        "replacement_template": "s3://x",
        "description": "test rule",
    }
    base.update(overrides)
    return base


def test_validate_rule_accepts_valid_input():
    rule = validate_and_build_rule(_valid_raw_rule(), source_file="test.yaml")
    assert rule.rule_id == "test-001"
    assert rule.match_type == RuleMatchType.EXACT
    assert rule.action == RuleAction.REPLACE


def test_validate_rule_rejects_missing_required_field():
    raw = _valid_raw_rule()
    del raw["description"]
    with pytest.raises(RuleRepositoryError, match="missing required field"):
        validate_and_build_rule(raw, source_file="test.yaml")


def test_validate_rule_rejects_invalid_match_type():
    raw = _valid_raw_rule(match_type="fuzzy")
    with pytest.raises(RuleRepositoryError, match="invalid match_type"):
        validate_and_build_rule(raw, source_file="test.yaml")


def test_validate_rule_rejects_invalid_action():
    raw = _valid_raw_rule(action="teleport")
    with pytest.raises(RuleRepositoryError, match="invalid action"):
        validate_and_build_rule(raw, source_file="test.yaml")


def test_validate_rule_rejects_replace_without_template():
    raw = _valid_raw_rule()
    del raw["replacement_template"]
    with pytest.raises(RuleRepositoryError, match="no replacement_template"):
        validate_and_build_rule(raw, source_file="test.yaml")


def test_validate_rule_rejects_invalid_regex():
    raw = _valid_raw_rule(match_type="regex", pattern="(unclosed")
    with pytest.raises(RuleRepositoryError, match="invalid regex"):
        validate_and_build_rule(raw, source_file="test.yaml")


def test_validate_rule_manual_review_does_not_require_template():
    raw = _valid_raw_rule(action="manual_review")
    del raw["replacement_template"]
    rule = validate_and_build_rule(raw, source_file="test.yaml")
    assert rule.requires_manual_review is True


def test_validate_rule_rejects_non_integer_priority():
    raw = _valid_raw_rule(priority="high")
    with pytest.raises(RuleRepositoryError, match="non-integer priority"):
        validate_and_build_rule(raw, source_file="test.yaml")


# ---------------------------------------------------------------------------
# RuleRepository (PipelineStage)
# ---------------------------------------------------------------------------

def _write_rule_file(path: Path, name: str, content: str) -> Path:
    f = path / name
    f.write_text(content)
    return f


def test_rule_repository_requires_config_populated():
    repo = RuleRepository()
    with pytest.raises(RuleRepositoryError, match="ConfigurationManager"):
        repo.run(PipelineContext())


def test_rule_repository_raises_when_dir_missing(tmp_path: Path):
    repo = RuleRepository(rules_dir=str(tmp_path / "nonexistent"))
    context = PipelineContext(config={"rules": {"rules_dir": "unused"}})
    with pytest.raises(RuleRepositoryError, match="does not exist"):
        repo.run(context)


def test_rule_repository_raises_when_no_rule_files_found(tmp_path: Path):
    repo = RuleRepository(rules_dir=str(tmp_path))
    context = PipelineContext(config={"rules": {"rules_dir": "unused"}})
    with pytest.raises(RuleRepositoryError, match="No '\\*_rules.yaml' files"):
        repo.run(context)


def test_rule_repository_loads_and_groups_by_category(tmp_path: Path):
    _write_rule_file(
        tmp_path, "storage_rules.yaml",
        """
- rule_id: s-1
  category: storage
  match_type: exact
  pattern: "abfss://x"
  action: replace
  replacement_template: "s3://x"
  description: "test"
  priority: 5
""",
    )
    _write_rule_file(
        tmp_path, "secret_rules.yaml",
        """
- rule_id: sec-1
  category: secret
  match_type: exact
  pattern: "vault"
  action: manual_review
  description: "test"
""",
    )
    repo = RuleRepository(rules_dir=str(tmp_path))
    context = PipelineContext(config={"rules": {"rules_dir": "unused"}})

    result_context = repo.run(context)

    artifact = result_context.get_artifact("rule_repository")
    assert artifact["rule_count"] == 2
    assert set(artifact["categories"]) == {"storage", "secret"}
    assert result_context.metadata["rules_loaded"] is True
    assert len(repo.get_rules("storage")) == 1
    assert len(repo.get_rules("secret")) == 1
    assert len(repo.get_rules("nonexistent_category")) == 0


def test_rule_repository_rules_sorted_by_priority_within_category(tmp_path: Path):
    _write_rule_file(
        tmp_path, "storage_rules.yaml",
        """
- rule_id: s-low-priority
  category: storage
  match_type: exact
  pattern: "x"
  action: no_change
  description: "test"
  priority: 50
- rule_id: s-high-priority
  category: storage
  match_type: exact
  pattern: "y"
  action: no_change
  description: "test"
  priority: 5
""",
    )
    repo = RuleRepository(rules_dir=str(tmp_path))
    context = PipelineContext(config={"rules": {"rules_dir": "unused"}})
    repo.run(context)

    rules = repo.get_rules("storage")
    assert [r.rule_id for r in rules] == ["s-high-priority", "s-low-priority"]


def test_rule_repository_rejects_duplicate_rule_ids_in_same_file(tmp_path: Path):
    _write_rule_file(
        tmp_path, "storage_rules.yaml",
        """
- rule_id: dup-1
  category: storage
  match_type: exact
  pattern: "x"
  action: no_change
  description: "test"
- rule_id: dup-1
  category: storage
  match_type: exact
  pattern: "y"
  action: no_change
  description: "test"
""",
    )
    repo = RuleRepository(rules_dir=str(tmp_path))
    context = PipelineContext(config={"rules": {"rules_dir": "unused"}})
    with pytest.raises(RuleRepositoryError, match="Duplicate rule_id"):
        repo.run(context)


def test_rule_repository_rejects_non_list_yaml_content(tmp_path: Path):
    _write_rule_file(tmp_path, "storage_rules.yaml", "not_a_list: true\n")
    repo = RuleRepository(rules_dir=str(tmp_path))
    context = PipelineContext(config={"rules": {"rules_dir": "unused"}})
    with pytest.raises(RuleRepositoryError, match="top-level list"):
        repo.run(context)


def test_rule_repository_raises_on_invalid_yaml_syntax(tmp_path: Path):
    _write_rule_file(tmp_path, "storage_rules.yaml", "- rule_id: [unclosed\n")
    repo = RuleRepository(rules_dir=str(tmp_path))
    context = PipelineContext(config={"rules": {"rules_dir": "unused"}})
    with pytest.raises(RuleRepositoryError, match="Invalid YAML"):
        repo.run(context)


def test_rule_repository_runs_as_stage_after_parser_engine():
    from repository.repository_manager import _PROJECT_ROOT
    real_source = _PROJECT_ROOT / "ucmp-demo" / "Loan-Platform"
    if not real_source.exists():
        pytest.skip("ucmp-demo/Loan-Platform not present in this checkout")

    """Full chain: Config -> Auth -> Repository -> Parser -> RuleRepository,
    using the real ucmp-demo/mappings/*.yaml files."""
    from auth.auth_manager import AuthenticationManager
    from config.config_manager import ConfigurationManager
    from orchestrator.orchestrator import Orchestrator
    from parser.parser_engine import ParserEngine
    from repository.repository_manager import RepositoryManager

    config_manager = ConfigurationManager(config_path=None, env={"UCMP__SOURCE__SOURCE_MODE": "local_repo", "UCMP__SOURCE__REPO_PATH": str(real_source)})
    auth_manager = AuthenticationManager()
    repository_manager = RepositoryManager(token_store=auth_manager.token_store)
    parser_engine = ParserEngine()
    rule_repository = RuleRepository()

    orchestrator = Orchestrator(
        stages=[config_manager, auth_manager, repository_manager, parser_engine, rule_repository]
    )
    context = orchestrator.run(PipelineContext())

    assert context.summary()["overall_status"] == "SUCCESS"
    artifact = context.get_artifact("rule_repository")
    expected_categories = {"storage", "secret", "workspace", "catalog", "library", "spark", "api"}
    assert set(artifact["categories"]) == expected_categories
    assert artifact["rule_count"] >= 14  # at least 2 per category across 7 files
