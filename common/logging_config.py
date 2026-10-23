"""
common.logging_config
======================
Central logging configuration for UCMP. All modules should call
`get_logger(__name__)` rather than configuring logging themselves, so that
log formatting and levels stay consistent across the whole pipeline.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-32s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    """
    Idempotently configure the root UCMP logging setup. Safe to call
    multiple times; only the first call takes effect.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger("ucmp")
    root.setLevel(level)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(handler)
    root.propagate = False

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a namespaced logger under the 'ucmp' root logger, e.g.
    'ucmp.orchestrator.orchestrator'.
    """
    configure_logging()
    if not name.startswith("ucmp"):
        name = f"ucmp.{name}"
    return logging.getLogger(name)
