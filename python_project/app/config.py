from pathlib import Path

# Defaults for locating the parquet bundle and generated artifacts.
DEFAULT_DATA_FILENAME = "TFL Webstite books - combined.parquet"
ENV_DATA_PATH = "DATA_PATH"

# Output locations for PDFs and HTML templates.
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# Shared Plotly defaults so charts look consistent across app and PDF.
PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
        "autoScale2d",
        "resetScale2d",
        "toImage",
    ],
}
