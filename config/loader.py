"""
config.loader
=============
Loads raw configuration as a plain nested dict, merging three layers in
increasing order of precedence:

    1. Built-in defaults (config/default_config.yaml, ships with ucmp-core)
    2. User-supplied YAML file (optional --config path)
    3. Environment variables prefixed `UCMP__`, using `__` as the nesting
       separator, e.g. UCMP__PIPELINE__DRY_RUN=false overrides
       config["pipeline"]["dry_run"].

The loader does NOT validate types or required fields — that is the
ConfigValidator's job (config/validator.py). The loader's only
responsibility is producing a single merged dict.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from common.exceptions import ConfigurationError
from common.logging_config import get_logger

logger = get_logger(__name__)

_ENV_PREFIX = "UCMP__"
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"

# Values that should be coerced from string env vars into real types.
_TRUE_STRINGS = {"1", "true", "yes", "on"}
_FALSE_STRINGS = {"0", "false", "no", "off"}


class ConfigLoader:
    """Produces a merged raw config dict from defaults + file + environment."""

    def __init__(self, env: Optional[Dict[str, str]] = None):
        # `env` is injectable for testing; defaults to the real process env.
        self._env = env if env is not None else os.environ

    def load(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        merged = self._load_yaml(_DEFAULT_CONFIG_PATH, required=True)

        if config_path:
            path = Path(config_path)
            user_config = self._load_yaml(path, required=True)
            merged = self._deep_merge(merged, user_config)
            logger.info("Merged user config from %s", path)
        else:
            logger.info("No user config path supplied; using built-in defaults only")

        env_overrides = self._collect_env_overrides()
        if env_overrides:
            merged = self._deep_merge(merged, env_overrides)
            logger.info("Applied %d environment variable override(s)", len(env_overrides))

        return merged

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _load_yaml(path: Path, required: bool) -> Dict[str, Any]:
        if not path.exists():
            if required:
                raise ConfigurationError(f"Config file not found: {path}")
            return {}
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigurationError(
                f"Config file {path} must contain a top-level mapping, "
                f"got {type(data).__name__}."
            )
        return data

    @classmethod
    def _deep_merge(cls, base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge `overlay` onto `base`, overlay taking precedence."""
        result = dict(base)
        for key, value in overlay.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _collect_env_overrides(self) -> Dict[str, Any]:
        """
        Scan environment variables for UCMP__ prefixed keys and turn them
        into a nested dict, e.g.:
            UCMP__PIPELINE__DRY_RUN=false
            UCMP__SOURCE__REPO_PATH=/tmp/repo
        becomes:
            {"pipeline": {"dry_run": False}, "source": {"repo_path": "/tmp/repo"}}
        """
        overrides: Dict[str, Any] = {}
        for raw_key, raw_value in self._env.items():
            if not raw_key.startswith(_ENV_PREFIX):
                continue
            path = raw_key[len(_ENV_PREFIX):].lower().split("__")
            if not path or path == [""]:
                continue
            self._set_nested(overrides, path, self._coerce(raw_value))
        return overrides

    @staticmethod
    def _set_nested(target: Dict[str, Any], path: list, value: Any) -> None:
        cursor = target
        for part in path[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[path[-1]] = value

    @staticmethod
    def _coerce(raw_value: str) -> Any:
        """Best-effort coercion of an env var string into bool/int/str."""
        lowered = raw_value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
        if raw_value.strip().lstrip("-").isdigit():
            return int(raw_value)
        return raw_value
