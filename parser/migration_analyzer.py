Step 1: Find this existing block
Starting at line 724, find:
# Add or normalize the environment declaration only when a generated# target path actually depends on {env}. Environment selection comes# from the process environment, not a Databricks widget.if any("{env}" in str(edit.resolved_value) for edit in result.edits):


Step 2: Replace the entire environment configuration block

# Ensure environment configuration exists in every notebook
insert_at = self._env_insert_location(assignments, result.edits)

env_widget = re.compile(
    r"^(?P<indent>\s*)env\s*=\s*dbutils\.widgets\.get\(\s*([\"'])env\2\s*\)\s*$"
)

env_os_declaration = re.compile(
    r"^\s*env\s*=\s*(?:os\.getenv|os\.environ\.get)\s*\("
)

env_assignment = None

for line_number, line in enumerate(text.splitlines(), 1):
    if env_widget.match(line):
        env_assignment = (line_number, line)
        break

has_env_os_declaration = any(
    env_os_declaration.match(line)
    for line in text.splitlines()
)

if env_assignment:
    # Replace the existing Databricks widget assignment.
    line_number, original_line = env_assignment

    result.edits.append(
        MigrationEdit(
            notebook=notebook,
            edit_type="env_config_replace",
            original_value=original_line,
            resolved_value='env = os.getenv("env")',
            line_number=line_number,
            notes="Replaced the env Databricks widget lookup with os.getenv.",
            construct_type="target_environment_config",
        )
    )

    result.edits.append(
        MigrationEdit(
            notebook=notebook,
            edit_type="add_target_config",
            original_value="",
            resolved_value="import os",
            line_number=1,
            notes="Added the os import required by environment lookup.",
            construct_type="target_environment_config",
        )
    )

elif has_env_os_declaration:
    # An environment assignment already exists.
    # Add only the import statement.
    result.edits.append(
        MigrationEdit(
            notebook=notebook,
            edit_type="add_target_config",
            original_value="",
            resolved_value="import os",
            line_number=1,
            notes="Added the os import required by environment lookup.",
            construct_type="target_environment_config",
        )
    )

else:
    # No environment assignment exists.
    # Add both lines.
    result.edits.append(
        MigrationEdit(
            notebook=notebook,
            edit_type="add_target_config",
            original_value="",
            resolved_value='import os\nenv = os.getenv("env")',
            line_number=1,
            notes="Added target environment configuration using os.getenv.",
            construct_type="target_environment_config",
        )
    )
