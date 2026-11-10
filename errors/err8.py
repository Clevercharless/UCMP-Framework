
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
    "/Workspace/Users/charless.binny@poonawallafincorp.com/validation/Validation_Reports"
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
        "name": "cca_disbursal_data",
        "azure": "/Workspace/Users/charless.binny@poonawallafincorp.com/validation/Validation_files/CCA_Disbursal_disbursal_tracking_report.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlik_apps/MD_Disbursal_RealTime/archive/2026-11-09/CCA_Disbursal_disbursal_tracking_report.csv",
    },
    {
        "name": "cca_login_data",
        "azure": "/Workspace/Users/charless.binny@poonawallafincorp.com/validation/Validation_files/CCA_Login_disbursal_tracking_report.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlik_apps/MD_Disbursal_RealTime/archive/2026-11-09/CCA_Login_disbursal_tracking_report.csv",
    },
    {
        "name": "cca_sanction_data",
        "azure": "/Workspace/Users/charless.binny@poonawallafincorp.com/validation/Validation_files/CCA_Sanctioned_disbursal_tracking_report.csv",
        "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlik_apps/MD_Disbursal_RealTime/archive/2026-11-09/CCA_Sanctioned_disbursal_tracking_report.csv",
    }

    # {
    #     "name": "Finnone_Receipt_RT_NACH",
    #     "azure": "/Volumes/pfl_dev_admin_catalog/temp/temp_upload/qlik_reporting_vol/nach_parts/",
    #     "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/dart-blob-reports/Finnone_Receipt_RT_Lite/Finnone_Receipt_RT_NACH/Finnone_Receipt_RT_NACH.csv",
    # },

    # {
    #     "name": "PayTM_STPL_Dashboard",
    #     "azure": "/Workspace/Users/puram.gangadhar@poonawallafincorp.com/validation_files/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv",
    #     "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/PayTM_STPL/MTD_disbursal/archive/2026-11-09/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv",
    # },

    # {
    #     "name": "Insta_STPL_Dashboard",
    #     "azure": "/Workspace/Users/puram.gangadhar@poonawallafincorp.com/validation_files/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts_insta.csv",
    #     "aws": "s3://bkt-dl-raw-prod-tableau-apps-aps1/qlikapps/qlik_apps/PL_INSTA_STPL/MTD_disbursal/archive/2026-11-09/MTD_Disbursal_LoanBand_Geo_ROI_Tenure_Band_Cuts.csv",
    # }

]

