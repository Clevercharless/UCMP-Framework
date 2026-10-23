from pathlib import Path
from orchestrator.context import PipelineContext
from repository.repository_manager import RepositoryManager
from auth.token_store import TokenStore
from auth.credentials import SimulatedToken
import time

def _token_store():
    s=TokenStore()
    now=time.time()
    s.put(SimulatedToken(principal="t", platform="azure_databricks", token_value="SIM.x",
                         issued_at=now, expires_at=now+3600, scopes=["workspace.read"]))
    return s

def test_explicit_scope_skips_legacy_category_validation(tmp_path):
    root=tmp_path/"repo"
    (root/"PFL/Delta-Lake").mkdir(parents=True)
    nb=root/"PFL/Delta-Lake/a.py"
    nb.write_text("# Databricks notebook source\nprint(1)\n")
    manager=RepositoryManager(token_store=_token_store(), staging_dir=str(tmp_path/"stage"))
    ctx=PipelineContext(config={
        "source":{"repo_path":str(root),"source_mode":"local_repo","workspace_path":"/"},
        "migration":{"notebook_list":["PFL/Delta-Lake/a"]},
        "pipeline":{"dry_run":True}
    })
    out=manager.run(ctx)
    assert out.get_artifact("repository")["notebook_count"] == 1

def test_referred_repo_prefix_is_configurable():
    from parser.migration_analyzer import MigrationAnalyzer
    a=MigrationAnalyzer(
        referred_notebook_path_root="/Workspace/Users/me",
        source_repo_path="/Workspace/Users/me/pfl-repo-dbx-datalake"
    )
    result=a.analyze("PFL/a.py", "x='/Workspace/pfl-repo-dbx-datalake/PFL/b'\n")
    edit=next(e for e in result.edits if e.edit_type=="referred_notebook_path")
    assert edit.resolved_value == "/Workspace/Users/me/pfl-repo-dbx-datalake/"

