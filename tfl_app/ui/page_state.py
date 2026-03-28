from __future__ import annotations

from typing import Any

from tfl_app.shared.session_state import ensure_state_defaults


NAV_STATE_DEFAULTS: dict[str, Any] = {
    "nav_search_query": "",
    "nav_search_last": "",
    "nav_search_trigger": False,
}

LOBBY_STATE_DEFAULTS: dict[str, Any] = {
    "scope": "This Session",
    "session": None,
    "lobbyshort": "",
    "lobby_filerid": None,
    "lobby_selected_key": "",
    "lobby_all_matches": False,
    "lobby_merge_keys": [],
    "lobby_candidate_map": {},
    "lobby_override_same": {},
    "lobby_override_diff": {},
    "lobby_match_query": "",
    "lobby_match_select": "No match",
    "search_query": "",
    "bill_search": "",
    "activity_search": "",
    "disclosure_search": "",
    "filter_lobbyshort": "",
    "recent_lobby_searches": [],
    "lobby_policy_focus": {},
}

CLIENT_STATE_DEFAULTS: dict[str, Any] = {
    "client_scope": "This Session",
    "client_session": None,
    "client_query": "",
    "client_name": "",
    "client_bill_search": "",
    "client_activity_search": "",
    "client_disclosure_search": "",
    "client_filter": "",
    "recent_client_searches": [],
    "client_policy_focus": {},
    "client_bill_search_seed": "",
}

MEMBER_STATE_DEFAULTS: dict[str, Any] = {
    "member_session": None,
    "member_query": "",
    "member_name": "",
    "member_bill_search": "",
    "member_witness_search": "",
    "member_activity_search": "",
    "member_filter": "",
    "recent_member_searches": [],
}


def map_state_defaults(default_basemap: str) -> dict[str, Any]:
    return {
        "map_scope": "This Session",
        "map_session": None,
        "map_basemap_label": default_basemap,
        "map_geocode_floor": 82,
        "map_probe_min_high": 0.0,
        "map_distance_cap_miles": 160,
        "map_subdivision_types_filter": [],
        "map_min_match_count": 1,
        "map_subdivision_map_cap": 550,
        "map_subdivision_name_filter": "",
        "map_subdivision_sort_v4": "Highest Signal",
        "map_subdivision_pick_v4": "",
        "map_selected_subdivision_context": {},
        "map_overlap_input_mode": "Street Address",
        "map_overlap_address_input": "",
        "map_overlap_address_query": "",
        "map_overlap_query_lat": None,
        "map_overlap_query_lon": None,
        "map_overlap_coord_lat": 31.0,
        "map_overlap_coord_lon": -99.0,
        "map_recent_addresses": [],
        "map_overlap_confidence_filter": [],
        "map_overlap_method_filter": [],
        "map_overlap_entity_filter": "",
        "map_overlap_focus_selected_subdivision": False,
        "map_overlap_focus_selected_clients": False,
        "map_overlap_sort_v4": "Signal Score",
        "map_forensics_show_charts": False,
        "map_watchlist": [],
        "map_batch_input_v4": "",
        "map_batch_max_v4": 8,
        "map_batch_results_v4": [],
        "map_queue_priority_filter_v4": [],
        "map_queue_search_v4": "",
        "map_queue_sort_v4": "Lead Score",
        "map_draw_addresses": [],
        "map_draw_last_click_lat": None,
        "map_draw_last_click_lon": None,
    }


def ensure_nav_state() -> None:
    ensure_state_defaults(NAV_STATE_DEFAULTS)


def ensure_lobby_state() -> None:
    ensure_state_defaults(LOBBY_STATE_DEFAULTS)


def ensure_client_state() -> None:
    ensure_state_defaults(CLIENT_STATE_DEFAULTS)


def ensure_member_state() -> None:
    ensure_state_defaults(MEMBER_STATE_DEFAULTS)


def ensure_map_state(default_basemap: str) -> dict[str, Any]:
    defaults = map_state_defaults(default_basemap)
    ensure_state_defaults(defaults)
    return defaults
