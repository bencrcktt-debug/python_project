import hashlib
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class FilterState:
    """Canonical set of global filters shared between UI and exports."""

    sessions: Tuple[str, ...] = ()
    scope: str = "default"
    lobbyist_match: Optional[str] = None
    client_match: Optional[str] = None
    taxpayer_only: bool = False
    entity_types: Tuple[str, ...] = ()
    policy_areas: Tuple[str, ...] = ()
    stances: Tuple[str, ...] = ()
    date_range: Optional[Tuple[str, str]] = None
    audience: str = "general"

    def cache_key(self) -> str:
        """Stable identifier for caching data derived from this filter set."""
        return hashlib.sha256(repr(self).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ReportContext:
    """
    Immutable description of a report run. This object should be passed
    through metrics, chart builders, narrative renderers, and the PDF layer
    so every artifact carries the same provenance.
    """

    report_type: str
    filters: FilterState
    preset: str = "custom"
    sections: Tuple[str, ...] = ()
    issued_at: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)

    def cache_key(self) -> str:
        stem = f"{self.report_type}|{self.filters.cache_key()}|{self.preset}|{self.sections}"
        return hashlib.sha256(stem.encode("utf-8")).hexdigest()[:16]
