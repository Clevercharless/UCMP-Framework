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
