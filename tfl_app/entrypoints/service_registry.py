from __future__ import annotations

from tfl_app.services import AppServices, MapServices, WorkspaceServices
from tfl_app.ui.fragments.bound import BoundMapFragments, BoundPageFragments


PAGE_FRAGMENT_HELPER_KEYS = (
    "CHART_COLORS",
    "FUNDING_COLOR_MAP",
    "OPPOSITION_COLOR_MAP",
    "PLOTLY_CONFIG",
    "TEA_ARCGIS_WEBAPP_URL",
    "TREND_COLOR_MAP",
    "_apply_plotly_layout",
    "_clean_options",
    "_client_page",
    "_last_first_initial_key",
    "_lobby_page",
    "_map_page",
    "_member_page",
    "_session_base_label",
    "_session_label",
    "_shorten_text",
    "_solutions_page",
    "bill_position_from_flags",
    "build_activities",
    "build_activities_multi",
    "build_bills_with_status",
    "build_disclosures",
    "build_disclosures_multi",
    "build_lobby_subject_counts",
    "build_lobbyist_trend",
    "build_member_activities",
    "build_policy_mentions",
    "build_timeline_counts",
    "build_top_clients",
    "ensure_cols",
    "export_dataframe",
    "first_name_norm_series",
    "fmt_usd",
    "get_app_state",
    "get_app_table",
    "get_app_tables",
    "get_client_scope_bundle",
    "get_client_workspace_detail_bundle",
    "get_lobby_scope_bundle",
    "get_lobby_workspace_detail_bundle",
    "get_member_session_bundle",
    "get_member_workspace_detail_bundle",
    "last_name_norm_from_text",
    "last_name_norm_series",
    "norm_name",
    "norm_name_series",
    "norm_person_variants",
    "norm_person_variants_with_nicknames",
    "parse_member_name",
    "parse_person_name",
    "render_pill_list",
    "require_columns",
)

MAP_FRAGMENT_HELPER_KEYS = (
    "MAP_BASEMAP_OPTIONS",
    "PATH",
    "_atlas_bridge",
    "_map_runtime",
    "_mp5_confidence_weight",
    "_mp5_geocode_badge",
    "_mp5_method_weight",
    "_mp5_miles",
    "_tfl_session_for_filter",
    "build_address_overlap_spending_rows",
    "build_overlap_map_points",
    "classify_requested_entity_type",
    "export_dataframe",
    "fmt_usd",
    "geocode_address_arcgis",
    "get_map_atlas_bundle",
    "get_map_forensics_bundle",
    "get_map_state",
    "query_texas_subdivisions_for_point",
    "render_address_overlap_arcgis_map",
    "render_draw_area_search_map",
    "render_subdivision_map_legend",
    "render_tfl_subdivision_arcgis_map",
)

def _copy_if_present(registry: dict[str, object], values: dict[str, object], key: str) -> None:
    if key in registry:
        values[key] = registry[key]


def build_workspace_service_values(registry: dict[str, object]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key in PAGE_FRAGMENT_HELPER_KEYS:
        _copy_if_present(registry, values, key)
    return values


def build_map_service_values(registry: dict[str, object]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key in MAP_FRAGMENT_HELPER_KEYS:
        _copy_if_present(registry, values, key)
    return values


def build_workspace_services(registry: dict[str, object]) -> WorkspaceServices:
    return WorkspaceServices.build(**build_workspace_service_values(registry))


def build_map_services(registry: dict[str, object]) -> MapServices:
    return MapServices.build(**build_map_service_values(registry))


def build_app_service_values(
    registry: dict[str, object],
    workspace_services: WorkspaceServices,
    map_services: MapServices,
) -> dict[str, object]:
    app_values = dict(registry)
    app_values.update(
        {
            "_page_fragments": BoundPageFragments(workspace_services),
            "_map_fragments": BoundMapFragments(map_services),
        }
    )
    return app_values


def build_app_services(
    registry: dict[str, object],
    workspace_services: WorkspaceServices,
    map_services: MapServices,
) -> AppServices:
    return AppServices.build(**build_app_service_values(registry, workspace_services, map_services))


def build_services(registry: dict[str, object]) -> tuple[WorkspaceServices, MapServices, AppServices]:
    workspace_services = build_workspace_services(registry)
    map_services = build_map_services(registry)
    return workspace_services, map_services, build_app_services(registry, workspace_services, map_services)
