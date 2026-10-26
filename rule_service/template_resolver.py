"""
rule_service.template_resolver
================================
Resolves a rule's `replacement_template` string into a concrete value.
Two kinds of placeholders are supported:

  * `{group_name}` - filled from the matching regex's named capture groups
    (only present when the rule's match_type is "regex").
  * `{config.dotted.path}` - filled by looking up a dotted path in
    `context.config` (e.g. `{config.target.catalog_name}`), for values
    that are environment-specific rather than derivable from the matched
    text itself.

Resolution never touches any notebook file - it only computes what the
resolved string *would be*. Writing that value into actual code is the
Replacement Engine's job (Module 9).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

_CONFIG_TOKEN_RE = re.compile(r"\{config\.([a-zA-Z0-9_.]+)\}")


class TemplateResolutionError(Exception):
    """Raised internally when a template references a placeholder that cannot be filled."""


class TemplateResolver:
    """Fills a replacement_template using regex match groups and config values."""

    def resolve(
        self,
        template: str,
        match: Optional[re.Match],
        config: Dict[str, Any],
    ) -> str:
        resolved = self._resolve_config_tokens(template, config)
        group_values = match.groupdict() if match else {}
        try:
            return resolved.format(**group_values)
        except (KeyError, IndexError) as exc:
            raise TemplateResolutionError(
                f"Template '{template}' references placeholder {exc} not present in "
                f"the regex match groups {list(group_values.keys())}"
            ) from exc

    # -- internals --------------------------------------------------------

    def _resolve_config_tokens(self, template: str, config: Dict[str, Any]) -> str:
        def replace(match_obj: re.Match) -> str:
            dotted_path = match_obj.group(1)
            value = self._lookup_dotted_path(config, dotted_path)
            if value is None:
                raise TemplateResolutionError(
                    f"Template '{template}' references config.{dotted_path}, "
                    f"which does not resolve to a value in context.config"
                )
            return str(value)

        return _CONFIG_TOKEN_RE.sub(replace, template)

    @staticmethod
    def _lookup_dotted_path(config: Dict[str, Any], dotted_path: str) -> Optional[Any]:
        cursor: Any = config
        for part in dotted_path.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return None
            cursor = cursor[part]
        return cursor
