from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from .context import ReportContext


def _build_env(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


class NarrativeRenderer:
    """
    Thin wrapper around Jinja2 so narrative and PDF layers can share templates.
    If a template is missing, render a minimal fallback string with the context.
    """

    def __init__(self, template_dir: Path):
        self.template_dir = template_dir
        self.env = _build_env(template_dir)

    def render(self, template_name: str, payload: Dict[str, Any]) -> str:
        try:
            template = self.env.get_template(template_name)
            return template.render(**payload)
        except TemplateNotFound:
            return f"[Missing template: {template_name}] {payload}"

    def exec_summary(self, ctx: ReportContext, metrics: Dict[str, Any]) -> str:
        payload = {"ctx": ctx, "metrics": metrics}
        return self.render("exec_summary.html", payload)

    def case_for_reform(self, ctx: ReportContext, findings: Dict[str, Any]) -> str:
        payload = {"ctx": ctx, "findings": findings}
        return self.render("case_for_reform.html", payload)

    def methodology(self, ctx: ReportContext, notes: Optional[Dict[str, Any]] = None) -> str:
        payload = {"ctx": ctx, "notes": notes or {}}
        return self.render("methodology.html", payload)
