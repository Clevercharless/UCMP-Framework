"""
tests.test_parser_engine
==========================
Unit tests for every Parser Engine sub-component (Notebook Reader, Magic
Parser, Regex Parser, AST Parser, SQL Parser, Dependency Extractor,
Dependency Graph Builder, Knowledge Model Generator) and the ParserEngine
PipelineStage itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.exceptions import ParserError
from parser.ast_parser import ASTParser
from parser.dependency_extractor import DependencyExtractor
from parser.dependency_graph import DependencyGraphBuilder
from parser.knowledge_model import KnowledgeModelGenerator, NotebookParseResult
from parser.magic_parser import MagicCommandParser
from parser.notebook_reader import NotebookReader
from parser.parser_engine import ParserEngine
from parser.regex_parser import AzureConstructType, RegexParser
from parser.sql_parser import SQLParser, SQLStatementType
from orchestrator.context import PipelineContext
from repository.inventory import NotebookLanguage


# ---------------------------------------------------------------------------
# NotebookReader
# ---------------------------------------------------------------------------

_PYTHON_NOTEBOOK = """# Databricks notebook source
# MAGIC %md
# MAGIC ## Title

# COMMAND ----------

# MAGIC %run "../Common/utils"

# COMMAND ----------

import json
x = 1

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM bronze.customers
"""

_SQL_NOTEBOOK = """-- Databricks notebook source
-- MAGIC %md
-- MAGIC ## SQL notebook

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS bronze.x USING DELTA LOCATION 'abfss://x@y.dfs.core.windows.net/x';
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    f = tmp_path / name
    f.write_text(content)
    return f


def test_notebook_reader_splits_python_cells(tmp_path: Path):
    f = _write(tmp_path, "nb.py", _PYTHON_NOTEBOOK)
    notebook = NotebookReader().read("nb.py", str(f))
    assert notebook.language == NotebookLanguage.PYTHON
    assert notebook.cell_count == 4


def test_notebook_reader_splits_sql_cells(tmp_path: Path):
    f = _write(tmp_path, "nb.sql", _SQL_NOTEBOOK)
    notebook = NotebookReader().read("nb.sql", str(f))
    assert notebook.language == NotebookLanguage.SQL
    assert notebook.cell_count == 2


def test_notebook_reader_raises_on_missing_header(tmp_path: Path):
    f = _write(tmp_path, "plain.py", "print('not a notebook export')\n")
    with pytest.raises(ParserError, match="export header"):
        NotebookReader().read("plain.py", str(f))


def test_notebook_reader_raises_on_missing_file(tmp_path: Path):
    with pytest.raises(ParserError, match="does not exist"):
        NotebookReader().read("missing.py", str(tmp_path / "missing.py"))


# ---------------------------------------------------------------------------
# MagicCommandParser
# ---------------------------------------------------------------------------

def test_magic_parser_finds_run_and_sql_magics(tmp_path: Path):
    f = _write(tmp_path, "nb.py", _PYTHON_NOTEBOOK)
    notebook = NotebookReader().read("nb.py", str(f))
    magics = MagicCommandParser().parse(notebook)

    types = [m.magic_type for m in magics]
    assert "run" in types
    assert "sql" in types
    run_magic = next(m for m in magics if m.magic_type == "run")
    assert run_magic.argument.strip('"') == "../Common/utils"


def test_magic_parser_returns_empty_for_notebook_with_no_magics(tmp_path: Path):
    content = "# Databricks notebook source\nprint(1)\n"
    f = _write(tmp_path, "nb.py", content)
    notebook = NotebookReader().read("nb.py", str(f))
    assert MagicCommandParser().parse(notebook) == []


# ---------------------------------------------------------------------------
# RegexParser
# ---------------------------------------------------------------------------

def test_regex_parser_detects_abfss_path():
    text = "df = spark.read.load('abfss://bronze@acct.dfs.core.windows.net/x')"
    findings = RegexParser().parse(text)
    assert any(f.construct_type == AzureConstructType.ABFSS_PATH for f in findings)


def test_regex_parser_detects_key_vault_secret_scope():
    text = 'x = dbutils.secrets.get(scope="my-kv", key="secret")'
    findings = RegexParser().parse(text)
    assert any(f.construct_type == AzureConstructType.KEY_VAULT for f in findings)


def test_regex_parser_detects_mount_path():
    text = "RAW_MOUNT_POINT = '/mnt/raw/customers'"
    findings = RegexParser().parse(text)
    assert any(f.construct_type == AzureConstructType.MOUNT_PATH for f in findings)


def test_regex_parser_detects_azure_sdk_import():
    text = "from azure.identity import ClientSecretCredential"
    findings = RegexParser().parse(text)
    assert any(f.construct_type == AzureConstructType.AZURE_SDK_IMPORT for f in findings)


def test_regex_parser_detects_jdbc_hardcoded_url():
    text = "jdbc_url = f'jdbc:sqlserver://{host}:1433;database=db'"
    findings = RegexParser().parse(text)
    assert any(f.construct_type == AzureConstructType.HARDCODED_URL for f in findings)


# ---------------------------------------------------------------------------
# ASTParser
# ---------------------------------------------------------------------------

def test_ast_parser_detects_imports_and_calls():
    source = (
        "# Databricks notebook source\n"
        "from azure.identity import ClientSecretCredential\n"
        "df = spark.read.format('csv').load('/tmp/x')\n"
        "df.write.format('parquet').save('/tmp/y')\n"
        "dbutils.notebook.run('../Bronze/ingest_customer', 3600, {})\n"
    )
    findings = ASTParser().parse(source, "nb.py")

    assert any("azure.identity" in i.module for i in findings.imports)
    categories = [c.category for c in findings.calls]
    assert "spark_read" in categories
    assert "spark_write" in categories
    assert "notebook_reference" in categories

    ref_call = next(c for c in findings.calls if c.category == "notebook_reference")
    assert ref_call.notebook_reference_target == "../Bronze/ingest_customer"


def test_ast_parser_categorizes_delta_format_write_as_delta_api():
    """.write.format('delta') is intentionally categorized as delta_api (checked
    before the generic spark_write pattern), since Delta writes need different
    migration handling than plain spark_write calls."""
    source = (
        "# Databricks notebook source\n"
        "df.write.format('delta').mode('overwrite').save('/tmp/y')\n"
    )
    findings = ASTParser().parse(source, "nb.py")
    categories = [c.category for c in findings.calls]
    assert "delta_api" in categories


def test_ast_parser_raises_parser_error_on_invalid_python():
    with pytest.raises(ParserError):
        ASTParser().parse("def broken(:\n", "broken.py")


def test_ast_parser_detects_function_defs():
    source = "def standardize_columns(df):\n    return df\n"
    findings = ASTParser().parse(source, "utils.py")
    assert any(f.name == "standardize_columns" for f in findings.function_defs)


# ---------------------------------------------------------------------------
# SQLParser
# ---------------------------------------------------------------------------

def test_sql_parser_detects_create_table_and_join():
    sql = """
    CREATE TABLE IF NOT EXISTS bronze.customers USING DELTA LOCATION 'x';
    SELECT * FROM silver.customers c JOIN silver.accounts a ON a.customer_id = c.customer_id;
    """
    findings = SQLParser().parse(sql)
    types = [s.statement_type for s in findings.statements]
    assert SQLStatementType.CREATE_TABLE in types
    assert SQLStatementType.SELECT_FROM in types
    assert SQLStatementType.JOIN in types
    assert "bronze.customers" in findings.table_dependencies


def test_sql_parser_merge_update_set_not_misparsed_as_table():
    sql = """
    MERGE INTO silver.loans AS target
    USING bronze.loans AS source
    ON target.loan_id = source.loan_id
    WHEN MATCHED THEN
        UPDATE SET target.principal_amount = source.principal_amount
    """
    findings = SQLParser().parse(sql)
    table_names = [s.table_name for s in findings.statements if s.statement_type == SQLStatementType.UPDATE]
    assert "SET" not in table_names


def test_sql_parser_detects_real_update_statement():
    sql = "UPDATE bronze.customers SET status = 'ACTIVE' WHERE id = 1;"
    findings = SQLParser().parse(sql)
    update_stmts = [s for s in findings.statements if s.statement_type == SQLStatementType.UPDATE]
    assert len(update_stmts) == 1
    assert update_stmts[0].table_name == "bronze.customers"


def test_sql_parser_detects_create_view():
    sql = "CREATE OR REPLACE VIEW gold.v_summary AS SELECT * FROM gold.customer_summary;"
    findings = SQLParser().parse(sql)
    assert any(s.statement_type == SQLStatementType.CREATE_VIEW for s in findings.statements)


# ---------------------------------------------------------------------------
# DependencyExtractor
# ---------------------------------------------------------------------------

def test_dependency_extractor_resolves_run_magic(tmp_path: Path):
    f = _write(tmp_path, "nb.py", _PYTHON_NOTEBOOK)
    notebook = NotebookReader().read("Bronze/ingest_x.py", str(f))
    magics = MagicCommandParser().parse(notebook)

    extractor = DependencyExtractor(known_notebook_paths=["Bronze/ingest_x.py", "Common/utils.py"])
    deps = extractor.extract("Bronze/ingest_x.py", magics, None)

    run_deps = [d for d in deps if d.dependency_type == "run_magic"]
    assert len(run_deps) == 1
    assert run_deps[0].resolved_target == "Common/utils.py"
    assert run_deps[0].is_resolved is True


def test_dependency_extractor_leaves_unresolvable_reference_unresolved():
    extractor = DependencyExtractor(known_notebook_paths=["Bronze/ingest_x.py"])
    from parser.magic_parser import MagicCommand

    magic = MagicCommand(magic_type="run", argument='"../DoesNotExist/thing"', cell_index=0, line_number=1)
    deps = extractor.extract("Bronze/ingest_x.py", [magic], None)

    assert len(deps) == 1
    assert deps[0].is_resolved is False
    assert deps[0].resolved_target is None


# ---------------------------------------------------------------------------
# DependencyGraphBuilder
# ---------------------------------------------------------------------------

def test_dependency_graph_detects_no_cycle_for_dag():
    from parser.dependency_extractor import NotebookDependency

    deps = [
        NotebookDependency("Bronze/a.py", "../Common/utils", "Common/utils.py", "run_magic", 1),
    ]
    builder = DependencyGraphBuilder()
    graph = builder.build(["Bronze/a.py", "Common/utils.py"], deps)
    summary = builder.summarize(graph, deps)

    assert summary.is_acyclic is True
    assert summary.cycles == []
    assert summary.node_count == 2
    assert summary.edge_count == 1


def test_dependency_graph_detects_cycle():
    from parser.dependency_extractor import NotebookDependency

    deps = [
        NotebookDependency("A.py", "B", "B.py", "run_magic", 1),
        NotebookDependency("B.py", "A", "A.py", "run_magic", 1),
    ]
    builder = DependencyGraphBuilder()
    graph = builder.build(["A.py", "B.py"], deps)
    summary = builder.summarize(graph, deps)

    assert summary.is_acyclic is False
    assert len(summary.cycles) == 1


def test_dependency_graph_to_dot_contains_nodes_and_edges():
    from parser.dependency_extractor import NotebookDependency

    deps = [NotebookDependency("A.py", "B", "B.py", "run_magic", 1)]
    builder = DependencyGraphBuilder()
    graph = builder.build(["A.py", "B.py"], deps)
    dot = builder.to_dot(graph)

    assert "digraph NotebookDependencies" in dot
    assert '"A.py" -> "B.py"' in dot


# ---------------------------------------------------------------------------
# KnowledgeModelGenerator
# ---------------------------------------------------------------------------

def test_knowledge_model_generator_produces_all_sections():
    result = NotebookParseResult(
        relative_path="Bronze/x.py", category="Bronze", language="python", cell_count=2
    )
    from parser.dependency_graph import DependencyGraphSummary

    graph_summary = DependencyGraphSummary(node_count=1, edge_count=0, is_acyclic=True)
    model = KnowledgeModelGenerator().generate(
        repo_name="Test-Platform",
        notebook_results=[result],
        dependencies=[],
        graph_summary=graph_summary,
    )
    model_dict = model.to_dict()

    for key in [
        "notebook_metadata", "dependencies", "azure_constructs",
        "configuration_references", "transformation_candidates",
        "business_objects", "manual_review_items",
    ]:
        assert key in model_dict


def test_knowledge_model_flags_hardcoded_url_for_manual_review():
    from parser.regex_parser import AzureConstruct

    result = NotebookParseResult(
        relative_path="Bronze/x.py", category="Bronze", language="python", cell_count=1,
        azure_constructs=[
            AzureConstruct(construct_type=AzureConstructType.HARDCODED_URL, value="jdbc:sqlserver://h", line_number=1)
        ],
    )
    from parser.dependency_graph import DependencyGraphSummary

    graph_summary = DependencyGraphSummary(node_count=1, edge_count=0, is_acyclic=True)
    model = KnowledgeModelGenerator().generate(
        repo_name="Test-Platform", notebook_results=[result], dependencies=[], graph_summary=graph_summary
    )
    assert len(model.manual_review_items) == 1
    assert "manual review" in model.manual_review_items[0]["reason"].lower()


# ---------------------------------------------------------------------------
# ParserEngine (PipelineStage) — integration against the real demo repo
# ---------------------------------------------------------------------------

def test_parser_engine_requires_repository_artifact():
    engine = ParserEngine()
    context = PipelineContext(config={"output": {"knowledge_model_dir": "x"}})
    with pytest.raises(ParserError, match="RepositoryManager"):
        engine.run(context)


def test_parser_engine_end_to_end_against_real_demo_repo(tmp_path: Path):
    """
    Runs the full Orchestrator chain (Config -> Auth -> Repository ->
    Parser) against the real ucmp-demo/Loan-Platform repo, writing the
    knowledge model to a throwaway tmp_path directory.
    """
    from auth.auth_manager import AuthenticationManager
    from config.config_manager import ConfigurationManager
    from orchestrator.orchestrator import Orchestrator
    from repository.repository_manager import RepositoryManager, _PROJECT_ROOT

    real_source = _PROJECT_ROOT / "ucmp-demo" / "Loan-Platform"
    if not real_source.exists():
        pytest.skip("ucmp-demo/Loan-Platform not present in this checkout")

    env = {
        "UCMP__SOURCE__REPO_PATH": str(real_source),
        "UCMP__OUTPUT__KNOWLEDGE_MODEL_DIR": str(tmp_path / "knowledge_model"),
    }
    config_manager = ConfigurationManager(config_path=None, env=env)
    auth_manager = AuthenticationManager()
    repository_manager = RepositoryManager(
        token_store=auth_manager.token_store, staging_dir=str(tmp_path / "staging")
    )
    parser_engine = ParserEngine()

    orchestrator = Orchestrator(
        stages=[config_manager, auth_manager, repository_manager, parser_engine]
    )
    context = orchestrator.run(PipelineContext())

    assert context.summary()["overall_status"] == "SUCCESS"

    model = context.get_artifact("knowledge_model")
    assert len(model["notebook_metadata"]) == 16
    assert model["dependencies"]["graph_summary"]["is_acyclic"] is True
    assert len(model["azure_constructs"]) > 0
    assert any(b["name"] == "bronze.customers" for b in model["business_objects"])

    output_file = tmp_path / "knowledge_model" / "MigrationKnowledgeModel.json"
    assert output_file.exists()

    import json
    with output_file.open() as fh:
        written = json.load(fh)
    assert written["repo_name"] == "Loan-Platform"
