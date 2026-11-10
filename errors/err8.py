
# ============================================================
# 1. IMPORTS
# ============================================================

import re
import os
from datetime import datetime

from pyspark.sql import functions as F
from pyspark.storagelevel import StorageLevel


# ============================================================
# 2. REPORT CONFIGURATION
# ============================================================

# Change this to the Workspace folder where you want reports.
# Ensure you have write permission to this folder.

REPORT_BASE_PATH = (
    "/Workspace/Users/your_email/Validation_Reports"
)

# Generate timestamp once per notebook execution
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Unique folder for this execution
RUN_PATH = os.path.join(
    REPORT_BASE_PATH,
    RUN_TIMESTAMP
)

print(f"Report execution timestamp: {RUN_TIMESTAMP}")
print(f"Report destination: {RUN_PATH}")


# ============================================================
# 3. COLUMN CLEANING FUNCTIONS
# ============================================================

def normalize_columns(df):
    new_cols = []
    seen = {}

    for col in df.columns:

        new_col = re.sub(r'[^a-zA-Z0-9_]', '_', col)
        new_col = re.sub(r'_+', '_', new_col)
        new_col = new_col.strip('_')

        key = new_col.lower()

        if key in seen:
            seen[key] += 1
            new_col = f"{new_col}_{seen[key]}"
        else:
            seen[key] = 1

        new_cols.append(new_col)

    return df.toDF(*new_cols)


def sanitize_columns(df):
    new_cols = []

    for c in df.columns:
        n = re.sub(r"[ ,;{}()\n\t=]+", "_", c.strip())
        n = n.strip("_")
        new_cols.append(n)

    return df.toDF(*new_cols)


def make_unique_columns(df):
    new_names = []

    for i, col in enumerate(df.columns):
        safe_name = f"col_{i}_{re.sub(r'[^A-Za-z0-9]', '_', col)}"
        new_names.append(safe_name)

    return df.toDF(*new_names), dict(zip(new_names, df.columns))


# ============================================================
# 4. FILE PAIRS
# ============================================================

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
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/Dashbord_Imports/Finnone_Receipt_RT/Finnone_Receipt_RT.csv",
    },

    {
        "name": "Finnone_Receipt_RT_NACH",
        "azure": "/Volumes/pfl_dev_admin_catalog/temp/temp_upload/qlik_reporting_vol/nach_parts/",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/dart-blob-reports/Finnone_Receipt_RT_Lite/Finnone_Receipt_RT_NACH/Finnone_Receipt_RT_NACH.csv",
    },

    {
        "name": "PayTM_STPL_Dashboard",
        "azure": "/Workspace/Users/puram.gangadhar@poonawallafincorp.com/validation_files/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/PayTM_STPL/MTD_disbursal/archive/2026-11-09/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv",
    },

    {
        "name": "Insta_STPL_Dashboard",
        "azure": "/Workspace/Users/puram.gangadhar@poonawallafincorp.com/validation_files/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts_insta.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/PL_INSTA_STPL/MTD_disbursal/archive/2026-11-09/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv",
    }

]


# ============================================================
# 5. VALIDATION CONFIGURATION
# ============================================================

DELIMITER = ","

CHECKS = [
    "Null Count",
    "Distinct Count",
    "White Space",
    "Min Value",
    "Max Value"
]

PREFIX_PATTERN = r"(?<![A-Za-z0-9])col_\d+_"
TRAILING_PATTERN = r"_+(?=[,'\]\)]|$)"


def clean_report_text(column_name):

    return F.regexp_replace(
        F.regexp_replace(
            F.col(column_name),
            PREFIX_PATTERN,
            ""
        ),
        TRAILING_PATTERN,
        ""
    )


# ============================================================
# 6. HELPER FUNCTIONS
# ============================================================

def add_result(validation, column, azure_value, aws_value):

    report.append({

        "Validation Type": validation,
        "Column": column,
        "Azure": str(azure_value),
        "AWS": str(aws_value),
        "Status": "PASS" if azure_value == aws_value else "FAIL"

    })


def save_csv_to_workspace(dataframe, file_path):

    """
    Saves a Pandas DataFrame as a CSV file
    inside the Databricks Workspace.
    """

    directory = os.path.dirname(file_path)

    os.makedirs(directory, exist_ok=True)

    dataframe.to_csv(
        file_path,
        index=False,
        encoding="utf-8"
    )

    print(f"Saved: {file_path}")


# ============================================================
# 7. CREATE EXECUTION DIRECTORY
# ============================================================

os.makedirs(RUN_PATH, exist_ok=True)

print("=" * 60)
print("VALIDATION EXECUTION STARTED")
print("=" * 60)


# ============================================================
# 8. PROCESS EACH FILE PAIR
# ============================================================

for pair in FILE_PAIRS:

    PAIR_NAME = pair["name"]
    AZURE_FILE = pair["azure"]
    AWS_FILE = pair["aws"]

    print("\n" + "#" * 60)
    print(f"VALIDATING : {PAIR_NAME}")
    print("#" * 60)

    azure_df = None
    aws_df = None

    try:

        # ----------------------------------------------------
        # READ AZURE FILE
        # ----------------------------------------------------

        azure_df = (
            spark.read
            .option("header", True)
            .option("inferSchema", True)
            .option("delimiter", DELIMITER)
            .csv(AZURE_FILE)
        )

        # ----------------------------------------------------
        # READ AWS FILE
        # ----------------------------------------------------

        aws_df = (
            spark.read
            .option("header", True)
            .option("inferSchema", True)
            .option("delimiter", DELIMITER)
            .csv(AWS_FILE)
        )

        # ----------------------------------------------------
        # SANITIZE COLUMN NAMES
        # ----------------------------------------------------

        azure_df = sanitize_columns(azure_df)
        aws_df = sanitize_columns(aws_df)

        azure_df, azure_col_map = make_unique_columns(azure_df)
        aws_df, aws_col_map = make_unique_columns(aws_df)

        # ----------------------------------------------------
        # CACHE DATAFRAMES
        # ----------------------------------------------------

        azure_df = azure_df.persist(
            StorageLevel.MEMORY_AND_DISK
        )

        aws_df = aws_df.persist(
            StorageLevel.MEMORY_AND_DISK
        )

        azure_df.count()
        aws_df.count()

        report = []

        # ----------------------------------------------------
        # RECORD COUNT
        # ----------------------------------------------------

        az_count = azure_df.count()
        aws_count = aws_df.count()

        add_result(
            "Record Count",
            "-",
            az_count,
            aws_count
        )

        # ----------------------------------------------------
        # COLUMN COUNT
        # ----------------------------------------------------

        add_result(
            "Column Count",
            "-",
            len(azure_df.columns),
            len(aws_df.columns)
        )

        # ----------------------------------------------------
        # COLUMN NAMES
        # ----------------------------------------------------

        add_result(
            "Column Names",
            "-",
            ",".join(azure_df.columns),
            ",".join(aws_df.columns)
        )

        # ----------------------------------------------------
        # SCHEMA
        # ----------------------------------------------------

        add_result(
            "Schema",
            "-",
            azure_df.dtypes,
            aws_df.dtypes
        )

        # ----------------------------------------------------
        # DUPLICATE ROWS
        # ----------------------------------------------------

        az_dup = (
            az_count -
            azure_df.dropDuplicates().count()
        )

        aws_dup = (
            aws_count -
            aws_df.dropDuplicates().count()
        )

        add_result(
            "Duplicate Rows",
            "-",
            az_dup,
            aws_dup
        )

        # ----------------------------------------------------
        # COLUMN LEVEL VALIDATION
        # ----------------------------------------------------

        column_rows = []
        column_failed_checks = 0

        for col in azure_df.columns:

            if col not in aws_df.columns:

                results = {
                    "Null Count": (None, "COLUMN_MISSING"),
                    "Distinct Count": (None, "COLUMN_MISSING"),
                    "White Space": (None, "COLUMN_MISSING"),
                    "Min Value": (None, "COLUMN_MISSING"),
                    "Max Value": (None, "COLUMN_MISSING")
                }

            else:

                # Null count
                az_null = (
                    azure_df
                    .filter(F.col(col).isNull())
                    .count()
                )

                aws_null = (
                    aws_df
                    .filter(F.col(col).isNull())
                    .count()
                )

                # Distinct count
                az_distinct = (
                    azure_df
                    .select(col)
                    .distinct()
                    .count()
                )

                aws_distinct = (
                    aws_df
                    .select(col)
                    .distinct()
                    .count()
                )

                # White space count
                az_ws = (
                    azure_df
                    .filter(
                        F.col(col).cast("string") !=
                        F.trim(F.col(col).cast("string"))
                    )
                    .count()
                )

                aws_ws = (
                    aws_df
                    .filter(
                        F.col(col).cast("string") !=
                        F.trim(F.col(col).cast("string"))
                    )
                    .count()
                )

                # Min value
                az_min = (
                    azure_df
                    .select(F.min(col))
                    .first()[0]
                )

                aws_min = (
                    aws_df
                    .select(F.min(col))
                    .first()[0]
                )

                # Max value
                az_max = (
                    azure_df
                    .select(F.max(col))
                    .first()[0]
                )

                aws_max = (
                    aws_df
                    .select(F.max(col))
                    .first()[0]
                )

                results = {

                    "Null Count": (az_null, aws_null),

                    "Distinct Count": (
                        az_distinct,
                        aws_distinct
                    ),

                    "White Space": (
                        az_ws,
                        aws_ws
                    ),

                    "Min Value": (
                        az_min,
                        aws_min
                    ),

                    "Max Value": (
                        az_max,
                        aws_max
                    )

                }

            # Identify failed checks
            failed_list = [

                name
                for name, (a, b) in results.items()
                if a != b

            ]

            column_failed_checks += len(failed_list)

            row = [col]

            for name in CHECKS:

                a, b = results[name]

                row += [
                    str(a),
                    str(b)
                ]

            row += [

                "PASS" if not failed_list else "FAIL",

                ", ".join(failed_list)

            ]

            column_rows.append(tuple(row))

        # ----------------------------------------------------
        # CREATE COLUMN REPORT SCHEMA
        # ----------------------------------------------------

        column_schema = ["Column"]

        for name in CHECKS:

            column_schema += [
                f"{name} Azure",
                f"{name} AWS"
            ]

        column_schema += [
            "Status",
            "Failed Checks"
        ]

        # ----------------------------------------------------
        # CREATE REPORT DATAFRAMES
        # ----------------------------------------------------

        report_df = spark.createDataFrame(report)

        column_report_df = spark.createDataFrame(
            column_rows,
            column_schema
        )

        # ----------------------------------------------------
        # CLEAN REPORT COLUMN NAMES
        # ----------------------------------------------------

        report_df = (
            report_df
            .withColumn(
                "Azure",
                F.when(
                    F.col("Validation Type").isin(
                        "Column Names",
                        "Schema"
                    ),
                    clean_report_text("Azure")
                ).otherwise(F.col("Azure"))
            )
            .withColumn(
                "AWS",
                F.when(
                    F.col("Validation Type").isin(
                        "Column Names",
                        "Schema"
                    ),
                    clean_report_text("AWS")
                ).otherwise(F.col("AWS"))
            )
        )

        column_report_df = (
            column_report_df
            .withColumn(
                "Column",
                clean_report_text("Column")
            )
        )

        # ----------------------------------------------------
        # DISPLAY REPORTS
        # ----------------------------------------------------

        display(report_df)
        display(column_report_df)

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        general_total = report_df.count()

        general_failed = (
            report_df
            .filter("Status='FAIL'")
            .count()
        )

        total = (
            general_total +
            len(column_rows) * len(CHECKS)
        )

        failed = (
            general_failed +
            column_failed_checks
        )

        passed = total - failed

        overall_result = (
            "PASS" if failed == 0 else "FAIL"
        )

        print("=" * 60)
        print(f"VALIDATION SUMMARY : {PAIR_NAME}")
        print("=" * 60)

        print(f"Total Checks : {total}")
        print(f"Passed       : {passed}")
        print(f"Failed       : {failed}")

        print("=" * 60)
        print(f"OVERALL RESULT : {overall_result}")

        # ====================================================
        # 9. SAVE REPORTS TO DATABRICKS WORKSPACE
        # ====================================================

        PAIR_PATH = os.path.join(
            RUN_PATH,
            PAIR_NAME
        )

        os.makedirs(
            PAIR_PATH,
            exist_ok=True
        )

        # General report
        general_pdf = report_df.toPandas()

        save_csv_to_workspace(
            general_pdf,
            os.path.join(
                PAIR_PATH,
                "general_report.csv"
            )
        )

        # Column-level report
        column_pdf = column_report_df.toPandas()

        save_csv_to_workspace(
            column_pdf,
            os.path.join(
                PAIR_PATH,
                "column_report.csv"
            )
        )

        # Summary report
        import pandas as pd

        summary_pdf = pd.DataFrame([{

            "File Name": PAIR_NAME,
            "Total Checks": total,
            "Passed": passed,
            "Failed": failed,
            "Overall Result": overall_result,
            "Execution Timestamp": RUN_TIMESTAMP

        }])

        save_csv_to_workspace(
            summary_pdf,
            os.path.join(
                PAIR_PATH,
                "summary.csv"
            )
        )

        print("-" * 60)
        print(f"REPORTS SAVED SUCCESSFULLY")
        print(f"Location: {PAIR_PATH}")
        print("-" * 60)

    except Exception as e:

        print(f"VALIDATION ERROR for {PAIR_NAME}: {str(e)}")

        raise

    finally:

        # ----------------------------------------------------
        # CLEANUP
        # ----------------------------------------------------

        if azure_df is not None:
            azure_df.unpersist()

        if aws_df is not None:
            aws_df.unpersist()


# ============================================================
# 10. EXECUTION COMPLETED
# ============================================================

print("\n" + "=" * 60)
print("ALL VALIDATION PROCESSES COMPLETED")
print("=" * 60)

print(f"Execution Timestamp : {RUN_TIMESTAMP}")
print(f"Reports Location    : {RUN_PATH}")
print("=" * 60)
