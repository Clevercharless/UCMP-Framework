if error == 'No Error':
    try:
        conn = mysql.connector.connect(
            host="xxxxx.rds.amazonaws.com",
            user="",
            password=secret_key,
            database=""


try:
      (df_dpd_communication_status_prod.write \
        .format("jdbc") \
        .mode("append") \
        .option("driver","com.mysql.cj.jdbc.Driver") \
        .option("url", "jdbc:mysql:/xxxx.rds.amazonaws.com:xxxxxxd") \
        .option("dbtable", "xxxxxs") \
        .option("user", "oxxxxx") \
        .option("password", secret_key).save())
