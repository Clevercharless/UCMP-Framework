"""
transformation.transformation_planner
========================================
`TransformationPlanner` is the eighth pipeline stage. It combines:

  * The Migration Knowledge Model (Module 5) — which notebooks exist, and
    what business logic (shared functions, business tables) they contain.
  * The Rule Service output (Module 7) — one resolved action per unique
    construct value, each tagged with every notebook it was found in.

...into a `TransformationPlan.json`: one ordered list of operations per
notebook, ready for the Replacement Engine (Module 9) to actually execute.
This stage performs no file writes to any notebook — only to the plan
JSON itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from common.exceptions import TransformationPlannerError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage
from transformation.operation_types import OperationType, derive_operation_type
from transformation.plan_models import (
    NotebookTransformationPlan,
    TransformationOperation,
    TransformationPlan,
)

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TransformationPlanner(PipelineStage):
    """Builds the ordered, per-notebook TransformationPlan and writes it to disk."""

    name = "TransformationPlanner"

    def run(self, context: PipelineContext) -> PipelineContext:
        knowledge_model = context.get_artifact("knowledge_model")
        rule_service_output = context.get_artifact("rule_service_output")

        if not knowledge_model:
            raise TransformationPlannerError(
                "TransformationPlanner requires context.artifacts['knowledge_model'] "
                "to be populated (run ParserEngine first)"
            )
        if not rule_service_output:
            raise TransformationPlannerError(
                "TransformationPlanner requires context.artifacts['rule_service_output'] "
                "to be populated (run RuleService first)"
            )
        if not context.config:
            raise TransformationPlannerError("TransformationPlanner requires context.config")

        operations_by_notebook = self._explode_actions_by_notebook(
            rule_service_output["actions"]
        )
        self._add_migration_specific_operations(operations_by_notebook, context.get_artifact("migration_analyses", []))

        plan = TransformationPlan(repo_name=knowledge_model["repo_name"])
        for notebook_meta in knowledge_model["notebook_metadata"]:
            plan.notebook_plans.append(
                self._build_notebook_plan(notebook_meta, operations_by_notebook)
            )

        # Classify every selected notebook before ReplacementEngine is allowed
        # to write changes. This is informational and does not alter business logic.
        classification = self._classify_notebooks(plan.to_dict()["notebook_plans"])
        context.set_artifact("migration_classification", classification)

        output_path = self._write_plan(context, plan.to_dict())

        context.set_artifact("transformation_plan", plan.to_dict())
        context.metadata["transformation_planner_complete"] = True
        context.metadata["transformation_plan_path"] = str(output_path)

        summary = plan.to_dict()["summary"]
        logger.info(
            "Transformation plan built: %d notebook(s), %d operation(s), "
            "%d notebook(s) need manual review. Written to %s",
            summary["notebook_count"],
            summary["total_operations"],
            summary["notebooks_with_manual_review"],
            output_path,
        )
        return context

    # -- internals --------------------------------------------------------

    def _explode_actions_by_notebook(
        self, actions: List[Dict]
    ) -> Dict[str, List[TransformationOperation]]:
        """
        Rule Service actions are deduplicated by construct VALUE across the
        whole repo (one action, many `found_in` notebooks). The plan needs
        the inverse: for each notebook, which operations apply to it. This
        "explodes" each action back out into one operation per notebook it
        was found in.
        """
        by_notebook: Dict[str, List[TransformationOperation]] = {}
        for action in actions:
            operation_type = derive_operation_type(action["rule_category"], action["action"])
            for notebook_path in action["found_in"]:
                operation = TransformationOperation(
                    operation_type=operation_type,
                    category=action["rule_category"],
                    action=action["action"],
                    construct_type=action["construct_type"],
                    original_value=action["original_value"],
                    resolved_value=action["resolved_value"],
                    rule_id=action["matched_rule_id"],
                    requires_manual_review=action["requires_manual_review"],
                    notes=action["notes"],
                )
                by_notebook.setdefault(notebook_path, []).append(operation)
        return by_notebook

    @staticmethod
    def _add_migration_specific_operations(
        operations_by_notebook: Dict[str, List[TransformationOperation]], analyses: List[Dict]
    ) -> None:
        """Add the user-agreed storage/workspace transformations to the normal plan."""
        for analysis in analyses or []:
            notebook = analysis.get("notebook")
            for edit in analysis.get("edits", []):
                edit_type = edit.get("edit_type")
                if edit_type == "storage_path":
                    op_type = OperationType.REPLACE_STORAGE_PATH
                    action = "replace"
                elif edit_type in {"workspace_run_path", "workspace_variable_path", "referred_notebook_path"}:
                    op_type = OperationType.TRANSFORM_WORKSPACE_NOTEBOOK_PATH
                    action = "replace"
                elif edit_type == "comment_source_config":
                    op_type = OperationType.COMMENT_SOURCE_CONFIG
                    action = "replace"
                elif edit_type == "add_target_config":
                    op_type = OperationType.ADD_TARGET_CONFIG
                    action = "add_config"
                else:
                    continue
                operations_by_notebook.setdefault(notebook, []).append(
                    TransformationOperation(
                        operation_type=op_type,
                        category="migration_specific",
                        action=action,
                        construct_type=edit.get("construct_type"),
                        original_value=edit.get("original_value") or None,
                        resolved_value=edit.get("resolved_value"),
                        rule_id=None,
                        requires_manual_review=bool(edit.get("requires_manual_review")),
                        notes=edit.get("notes"),
                    )
                )

    def _build_notebook_plan(
        self, notebook_meta: Dict, operations_by_notebook: Dict[str, List[TransformationOperation]]
    ) -> NotebookTransformationPlan:
        relative_path = notebook_meta["relative_path"]

        plan = NotebookTransformationPlan(
            relative_path=relative_path, category=notebook_meta["category"]
        )
        plan.operations.append(self._build_keep_business_logic_operation(notebook_meta))

        construct_operations = operations_by_notebook.get(relative_path, [])
        construct_operations.sort(key=lambda op: (op.category, op.original_value or ""))
        plan.operations.extend(construct_operations)

        return plan

    @staticmethod
    def _build_keep_business_logic_operation(notebook_meta: Dict) -> TransformationOperation:
        function_count = notebook_meta.get("function_def_count", 0)
        table_count = notebook_meta.get("table_dependency_count", 0)
        notes = (
            f"Preserve business logic as-is: {function_count} function definition(s), "
            f"{table_count} table reference(s) referencing domain data (customers, loans, "
            f"accounts). Only Azure-specific infrastructure constructs are modified by "
            f"this migration; transformation logic, business rules, and SQL semantics "
            f"are untouched."
        )
        return TransformationOperation(
            operation_type=OperationType.KEEP_BUSINESS_LOGIC,
            category="business_logic",
            action="keep",
            construct_type=None,
            original_value=None,
            resolved_value=None,
            rule_id=None,
            requires_manual_review=False,
            notes=notes,
        )

    @staticmethod
    def _classify_notebooks(notebook_plans: List[Dict]) -> Dict:
        """Classify selected notebooks before any replacement is performed."""
        changes_required = []
        no_changes_required = []
        manual_review = []
        for plan in notebook_plans:
            actionable = [
                op for op in plan.get("operations", [])
                if op.get("action") in {"replace", "remove", "add_config"}
            ]
            if actionable:
                changes_required.append(plan["relative_path"])
            else:
                no_changes_required.append(plan["relative_path"])
            if any(op.get("requires_manual_review") for op in actionable):
                manual_review.append(plan["relative_path"])
        return {
            "changes_required": changes_required,
            "no_changes_required": no_changes_required,
            "manual_review": manual_review,
            "total_selected": len(notebook_plans),
        }

    def _write_plan(self, context: PipelineContext, plan_dict: Dict) -> Path:
        output_dir_config = context.config["output"]["reports_dir"]
        output_dir = Path(output_dir_config)
        if not output_dir.is_absolute():
            output_dir = _PROJECT_ROOT / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "TransformationPlan.json"
        output_path.write_text(json.dumps(plan_dict, indent=2, default=str), encoding="utf-8")
        return output_path
