from datetime import datetime
from pathlib import Path


def get_run_timestamp(context) -> str:
    """Return one consistent timestamp for the entire pipeline run."""
    if "run_timestamp" not in context.metadata:
        context.metadata["run_timestamp"] = datetime.fromtimestamp(
            context.created_at
        ).strftime("%Y%m%d_%H%M%S")

    return context.metadata["run_timestamp"]


def timestamped_path(path: Path, context) -> Path:
    """Add the pipeline timestamp before the file extension."""
    timestamp = get_run_timestamp(context)
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")



# replace the _write in reporting_engine.py

from common.output_naming import timestamped_path


@staticmethod
def _write_reports(output_dir, reports, context):
    written_paths = {}

    for filename, content in reports.items():
        output_path = timestamped_path(
            output_dir / filename,
            context
        )

        output_path.write_text(content, encoding="utf-8")
        written_paths[filename] = str(output_path)

    return written_paths
