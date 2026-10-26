**************************cc8d
2026-10-26 11:44:32 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'AuthenticationManager' completed successfully
2026-10-26 11:44:32 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'AuthenticationManager' completed successfully
2026-10-26 11:44:32 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'RepositoryManager'
2026-10-26 11:44:32 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'RepositoryManager'
2026-10-26 11:44:32 | INFO     | ucmp.repository.repository_manager | RepositoryManager running in real Databricks workspace mode
2026-10-26 11:44:32 | INFO     | ucmp.repository.repository_manager | RepositoryManager running in real Databricks workspace mode
2026-10-26 11:44:32 | INFO     | ucmp.repository.repository_manager | Workspace root: /Workspace/Users/charless.binny@poonawallafincorp.com/pfl-repo-dbx-datalake
2026-10-26 11:44:32 | INFO     | ucmp.repository.repository_manager | Workspace root: /Workspace/Users/charless.binny@poonawallafincorp.com/pfl-repo-dbx-datalake
2026-10-26 11:44:33 | INFO     | ucmp.repository.databricks_workspace | DatabricksWorkspaceClient using native Databricks SDK authentication
2026-10-26 11:44:33 | INFO     | ucmp.repository.databricks_workspace | DatabricksWorkspaceClient using native Databricks SDK authentication
2026-10-26 11:44:33 | INFO     | ucmp.repository.repository_manager | Discovering Databricks workspace recursively: /Workspace/Users/charless.binny@poonawallafincorp.com/pfl-repo-dbx-datalake
2026-10-26 11:44:33 | INFO     | ucmp.repository.repository_manager | Discovering Databricks workspace recursively: /Workspace/Users/charless.binny@poonawallafincorp.com/pfl-repo-dbx-datalake
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Discovered 7461 workspace object(s)
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Discovered 7461 workspace object(s)
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Discovered 5923 source notebook(s)
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Discovered 5923 source notebook(s)
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Using migration.notebook_list with 1 notebook(s)
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Using migration.notebook_list with 1 notebook(s)
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Selected 1 notebook(s) for migration
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Selected 1 notebook(s) for migration
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Selected notebook exported: /Workspace/Users/charless.binny@poonawallafincorp.com/pfl-repo-dbx-datalake/PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report -> /tmp/ucmp_workspace_selected_39612v6_/PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Selected notebook exported: /Workspace/Users/charless.binny@poonawallafincorp.com/pfl-repo-dbx-datalake/PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report -> /tmp/ucmp_workspace_selected_39612v6_/PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Workspace preparation completed successfully: 1 notebook(s) exported for migration
2026-10-26 11:45:10 | INFO     | ucmp.repository.repository_manager | Workspace preparation completed successfully: 1 notebook(s) exported for migration
2026-10-26 11:45:10 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'RepositoryManager' completed successfully
2026-10-26 11:45:10 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'RepositoryManager' completed successfully
2026-10-26 11:45:10 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ParserEngine'
2026-10-26 11:45:10 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ParserEngine'
2026-10-26 11:45:10 | INFO     | ucmp.parser.parser_engine        | Parsed 1 notebook(s); 0 dependency edge(s), 1 azure construct(s), 0 manual review item(s). Knowledge model written to /Workspace/Users/charless.binny@poonawallafincorp.com/ucmp-demo/reports/knowledge_model/MigrationKnowledgeModel.json
2026-10-26 11:45:10 | INFO     | ucmp.parser.parser_engine        | Parsed 1 notebook(s); 0 dependency edge(s), 1 azure construct(s), 0 manual review item(s). Knowledge model written to /Workspace/Users/charless.binny@poonawallafincorp.com/ucmp-demo/reports/knowledge_model/MigrationKnowledgeModel.json
2026-10-26 11:45:10 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'ParserEngine' completed successfully
2026-10-26 11:45:10 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'ParserEngine' completed successfully
2026-10-26 11:45:10 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'RuleRepository'
2026-10-26 11:45:10 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'RuleRepository'
2026-10-26 11:45:11 | INFO     | ucmp.rules.rule_repository       | Loaded 9 rule(s) from 1 file(s) across categories: ['azure_blob', 'azure_identity', 'jdbc', 'secret', 'storage', 'workspace']
2026-10-26 11:45:11 | INFO     | ucmp.rules.rule_repository       | Loaded 9 rule(s) from 1 file(s) across categories: ['azure_blob', 'azure_identity', 'jdbc', 'secret', 'storage', 'workspace']
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'RuleRepository' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'RuleRepository' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'RuleService'
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'RuleService'
2026-10-26 11:45:11 | INFO     | ucmp.rule_service.rule_service   | Rule Service resolved 0 transformation candidate(s): {'total': 0, 'replace': 0, 'remove': 0, 'manual_review': 0, 'no_change': 0, 'unmatched': 0, 'requires_manual_review_count': 0}
2026-10-26 11:45:11 | INFO     | ucmp.rule_service.rule_service   | Rule Service resolved 0 transformation candidate(s): {'total': 0, 'replace': 0, 'remove': 0, 'manual_review': 0, 'no_change': 0, 'unmatched': 0, 'requires_manual_review_count': 0}
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'RuleService' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'RuleService' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'TransformationPlanner'
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'TransformationPlanner'
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG migration_analyses: [{'notebook': 'PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py', 'changed': True, 'requires_review': True, 'edits': [{'notebook': 'PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py', 'edit_type': 'storage_path', 'original_value': 'abfss://dart-input-files@sapfldloperationsci001.dfs.core.windows.net/CKYC', 'resolved_value': 's3://dart-input-files/CKYC', 'line_number': 66, 'requires_manual_review': True, 'notes': "No container-to-bucket mapping found for 'dart-input-files'; mechanical S3 placeholder applied and manual verification required.", 'construct_type': 'abfss_path'}], 'review_items': []}]
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG migration_analyses: [{'notebook': 'PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py', 'changed': True, 'requires_review': True, 'edits': [{'notebook': 'PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py', 'edit_type': 'storage_path', 'original_value': 'abfss://dart-input-files@sapfldloperationsci001.dfs.core.windows.net/CKYC', 'resolved_value': 's3://dart-input-files/CKYC', 'line_number': 66, 'requires_manual_review': True, 'notes': "No container-to-bucket mapping found for 'dart-input-files'; mechanical S3 placeholder applied and manual verification required.", 'construct_type': 'abfss_path'}], 'review_items': []}]
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG migration edit received by planner: {'notebook': 'PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py', 'edit_type': 'storage_path', 'original_value': 'abfss://dart-input-files@sapfldloperationsci001.dfs.core.windows.net/CKYC', 'resolved_value': 's3://dart-input-files/CKYC', 'line_number': 66, 'requires_manual_review': True, 'notes': "No container-to-bucket mapping found for 'dart-input-files'; mechanical S3 placeholder applied and manual verification required.", 'construct_type': 'abfss_path'}
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG migration edit received by planner: {'notebook': 'PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py', 'edit_type': 'storage_path', 'original_value': 'abfss://dart-input-files@sapfldloperationsci001.dfs.core.windows.net/CKYC', 'resolved_value': 's3://dart-input-files/CKYC', 'line_number': 66, 'requires_manual_review': True, 'notes': "No container-to-bucket mapping found for 'dart-input-files'; mechanical S3 placeholder applied and manual verification required.", 'construct_type': 'abfss_path'}
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG operaions_by_notebook: ['PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py']
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG operaions_by_notebook: ['PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py']
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG notebook=PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py operations=[{'type': <OperationType.REPLACE_STORAGE_PATH: 'replace_storage_path'>, 'action': 'replace', 'origial': 'abfss://dart-input-files@sapfldloperationsci001.dfs.core.windows.net/CKYC', 'resolved': 's3://dart-input-files/CKYC'}]
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG notebook=PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py operations=[{'type': <OperationType.REPLACE_STORAGE_PATH: 'replace_storage_path'>, 'action': 'replace', 'origial': 'abfss://dart-input-files@sapfldloperationsci001.dfs.core.windows.net/CKYC', 'resolved': 's3://dart-input-files/CKYC'}]
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG build plan lookup: relative_path=PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py, available_keys=['PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py']
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | DEBUG build plan lookup: relative_path=PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py, available_keys=['PFL/Delta-Lake/Notebook_Execution/CKYC Communication/CKYC_Communication_report.py']
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | Transformation plan built: 1 notebook(s), 2 operation(s), 1 notebook(s) need manual review. Written to /Workspace/Users/charless.binny@poonawallafincorp.com/ucmp-demo/reports/TransformationPlan.json
2026-10-26 11:45:11 | INFO     | ucmp.transformation.transformation_planner | Transformation plan built: 1 notebook(s), 2 operation(s), 1 notebook(s) need manual review. Written to /Workspace/Users/charless.binny@poonawallafincorp.com/ucmp-demo/reports/TransformationPlan.json
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'TransformationPlanner' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'TransformationPlanner' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ReplacementEngine'
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ReplacementEngine'
2026-10-26 11:45:11 | INFO     | ucmp.replacement.replacement_engine | Replacement Engine wrote 1 notebook(s) (1 operation(s) applied, 1 notebook(s) flagged for review) + 0 config asset(s) to /tmp/ucmp_workspace_preview_9kzehw68
2026-10-26 11:45:11 | INFO     | ucmp.replacement.replacement_engine | Replacement Engine wrote 1 notebook(s) (1 operation(s) applied, 1 notebook(s) flagged for review) + 0 config asset(s) to /tmp/ucmp_workspace_preview_9kzehw68
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'ReplacementEngine' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'ReplacementEngine' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ValidationEngine'
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ValidationEngine'
2026-10-26 11:45:11 | INFO     | ucmp.validation.validation_engine | Validation complete: overall_status=PASS (0 error(s), 0 warning(s), 7 info)
2026-10-26 11:45:11 | INFO     | ucmp.validation.validation_engine | Validation complete: overall_status=PASS (0 error(s), 0 warning(s), 7 info)
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'ValidationEngine' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'ValidationEngine' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'DeploymentEngine'
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'DeploymentEngine'
2026-10-26 11:45:11 | INFO     | ucmp.deployment.deployment_engine | Deployment engine finished: overall_status=READY_NOT_DEPLOYED (mode=workspace_preview, 2 step(s))
2026-10-26 11:45:11 | INFO     | ucmp.deployment.deployment_engine | Deployment engine finished: overall_status=READY_NOT_DEPLOYED (mode=workspace_preview, 2 step(s))
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'DeploymentEngine' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | <- Stage 'DeploymentEngine' completed successfully
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ReportingEngine'
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | -> Running stage 'ReportingEngine'
2026-10-26 11:45:11 | ERROR    | ucmp.orchestrator.orchestrator   | <- Stage 'ReportingEngine' failed: ReportingEngine._write_reports() missing 1 required positional argument: 'context'
Traceback (most recent call last):
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/orchestrator/orchestrator.py", line 105, in _run_stage
    updated_context = stage.run(context)
                      ^^^^^^^^^^^^^^^^^^
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/reporting/reporting_engine.py", line 83, in run
    written_paths = self._write_reports(output_dir, reports, context)
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: ReportingEngine._write_reports() missing 1 required positional argument: 'context'
2026-10-26 11:45:11 | ERROR    | ucmp.orchestrator.orchestrator   | <- Stage 'ReportingEngine' failed: ReportingEngine._write_reports() missing 1 required positional argument: 'context'
Traceback (most recent call last):
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/orchestrator/orchestrator.py", line 105, in _run_stage
    updated_context = stage.run(context)
                      ^^^^^^^^^^^^^^^^^^
  File "/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/reporting/reporting_engine.py", line 83, in run
    written_paths = self._write_reports(output_dir, reports, context)
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: ReportingEngine._write_reports() missing 1 required positional argument: 'context'
2026-10-26 11:45:11 | ERROR    | ucmp.orchestrator.orchestrator   | Stage 'ReportingEngine' failed; aborting pipeline (fail_fast=True)
2026-10-26 11:45:11 | ERROR    | ucmp.orchestrator.orchestrator   | Stage 'ReportingEngine' failed; aborting pipeline (fail_fast=True)
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | Pipeline run_id=18d847f5b9fe finished with overall status=FAILED
2026-10-26 11:45:11 | INFO     | ucmp.orchestrator.orchestrator   | Pipeline run_id=18d847f5b9fe finished with overall status=FAILED

======================================================================
UCMP PIPELINE RESULT
======================================================================
  ConfigurationManager         SUCCESS    0.0052s
  AuthenticationManager        SUCCESS    0.0145s
  RepositoryManager            SUCCESS    38.4591s
  ParserEngine                 SUCCESS    0.209s
  RuleRepository               SUCCESS    0.1851s
  RuleService                  SUCCESS    0.0059s
  TransformationPlanner        SUCCESS    0.0443s
  ReplacementEngine            SUCCESS    0.0041s
  ValidationEngine             SUCCESS    0.0656s
  DeploymentEngine             SUCCESS    0.0225s
  ReportingEngine              FAILED     0.0119s

Overall pipeline status: FAILED
1
