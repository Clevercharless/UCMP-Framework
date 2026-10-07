# Databricks notebook source
# MAGIC %md
# MAGIC - Name: FinnOne_DimCollateralProperty
# MAGIC - SCD Type:  1
# MAGIC - Author:  Kapil Patil
# MAGIC - Description:  Creating Dimension table for Collateral Property

# COMMAND ----------

# MAGIC %md 
# MAGIC ## Import Libraries

# COMMAND ----------

import os
import json
import datetime
from pytz import timezone
import random
import time

# COMMAND ----------

# MAGIC %md
# MAGIC ###Code Execution Start time

# COMMAND ----------

#get startTime of the notebook
timezone = timezone('Asia/Kolkata')
startTime = datetime.datetime.now(tz=timezone)
print("Start Time --> ",startTime)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Declare Variables

# COMMAND ----------

silver_catalog_name = os.getenv("silver_catalog_name")
gold_catalog_name = os.getenv("gold_catalog_name")
admin_catalog_name = os.getenv("admin_catalog_name")
view_catalog_name = os.getenv("view_catalog_name")

error = "No Error"
config_id = dbutils.widgets.get('config_id')
business_date = dbutils.widgets.get('business_date')
raw_sa_name = dbutils.widgets.get('raw_sa_name')
dim_start_date = datetime.datetime.strptime(dbutils.widgets.get('Last_Sink_Date'),"%m/%d/%Y %I:%M:%S %p")
trigger_time = datetime.datetime.strptime(dbutils.widgets.get("trigger_time")[:-2],"%Y-%m-%dT%H:%M:%S.%f")
src_system_id = spark.sql(f"""SELECT ID FROM {gold_catalog_name}.pfldw.dim_source_systems 
                                  WHERE System_Name = 'FinnOneReplica' and is_Active = 1""").collect()[0][0]

# COMMAND ----------

# MAGIC %md
# MAGIC ### UPDATE INPROGRESS STATUS DIMENSION EXECUTION

# COMMAND ----------

# while True:
#     try:
#         spark.sql(f"""
#                 UPDATE {admin_catalog_name}.config.tb_dwh_config
#                 SET Status = 'In-Progress'
#                 WHERE Config_ID = {config_id}
#                 """).display()
#         break
#     except Exception as e:
#         print(e)
#         if "MetadataChangedException" in str(type(e)) or "ConcurrentAppendException" in str(type(e)) :
#             sleep_duration = random.uniform(1,5)
#             time.sleep(sleep_duration)
#         else:
#             error = e
#             print(error)
#             break

# COMMAND ----------

# MAGIC %md
# MAGIC ####SCD1 COLUMNS DEFINITION ![](path)

# COMMAND ----------

if error == "No Error":
    try:
        # Scd1 columns
        SCD1_COL = ['Collateral_ID']
        hkc_scd1_fin_cols = ''
        for x in SCD1_COL:
            hkc_scd1_fin_cols += "coalesce(trim(" + x + "),''),"
        hkc_scd1_fin_cols = "concat("+ hkc_scd1_fin_cols[:-1]+")"
    except Exception as e:
        error = str(e)

# COMMAND ----------

# MAGIC %md
# MAGIC ###CREATE DIMENSION TABLE

# COMMAND ----------

if error == "No Error":
    try: 
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {gold_catalog_name}.pfldw.DimCollateralProperty (
            Collateral_Property_Key BigInt GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1),
            Collateral_Key BigInt,
            Collateral_ID  STRING,
            Property_Application_Type String,
            Coll_SubType_Property_Details String,
            Type_of_Purchase String,
            Property_Type String,
            Nature_of_Property String,
            Contractor String,
            Architect String,
            Cost_of_Construction decimal(25,7),
            Cost_of_Land decimal(25,7),
            Property_Classification String,
            Property_Ownership String,
            Market_Value decimal(25,7),
            Carpert_Area decimal(10,2),
            Carpet_Area_Unit String,
            Build_up_Area decimal(10,2),
            Build_Up_Area_Unit String,
            Property_Purpose String,
            Age_of_Property_In_Years decimal(10,2),
            Residual_Age_of_Property String,
            Property_Cost decimal(25,7),
            Agreement_Value decimal(25,7),
            Full_Address String,
            Property_Address_1 String,
            Property_Address_2 String,
            Property_Address_3 String,
            Property_City String,
            Property_State String,
            Property_Pincode String,
            Property_Country String,
            Builder_Constructed String,
            Builder_Company_Name String,
            Tier_of_Builder String,
            Builder_Project_Code String,
            Project_Name String,
            APF_Flag String,
            ADF_Flag String,
            Building_Name String,
            Wing_Name String,
            Builder_Flat_Shop_No String,
            Floor_No String,
            Building_Completion String,
            Seller_Name String,
            Present_Registered_Owner String,
            TCT_CCT_No String,
            LOT_No String,
            Percentage_Share String,
            Current_Usage String,
            Other_Remarks String,
            Registration_No String,
            Agreement_Type String,
            SRO String,
            Sale_Deed_Number String,
            Registration_Date timestamp,
            Sale_Deed_Date timestamp,
            Comp_Code STRING,
            HKC_Source_System_ID BigInt ,
            HKC_Created_On timestamp,
            HKC_Modified_On timestamp,
            HKC_Cardinal_Value String
            )
          """)
    except Exception as e:
        error = str(e)
        print(error)

# COMMAND ----------

if error == "No Error":
    try: 
        spark.sql(f"""
CREATE OR REPLACE TEMPORARY VIEW vw_DimCollateralProperty AS
With cte_1 AS (
SELECT
  B.COLLATERAL_NUMBER AS Collateral_ID,
  GP1.NAME AS Property_Application_Type,
  CST.name AS Coll_SubType_Property_Details,
  GP2.NAME AS Type_of_Purchase,
  BPT.PROPERTY_TYPE AS Property_Type,
  GP3.NAME AS Nature_of_Property,
  a.CONTRCTOR AS Contractor,
  a.ARCHITECT AS Architect,
  A.CCONST_BASE_VALUE AS Cost_of_Construction,
  A.CLAND_BASE_VALUE AS Cost_of_Land,
  PC.NAME AS Property_Classification,
  GP4.NAME AS Property_Ownership,
  A.FAIRMKT_BASE_VALUE AS Market_Value,
  a.CONST_AREA_VAL AS Carpert_Area,
  A.CONST_AR_MU_CODE AS Carpet_Area_Unit,
  a.TOTAL_AREA_VAL AS Build_up_Area,
  A.TOTAL_AR_MU_CODE AS Build_Up_Area_Unit,
  GP6.NAME AS Property_Purpose,
  A.age AS Age_of_Property_In_Years,
  GP7.NAME AS Residual_Age_of_Property,
  A.PCOST_BASE_VALUE AS Property_Cost,
  G.AGMVAL_BASE_VALUE AS Agreement_Value,
  D.COMPLETE_ADDRESS AS Full_Address,
  d.address_line1 AS Property_Address_1,
  d.address_line2 AS Property_Address_2,
  d.address_line3 AS Property_Address_3,
  city.city_name AS Property_City,
  STATE.STATE_name AS Property_State,
  zip_code.zip_code AS Property_Pincode,
  country.country_name AS Property_Country,
  CASE
    CAST(a.IS_BUILDER_CONSTRUCTED AS INTEGER)
    WHEN 1 THEN 'Yes'
    ELSE 'No'
  END AS Builder_Constructed,
  BP.NAME AS Builder_Company_Name,
  GP8.NAME AS Tier_of_Builder,
  BUILDER_PROJECT.code AS Builder_Project_Code,
  BUILDER_PROJECT.NAME AS Project_Name,
  CASE
    CAST(BUILDER_PROJECT.ISAPF AS INTEGER)
    WHEN 1 THEN 'Yes'
    ELSE 'No'
  END AS APF_Flag,
  CASE
    CAST(BUILDER_PROJECT.ISADF AS INTEGER)
    WHEN 1 THEN 'Yes'
    ELSE 'No'
  END AS ADF_Flag,
  BUILDING.NAME AS Building_Name,
  BUILDING_WING.NAME AS Wing_Name,
  A.FLAT_NUMBER AS Builder_Flat_Shop_No,
  A.FLOOR_NUMBER AS Floor_No,
  BUILDING.COMPLETION_PERCENTAGE AS Building_Completion,
  A.SELLER_NAME AS Seller_Name,
  A.PRESENT_REGISTERED_OWNER AS Present_Registered_Owner,
  A.TCT_NUMBER AS TCT_CCT_No,
  A.LOT_NUMBER AS LOT_No,
  A.Percentage_Share AS Percentage_Share,
  GP9.NAME AS Current_Usage,
  a.other_remarks AS Other_Remarks,
  g.registration_number AS Registration_No,
  GP10.NAME AS Agreement_Type,
  g.sro AS SRO,
  g.sale_deed_number AS Sale_Deed_Number,
  g.REGISTRATION_DATE AS Registration_Date,
  g.SALE_DEED_DATE AS Sale_Deed_Date,
  COALESCE(B.COLLATERAL_NUMBER,'') AS HKC_Cardinal_Value
FROM {silver_catalog_name}.finrep_tab_neo_cms.property_details a
LEFT OUTER JOIN {silver_catalog_name}.finrep_tab_neo_common_master.address d 
ON a.address = d.id
LEFT OUTER JOIN {silver_catalog_name}.finrep_tab_neo_cms.AGREEMENT_DETAILS G 
ON g.PROPERTY_DETAIL_FK = a.id,
{silver_catalog_name}.finrep_tab_neo_cms.collateral b
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP1
ON GP1.ID = A.APPLICATION_TYPE
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.COLLATERAL_SUB_TYPE CST
ON CST.id = b.COLLATERAL_SUB_TYPE
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP2
ON GP2.ID = B.asset_type
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.BUILDER_PROPERTY_TYPE BPT
ON BPT.ID = A.property_type
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP3
ON GP3.ID = A.NATURE_OF_PROPERTY
LEFT JOIN   {silver_catalog_name}.finrep_tab_neo_common_master.PROPERTY_CLASSIFICATION PC
ON PC.ID = A.PROPERTY_CLASSIFICATION
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP4
ON GP4.ID = A.PROPERTY_OWNERSHIP
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.generic_parameter GP5
ON GP5.id = A.CONSIDERED_VALUATION
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP6
ON GP6.ID = A.PROPERTY_PURPOSE
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP7
ON GP7.ID = A.RESIDUAL_AGE
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.city 
ON city.id = d.city
LEFT JOIN {silver_catalog_name}.finrep_tab_neo_common_master.STATE
ON STATE.id = d.STATE
LEFT JOIN {silver_catalog_name}.finrep_tab_neo_common_master.zip_code
ON zip_code.id = D.ZIPCODE
LEFT JOIN   {silver_catalog_name}.finrep_tab_neo_common_master.country
ON country.id = D.COUNTRY
LEFT JOIN {silver_catalog_name}.finrep_tab_neo_common_master.BUSINESS_PARTNER BP
ON BP.ID = A.BUILDER_COMPANY
LEFT JOIN (SELECT BUILDER_COMPANY_CATEGORY, ID 
          FROM {silver_catalog_name}.finrep_tab_neo_common_master.Builder_Company) Builder_Company 
ON Builder_Company.ID = A.BUILDER_COMPANY
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP8
ON GP8.ID =Builder_Company.BUILDER_COMPANY_CATEGORY
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.BUILDER_PROJECT 
ON BUILDER_PROJECT.ID = A.BUILDER_PROJECT
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.BUILDING
ON BUILDING.ID = A.BUILDING
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.BUILDING_WING
ON BUILDING_WING.ID = A.BUILDING_WING
LEFT JOIN {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP9
ON GP9.ID = A.CURRENT_PROPERTY_USAGE
LEFT JOIN  {silver_catalog_name}.finrep_tab_neo_common_master.GENERIC_PARAMETER GP10
ON GP10.ID = g.agreement_type
WHERE
  a.id = b.property_details
  AND NOT EXISTS (
    SELECT
      1
    FROM
      { silver_catalog_name }.finrep_tab_neo_cms.Asset_Details AD
    WHERE
      b.ASSET_DETAILS = AD.ID
  )
  AND B.COLLATERAL_NUMBER IS NOT NULL
 AND CAST(a.hkc_insert_date AS DATE) >= CAST('{dim_start_date}' AS DATE)
)
SELECT ct.*,cm.collateral_key FROM Cte_1 ct 
LEFT JOIN {gold_catalog_name}.pfldw.DimCollateralMaster CM ON ct.Collateral_ID = CM.Collateral_ID
    """)
    except Exception as e:
        error = str(e)
        print(error)

# COMMAND ----------

# MAGIC %md
# MAGIC ###IMPLEMENTED SCD FUNCTIONS
# MAGIC - Execute SCD1 Function 

# COMMAND ----------

# MAGIC %run 
# MAGIC /Workspace/PFL/Delta-Lake/Gold/pfl_dwh/SCD_FUNCTIONS/fn_dwh_SCD_function

# COMMAND ----------

scd1_load_to_target(f'{gold_catalog_name}.pfldw.DimCollateralProperty','vw_DimCollateralProperty',['HKC_Cardinal_Value'], src_system_id)

# COMMAND ----------

# MAGIC %md
# MAGIC ##Code Execution End time

# COMMAND ----------

#get endTime of the notebook
endTime = datetime.datetime.now(tz=timezone)
print("End time --> ",endTime)
 
#get copyDuration in seconds
copyDuration = endTime - startTime
copyDurationInSec = copyDuration.total_seconds()
print("Copy duration in seconds --> ",copyDurationInSec)

# COMMAND ----------

# MAGIC %md
# MAGIC ###Updating report notebook execution config table
# MAGIC - Last_Sink_Date
# MAGIC - Satus: "In-Progress" --> "Completed"
# MAGIC - Business_Date

# COMMAND ----------

while True:
    try:
        if error == "No Error":
            spark.sql(f"""
                UPDATE {admin_catalog_name}.config.tb_dwh_config
                SET  Last_Sink_Date = '{trigger_time}', Status = "Succeeded", Business_Date = "{business_date}"
                WHERE Config_ID = {config_id}
                """)
            break
        else:
            spark.sql(f"""
                UPDATE {admin_catalog_name}.config.tb_dwh_config
                SET Status = "Failed"
                WHERE Config_ID = {config_id}
                """)
            break
    except Exception as e:
            if "MetadataChangedException" in str(type(e)) or "ConcurrentAppendException" in str(type(e)) :
                sleep_duration = random.uniform(1,5)
                time.sleep(sleep_duration)
            else:
                error = e
                print(error)
                break

# COMMAND ----------

if error == "No Error":
    dbutils.notebook.exit(json.dumps({
        "copyDurationInSec":f"{copyDurationInSec}",
        "startTime":f"{str(startTime).split('+')[0]}",
        "endTime":f"{str(endTime).split('+')[0]}",
        "status":"Succeeded"
    }))
else:
    dbutils.notebook.exit(json.dumps({
        "copyDurationInSec":f"{copyDurationInSec}",
        "startTime":f"{str(startTime).split('+')[0]}",
        "endTime":f"{str(endTime).split('+')[0]}",
        "status":"Failed",
        "errorMessage":f"{error}"
    }))
