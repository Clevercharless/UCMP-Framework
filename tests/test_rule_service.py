"""
tests.test_rule_service
=========================
Unit tests for rule_service.matcher, rule_service.template_resolver, and
rule_service.rule_service.RuleService.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.exceptions import RuleServiceError
from orchestrator.context import PipelineContext
from rule_service.matcher import RuleMatcher
from rule_service.rule_service import RuleService
from rule_service.template_resolver import TemplateResolutionError, TemplateResolver
from rules.rule_models import validate_and_build_rule
from rules.rule_repository import RuleRepository


# ---------------------------------------------------------------------------
# RuleMatcher
# ---------------------------------------------------------------------------

def _rule(**overrides):
    base = {
        "rule_id": "r-1", "category": "storage", "match_type": "exact",
        "pattern": "x", "action": "no_change", "description": "test",
    }
    base.update(overrides)
    return validate_and_build_rule(base, source_file="test.yaml")


def test_matcher_exact_match():
    rule = _rule(match_type="exact", pattern="abc")
    results = RuleMatcher().match("abc", [rule])
    assert len(results) == 1
    assert results[0][0].rule_id == "r-1"


def test_matcher_exact_no_match():
    rule = _rule(match_type="exact", pattern="abc")
    assert RuleMatcher().match("xyz", [rule]) == []


def test_matcher_prefix_match():
    rule = _rule(match_type="prefix", pattern="azure.")
    results = RuleMatcher().match("azure.identity.ClientSecretCredential", [rule])
    assert len(results) == 1


def test_matcher_regex_match_returns_match_object():
    rule = _rule(match_type="regex", pattern=r"abfss://(?P<container>\w+)@")
    results = RuleMatcher().match("abfss://bronze@account.dfs.core.windows.net/x", [rule])
    assert len(results) == 1
    _, match_obj = results[0]
    assert match_obj.group("container") == "bronze"


def test_matcher_sorts_multiple_matches_by_priority():
    low_priority = _rule(rule_id="low", match_type="prefix", pattern="a", priority=50)
    high_priority = _rule(rule_id="high", match_type="prefix", pattern="a", priority=5)
    results = RuleMatcher().match("abc", [low_priority, high_priority])
    assert [r[0].rule_id for r in results] == ["high", "low"]


# ---------------------------------------------------------------------------
# TemplateResolver
# ---------------------------------------------------------------------------

def test_template_resolver_fills_regex_groups():
    import re
    match_obj = re.search(r"abfss://(?P<container>\w+)@(?P<account>\w+)\.dfs.*/(?P<path>.*)",
                           "abfss://bronze@acct.dfs.core.windows.net/customers")
    resolved = TemplateResolver().resolve("s3://{account}-{container}/{path}", match_obj, {})
    assert resolved == "s3://acct-bronze/customers"


def test_template_resolver_fills_config_token():
    resolved = TemplateResolver().resolve(
        "{config.target.catalog_name}", None, {"target": {"catalog_name": "loanplatform_catalog"}}
    )
    assert resolved == "loanplatform_catalog"


def test_template_resolver_raises_on_missing_config_path():
    with pytest.raises(TemplateResolutionError, match="does not resolve"):
        TemplateResolver().resolve("{config.does.not.exist}", None, {"target": {}})


def test_template_resolver_raises_on_missing_regex_group():
    with pytest.raises(TemplateResolutionError, match="not present"):
        TemplateResolver().resolve("{missing_group}", None, {})


# ---------------------------------------------------------------------------
# RuleService (PipelineStage)
# ---------------------------------------------------------------------------

def _write_rule_file(path: Path, name: str, content: str) -> Path:
    f = path / name
    f.write_text(content)
    return f


def _rule_repo_with(tmp_path: Path, content: str) -> RuleRepository:
    _write_rule_file(tmp_path, "storage_rules.yaml", content)
    repo = RuleRepository(rules_dir=str(tmp_path))
    repo.run(PipelineContext(config={"rules": {"rules_dir": "unused"}}))
    return repo


def _knowledge_model_with(candidates):
    return {"transformation_candidates": candidates}


def test_rule_service_requires_knowledge_model():
    service = RuleService(rule_repository=RuleRepository())
    context = PipelineContext(config={})
    with pytest.raises(RuleServiceError, match="ParserEngine"):
        service.run(context)


def test_rule_service_requires_rule_repository_artifact(tmp_path: Path):
    rule_repo = _rule_repo_with(tmp_path, """
- rule_id: s-1
  category: storage
  match_type: exact
  pattern: "x"
  action: no_change
  description: "test"
""")
    service = RuleService(rule_repository=rule_repo)
    context = PipelineContext(config={})
    context.set_artifact("knowledge_model", _knowledge_model_with([]))
    with pytest.raises(RuleServiceError, match="RuleRepository"):
        service.run(context)


def test_rule_service_replace_action_resolves_template(tmp_path: Path):
    rule_repo = _rule_repo_with(tmp_path, """
- rule_id: storage-001
  category: storage
  match_type: regex
  pattern: 'abfss://(?P<container>\\w+)@(?P<account>\\w+)\\.dfs.*/(?P<path>.*)'
  action: replace
  replacement_template: "s3://{account}-{container}/{path}"
  description: "test"
  priority: 10
""")
    service = RuleService(rule_repository=rule_repo)
    context = PipelineContext(config={"target": {}})
    context.set_artifact("rule_repository", {"rule_count": 1})
    context.set_artifact("knowledge_model", _knowledge_model_with([
        {
            "construct_type": "abfss_path",
            "value": "abfss://bronze@acct.dfs.core.windows.net/customers",
            "rule_category_hint": "storage_rules",
            "occurrences": 3,
            "found_in": ["Bronze/x.py"],
        }
    ]))

    result_context = service.run(context)
    output = result_context.get_artifact("rule_service_output")

    assert output["summary"]["replace"] == 1
    action = output["actions"][0]
    assert action["action"] == "replace"
    assert action["resolved_value"] == "s3://acct-bronze/customers"
    assert action["matched_rule_id"] == "storage-001"
    assert action["requires_manual_review"] is False


def test_rule_service_manual_review_action(tmp_path: Path):
    rule_repo = _rule_repo_with(tmp_path, """
- rule_id: storage-review
  category: storage
  match_type: prefix
  pattern: "/mnt/"
  action: manual_review
  description: "test manual review"
  priority: 10
""")
    service = RuleService(rule_repository=rule_repo)
    context = PipelineContext(config={})
    context.set_artifact("rule_repository", {"rule_count": 1})
    context.set_artifact("knowledge_model", _knowledge_model_with([
        {
            "construct_type": "mount_path", "value": "/mnt/raw/customers",
            "rule_category_hint": "storage_rules", "occurrences": 1, "found_in": ["Bronze/x.py"],
        }
    ]))

    result_context = service.run(context)
    output = result_context.get_artifact("rule_service_output")

    assert output["summary"]["manual_review"] == 1
    assert output["actions"][0]["requires_manual_review"] is True
    assert output["actions"][0]["resolved_value"] is None


def test_rule_service_unmatched_when_no_rule_in_category(tmp_path: Path):
    rule_repo = _rule_repo_with(tmp_path, """
- rule_id: s-1
  category: storage
  match_type: exact
  pattern: "will-not-match"
  action: no_change
  description: "test"
""")
    service = RuleService(rule_repository=rule_repo)
    context = PipelineContext(config={})
    context.set_artifact("rule_repository", {"rule_count": 1})
    context.set_artifact("knowledge_model", _knowledge_model_with([
        {
            "construct_type": "abfss_path", "value": "abfss://something/else",
            "rule_category_hint": "storage_rules", "occurrences": 1, "found_in": ["x.py"],
        }
    ]))

    result_context = service.run(context)
    output = result_context.get_artifact("rule_service_output")

    assert output["summary"]["unmatched"] == 1
    assert output["actions"][0]["action"] == "unmatched"
    assert output["actions"][0]["requires_manual_review"] is True


def test_rule_service_remove_action(tmp_path: Path):
    rule_repo = _rule_repo_with(tmp_path, """
- rule_id: s-remove
  category: storage
  match_type: exact
  pattern: "delete-me"
  action: remove
  description: "test"
""")
    service = RuleService(rule_repository=rule_repo)
    context = PipelineContext(config={})
    context.set_artifact("rule_repository", {"rule_count": 1})
    context.set_artifact("knowledge_model", _knowledge_model_with([
        {
            "construct_type": "x", "value": "delete-me",
            "rule_category_hint": "storage_rules", "occurrences": 1, "found_in": ["x.py"],
        }
    ]))
    output = service.run(context).get_artifact("rule_service_output")
    assert output["actions"][0]["action"] == "remove"
    assert output["actions"][0]["resolved_value"] is None


def test_rule_service_unresolvable_template_falls_back_to_manual_review(tmp_path: Path):
    rule_repo = _rule_repo_with(tmp_path, """
- rule_id: s-bad-template
  category: storage
  match_type: exact
  pattern: "x"
  action: replace
  replacement_template: "{config.missing.path}"
  description: "test"
""")
    service = RuleService(rule_repository=rule_repo)
    context = PipelineContext(config={"target": {}})
    context.set_artifact("rule_repository", {"rule_count": 1})
    context.set_artifact("knowledge_model", _knowledge_model_with([
        {
            "construct_type": "x", "value": "x",
            "rule_category_hint": "storage_rules", "occurrences": 1, "found_in": ["x.py"],
        }
    ]))
    output = service.run(context).get_artifact("rule_service_output")
    assert output["actions"][0]["action"] == "manual_review"
    assert output["actions"][0]["requires_manual_review"] is True
    assert "UNRESOLVED" in output["actions"][0]["notes"]


def test_rule_service_never_modifies_notebook_files(tmp_path: Path):
    """Rule Service must not write to disk at all — it only produces data."""
    rule_repo = _rule_repo_with(tmp_path, """
- rule_id: s-1
  category: storage
  match_type: exact
  pattern: "x"
  action: replace
  replacement_template: "y"
  description: "test"
""")
    before = set(tmp_path.iterdir())  # snapshot AFTER rule file setup, before RuleService runs
    service = RuleService(rule_repository=rule_repo)
    context = PipelineContext(config={})
    context.set_artifact("rule_repository", {"rule_count": 1})
    context.set_artifact("knowledge_model", _knowledge_model_with([
        {"construct_type": "x", "value": "x", "rule_category_hint": "storage_rules",
         "occurrences": 1, "found_in": ["x.py"]}
    ]))
    service.run(context)
    after = set(tmp_path.iterdir())
    assert before == after  # no new files written anywhere


# ---------------------------------------------------------------------------
# Full pipeline integration (real demo repo + real mappings)
# ---------------------------------------------------------------------------

def test_rule_service_full_pipeline_zero_unmatched_against_real_demo():
    from repository.repository_manager import _PROJECT_ROOT
    real_source = _PROJECT_ROOT / "ucmp-demo" / "Loan-Platform"
    if not real_source.exists():
        pytest.skip("ucmp-demo/Loan-Platform not present in this checkout")

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
    rule_service = RuleService(rule_repository=rule_repository)

    orchestrator = Orchestrator(stages=[
        config_manager, auth_manager, repository_manager, parser_engine,
        rule_repository, rule_service,
    ])
    context = orchestrator.run(PipelineContext())

    assert context.summary()["overall_status"] == "SUCCESS"
    output = context.get_artifact("rule_service_output")

    assert output["summary"]["unmatched"] == 0
    assert output["summary"]["replace"] > 0
    assert output["summary"]["manual_review"] > 0
    assert output["summary"]["total"] == output["summary"]["replace"] + output["summary"]["remove"] + \
        output["summary"]["manual_review"] + output["summary"]["no_change"] + output["summary"]["unmatched"]
