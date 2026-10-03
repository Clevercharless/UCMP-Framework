"""
config.validator
=================
Converts a raw merged config dict (produced by ConfigLoader) into a
validated, immutable `UCMPConfig`. Raises `ConfigurationError` with a
clear, actionable message on any problem — missing required field, wrong
type, or an unsupported platform value.

Deliberately scope-locked: `source.platform` and `target.platform` are
checked against the exact frozensets defined in config/schema.py
(azure_databricks / aws_databricks only), so a config file requesting GCP
or Snowflake fails loudly and immediately rather than being silently
accepted.
"""

from __future__ import annotations

from typing import Any, Dict, List

from common.exceptions import ConfigurationError
from config.schema import (
    SUPPORTED_LOG_LEVELS,
    SUPPORTED_SOURCE_PLATFORMS,
    SUPPORTED_TARGET_PLATFORMS,
    SUPPORTED_OUTPUT_MODES,
    LoggingConfig,
    MigrationConfig,
    OutputConfig,
    PipelineConfig,
    ProjectConfig,
    RulesConfig,
    SourceConfig,
    TargetConfig,
    UCMPConfig,
)


class ConfigValidator:
    """Validates and type-converts a raw config dict into a UCMPConfig."""

    def validate(self, raw: Dict[str, Any]) -> UCMPConfig:
        errors: List[str] = []

        project = self._build_project(raw, errors)
        source = self._build_source(raw, errors)
        target = self._build_target(raw, errors)
        pipeline = self._build_pipeline(raw, errors)
        rules = self._build_rules(raw, errors)
        output = self._build_output(raw, errors)
        migration = self._build_migration(raw, errors)
        logging_cfg = self._build_logging(raw, errors)

        if errors:
            joined = "; ".join(errors)
            raise ConfigurationError(f"Invalid configuration ({len(errors)} error(s)): {joined}")

        known_top_level = {
            "project", "source", "target", "pipeline", "rules", "output", "migration", "logging",
        }
        extra = {k: v for k, v in raw.items() if k not in known_top_level}

        return UCMPConfig(
            project=project,
            source=source,
            target=target,
            pipeline=pipeline,
            rules=rules,
            output=output,
            migration=migration,
            logging=logging_cfg,
            extra=extra,
        )

    # -- section builders -----------------------------------------------

    def _build_project(self, raw: Dict[str, Any], errors: List[str]) -> ProjectConfig:
        section = raw.get("project", {}) or {}
        name = section.get("name", ProjectConfig.name)
        version = section.get("version", ProjectConfig.version)
        return ProjectConfig(name=str(name), version=str(version))

    def _build_source(self, raw: Dict[str, Any], errors: List[str]) -> SourceConfig:
        section = raw.get("source")
        if not isinstance(section, dict):
            errors.append("Missing required section 'source'")
            section = {}

        platform = section.get("platform")
        if platform not in SUPPORTED_SOURCE_PLATFORMS:
            errors.append(
                f"source.platform must be one of {sorted(SUPPORTED_SOURCE_PLATFORMS)}, "
                f"got {platform!r}"
            )
            platform = platform or "azure_databricks"

        repo_path = section.get("repo_path")
        if not repo_path or not isinstance(repo_path, str):
            errors.append("source.repo_path is required and must be a non-empty string")
            repo_path = repo_path or ""

        return SourceConfig(
            platform=str(platform),
            repo_path=str(repo_path),
            workspace_url=str(section.get("workspace_url", SourceConfig.workspace_url)),
            key_vault_name=str(section.get("key_vault_name", SourceConfig.key_vault_name)),
            source_mode=str(section.get("source_mode", SourceConfig.source_mode)),
            access_token_env=str(section.get("access_token_env", SourceConfig.access_token_env)),
            workspace_path=str(section.get("workspace_path", SourceConfig.workspace_path)),
        )

    def _build_target(self, raw: Dict[str, Any], errors: List[str]) -> TargetConfig:
        section = raw.get("target")
        if not isinstance(section, dict):
            errors.append("Missing required section 'target'")
            section = {}

        platform = section.get("platform")
        if platform not in SUPPORTED_TARGET_PLATFORMS:
            errors.append(
                f"target.platform must be one of {sorted(SUPPORTED_TARGET_PLATFORMS)}, "
                f"got {platform!r}"
            )
            platform = platform or "aws_databricks"

        repo_path = section.get("repo_path")
        if not repo_path or not isinstance(repo_path, str):
            errors.append("target.repo_path is required and must be a non-empty string")
            repo_path = repo_path or ""

        return TargetConfig(
            platform=str(platform),
            repo_path=str(repo_path),
            workspace_url=str(section.get("workspace_url", TargetConfig.workspace_url)),
            catalog_name=str(section.get("catalog_name", TargetConfig.catalog_name)),
        )

    def _build_pipeline(self, raw: Dict[str, Any], errors: List[str]) -> PipelineConfig:
        section = raw.get("pipeline", {}) or {}
        fail_fast = section.get("fail_fast", PipelineConfig.fail_fast)
        dry_run = section.get("dry_run", PipelineConfig.dry_run)

        if not isinstance(fail_fast, bool):
            errors.append(f"pipeline.fail_fast must be a boolean, got {type(fail_fast).__name__}")
            fail_fast = PipelineConfig.fail_fast
        if not isinstance(dry_run, bool):
            errors.append(f"pipeline.dry_run must be a boolean, got {type(dry_run).__name__}")
            dry_run = PipelineConfig.dry_run

        return PipelineConfig(fail_fast=fail_fast, dry_run=dry_run)

    def _build_rules(self, raw: Dict[str, Any], errors: List[str]) -> RulesConfig:
        section = raw.get("rules", {}) or {}
        rules_dir = section.get("rules_dir", RulesConfig.rules_dir)
        if not isinstance(rules_dir, str) or not rules_dir:
            errors.append("rules.rules_dir must be a non-empty string")
            rules_dir = RulesConfig.rules_dir
        return RulesConfig(rules_dir=str(rules_dir))

    def _build_output(self, raw: Dict[str, Any], errors: List[str]) -> OutputConfig:
        section = raw.get("output", {}) or {}
        reports_dir = section.get("reports_dir", OutputConfig.reports_dir)
        knowledge_model_dir = section.get(
            "knowledge_model_dir", OutputConfig.knowledge_model_dir
        )
        mode = str(section.get("mode", OutputConfig.mode)).strip().lower()
        if mode not in SUPPORTED_OUTPUT_MODES:
            errors.append(
                f"output.mode must be one of {sorted(SUPPORTED_OUTPUT_MODES)}, got {mode!r}"
            )
            mode = OutputConfig.mode
        return OutputConfig(
            reports_dir=str(reports_dir),
            knowledge_model_dir=str(knowledge_model_dir),
            mode=mode,
        )

    def _build_migration(self, raw: Dict[str, Any], errors: List[str]) -> MigrationConfig:
        section = raw.get("migration", {}) or {}
        if not isinstance(section, dict):
            errors.append("migration must be a mapping")
            section = {}
        notebook_list = section.get("notebook_list", []) or []
        if not isinstance(notebook_list, (list, tuple)):
            errors.append("migration.notebook_list must be a list")
            notebook_list = []
        notebook_list = [str(v).strip() for v in notebook_list if str(v).strip()]
        list_file = section.get("notebook_list_file", MigrationConfig.notebook_list_file)
        column = section.get("notebook_path_column", MigrationConfig.notebook_path_column)
        mapping_file = section.get("container_bucket_mapping_file", MigrationConfig.container_bucket_mapping_file)
        workspace_root = section.get("workspace_root", MigrationConfig.workspace_root)
        bucket_variable = section.get("bucket_variable", MigrationConfig.bucket_variable)
        mapping = section.get("container_bucket_mapping", {}) or {}
        if not isinstance(mapping, dict):
            errors.append("migration.container_bucket_mapping must be a mapping")
            mapping = {}
        if not isinstance(list_file, str):
            errors.append("migration.notebook_list_file must be a string")
            list_file = ""
        return MigrationConfig(
            notebook_list=notebook_list,
            notebook_list_file=list_file,
            notebook_path_column=str(column),
            container_bucket_mapping_file=str(mapping_file),
            workspace_root=str(workspace_root),
            bucket_variable=str(bucket_variable),
            container_bucket_mapping={str(k): str(v) for k, v in mapping.items()},
        )

    def _build_logging(self, raw: Dict[str, Any], errors: List[str]) -> LoggingConfig:
        section = raw.get("logging", {}) or {}
        level = str(section.get("level", LoggingConfig.level)).upper()
        if level not in SUPPORTED_LOG_LEVELS:
            errors.append(
                f"logging.level must be one of {sorted(SUPPORTED_LOG_LEVELS)}, got {level!r}"
            )
            level = LoggingConfig.level
        return LoggingConfig(level=level)
