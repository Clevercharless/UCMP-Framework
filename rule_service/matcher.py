"""
rule_service.matcher
======================
`RuleMatcher` answers one question: given a construct's value and a list
of candidate rules (already filtered to the right category by the
caller), which rules match, and in what priority order? It performs no
substitution and makes no decision about *what to do* with a match — that
belongs to `RuleService`. This keeps the matching logic (exact / prefix /
regex) independently testable from the action-generation logic.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from rules.rule_models import MigrationRule, RuleMatchType

MatchResult = Tuple[MigrationRule, Optional[re.Match]]


class RuleMatcher:
    """Matches a construct value against a list of MigrationRule candidates."""

    def match(self, value: str, rules: List[MigrationRule]) -> List[MatchResult]:
        """
        Returns every rule that matches `value`, paired with its regex Match
        object (None for exact/prefix rules), sorted ascending by priority
        (lower priority number = evaluated/preferred first).
        """
        results: List[MatchResult] = []
        for rule in rules:
            match_obj = self._try_match(value, rule)
            if match_obj is not False:
                results.append((rule, match_obj))
        results.sort(key=lambda pair: pair[0].priority)
        return results

    @staticmethod
    def _try_match(value: str, rule: MigrationRule):
        """Returns a re.Match (or None for non-regex matches) on success, False on no match."""
        if rule.match_type == RuleMatchType.EXACT:
            return None if value == rule.pattern else False
        if rule.match_type == RuleMatchType.PREFIX:
            return None if value.startswith(rule.pattern) else False
        if rule.match_type == RuleMatchType.REGEX:
            match_obj = re.search(rule.pattern, value)
            return match_obj if match_obj else False
        return False  # pragma: no cover - unreachable given RuleMatchType enum
