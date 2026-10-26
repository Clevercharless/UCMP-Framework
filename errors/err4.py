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








from parser.ast_parser import ASTParser
from parser.regex_parser import RegexParser

sample = '''
conn = mysql.connector.connect(
    host="example.rds.amazonaws.com",
    user="db_user",
    password=secret_key,
    database="analytics"
)

df.write.format("jdbc") \\
    .option("driver", "com.mysql.cj.jdbc.Driver") \\
    .option("url", "jdbc:mysql://example.rds.amazonaws.com:3306/analytics") \\
    .option("password", secret_key).save()

password = dbutils.secrets.get(
    scope="my_scope",
    key="my_key"
)
'''

regex_parser = RegexParser()

print("Regex findings:")
for finding in regex_parser.parse_general_constructs(sample):
    print(finding.to_dict())

ast_parser = ASTParser()

print("\nAST findings:")
findings = ast_parser.parse(sample, "test_notebook.py")
print(findings.to_dict())










Regex findings:
{'category': 'jdbc_url', 'value': 'jdbc:mysql://example.rds.amazonaws.com:3306/analytics', 'line_number': 11}
{'category': 'secret_retrieval_api', 'value': 'dbutils.secrets.get', 'line_number': 14}

AST findings:
{'imports': [], 'assignments': [{'target': 'conn', 'value_snippet': "mysql.connector.connect(host='example.rds.amazonaws.com', user='db_user', password=[REDACTED] database='analytics')", 'line_number': 2}, {'target': 'password', 'value_snippet': '[REDACTED]', 'line_number': 14}], 'function_defs': [], 'calls': [{'category': 'database_connection', 'snippet': "mysql.connector.connect(host='example.rds.amazonaws.com', user='db_user', password=[REDACTED] database='analytics')", 'line_number': 2}, {'category': 'spark_write', 'snippet': "df.write.format('jdbc').option('driver', 'com.mysql.cj.jdbc.Driver').option('url', 'jdbc:mysql://example.rds.amazonaws.com:3306/analytics').option('password', s", 'line_number': 9}, {'category': 'dbutils_call', 'snippet': "dbutils.secrets.get(scope='my_scope', key='my_key')", 'line_number': 14}, {'category': 'spark_write', 'snippet': "df.write.format('jdbc').option('driver', 'com.mysql.cj.jdbc.Driver').option('url', 'jdbc:mysql://example.rds.amazonaws.com:3306/analytics').option('password', s", 'line_number': 9}, {'category': 'spark_write', 'snippet': "df.write.format('jdbc').option('driver', 'com.mysql.cj.jdbc.Driver').option('url', 'jdbc:mysql://example.rds.amazonaws.com:3306/analytics')", 'line_number': 9}, {'category': 'spark_write', 'snippet': "df.write.format('jdbc').option('driver', 'com.mysql.cj.jdbc.Driver')", 'line_number': 9}, {'category': 'spark_write', 'snippet': "df.write.format('jdbc')", 'line_number': 9}], 'database_connections': [{'connection_type': 'mysql', 'detection_method': 'mysql_connector_connect', 'line_number': 2, 'host': 'example.rds.amazonaws.com', 'database': 'analytics', 'username': 'db_user', 'password_argument_present': True, 'password_is_variable': True}, {'connection_type': 'mysql', 'detection_method': 'spark_jdbc_write', 'line_number': 9, 'driver': 'com.mysql.cj.jdbc.Driver', 'url': 'jdbc:mysql://example.rds.amazonaws.com:3306/analytics', 'table': None, 'username': None, 'write_mode': None, 'password_argument_present': True, 'password_is_variable': True}], 'secret_references': [{'api': 'dbutils.secrets.get', 'line_number': 14, 'scope': 'my_scope', 'key': 'my_key', 'scope_is_literal': True, 'key_is_literal': True}], 'credential_findings': [{'credential_type': 'password', 'line_number': 14, 'variable': 'password', 'literal_value_redacted': None, 'is_hardcoded_literal': False, 'source_is_secret_reference': True, 'source_api': 'dbutils.secrets.get'}, {'credential_type': 'password', 'line_number': 2, 'variable': 'secret_key', 'literal_value_redacted': None, 'is_hardcoded_literal': False, 'source_is_secret_reference': False, 'source_api': None}, {'credential_type': 'password', 'line_number': 9, 'variable': 'secret_key', 'literal_value_redacted': None, 'is_hardcoded_literal': False, 'source_is_secret_reference': False, 'source_api': None}]}
