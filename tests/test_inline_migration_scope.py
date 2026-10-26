from pathlib import Path

from parser.parser_engine import ParserEngine


def test_inline_notebook_list_is_authoritative(tmp_path):
    class Ctx:
        config = {"migration": {"notebook_list": ["Bronze/b.py", "Bronze/a.py", "Bronze/b.py"]}}

    result = ParserEngine._load_migration_scope(Ctx(), ["Bronze/a.py", "Bronze/b.py", "Bronze/c.py"])
    assert result == ["Bronze/b.py", "Bronze/a.py"]
