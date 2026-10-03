"""
config.config_manager
======================
`ConfigurationManager` is the first REAL (non-placeholder) PipelineStage in
UCMP. It wraps ConfigLoader + ConfigValidator and:

  1. Loads + validates configuration once, on construction.
  2. As a PipelineStage, stamps the resolved config onto
     `context.config` (as a plain dict, for stages that just want to read
     values) AND keeps the typed `UCMPConfig` object accessible via
     `.resolved_config` for stages/tests that want type safety.
  3. Applies the configured logging level to the UCMP logger hierarchy.

Every later module (Repository Manager, Parser Engine, ...) will read its
settings from `context.config` rather than constructing its own
ConfigLoader — this is the ONLY module that touches config files/env vars.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Dict, Optional

from common.exceptions import ConfigurationError
from common.logging_config import get_logger
from config.loader import ConfigLoader
from config.schema import UCMPConfig
from config.validator import ConfigValidator
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage

logger = get_logger(__name__)


class ConfigurationManager(PipelineStage):
    """
    Loads, validates, and exposes UCMP configuration; also serves as the
    Orchestrator's first pipeline stage.

    Parameters
    ----------
    config_path:
        Optional path to a user-supplied YAML config file. If omitted,
        only the built-in defaults (config/default_config.yaml) are used.
    env:
        Optional dict to use instead of the real process environment
        (primarily for testing). Passed through to ConfigLoader.
    """

    name = "ConfigurationManager"

    def __init__(
        self,
        config_path: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        self._config_path = config_path
        self._loader = ConfigLoader(env=env)
        self._validator = ConfigValidator()
        self._resolved_config: Optional[UCMPConfig] = None
        # Loaded eagerly so construction fails fast if config is invalid,
        # rather than failing mid-pipeline.
        self._resolved_config = self._load_and_validate()

    @property
    def resolved_config(self) -> UCMPConfig:
        """The typed, validated configuration object."""
        assert self._resolved_config is not None  # set in __init__
        return self._resolved_config

    def run(self, context: PipelineContext) -> PipelineContext:
        config_dict = dataclasses.asdict(self.resolved_config)
        context.config = config_dict
        context.metadata.setdefault("source_platform", self.resolved_config.source.platform)
        context.metadata.setdefault("target_platform", self.resolved_config.target.platform)
        context.metadata.setdefault("dry_run", self.resolved_config.pipeline.dry_run)
        context.set_artifact("resolved_config_summary", self._summary())

        self._apply_logging_level()

        logger.info(
            "Configuration resolved: source=%s target=%s dry_run=%s fail_fast=%s",
            self.resolved_config.source.platform,
            self.resolved_config.target.platform,
            self.resolved_config.pipeline.dry_run,
            self.resolved_config.pipeline.fail_fast,
        )
        return context

    # -- internals --------------------------------------------------------

    def _load_and_validate(self) -> UCMPConfig:
        try:
            raw = self._loader.load(self._config_path)
            return self._validator.validate(raw)
        except ConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConfigurationError(f"Unexpected error loading configuration: {exc}") from exc

    def _apply_logging_level(self) -> None:
        level_name = self.resolved_config.logging.level
        level = getattr(logging, level_name, logging.INFO)
        logging.getLogger("ucmp").setLevel(level)

    def _summary(self) -> Dict[str, Any]:
        cfg = self.resolved_config
        return {
            "project": f"{cfg.project.name} v{cfg.project.version}",
            "source_platform": cfg.source.platform,
            "target_platform": cfg.target.platform,
            "source_repo_path": cfg.source.repo_path,
            "target_repo_path": cfg.target.repo_path,
            "dry_run": cfg.pipeline.dry_run,
            "fail_fast": cfg.pipeline.fail_fast,
            "rules_dir": cfg.rules.rules_dir,
            "reports_dir": cfg.output.reports_dir,
            "output_mode": cfg.output.mode,
            "log_level": cfg.logging.level,
        }
