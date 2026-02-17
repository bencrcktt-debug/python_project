from pathlib import Path
from typing import Any, Dict

from .config import DEFAULT_TEMPLATE_DIR
from .narrative import NarrativeRenderer


def build_html_report(payload: Dict[str, Any], template_dir: Path | None = None) -> str:
    """
    Render an HTML report using the Jinja2 template in templates/report.html.
    Falls back to a minimal string if rendering fails.
    """
    templates = template_dir or DEFAULT_TEMPLATE_DIR
    renderer = NarrativeRenderer(templates)
    try:
        return renderer.render("report.html", {"payload": payload})
    except Exception:
        # Fallback keeps PDF generation alive even if templating breaks.
        return f"<html><body><pre>{payload}</pre></body></html>"
