# Ensure environment configuration exists in every notebook
env_os_assignment = re.search(
    r"(?m)^\s*env\s*=\s*(?:os\.getenv|os\.environ\.get)\s*\(",
    text,
)

if env_os_assignment:
    # Environment assignment already exists.
    # Add only the import statement.
    result.edits.append(
        MigrationEdit(
            edit_type="add_target_config",
            resolved_value="import os",
            line_number=1,
        )
    )
else:
    # No environment assignment exists.
    # Add both lines.
    result.edits.append(
        MigrationEdit(
            edit_type="add_target_config",
            resolved_value='import os\nenv = os.getenv("env")',
            line_number=1,
        )
    )
