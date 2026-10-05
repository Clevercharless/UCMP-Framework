"""
config.schema
=============
Typed schema for UCMP's resolved configuration. This is the single source
of truth for "what a valid UCMP config looks like" — the loader produces a
raw merged dict, and the validator converts + checks it into these frozen
dataclasses.

Scope note: only Azure Databricks (source) -> AWS Databricks (target) is
supported in v1, per project scope. `platform` fields are therefore
constrained to exactly one allowed value each, not an open enum — adding
new clouds is a documented future enhancement (see ROADMAP.md), not
something this schema accepts today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Only these values are supported in v1. Intentionally not a general enum
# of clouds, to keep scope locked to Azure Databricks -> AWS Databricks.
SUPPORTED_SOURCE_PLATFORMS = frozenset({"azure_databricks"})
SUPPORTED_TARGET_PLATFORMS = frozenset({"aws_databricks"})
SUPPORTED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
SUPPORTED_OUTPUT_MODES = frozenset({"separate", "in_place"})


@dataclass(frozen=True)
class SourceConfig:
    """Describes the Azure Databricks source environment (simulated)."""

    platform: str
    repo_path: str
    workspace_url: str = "https://adb-simulated.azuredatabricks.net"
    key_vault_name: str = "simulated-kv"
    source_mode: str = "local_repo"
    access_token_env: str = "DATABRICKS_AZURE_TOKEN"
    workspace_path: str = "/"


@dataclass(frozen=True)
class TargetConfig:
    """Describes the AWS Databricks target environment (simulated)."""

    platform: str
    repo_path: str
    workspace_url: str = "https://simulated.cloud.databricks.com"
    catalog_name: str = "simulated_unity_catalog"


@dataclass(frozen=True)
class PipelineConfig:
    """Controls Orchestrator execution behavior."""

    fail_fast: bool = True
    dry_run: bool = True


@dataclass(frozen=True)
class RulesConfig:
    """Where the Rule Repository module should load YAML mappings from."""

    rules_dir: str = "rules/mappings"


@dataclass(frozen=True)
class DeploymentConfig:
    """Controls real workspace write-back. Disabled by default for safety."""

    auto_deploy: bool = False


@dataclass(frozen=True)
class OutputConfig:
    """Where generated artifacts (reports, plans) should be written."""

    reports_dir: str = "output/reports"
    knowledge_model_dir: str = "output/knowledge_model"
    mode: str = "separate"


@dataclass(frozen=True)
class MigrationConfig:
    """User-driven notebook migration inputs and target path settings."""

    # Inline notebook paths are the preferred user input. The file-based
    # option remains supported for backward compatibility.
    notebook_list: list = field(default_factory=list)
    notebook_list_file: str = ""
    notebook_path_column: str = "Notebook Path"
    container_bucket_mapping_file: str = ""
    workspace_root: str = "${WORKSPACE_ROOT}"
    # Target root used when rewriting hardcoded source notebook/repository paths.
    referred_notebook_path_root: str = "${TARGET_WORKSPACE_ROOT}"
    bucket_variable: str = "bucket"
    container_bucket_mapping: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LoggingConfig:
    """Logging verbosity for the run."""

    level: str = "INFO"


@dataclass(frozen=True)
class ProjectConfig:
    name: str = "Universal Cloud Migration Platform"
    version: str = "1.0.0"


@dataclass(frozen=True)
class UCMPConfig:
    """
    The fully resolved, validated configuration for a single migration run.
    Immutable (frozen) once constructed by ConfigValidator, so no stage
    downstream can accidentally mutate shared config mid-run.
    """

    project: ProjectConfig
    source: SourceConfig
    target: TargetConfig
    pipeline: PipelineConfig
    rules: RulesConfig
    output: OutputConfig
    deployment: DeploymentConfig
    migration: MigrationConfig
    logging: LoggingConfig
    extra: dict = field(default_factory=dict)
