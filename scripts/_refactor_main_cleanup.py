from __future__ import annotations

from pathlib import Path


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "tfl_app").exists())
MAIN_PATH = ROOT / "main.py"


HELPER_BLOCK = """
_PAGE_FRAGMENT_HELPER_KEYS = (
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
_MAP_FRAGMENT_HELPER_KEYS = (
    "MAP_BASEMAP_OPTIONS",
    "ThreadPoolExecutor",
    "_atlas_bridge",
    "_build_filtered_atlas_bundle",
    "_build_filtered_forensics_bundle",
    "_mp5_confidence_weight",
    "_mp5_geocode_badge",
    "_mp5_method_weight",
    "_mp5_miles",
    "_session_cached_value",
    "_stable_json_signature",
    "as_completed",
    "build_address_overlap_spending_rows",
    "build_overlap_map_points",
    "classify_requested_entity_type",
    "export_dataframe",
    "fmt_usd",
    "geocode_address_arcgis",
    "query_texas_subdivisions_for_point",
    "render_address_overlap_arcgis_map",
    "render_draw_area_search_map",
    "render_subdivision_map_legend",
    "render_tfl_subdivision_arcgis_map",
)
_CLIENT_WORKSPACE_CTX_KEYS = (
    "Bill_Status_All",
    "Bill_Sub_All",
    "Fiscal_Impact",
    "LaCvr",
    "LaDock",
    "LaI4E",
    "LaSub",
    "Lobby_Sub_All",
    "Lobby_TFL_Client_All",
    "Staff_All",
    "Wit_All",
    "all_clients",
    "all_stats",
    "client_scope_bundle",
    "data",
    "name_to_short",
    "tfl_session_val",
)
_MEMBER_WORKSPACE_CTX_KEYS = (
    "Lobby_TFL_Client_All",
    "Staff_All",
    "Wit_All",
    "all_leg_stats",
    "all_legislators",
    "author_bills_all",
    "data",
    "name_to_short",
    "short_to_names",
    "tfl_session_val",
)
_MAP_WORKSPACE_CTX_KEYS = (
    "_atlas_label",
    "_docket_label",
    "_forensics_label",
    "_open_client",
    "_render_cross_context_banner",
    "atlas_bundle",
    "subdivision_matches",
    "tfl_spend",
    "total_high",
)


def _build_fragment_ctx(keys: tuple[str, ...], values: dict[str, object]) -> dict[str, object]:
    return {key: values[key] for key in keys if key in values}


def _subset_globals(keys: tuple[str, ...]) -> dict[str, object]:
    scope = globals()
    return {key: scope[key] for key in keys if key in scope}


def _page_fragment_helpers() -> dict[str, object]:
    return _subset_globals(_PAGE_FRAGMENT_HELPER_KEYS)


def _map_fragment_helpers() -> dict[str, object]:
    return _subset_globals(_MAP_FRAGMENT_HELPER_KEYS)


_page_fragments.configure_page_fragment_helpers(**_page_fragment_helpers())
_map_fragments.configure_map_fragment_helpers(**_map_fragment_helpers())
"""


def remove_between(text: str, start: str, end: str) -> str:
    start_idx = text.index(start)
    end_idx = text.index(end, start_idx)
    return text[:start_idx] + start + "\n" + text[end_idx:]


def main() -> None:
    src = MAIN_PATH.read_text(encoding="utf-8")

    src = src.replace(
        '_page_fragments.configure_page_fragment_helpers(**globals())\n_map_fragments.configure_map_fragment_helpers(**globals())',
        HELPER_BLOCK.strip(),
    )

    src = src.replace(
        'st.session_state["_client_workspace_ctx"] = locals().copy()',
        'st.session_state["_client_workspace_ctx"] = _build_fragment_ctx(_CLIENT_WORKSPACE_CTX_KEYS, locals())',
    )
    src = src.replace(
        'st.session_state["_member_workspace_ctx"] = locals().copy()',
        'st.session_state["_member_workspace_ctx"] = _build_fragment_ctx(_MEMBER_WORKSPACE_CTX_KEYS, locals())',
    )
    src = src.replace(
        'st.session_state["_map_workspace_ctx"] = locals().copy()',
        'st.session_state["_map_workspace_ctx"] = _build_fragment_ctx(_MAP_WORKSPACE_CTX_KEYS, locals())',
    )

    client_return = '    _page_fragments.render_client_workspace_fragment("_client_workspace_ctx")\n    return'
    member_start = 'def _page_member_lookup():'
    src = remove_between(src, client_return, member_start)

    member_return = '    _page_fragments.render_member_workspace_fragment("_member_workspace_ctx")\n    return'
    map_start = 'def _mp5_miles'
    src = remove_between(src, member_return, map_start)

    map_return = '    _render_workspace_links(\n        "map_rebuild_next_v4",\n        [\n            ("Open Clients", _client_page, "Validate ranked entities at filing level."),\n            ("Open Lobbyists", _lobby_page, "Reconnect leads to statewide concentration."),\n            ("Open Legislators", _member_page, "Attach overlap to bill and witness activity."),\n        ],\n    )\n    return'
    map_rebuild_start = '@_safe_page("Map & Address Rebuild")'
    src = remove_between(src, map_return, map_rebuild_start)

    dead_lobby_marker = 'st.stop()\n\n# =========================================================\n# TABS\n# =========================================================\n'
    if dead_lobby_marker in src:
        src = src.split(dead_lobby_marker, 1)[0] + 'st.stop()\n'

    MAIN_PATH.write_text(src, encoding="utf-8")
    print("updated main.py")


if __name__ == "__main__":
    main()

