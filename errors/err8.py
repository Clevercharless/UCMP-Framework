# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
import re

def normalize_columns(df):
    """
    1. Replace invalid characters with '_'
    2. Preserve case
    3. Handle duplicate names (case-insensitive)
    """

    new_cols = []
    seen = {}

    for col in df.columns:

        # Replace invalid characters
        new_col = re.sub(r'[^a-zA-Z0-9_]', '_', col)
        new_col = re.sub(r'_+', '_', new_col)
        new_col = new_col.strip('_')

        # Spark is case-insensitive by default
        key = new_col.lower()

        if key in seen:
            seen[key] += 1
            new_col = f"{new_col}_{seen[key]}"
        else:
            seen[key] = 1

        new_cols.append(new_col)

    return df.toDF(*new_cols)

# COMMAND ----------

import re

def sanitize_columns(df):
    new_cols = []
    for c in df.columns:
        n = re.sub(r"[ ,;{}()\n\t=]+", "_", c.strip())
        n = n.strip("_")
        new_cols.append(n)
    return df.toDF(*new_cols)

# COMMAND ----------

def make_unique_columns(df):
    new_names = []

    for i, col in enumerate(df.columns):
        safe_name = f"col_{i}_{re.sub(r'[^A-Za-z0-9]', '_', col)}"
        new_names.append(safe_name)

    return df.toDF(*new_names), dict(zip(new_names, df.columns))

    #  bkt-dl-raw-prod-finnone-replica-aps1

# COMMAND ----------

# paths = [
#     "s3://bkt-sales-ds-mis-automation-prod-aps1/",
#     "s3://bkt-int-audit-manual-prod-aps1/",
#     "s3://bkt-credit-fcu-team-prod-aps1/",
#     "s3://bkt-operations-dart-mis-prod-aps1/",
#     "s3://bkt-it-dart-blob-reports-prod-aps1/",
#     "s3://bkt-finance-fpm-prod-aps1/",
#     "s3://bkt-marketing-digital-marketing-prod-aps1/",
#     "s3://bkt-collections-consumer-durable-prod-aps1/",
#     "s3://bkt-finance-finnone-accounts-reports-prod-aps1/"
# ]

# all_files = []

# def list_recursive(path):
#     try:
#         for item in dbutils.fs.ls(path):
#             if item.path.endswith("/"):
#                 list_recursive(item.path)
#             else:
#                 all_files.append({
#                     "name": item.name,
#                     "path": item.path,
#                     "size": item.size,
#                     "modificationTime": item.modificationTime
#                 })
#     except Exception as e:
#         print(f"Error accessing {path}: {e}")

# for p in paths:
#     list_recursive(p)

# display(spark.createDataFrame(all_files))

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.storagelevel import StorageLevel

FILE_PAIRS = [
    {
        "name": "Finnone_Receipt_RT_AutoDebit",
        "azure": "/Workspace/Users/puram.gangadhar@poonawallafincorp.com/validation_files/Finnone_Receipt_RT_AutoDebit.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/Dashbord_Imports/Finnone_Receipt_RT/Finnone_Receipt_RT_AutoDebit.csv",
    },
    {
        "name": "Finnone_Receipt_RT",
        "azure": "/Volumes/pfl_dev_admin_catalog/temp/temp_upload/qlik_reporting_vol/Finnone_Receipt_RT.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/Dashbord_Imports/Finnone_Receipt_RT/Finnone_Receipt_RT.csv",
    },
    {
        "name": "Finnone_Receipt_RT_NACH_Removed",
        "azure": "/Workspace/Users/puram.gangadhar@poonawallafincorp.com/validation_files/Finnone_Receipt_RT_NACH_Removed.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/Dashbord_Imports/Finnone_Receipt_RT/Finnone_Receipt_RT_NACH_Removed.csv",
    },
    {
        "name": "Finnone_Receipt_RT_NACH",
        "azure": "/Volumes/pfl_dev_admin_catalog/temp/temp_upload/qlik_reporting_vol/nach_parts/",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/dart-blob-reports/Finnone_Receipt_RT_Lite/Finnone_Receipt_RT_NACH/Finnone_Receipt_RT_NACH.csv",
    },
    {
        "name": "PayTM_STPL_Dashboard",
        "azure":"/Workspace/Users/puram.gangadhar@poonawallafincorp.com/validation_files/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/PayTM_STPL/MTD_disbursal/archive/2026-11-09/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv"
    },
    {
        "name": "Insta_STPL_Dashboard",
        "azure":"/Workspace/Users/puram.gangadhar@poonawallafincorp.com/validation_files/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts_insta.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/PL_INSTA_STPL/MTD_disbursal/archive/2026-11-09/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv"
    }
]

DELIMITER = ","

# Column-level checks (each becomes an Azure/AWS pair of columns in the report)
CHECKS = ["Null Count", "Distinct Count", "White Space", "Min Value", "Max Value"]

# Patterns used to clean column names in the report display only
PREFIX_PATTERN = r"(?<![A-Za-z0-9])col_\d+_"       # removes leading col_0_, col_1_ ...
TRAILING_PATTERN = r"_+(?=[,'\]\)]|$)"              # removes trailing underscores (__ etc.)

def clean_report_text(column_name):
    return F.regexp_replace(
        F.regexp_replace(F.col(column_name), PREFIX_PATTERN, ""),
        TRAILING_PATTERN, ""
    )

# ============================================================
# HELPER
# ============================================================

def add_result(validation, column, azure_value, aws_value):
    report.append({
        "Validation Type": validation,
        "Column": column,
        "Azure": str(azure_value),
        "AWS": str(aws_value),
        "Status": "PASS" if azure_value == aws_value else "FAIL"
    })

# ============================================================
# PROCESS EACH FILE PAIR
# ============================================================

for pair in FILE_PAIRS:

    PAIR_NAME = pair["name"]
    AZURE_FILE = pair["azure"]
    AWS_FILE = pair["aws"]

    print("\n" + "#" * 60)
    print(f"VALIDATING : {PAIR_NAME}")
    print("#" * 60)

    # ============================================================
    # READ FILES
    # ============================================================

    azure_df = (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .option("delimiter", DELIMITER)
        .csv(AZURE_FILE)
        # .persist(StorageLevel.MEMORY_AND_DISK)
    )

    aws_df = (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .option("delimiter", DELIMITER)
        .csv(AWS_FILE)
        # .persist(StorageLevel.MEMORY_AND_DISK)
    )

    azure_df = sanitize_columns(azure_df)
    aws_df = sanitize_columns(aws_df)

    azure_df, azure_col_map = make_unique_columns(azure_df)
    aws_df, aws_col_map = make_unique_columns(aws_df)

    # Cache after sanitizing
    azure_df = azure_df.persist(StorageLevel.MEMORY_AND_DISK)
    aws_df = aws_df.persist(StorageLevel.MEMORY_AND_DISK)

    # Materialize cache
    azure_df.count()
    aws_df.count()

    # print(azure_df.columns)
    # print("=============================")
    # print(aws_df.columns)

    report = []

    # ============================================================
    # RECORD COUNT
    # ============================================================

    az_count = azure_df.count()
    aws_count = aws_df.count()

    add_result("Record Count", "-", az_count, aws_count)

    # ============================================================
    # COLUMN COUNT
    # ============================================================

    add_result(
        "Column Count",
        "-",
        len(azure_df.columns),
        len(aws_df.columns)
    )

    # ============================================================
    # COLUMN NAMES
    # ============================================================

    add_result(
        "Column Names",
        "-",
        ",".join(azure_df.columns),
        ",".join(aws_df.columns)
    )

    # ============================================================
    # SCHEMA
    # ============================================================

    add_result(
        "Schema",
        "-",
        azure_df.dtypes,
        aws_df.dtypes
    )

    # ============================================================
    # DUPLICATES
    # ============================================================

    az_dup = az_count - azure_df.dropDuplicates().count()
    aws_dup = aws_count - aws_df.dropDuplicates().count()

    add_result(
        "Duplicate Rows",
        "-",
        az_dup,
        aws_dup
    )

    # ============================================================
    # COLUMN LEVEL VALIDATION  (one row per column)
    # ============================================================

    column_rows = []
    column_failed_checks = 0

    for col in azure_df.columns:

        # Null count
        az_null = azure_df.filter(F.col(col).isNull()).count()
        aws_null = aws_df.filter(F.col(col).isNull()).count()

        # Distinct count
        az_distinct = azure_df.select(col).distinct().count()
        aws_distinct = aws_df.select(col).distinct().count()

        # White space count
        az_ws = azure_df.filter(
            F.col(col).cast("string") !=
            F.trim(F.col(col).cast("string"))
        ).count()

        aws_ws = aws_df.filter(
            F.col(col).cast("string") !=
            F.trim(F.col(col).cast("string"))
        ).count()

        # Min value
        az_min = azure_df.select(F.min(col)).first()[0]
        aws_min = aws_df.select(F.min(col)).first()[0]

        # Max value
        az_max = azure_df.select(F.max(col)).first()[0]
        aws_max = aws_df.select(F.max(col)).first()[0]

        results = {
            "Null Count":     (az_null, aws_null),
            "Distinct Count": (az_distinct, aws_distinct),
            "White Space":    (az_ws, aws_ws),
            "Min Value":      (az_min, aws_min),
            "Max Value":      (az_max, aws_max),
        }

        failed_list = [name for name, (a, b) in results.items() if a != b]
        column_failed_checks += len(failed_list)

        row = [col]
        for name in CHECKS:
            a, b = results[name]
            row += [str(a), str(b)]
        row += ["PASS" if not failed_list else "FAIL", ", ".join(failed_list)]

        column_rows.append(tuple(row))

    column_schema = ["Column"]
    for name in CHECKS:
        column_schema += [f"{name} Azure", f"{name} AWS"]
    column_schema += ["Status", "Failed Checks"]

    # ============================================================
    # FINAL REPORT
    # ============================================================

    report_df = spark.createDataFrame(report)                              # general checks (5 rows)
    column_report_df = spark.createDataFrame(column_rows, column_schema)   # 1 row per column

    # ------------------------------------------------------------
    # CLEAN COLUMN NAMES IN REPORT ONLY (processing keeps unique names)
    # ------------------------------------------------------------

    # General report: only clean the rows that list column names
    report_df = (
        report_df
        .withColumn(
            "Azure",
            F.when(F.col("Validation Type").isin("Column Names", "Schema"),
                   clean_report_text("Azure"))
             .otherwise(F.col("Azure"))
        )
        .withColumn(
            "AWS",
            F.when(F.col("Validation Type").isin("Column Names", "Schema"),
                   clean_report_text("AWS"))
             .otherwise(F.col("AWS"))
        )
    )

    # Column-level report: clean the Column name only (values are left untouched)
    column_report_df = column_report_df.withColumn("Column", clean_report_text("Column"))

    display(report_df)
    display(column_report_df)

    # ============================================================
    # SUMMARY
    # ============================================================

    general_total = report_df.count()
    general_failed = report_df.filter("Status='FAIL'").count()

    total = general_total + len(column_rows) * len(CHECKS)
    failed = general_failed + column_failed_checks
    passed = total - failed

    print("=" * 60)
    print(f"VALIDATION SUMMARY : {PAIR_NAME}")
    print("=" * 60)
    print(f"Total Checks : {total}")
    print(f"Passed       : {passed}")
    print(f"Failed       : {failed}")
    print("=" * 60)

    if failed == 0:
        print("OVERALL RESULT : PASS")
    else:
        print("OVERALL RESULT : FAIL")

    # ============================================================
    # CLEANUP
    # ============================================================

    azure_df.unpersist()
    aws_df.unpersist()
