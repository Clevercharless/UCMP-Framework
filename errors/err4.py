# ------------------------------------------------------------
# Referred notebook/repository paths
# Disabled by default; enable when needed.
# ------------------------------------------------------------
if self.enable_referred_notebook_path_changes:
    repo_name = (
        Path(self.source_repo_path).name
        if self.source_repo_path
        else ""
    )

    if repo_name:
        source_prefixes = {
            f"/Workspace/{repo_name}/",
            f"{self.source_repo_path}/" if self.source_repo_path else "",
        }
        source_prefixes.discard("")

        target_prefix = (
            f"{self.referred_notebook_path_root}/{repo_name}/"
        )

        for line_no, line in enumerate(text.splitlines(), 1):
            for source_prefix in sorted(
                source_prefixes, key=len, reverse=True
            ):
                if source_prefix in line:
                    result.edits.append(
                        MigrationEdit(
                            notebook=notebook,
                            edit_type="referred_notebook_path",
                            original_value=source_prefix,
                            resolved_value=target_prefix,
                            line_number=line_no,
                            notes=(
                                "Replaced the hardcoded source workspace "
                                "repository prefix with the configured "
                                "target workspace repository root."
                            ),
                            construct_type="workspace_notebook_path",
                        )
                    )
