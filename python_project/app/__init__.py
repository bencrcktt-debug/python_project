"""
Modular scaffolding for the TFL reporting application.

This package is the foundation for separating data access, metrics,
visuals and PDF generation into testable modules.
"""

from .config import (
    DEFAULT_DATA_FILENAME,
    DEFAULT_REPORT_DIR,
    ENV_DATA_PATH,
)
from .context import FilterState, ReportContext

__all__ = [
    "DEFAULT_DATA_FILENAME",
    "DEFAULT_REPORT_DIR",
    "ENV_DATA_PATH",
    "FilterState",
    "ReportContext",
]
