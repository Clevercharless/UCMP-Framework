from parser.migration_analyzer import MigrationAnalyzer


def test_configured_container_and_account_path():
    text = (
        '# Databricks notebook source\n'
        'container = dbutils.widgets.get("container")\n'
        'storage_account = dbutils.widgets.get("storage_account")\n'
        'path = f"abfss://{container}@{storage_account}.dfs.core.windows.net/customer/"\n'
    )
    result = MigrationAnalyzer().analyze("Bronze/a.py", text)
    edits = result.edits
    assert any(e.original_value.startswith("abfss://") and e.resolved_value == "s3://{bucket}/customer/" for e in edits)
    assert sum(e.edit_type == "comment_source_config" for e in edits) == 2
    assert any(e.edit_type == "add_target_config" for e in edits)
    assert not result.requires_review


def test_hardcoded_container_with_configured_account_uses_bucket_variable():
    text = (
        '# Databricks notebook source\n'
        'storage_account = dbutils.widgets.get("storage_account")\n'
        'path = f"abfss://qlikapps@{storage_account}.dfs.core.windows.net/customer/"\n'
    )
    result = MigrationAnalyzer().analyze("Bronze/a.py", text)
    assert any(e.resolved_value == "s3://{bucket}/customer/" for e in result.edits)
    assert any(e.original_value.startswith("storage_account =") for e in result.edits)


def test_hardcoded_path_uses_container_bucket_mapping():
    text = 'path = "abfss://qlikapps@companyadls.dfs.core.windows.net/customer/"\n'
    result = MigrationAnalyzer({"qlikapps": "raw_qlik"}).analyze("Bronze/a.py", text)
    assert any(e.resolved_value == "s3://raw_qlik/customer/" for e in result.edits)
    assert not result.requires_review


def test_missing_mapping_is_reviewed_with_mechanical_transformation():
    text = 'path = "abfss://unknown@companyadls.dfs.core.windows.net/customer/"\n'
    result = MigrationAnalyzer().analyze("Bronze/a.py", text)
    edit = next(e for e in result.edits if e.edit_type == "storage_path")
    assert edit.resolved_value == "s3://unknown/customer/"
    assert edit.requires_manual_review
    assert result.requires_review


def test_workspace_run_and_variable_paths_are_transformed():
    text = (
        '# Databricks notebook source\n'
        '%run /workspace/pfl/common/utils\n'
        'NOTEBOOK_PATH = "/workspace/pfl/bronze/ingest"\n'
    )
    result = MigrationAnalyzer().analyze("Bronze/a.py", text)
    values = {(e.edit_type, e.resolved_value) for e in result.edits}
    assert ("workspace_run_path", "${WORKSPACE_ROOT}/pfl/common/utils") in values
    assert ("workspace_variable_path", "${WORKSPACE_ROOT}/pfl/bronze/ingest") in values
