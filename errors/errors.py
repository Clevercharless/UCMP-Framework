RUN_RE = re.compile(
    r"(?:#\s*M​​AGIC\s+)?%run\s+"
    r"(?:#\s*M​​AGIC\s+)?"
    r"(?P<quote>[\"']?)"
    r"(?P<path>/Workspace/[^\s\"']+)"
    r"(?P=quote)",
    re.MULTILINE,
)

for match in RUN_RE.finditer(text):
    raw = match.group("path")
    relative = raw[len("/Workspace/"):]
    target = f"{self.workspace_root.rstrip('/')}/{relative}"
    line_number = text.count("\n", 0, match.start("path")) + 1

    result.edits.append(MigrationEdit(
        notebook=notebook,
        edit_type="workspace_run_path",
        original_value=raw,
        resolved_value=target,
        line_number=line_number,
        notes=(
            "Converted hardcoded source workspace %run "
            "reference to the configured target workspace root."
        ),
        construct_type="workspace_notebook_path",
    ))
  
