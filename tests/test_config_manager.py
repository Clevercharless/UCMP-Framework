"""
tests.test_config_manager
==========================
Unit tests for config.loader, config.validator, and
config.config_manager.ConfigurationManager.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from common.exceptions import ConfigurationError
from config.config_manager import ConfigurationManager
from config.loader import ConfigLoader
from config.validator import ConfigValidator
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# ConfigLoader
# ---------------------------------------------------------------------------

def test_loader_returns_defaults_when_no_file_given():
    raw = ConfigLoader(env={}).load(config_path=None)
    assert raw["source"]["platform"] == "azure_databricks"
    assert raw["target"]["platform"] == "aws_databricks"


def test_loader_merges_user_file_over_defaults(tmp_path: Path):
    user_yaml = tmp_path / "user_config.yaml"
    user_yaml.write_text(
        textwrap.dedent(
            """
            source:
              repo_path: "/custom/source/repo"
            pipeline:
              dry_run: false
            """
        )
    )
    raw = ConfigLoader(env={}).load(config_path=str(user_yaml))

    # Overridden value
    assert raw["source"]["repo_path"] == "/custom/source/repo"
    assert raw["pipeline"]["dry_run"] is False
    # Untouched default still present (deep merge, not replace)
    assert raw["source"]["platform"] == "azure_databricks"
    assert raw["pipeline"]["fail_fast"] is True


def test_loader_missing_user_file_raises():
    with pytest.raises(ConfigurationError):
        ConfigLoader(env={}).load(config_path="/nonexistent/path.yaml")


def test_loader_env_overrides_take_highest_precedence(tmp_path: Path):
    user_yaml = tmp_path / "user_config.yaml"
    user_yaml.write_text("pipeline:\n  dry_run: false\n")

    env = {"UCMP__PIPELINE__DRY_RUN": "true", "UCMP__LOGGING__LEVEL": "DEBUG"}
    raw = ConfigLoader(env=env).load(config_path=str(user_yaml))

    assert raw["pipeline"]["dry_run"] is True  # env beat the file
    assert raw["logging"]["level"] == "DEBUG"


def test_loader_env_type_coercion():
    env = {"UCMP__PIPELINE__FAIL_FAST": "false"}
    raw = ConfigLoader(env=env).load(config_path=None)
    assert raw["pipeline"]["fail_fast"] is False
    assert isinstance(raw["pipeline"]["fail_fast"], bool)


def test_loader_invalid_yaml_raises(tmp_path: Path):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("source: [unclosed")
    with pytest.raises(ConfigurationError):
        ConfigLoader(env={}).load(config_path=str(bad_yaml))


# ---------------------------------------------------------------------------
# ConfigValidator
# ---------------------------------------------------------------------------

def _valid_raw_config() -> dict:
    return ConfigLoader(env={}).load(config_path=None)


def test_validator_accepts_valid_defaults():
    cfg = ConfigValidator().validate(_valid_raw_config())
    assert cfg.source.platform == "azure_databricks"
    assert cfg.target.platform == "aws_databricks"


def test_validator_rejects_unsupported_source_platform():
    raw = _valid_raw_config()
    raw["source"]["platform"] = "gcp_dataproc"
    with pytest.raises(ConfigurationError, match="source.platform"):
        ConfigValidator().validate(raw)


def test_validator_rejects_unsupported_target_platform():
    raw = _valid_raw_config()
    raw["target"]["platform"] = "snowflake"
    with pytest.raises(ConfigurationError, match="target.platform"):
        ConfigValidator().validate(raw)


def test_validator_rejects_missing_repo_path():
    raw = _valid_raw_config()
    raw["source"]["repo_path"] = ""
    with pytest.raises(ConfigurationError, match="source.repo_path"):
        ConfigValidator().validate(raw)


def test_validator_rejects_bad_boolean_type():
    raw = _valid_raw_config()
    raw["pipeline"]["dry_run"] = "not_a_bool"
    with pytest.raises(ConfigurationError, match="pipeline.dry_run"):
        ConfigValidator().validate(raw)


def test_validator_rejects_invalid_log_level():
    raw = _valid_raw_config()
    raw["logging"]["level"] = "VERBOSE"
    with pytest.raises(ConfigurationError, match="logging.level"):
        ConfigValidator().validate(raw)


def test_validator_collects_multiple_errors_at_once():
    raw = _valid_raw_config()
    raw["source"]["platform"] = "gcp"
    raw["target"]["platform"] = "snowflake"
    with pytest.raises(ConfigurationError) as exc_info:
        ConfigValidator().validate(raw)
    message = str(exc_info.value)
    assert "source.platform" in message
    assert "target.platform" in message


def test_validator_preserves_unknown_extra_keys():
    raw = _valid_raw_config()
    raw["experimental_feature"] = {"enabled": True}
    cfg = ConfigValidator().validate(raw)
    assert cfg.extra == {"experimental_feature": {"enabled": True}}


# ---------------------------------------------------------------------------
# ConfigurationManager (PipelineStage)
# ---------------------------------------------------------------------------

def test_configuration_manager_fails_fast_on_construction_with_bad_config(tmp_path: Path):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("source:\n  platform: 'gcp'\n")
    with pytest.raises(ConfigurationError):
        ConfigurationManager(config_path=str(bad_yaml))


def test_configuration_manager_populates_context_config():
    manager = ConfigurationManager(config_path=None, env={})
    context = PipelineContext()

    result = manager.run(context)

    assert result is context
    assert result.config["source"]["platform"] == "azure_databricks"
    assert result.metadata["source_platform"] == "azure_databricks"
    assert result.metadata["target_platform"] == "aws_databricks"
    assert "resolved_config_summary" in result.artifacts


def test_configuration_manager_runs_as_first_orchestrator_stage():
    manager = ConfigurationManager(config_path=None, env={})
    orchestrator = Orchestrator(stages=[manager])

    context = orchestrator.run()

    assert context.summary()["overall_status"] == "SUCCESS"
    assert context.config["pipeline"]["dry_run"] is True


def test_configuration_manager_env_override_flows_through_pipeline():
    env = {"UCMP__PIPELINE__DRY_RUN": "false"}
    manager = ConfigurationManager(config_path=None, env=env)
    orchestrator = Orchestrator(stages=[manager])

    context = orchestrator.run()

    assert context.config["pipeline"]["dry_run"] is False


def test_validator_accepts_migration_configuration():
    raw = _valid_raw_config()
    raw["migration"] = {
        "notebook_list": ["Bronze/a.py", "Silver/b.py"],
        "notebook_list_file": "input.xlsx",
        "notebook_path_column": "Notebook Path",
        "container_bucket_mapping_file": "mapping.yaml",
        "workspace_root": "${WORKSPACE_ROOT}",
        "bucket_variable": "bucket",
        "container_bucket_mapping": {"qlikapps": "raw_qlik"},
    }
    cfg = ConfigValidator().validate(raw)
    assert cfg.migration.notebook_list == ["Bronze/a.py", "Silver/b.py"]
    assert cfg.migration.notebook_list_file == "input.xlsx"
    assert cfg.migration.container_bucket_mapping["qlikapps"] == "raw_qlik"


def test_output_mode_in_place_is_validated():
    from config.validator import ConfigValidator

    raw = {
        "source": {"platform": "azure_databricks", "repo_path": "/tmp/source", "source_mode": "local_repo"},
        "target": {"platform": "aws_databricks", "repo_path": "/tmp/target"},
        "output": {"mode": "in_place"},
    }
    config = ConfigValidator().validate(raw)
    assert config.output.mode == "in_place"


def test_invalid_output_mode_is_rejected():
    import pytest
    from common.exceptions import ConfigurationError
    from config.validator import ConfigValidator

    raw = {
        "source": {"platform": "azure_databricks", "repo_path": "/tmp/source"},
        "target": {"platform": "aws_databricks", "repo_path": "/tmp/target"},
        "output": {"mode": "overwrite_everything"},
    }
    with pytest.raises(ConfigurationError, match="output.mode"):
        ConfigValidator().validate(raw)
