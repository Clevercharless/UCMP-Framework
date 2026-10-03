# User-Driven Notebook Migration

The modified UCMP pipeline uses a user-provided notebook list as the authoritative migration scope.

## 1. Notebook list

The preferred input is a simple YAML list in the migration configuration:

```yaml
migration:
  notebook_list:
    - /Bronze/ingest_customer.py
    - /Bronze/ingest_accounts.py
    - /Silver/customer_transform.py
    - /Gold/customer_summary.py
```

Only notebooks in this list are migrated. A notebook discovered only as a dependency is **not** added automatically; it is reported with its source existence and migration-list status.

For backward compatibility, CSV/TXT/XLSX/XLSM notebook-list files are still supported through `migration.notebook_list_file` when the inline list is empty.

## 2. Container-to-bucket mapping

Keep the Azure container to AWS S3 bucket mapping directly in the same configuration:

```yaml
migration:
  container_bucket_mapping:
    qlikapps: raw_qlik
    customer: raw_customer
    finance: raw_finance
```

For example:

```python
path = "abfss://qlikapps@companyadls.dfs.core.windows.net/customer/"
```

can be transformed using:

```text
qlikapps -> raw_qlik
```

to:

```python
path = "s3://raw_qlik/customer/"
```

A separate mapping file remains supported through `migration.container_bucket_mapping_file` for backward compatibility.

## 3. Workspace root

External notebook references such as:

```python
%run /workspace/pfl/common/utils
```

are transformed to:

```python
%run ${WORKSPACE_ROOT}/pfl/common/utils
```

Configure the target root with:

```yaml
migration:
  workspace_root: "${WORKSPACE_ROOT}"
```

## 4. Bucket variable

When the source ABFSS path uses configured source variables, UCMP uses the configurable target bucket variable:

```yaml
migration:
  bucket_variable: bucket
```

which produces:

```python
bucket = dbutils.widgets.get("bucket")
```

## 5. Example complete configuration

```yaml
migration:
  notebook_list:
    - /Bronze/ingest_customer.py
    - /Bronze/ingest_accounts.py
    - /Silver/customer_transform.py

  container_bucket_mapping:
    qlikapps: raw_qlik
    customer: raw_customer
    finance: raw_finance

  workspace_root: "${WORKSPACE_ROOT}"
  bucket_variable: "bucket"
```

## 6. Reports

The migration reports record:

- requested, found, and missing notebooks;
- existing UCMP findings;
- storage path transformations with before/after values;
- workspace notebook path transformations;
- source configuration variables commented because they feed a migrated path;
- dependency existence in the source repository;
- whether a dependency is included in the migration list;
- notebook classification (`NO_CHANGE` or `CHANGED`);
- separate manual-review status.

The original source notebook is never modified.

## Output mode

The framework supports two output modes:

```yaml
output:
  mode: "in_place"
```

- `in_place`: transformed notebooks are written back to `source.repo_path` while preserving the existing repository/folder structure. The source files are therefore changed in place. This mode currently requires `source.source_mode: local_repo`.
- `separate`: transformed notebooks/config assets are written under `target.repo_path`, preserving the repository structure there.

Reports and knowledge-model artifacts continue to use `output.reports_dir` and `output.knowledge_model_dir` regardless of the mode.

For a real migration, use `in_place` only when you intentionally want the selected notebooks changed in the source repository.
