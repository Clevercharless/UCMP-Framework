"""
rule_service.rule_service
============================
`RuleService` is the seventh pipeline stage. For every transformation
candidate the Parser Engine (Module 5) found, it:

  1. Looks up candidate rules in the matching category from the
     RuleRepository (Module 6).
  2. Matches the construct's value against those rules (exact/prefix/regex),
     resolving conflicts by priority (lowest number wins).
  3. Resolves the winning rule's action into a concrete `TransformationAction`
     — computing the replacement string for `replace` rules, but never
     writing it anywhere.

Per the spec: "Rule Service must NEVER modify notebook code." This stage
performs zero filesystem writes to any notebook; it only produces data
for the Transformation Planner (Module 8) to plan around.
"""

from __future__ import annotations

from typing import Dict, List

from common.exceptions import RuleServiceError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from rule_service.matcher import RuleMatcher
from rule_service.template_resolver import TemplateResolutionError, TemplateResolver
from rule_service.transformation_action import TransformationAction
from rules.rule_models import RuleAction
from rules.rule_repository import RuleRepository

logger = get_logger(__name__)


class RuleService(PipelineStage):
    """
    Matches Parser Engine transformation candidates against RuleRepository
    rules and produces TransformationActions. Read-only with respect to
    notebook content — it never modifies any notebook file.
    """

    name = "RuleService"

    def __init__(self, rule_repository: RuleRepository):
        self._rule_repository = rule_repository
        self._matcher = RuleMatcher()
        self._template_resolver = TemplateResolver()

    def run(self, context: PipelineContext) -> PipelineContext:
        knowledge_model = context.get_artifact("knowledge_model")
        if not knowledge_model:
            raise RuleServiceError(
                "RuleService requires context.artifacts['knowledge_model'] to be populated "
                "(run ParserEngine first)"
            )
        if not context.get_artifact("rule_repository"):
            raise RuleServiceError(
                "RuleService requires context.artifacts['rule_repository'] to be populated "
                "(run RuleRepository first)"
            )

        migration_edits = context.get_artifact("migration_analyses", []) or []
        migration_storage_values = {
            edit.get("original_value")
            for analysis in migration_edits
            for edit in analysis.get("edits", [])
            if edit.get("edit_type") == "storage_path"
        }
        actions: List[TransformationAction] = []
        for candidate in knowledge_model["transformation_candidates"]:
            if (candidate.get("construct_type") == "abfss_path"
                    and candidate.get("value") in migration_storage_values):
                continue
            actions.append(self._resolve_candidate(candidate, context.config))

        summary = self._summarize(actions)
        context.set_artifact(
            "rule_service_output",
            {"actions": [a.to_dict() for a in actions], "summary": summary},
        )
        context.metadata["rule_service_complete"] = True

        logger.info(
            "Rule Service resolved %d transformation candidate(s): %s",
            len(actions),
            summary,
        )
        return context

    # -- internals --------------------------------------------------------

    def _resolve_candidate(self, candidate: Dict, config: Dict) -> TransformationAction:
        value = candidate["value"]
        construct_type = candidate["construct_type"]
        category = candidate["rule_category_hint"].removesuffix("_rules")
        occurrences = candidate["occurrences"]
        found_in = candidate["found_in"]

        candidate_rules = self._rule_repository.get_rules(category)
        matches = self._matcher.match(value, candidate_rules)

        if not matches:
            return TransformationAction(
                construct_type=construct_type,
                original_value=value,
                rule_category=category,
                action="unmatched",
                matched_rule_id=None,
                resolved_value=None,
                requires_manual_review=True,
                occurrences=occurrences,
                found_in=found_in,
                candidate_rule_ids=[],
                notes=f"No rule in category '{category}' matched this construct; "
                f"needs a new rule or manual handling.",
            )

        winning_rule, match_obj = matches[0]
        candidate_rule_ids = [rule.rule_id for rule, _ in matches]

        return self._build_action(
            construct_type, value, category, occurrences, found_in,
            winning_rule, match_obj, candidate_rule_ids, config,
        )

    def _build_action(
        self, construct_type, value, category, occurrences, found_in,
        rule, match_obj, candidate_rule_ids, config,
    ) -> TransformationAction:
        base_kwargs = dict(
            construct_type=construct_type,
            original_value=value,
            rule_category=category,
            matched_rule_id=rule.rule_id,
            occurrences=occurrences,
            found_in=found_in,
            candidate_rule_ids=candidate_rule_ids,
            notes=rule.description.strip(),
        )

        if rule.action == RuleAction.NO_CHANGE:
            return TransformationAction(
                action="no_change", resolved_value=value,
                requires_manual_review=False, **base_kwargs,
            )

        if rule.action == RuleAction.REMOVE:
            return TransformationAction(
                action="remove", resolved_value=None,
                requires_manual_review=rule.requires_manual_review, **base_kwargs,
            )

        if rule.action == RuleAction.MANUAL_REVIEW:
            return TransformationAction(
                action="manual_review", resolved_value=None,
                requires_manual_review=True, **base_kwargs,
            )

        # RuleAction.REPLACE
        try:
            resolved_value = self._template_resolver.resolve(
                rule.replacement_template, match_obj, config
            )
            return TransformationAction(
                action="replace", resolved_value=resolved_value,
                requires_manual_review=rule.requires_manual_review, **base_kwargs,
            )
        except TemplateResolutionError as exc:
            logger.warning(
                "Rule '%s' matched '%s' but its template could not be resolved: %s",
                rule.rule_id, value, exc,
            )
            base_kwargs["notes"] = f"{base_kwargs['notes']} | UNRESOLVED: {exc}"
            return TransformationAction(
                action="manual_review", resolved_value=None,
                requires_manual_review=True, **base_kwargs,
            )

    @staticmethod
    def _summarize(actions: List[TransformationAction]) -> Dict:
        summary = {
            "total": len(actions),
            "replace": 0, "remove": 0, "manual_review": 0,
            "no_change": 0, "unmatched": 0,
            "requires_manual_review_count": 0,
        }
        for action in actions:
            summary[action.action] = summary.get(action.action, 0) + 1
            if action.requires_manual_review:
                summary["requires_manual_review_count"] += 1
        return summary
