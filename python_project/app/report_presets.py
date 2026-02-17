from dataclasses import dataclass
from typing import Dict, Tuple

from .context import FilterState, ReportContext


@dataclass(frozen=True)
class ReportPreset:
    label: str
    sections: Tuple[str, ...]
    audience: str = "general"


REPORT_PRESETS: Dict[str, ReportPreset] = {
    "lobbyist": ReportPreset(
        label="Individual Lobbyist",
        sections=(
            "exec_summary",
            "kpis",
            "compensation",
            "witness",
            "policy_areas",
            "activities",
            "disclosures",
            "network",
            "methodology",
        ),
        audience="legislator",
    ),
    "client": ReportPreset(
        label="Client Portfolio",
        sections=("exec_summary", "kpis", "compensation", "policy_areas", "network", "methodology"),
        audience="budget_analyst",
    ),
    "session": ReportPreset(
        label="Session Brief",
        sections=("exec_summary", "kpis", "policy_areas", "top_bills", "activities", "methodology"),
        audience="journalist",
    ),
    "aggregate": ReportPreset(
        label="All Lobbyists Aggregate",
        sections=("exec_summary", "kpis", "compensation", "policy_areas", "network", "methodology"),
        audience="watchdog",
    ),
}


def build_context(report_type: str, filters: FilterState) -> ReportContext:
    preset = REPORT_PRESETS.get(report_type)
    if not preset:
        return ReportContext(report_type=report_type, filters=filters, preset="custom", sections=())
    return ReportContext(
        report_type=report_type,
        filters=filters,
        preset=report_type,
        sections=preset.sections,
        extra={"label": preset.label, "audience": preset.audience},
    )
