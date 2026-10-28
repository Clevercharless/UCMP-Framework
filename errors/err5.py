# Validation Report

**Repository:** pfl-repo-dbx-datalake  
**Overall Status:** **FAIL**  
**Errors:** 1  
**Warnings:** 9  
**Info:** 5


## Findings by Category

| Category | Errors | Warnings | Info |
| --- | --- | --- | --- |
| azure_residue | 0 | 9 | 0 |
| configuration | 1 | 0 | 0 |
| dependency | 0 | 0 | 1 |
| hardcoded_secret | 0 | 0 | 1 |
| rule_validation | 0 | 0 | 1 |
| syntax | 0 | 0 | 1 |
| unsupported_sdk | 0 | 0 | 1 |


## Errors

| Category | Notebook | Message | Detail |
| --- | --- | --- | --- |
| configuration | - | No rules loaded for category 'api', which is needed by at least one transformation candidate | - |


## Warnings

| Category | Notebook | Message | Detail |
| --- | --- | --- | --- |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/MS_Dynamic/lentra_ms_dynamics.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://10.110.13.100;databaseName=Magma_Staging_Prod |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/MS_Dynamic/pennant_ms_dynamics.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://10.110.13.100;databaseName=Magma_Staging_Prod |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/MS_Dynamic_New_CRM/cca_new_ms_dynamics.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://10.110.13.100;databaseName=PFL_PROD |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/MS_Dynamic_New_CRM/finnone_new_ms_dynamics.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://10.110.13.100;databaseName=PFL_PROD |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/MS_Dynamic_New_CRM/lentra_new_ms_dynamics.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://10.110.13.100;databaseName=PFL_PROD |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/MS_Dynamic_New_CRM/pennant_new_ms_dynamics.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://10.110.13.100;databaseName=PFL_PROD |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/Transaction_Monitoring_Trackwizz_Report/Full_Load_Trackwizz.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://10.110.14.75:1456;databaseName=PROD_TBDB |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/Transaction_Monitoring_Trackwizz_Report/Incremental_Load_Trackwizz.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://commonkstprdb.poonawallafincorp.com:1456;databaseName=PROD_TBDB |
| azure_residue | PFL/Delta-Lake/Notebook_Execution/Transaction_Monitoring_Trackwizz_Report/Rejection_cases_of_Trackwizz.py | Expected residual hardcoded_url (flagged for manual review, not auto-replaced) | jdbc:sqlserver://10.110.14.75:1456;databaseName=PROD_TBDB |
