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