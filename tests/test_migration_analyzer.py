# Databricks notebook source
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
    assert any(e.original_value.startswith("abfss://") and e.resolved_value == "s3://{bucket_name}/customer/" for e in edits)
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
    assert any(e.resolved_value == "s3://{bucket_name}/customer/" for e in result.edits)
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


def test_hardcoded_container_with_templated_account_uses_bucket_variable():
    text = (
        '# Databricks notebook source\n'
        'path = "abfss://qlikapps@{storage_account}.dfs.core.windows.net/customer/"\n'
    )
    result = MigrationAnalyzer({"qlikapps": "raw_qlik"}).analyze("Bronze/a.py", text)
    edit = next(e for e in result.edits if e.edit_type == "storage_path")
    assert edit.resolved_value == "s3://{bucket_name}/customer/"
    assert not edit.requires_manual_review
    assert any(e.edit_type == "add_target_config" for e in result.edits)


def test_hardcoded_container_with_dollar_templated_account_uses_bucket_variable():
    text = (
        '# Databricks notebook source\n'
        'path = "abfss://qlikapps@${storage_account}.dfs.core.windows.net/customer/"\n'
    )
    result = MigrationAnalyzer({"qlikapps": "raw_qlik"}).analyze("Bronze/a.py", text)
    edit = next(e for e in result.edits if e.edit_type == "storage_path")
    assert edit.resolved_value == "s3://{bucket_name}/customer/"
    assert not edit.requires_manual_review


def test_dynamic_workspace_prefix_reference_is_transformed():
    text = (
        '# Databricks notebook source\n'
        '%run ${workspace_prefix}/PFL/Delta-Lake/Common/utils\n'
    )
    result = MigrationAnalyzer(
        workspace_root="/Workspace/Users/test/pfl-repo"
    ).analyze("PFL/report.py", text)
    edit = next(e for e in result.edits if e.edit_type == "workspace_run_path")
    assert edit.original_value == "${workspace_prefix}/PFL/Delta-Lake/Common/utils"
    assert edit.resolved_value == "/Workspace/Users/test/pfl-repo/PFL/Delta-Lake/Common/utils"

def test_env_widget_is_replaced_with_os_getenv_when_target_root_uses_env():
    text = (
        '# Databricks notebook source\n'
        'import os\n'
        'env = dbutils.widgets.get("env")\n'
        '%run /Workspace/pfl/Common/utils\n'
    )
    result = MigrationAnalyzer(
        workspace_root="/Workspace/Deployed-Assets/{env}",
        referred_notebook_path_root="/Workspace/Deployed-Assets/{env}",
    ).analyze("Common/main.py", text)

    edit = next(e for e in result.edits if e.edit_type == "env_config_replace")
    assert edit.original_value == 'env = dbutils.widgets.get("env")'
    assert edit.resolved_value == 'env = os.getenv("env", "dev")'
    assert not any(e.edit_type == "add_target_config" and e.resolved_value == "import os" for e in result.edits)


def test_env_declaration_and_os_import_are_added_when_missing():
    text = '# Databricks notebook source\n%run /Workspace/pfl/Common/utils\n'
    result = MigrationAnalyzer(
        workspace_root="/Workspace/Deployed-Assets/{env}",
        referred_notebook_path_root="/Workspace/Deployed-Assets/{env}",
    ).analyze("Common/main.py", text)

    additions = {e.resolved_value for e in result.edits if e.edit_type == "add_target_config"}
    assert "import os" in additions
    assert 'env = os.getenv("env", "dev")' in additions


def test_existing_os_getenv_declaration_is_not_duplicated():
    text = (
        '# Databricks notebook source\n'
        'import os\n'
        'env = os.getenv("env")\n'
        '%run /Workspace/pfl/Common/utils\n'
    )
    result = MigrationAnalyzer(
        workspace_root="/Workspace/Deployed-Assets/{env}",
        referred_notebook_path_root="/Workspace/Deployed-Assets/{env}",
    ).analyze("Common/main.py", text)

    assert not any(
        e.edit_type == "add_target_config" and e.resolved_value.startswith("env =")
        for e in result.edits
    )
    assert any(e.edit_type == "env_config_existing" for e in result.edits)


def test_output_container_identifier_is_renamed_to_bucket_identifier():
    text = 'output_container_path = config["output_container_path"]\n'
    result = MigrationAnalyzer().analyze("Bronze/main.py", text)
    edit = next(e for e in result.edits if e.edit_type == "config_identifier_rename")
    assert edit.original_value == "output_container_path"
    assert edit.resolved_value == "output_bucket_name"
