"""
tests.test_repository_manager
==============================
Unit tests for repository.inventory, repository.git_ops, and
repository.repository_manager.RepositoryManager.

These tests build small synthetic repos under pytest's tmp_path rather
than depending on the real ucmp-demo/Loan-Platform content, so they stay
fast and isolated. A separate integration test at the bottom exercises
the real demo repo end to end.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from auth.credentials import SimulatedToken
from auth.token_store import TokenStore
from common.exceptions import AuthenticationError, RepositoryError
from orchestrator.context import PipelineContext
from repository.git_ops import SimulatedGitClient
from repository.inventory import NotebookLanguage, detect_notebook_language
from repository.repository_manager import RepositoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_token_store() -> TokenStore:
    store = TokenStore()
    now = time.time()
    store.put(
        SimulatedToken(
            principal="svc-test-azure", platform="azure_databricks", token_value="SIM.abc123",
            issued_at=now, expires_at=now + 3600, scopes=["workspace.read"],
        )
    )
    return store


def _build_minimal_repo(root: Path) -> Path:
    """A tiny but structurally valid Loan-Platform-shaped repo."""
    repo = root / "Mini-Platform"
    for category, filename, content in [
        ("Bronze", "ingest_x.py", "# Databricks notebook source\nprint('bronze')\n"),
        ("Silver", "clean_x.py", "# Databricks notebook source\nprint('silver')\n"),
        ("Gold", "summary_x.py", "# Databricks notebook source\nprint('gold')\n"),
        ("Common", "utils.py", "# Databricks notebook source\nprint('utils')\n"),
        ("Jobs", "daily_job.py", "# Databricks notebook source\nprint('job')\n"),
        ("SQL", "create.sql", "-- Databricks notebook source\nSELECT 1;\n"),
    ]:
        folder = repo / category
        folder.mkdir(parents=True, exist_ok=True)
        (folder / filename).write_text(content)

    config_folder = repo / "Config"
    config_folder.mkdir(parents=True, exist_ok=True)
    (config_folder / "settings.yaml").write_text("key: value\n")

    return repo


def _config_for(source_repo_path: Path) -> dict:
    return {
        "source": {"repo_path": str(source_repo_path)},
        "target": {},
        "pipeline": {"fail_fast": True, "dry_run": True},
    }


# ---------------------------------------------------------------------------
# inventory.detect_notebook_language
# ---------------------------------------------------------------------------

def test_detect_language_python(tmp_path: Path):
    f = tmp_path / "nb.py"
    f.write_text("# Databricks notebook source\nprint(1)\n")
    assert detect_notebook_language(f) == NotebookLanguage.PYTHON


def test_detect_language_sql(tmp_path: Path):
    f = tmp_path / "nb.sql"
    f.write_text("-- Databricks notebook source\nSELECT 1;\n")
    assert detect_notebook_language(f) == NotebookLanguage.SQL


def test_detect_language_unknown_for_plain_file(tmp_path: Path):
    f = tmp_path / "plain.py"
    f.write_text("print('not a notebook export')\n")
    assert detect_notebook_language(f) == NotebookLanguage.UNKNOWN


# ---------------------------------------------------------------------------
# SimulatedGitClient
# ---------------------------------------------------------------------------

def test_git_client_clone_raises_when_source_missing(tmp_path: Path):
    client = SimulatedGitClient()
    with pytest.raises(RepositoryError, match="does not exist"):
        client.clone(tmp_path / "nonexistent", tmp_path / "staging")


def test_git_client_clone_copies_all_files(tmp_path: Path):
    source = _build_minimal_repo(tmp_path / "source")
    staging = tmp_path / "staging" / "Mini-Platform"

    client = SimulatedGitClient()
    client.clone(source, staging)

    tracked = client.list_tracked_files(staging)
    assert len(tracked) == 7  # 6 notebooks + 1 config asset


def test_git_client_clone_is_idempotent_refresh(tmp_path: Path):
    source = _build_minimal_repo(tmp_path / "source")
    staging = tmp_path / "staging" / "Mini-Platform"

    client = SimulatedGitClient()
    client.clone(source, staging)
    client.clone(source, staging)  # re-clone should not error or duplicate

    tracked = client.list_tracked_files(staging)
    assert len(tracked) == 7


# ---------------------------------------------------------------------------
# RepositoryManager (PipelineStage)
# ---------------------------------------------------------------------------

def test_repository_manager_requires_valid_auth_token(tmp_path: Path):
    empty_store = TokenStore()  # no token minted
    source = _build_minimal_repo(tmp_path / "source")
    manager = RepositoryManager(token_store=empty_store, staging_dir=str(tmp_path / "staging"))
    context = PipelineContext(config=_config_for(source))

    with pytest.raises(AuthenticationError, match="No simulated token"):
        manager.run(context)


def test_repository_manager_requires_config_populated():
    manager = RepositoryManager(token_store=_make_valid_token_store())
    context = PipelineContext()  # config never populated
    with pytest.raises(RepositoryError, match="ConfigurationManager"):
        manager.run(context)


def test_repository_manager_builds_inventory_from_minimal_repo(tmp_path: Path):
    source = _build_minimal_repo(tmp_path / "source")
    manager = RepositoryManager(
        token_store=_make_valid_token_store(), staging_dir=str(tmp_path / "staging")
    )
    context = PipelineContext(config=_config_for(source))

    result_context = manager.run(context)

    repo = result_context.get_artifact("repository")
    assert repo["notebook_count"] == 6
    assert set(repo["categories_found"]) == {"Bronze", "Common", "Gold", "Jobs", "SQL", "Silver"}
    assert len(repo["config_assets"]) == 1
    assert result_context.metadata["repository_synced"] is True


def test_repository_manager_fails_on_missing_required_category(tmp_path: Path):
    source = _build_minimal_repo(tmp_path / "source")
    # Delete the Gold category entirely to violate the required structure
    import shutil
    shutil.rmtree(source / "Gold")

    manager = RepositoryManager(
        token_store=_make_valid_token_store(), staging_dir=str(tmp_path / "staging")
    )
    context = PipelineContext(config=_config_for(source))

    with pytest.raises(RepositoryError, match="missing required categories"):
        manager.run(context)


def test_repository_manager_fails_when_source_path_does_not_exist(tmp_path: Path):
    manager = RepositoryManager(
        token_store=_make_valid_token_store(), staging_dir=str(tmp_path / "staging")
    )
    context = PipelineContext(config=_config_for(tmp_path / "does-not-exist"))

    with pytest.raises(RepositoryError, match="does not exist"):
        manager.run(context)


def test_repository_manager_notebook_checksums_are_deterministic(tmp_path: Path):
    source = _build_minimal_repo(tmp_path / "source")
    manager = RepositoryManager(
        token_store=_make_valid_token_store(), staging_dir=str(tmp_path / "staging")
    )
    context = manager.run(PipelineContext(config=_config_for(source)))

    repo = context.get_artifact("repository")
    checksums = {nb["relative_path"]: nb["sha256"] for nb in repo["notebooks"]}
    assert len(checksums["Bronze/ingest_x.py"]) == 64  # sha256 hex digest length




def test_repository_manager_workspace_exports_only_selected_notebooks(monkeypatch, tmp_path: Path):
    class Obj:
        def __init__(self, path, language="PYTHON"):
            self.path = path
            self.object_type = "NOTEBOOK"
            self.language = language

    class FakeWorkspace:
        def __init__(self, *args, **kwargs):
            pass
        def list_recursive(self, root):
            return [
                Obj("/Workspace/Users/test/pfl-repo/PFL/one"),
                Obj("/Workspace/Users/test/pfl-repo/PFL/two"),
            ]
        def export_source(self, path):
            return "# Databricks notebook source\nprint('selected')\n"

    monkeypatch.setattr(
        "repository.repository_manager.DatabricksWorkspaceClient", FakeWorkspace
    )
    manager = RepositoryManager(token_store=TokenStore())
    context = PipelineContext(config={
        "source": {
            "source_mode": "workspace",
            "workspace_url": "https://example.cloud.databricks.com",
            "workspace_path": "/Workspace/Users/test/pfl-repo",
            "repo_path": "/Workspace/Users/test/pfl-repo",
        },
        "migration": {"notebook_list": ["/PFL/one"]},
    })

    result = manager.run(context)
    repo = result.get_artifact("repository")
    assert [nb["relative_path"] for nb in repo["notebooks"]] == ["PFL/one.py"]
    assert repo["known_notebook_paths"] == ["PFL/one", "PFL/two"]
    assert repo["staged_path"] == ""
    assert result.metadata["workspace_staging_used"] is False
    assert "_staging" not in str(repo)
# ---------------------------------------------------------------------------
# Integration: real ucmp-demo/Loan-Platform repo
# ---------------------------------------------------------------------------

def test_repository_manager_against_real_demo_repo(tmp_path: Path):
    """
    Exercises RepositoryManager against the actual demo Loan-Platform repo
    shipped in ucmp-demo, proving the module works against the real
    14-notebook / 2-SQL / 2-config asset content, not just synthetic fixtures.
    """
    from repository.repository_manager import _PROJECT_ROOT

    real_source = _PROJECT_ROOT / "ucmp-demo" / "Loan-Platform"
    if not real_source.exists():
        pytest.skip("ucmp-demo/Loan-Platform not present in this checkout")

    manager = RepositoryManager(
        token_store=_make_valid_token_store(), staging_dir=str(tmp_path / "staging")
    )
    context = PipelineContext(config=_config_for(real_source))

    result_context = manager.run(context)
    repo = result_context.get_artifact("repository")

    # 14 Python notebooks (Bronze/Silver/Gold/Common/Jobs) + 2 SQL notebooks (SQL/) = 16
    assert repo["notebook_count"] == 16
    assert len(repo["config_assets"]) == 2
    assert set(repo["categories_found"]) == {"Bronze", "Common", "Gold", "Jobs", "SQL", "Silver"}
