"""
transformation.operation_types
================================
Defines the taxonomy of planned operations the Transformation Planner can
emit, and the mapping from a Rule Service (category, action) pair to a
human-readable operation type — matching the spec's own examples (Replace
Storage Path, Replace Secret Scope, Replace Workspace URL, Remove Azure
SDK, Keep Business Logic, Flag Manual Review).

This mapping is presentation/grouping only: the underlying `action`
(replace/remove/manual_review/no_change/unmatched) from Rule Service
remains on every operation, so nothing here changes what will actually
happen — it only makes the plan and its reports easier to read.
"""

from __future__ import annotations

from enum import Enum


class OperationType(str, Enum):
    REPLACE_STORAGE_PATH = "replace_storage_path"
    REPLACE_SECRET_SCOPE = "replace_secret_scope"
    REPLACE_WORKSPACE_URL = "replace_workspace_url"
    REPLACE_CATALOG_NAME = "replace_catalog_name"
    REMOVE_AZURE_SDK_IMPORT = "remove_azure_sdk_import"
    REMOVE_SPARK_CONFIG = "remove_spark_config"
    REMOVE_STORAGE_REFERENCE = "remove_storage_reference"
    REMOVE_SECRET_REFERENCE = "remove_secret_reference"
    GENERIC_REPLACE = "generic_replace"
    GENERIC_REMOVE = "generic_remove"
    FLAG_MANUAL_REVIEW = "flag_manual_review"
    NO_CHANGE = "no_change"
    UNMATCHED_NEEDS_RULE = "unmatched_needs_rule"
    KEEP_BUSINESS_LOGIC = "keep_business_logic"
    TRANSFORM_WORKSPACE_NOTEBOOK_PATH = "transform_workspace_notebook_path"
    COMMENT_SOURCE_CONFIG = "comment_source_config"
    ADD_TARGET_CONFIG = "add_target_config"


_REPLACE_BY_CATEGORY = {
    "storage": OperationType.REPLACE_STORAGE_PATH,
    "secret": OperationType.REPLACE_SECRET_SCOPE,
    "workspace": OperationType.REPLACE_WORKSPACE_URL,
    "catalog": OperationType.REPLACE_CATALOG_NAME,
}

_REMOVE_BY_CATEGORY = {
    "storage": OperationType.REMOVE_STORAGE_REFERENCE,
    "secret": OperationType.REMOVE_SECRET_REFERENCE,
    "spark": OperationType.REMOVE_SPARK_CONFIG,
    "library": OperationType.REMOVE_AZURE_SDK_IMPORT,
}


def derive_operation_type(category: str, action: str) -> OperationType:
    """
    Maps a Rule Service (category, action) pair onto the friendliest
    matching OperationType. `action` always remains the source of truth
    for what actually happens; this is purely a readable label.
    """
    if action == "replace":
        return _REPLACE_BY_CATEGORY.get(category, OperationType.GENERIC_REPLACE)
    if action == "remove":
        return _REMOVE_BY_CATEGORY.get(category, OperationType.GENERIC_REMOVE)
    if action == "manual_review":
        return OperationType.FLAG_MANUAL_REVIEW
    if action == "no_change":
        return OperationType.NO_CHANGE
    if action == "unmatched":
        return OperationType.UNMATCHED_NEEDS_RULE
    return OperationType.FLAG_MANUAL_REVIEW  # pragma: no cover - defensive fallback
