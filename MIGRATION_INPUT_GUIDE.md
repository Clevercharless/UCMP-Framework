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

## Real workspace mode and deployment

Real Databricks workspace mode does **not** clone or stage the complete repository. UCMP performs metadata discovery against the configured workspace, exports only the explicitly selected notebooks, and keeps their source in memory for parsing, transformation, and validation.

Use:

```yaml
source:
  source_mode: "workspace"
  workspace_path: "/Workspace/Users/<user>/<repo>"

migration:
  notebook_list:
    - /PFL/Delta-Lake/example_notebook

output:
  mode: "in_place"

deployment:
  auto_deploy: false

pipeline:
  dry_run: true
```

`deployment.auto_deploy` is the explicit safety gate. It defaults to `false`.

- `auto_deploy: false`: analyze, transform, validate, and report; **do not write to the Databricks workspace**.
- `auto_deploy: true` + `dry_run: true`: still do not write.
- `auto_deploy: true` + `dry_run: false`: write only the notebooks in `migration.notebook_list` directly to the target workspace.

The legacy local-repository/separate-output modes remain supported for existing workflows.

Dependencies discovered through `%run` or `dbutils.notebook.run()` are analyzed separately and are **not automatically migrated** unless they are explicitly present in `migration.notebook_list`. Dynamic prefixes such as `${workspace_prefix}/PFL/Common/utils` are resolved by static suffix where possible and otherwise reported for review rather than guessed.
