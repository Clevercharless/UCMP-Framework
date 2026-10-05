2026-10-05 07:20:10 | INFO     | ucmp.config.loader               | Merged user config from config/default_config.yaml
2026-10-05 07:20:10 | INFO     | ucmp.orchestrator.orchestrator   | Starting migration pipeline run_id=01be45c117ea with 11 stage(s)
2026-10-05 07:20:10 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ConfigurationManager'
2026-10-05 07:20:10 | INFO     | ucmp.config.config_manager       | Configuration resolved: source=azure_databricks target=aws_databricks dry_run=False fail_fast=True
2026-10-05 07:20:10 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'ConfigurationManager' completed successfully
2026-10-05 07:20:10 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'AuthenticationManager'
2026-10-05 07:20:10 | INFO     | ucmp.auth.providers              | Simulating Azure AD auth for principal='svc-ucmp-azure-migration' workspace='https://dbc-823a9807-66e5.cloud.databricks.com/' key_vault='simulated-kv'
2026-10-05 07:20:10 | INFO     | ucmp.auth.providers              | Azure Databricks token minted (masked): ******************************************f8b4
2026-10-05 07:20:10 | INFO     | ucmp.auth.providers              | Simulating AWS STS assume-role for principal='svc-ucmp-aws-migration' workspace='https://dbc-823a9807-66e5.cloud.databricks.com/' catalog='main'
2026-10-05 07:20:10 | INFO     | ucmp.auth.providers              | AWS Databricks token minted (masked): ****************************************d6bf
2026-10-05 07:20:10 | INFO     | ucmp.auth.auth_manager           | Authentication simulation complete: azure=******************************************f8b4 aws=****************************************d6bf
2026-10-05 07:20:10 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'AuthenticationManager' completed successfully
2026-10-05 07:20:10 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'RepositoryManager'
2026-10-05 07:20:10 | INFO     | ucmp.repository.repository_manager | RepositoryManager using real Databricks workspace discovery; no user-created PAT is required
/databricks/python_shell/lib/third_party/python/vendor/protobuf/google/protobuf/internal/api_implementation.py:120: UserWarning: Selected implementation upb is not available. Falling back to the python implementation.
  warnings.warn('Selected implementation upb is not available. '
2026-10-05 07:20:13 | ERROR    | ucmp.orchestrator.orchestrator   | <- Stage 'RepositoryManager' failed: No Databricks access token was supplied, the current Databricks notebook execution context was unavailable, and native Databricks SDK authentication could not be initialized: default auth: runtime: 'NoneType' object has no attribute 'parent_header'
Traceback (most recent call last):
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/credentials_provider.py", line 1471, in __call__
    header_factory = provider(cfg)
                     ^^^^^^^^^^^^^
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/credentials_provider.py", line 101, in wrapper
    return func(cfg)
           ^^^^^^^^^
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/credentials_provider.py", line 191, in runtime_native_auth
    host, inner = init()
                  ^^^^^^
  File "/databricks/python_shell/lib/dbruntime/sdk_credential_provider.py", line 6, in init_runtime_native_auth
    host = _get_ipython_attribute("api_url")
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/databricks/python_shell/lib/dbruntime/sdk_credential_provider.py", line 27, in _get_ipython_attribute
    return _getIpython().parent_header['metadata']['commandMetadata']['extraContext'][attr]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'parent_header'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/config.py", line 834, in init_auth
    self._header_factory = self._credentials_strategy(self)
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/credentials_provider.py", line 1478, in __call__
    raise ValueError(f"{auth_type}: {e}") from e
ValueError: runtime: 'NoneType' object has no attribute 'parent_header'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/config.py", line 323, in __init__
    self.init_auth()
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/config.py", line 839, in init_auth
    raise ValueError(f"{self._credentials_strategy.auth_type()} auth: {e}") from e
ValueError: default auth: runtime: 'NoneType' object has no attribute 'parent_header'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/repository/databricks_workspace.py", line 112, in __init__
    self._sdk_client = WorkspaceClient()
                       ^^^^^^^^^^^^^^^^^
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/__init__.py", line 327, in __init__
    config = client.Config(
             ^^^^^^^^^^^^^^
  File "/databricks/python/lib/python3.12/site-packages/databricks/sdk/config.py", line 327, in __init__
    raise ValueError(message) from e
ValueError: default auth: runtime: 'NoneType' object has no attribute 'parent_header'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/orchestrator/orchestrator.py", line 105, in _run_stage
    updated_context = stage.run(context)
                      ^^^^^^^^^^^^^^^^^^
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/repository/repository_manager.py", line 101, in run
    inventory = self._sync_databricks_workspace(source_cfg)
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/repository/repository_manager.py", line 168, in _sync_databricks_workspace
    client = DatabricksWorkspaceClient(workspace_url)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/repository/databricks_workspace.py", line 120, in __init__
    raise RepositoryError(
common.exceptions.RepositoryError: No Databricks access token was supplied, the current Databricks notebook execution context was unavailable, and native Databricks SDK authentication could not be initialized: default auth: runtime: 'NoneType' object has no attribute 'parent_header'
2026-10-05 07:20:13 | ERROR    | ucmp.orchestrator.orchestrator   | Stage 'RepositoryManager' failed; aborting pipeline (fail_fast=True)
2026-10-05 07:20:13 | INFO     | ucmp.orchestrator.orchestrator   | Pipeline run_id=01be45c117ea finished with overall status=FAILED

======================================================================
UCMP PIPELINE RESULT
======================================================================
  ConfigurationManager         SUCCESS    0.0007s
  AuthenticationManager        SUCCESS    0.0009s
  RepositoryManager            FAILED     3.3663s

Overall pipeline status: FAILED
