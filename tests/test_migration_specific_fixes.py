from pathlib import Path
from types import SimpleNamespace

from parser.migration_analyzer import MigrationAnalyzer
from replacement.replacement_engine import ReplacementEngine
from transformation.transformation_planner import TransformationPlanner


def test_output_container_identifier_rename_reaches_replacement_engine():
    source = 'output_container_path = config["output_container_path"]\n'
    analysis = MigrationAnalyzer().analyze("Bronze/main.py", source).to_dict()
    operations = {}
    TransformationPlanner._add_migration_specific_operations(operations, [analysis])

    transformed, applied = ReplacementEngine._apply_operations(
        source,
        [operation.to_dict() for operation in operations["Bronze/main.py"]],
    )

    assert applied == 1
    assert 'output_bucket_name = config["output_bucket_name"]' in transformed
    assert "output_container_path" not in transformed


def test_output_container_identifier_in_config_asset_is_renamed(tmp_path: Path):
    source = tmp_path / "source" / "Config" / "config.yaml"
    target_root = tmp_path / "target"
    source.parent.mkdir(parents=True)
    source.write_text("output_container_path: s3://example/path\nother_key: keep\n", encoding="utf-8")
    asset = SimpleNamespace(absolute_path=str(source), relative_path="Config/config.yaml")
    repository = SimpleNamespace(config_assets=[asset])

    engine = ReplacementEngine.__new__(ReplacementEngine)
    engine._copy_config_assets(repository, target_root)

    output = target_root / "Config" / "config.yaml"
    content = output.read_text(encoding="utf-8")
    assert "output_bucket_name: s3://example/path" in content
    assert "output_container_path" not in content
    assert "other_key: keep" in content
