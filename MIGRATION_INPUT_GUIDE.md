# User-Driven Real Workspace Notebook Migration

The migration scope is controlled by `migration.notebook_list`. In real Databricks workspace mode, UCMP does not clone or stage the entire repository.

## 1. Notebook list

```yaml
migration:
  notebook_list:
    - /PFL/Delta-Lake/Qlik_Reporting/FinnOne_Receipts_Summary_Report/Report/Product_wise_summary
    - /PFL/Delta-Lake/Qlik_Reporting/FinnOne_Receipts_Summary_Report/Write CSV/write_to_csv_account_classification_wise_summary
```

Only notebooks in this list are migrated. Dependencies are discovered for analysis, but are not automatically added or deployed.

CSV/TXT/XLSX/XLSM notebook-list files remain supported when the inline list is empty.

## 2. Real workspace mode

Use:

```yaml
source:
  source_mode: "workspace"
  workspace_path: "/Workspace/Users/<user>/<repo>"
```

Workspace mode:

- discovers workspace metadata to locate the requested notebooks;
- exports only the selected notebooks required for processing;
- does not clone the repository;
- does not create `output/_staging/<repository>`;
- does not commit or push Git changes;
- does not automatically migrate discovered dependencies.

## 3. Container-to-bucket mapping

```yaml
migration:
  container_bucket_mapping:
    qlikapps: raw_qlik
    customer: raw_customer
    finance: raw_finance
```

Azure container names map directly to AWS S3 buckets.

### Supported ABFSS forms

Configured container and account:

```python
container = dbutils.widgets.get("container")
storage_account = dbutils.widgets.get("storage_account")
path = f"abfss://{container}@{storage_account}.dfs.core.windows.net/customer/"
```

Hardcoded container with configured account:

```python
storage_account = dbutils.widgets.get("storage_account")
path = f"abfss://qlikapps@{storage_account}.dfs.core.windows.net/customer/"
```

Hardcoded container with a templated account:

```python
path = "abfss://qlikapps@{storage_account}.dfs.core.windows.net/customer/"
```

The `{storage_account}` and `${storage_account}` forms are treated as dynamic/configured storage-account references.

Fully hardcoded container and account:

```python
path = "abfss://qlikapps@companyadls.dfs.core.windows.net/customer/"
```

If a hardcoded container has no mapping, UCMP applies a mechanical S3 placeholder and marks the transformation `REVIEW_REQUIRED` rather than failing the complete migration.

DBFS and mount-backed paths are not blindly converted and are reported for review unless an explicit rule exists.

## 4. External notebook references

The guaranteed source form is:

```python
%run /workspace/PFL/Delta-Lake/Common/utils
```

Configure the real workspace root:

```yaml
migration:
  workspace_root: "/Workspace/Users/<user>/<repo>"
```

UCMP resolves `/workspace/...` references against that root while preserving the notebook's relative path.

Dynamic prefixes are also recognized for dependency resolution, for example:

```python
%run ${workspace_prefix}/PFL/Delta-Lake/Common/utils
```

The stable notebook-path suffix is used to resolve the dependency against the real workspace inventory.

## 5. Deployment safety

Workspace write-back is explicitly opt-in:

```yaml
deployment:
  auto_deploy: false
```

Safe/default behavior:

```yaml
deployment:
  auto_deploy: false

pipeline:
  dry_run: true
```

UCMP analyzes and transforms the selected notebooks for validation/reporting, but does not write them back to Databricks.

Actual workspace write-back requires both:

```yaml
deployment:
  auto_deploy: true

pipeline:
  dry_run: false
```

When enabled, only notebooks in `migration.notebook_list` are written to the target workspace. Discovered dependencies are never deployed automatically.

`auto_deploy` does not mean Git commit or Git push. Workspace mode writes directly through the Databricks workspace API.

## 6. Reports

Reports record:

- requested, found, and missing notebooks;
- storage transformations and mappings;
- dependency existence and migration-list status;
- `NO_CHANGE` / `CHANGED` classification;
- `REVIEW_REQUIRED` status and reasons;
- deployment mode and workspace write status.

The framework does not use the old full-repository staging directory for workspace mode.
