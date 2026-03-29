from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from tfl_app.search.models import NavQueryKey, NavSearchBundle
from tfl_app.search.resolve import can_reuse_nav_search_bundle


_NAV_SEARCH_BUNDLE_KEY = "_nav_search_bundle_v1"
_NAV_SEARCH_QUERY_KEY = "_nav_search_bundle_query_v1"


def remember_nav_search_bundle(bundle: NavSearchBundle) -> None:
    st.session_state[_NAV_SEARCH_BUNDLE_KEY] = bundle
    st.session_state[_NAV_SEARCH_QUERY_KEY] = bundle.normalized_query


def cached_nav_search_bundle(query: str) -> NavSearchBundle | None:
    bundle = st.session_state.get(_NAV_SEARCH_BUNDLE_KEY)
    if can_reuse_nav_search_bundle(query, bundle):
        return bundle
    return None


def prefetch_nav_search_bundle(
    query: str,
    *,
    path: str,
    path_available: bool,
    build_cached: Callable[[NavQueryKey, object], NavSearchBundle],
    get_app_state: Callable[[str], object],
) -> NavSearchBundle | None:
    if not (query and len(query) >= 2 and path and path_available):
        return None
    bundle = build_cached(NavQueryKey(query), get_app_state(path))
    remember_nav_search_bundle(bundle)
    return bundle


def render_nav_suggestions(
    nav_bundle: NavSearchBundle | None,
    nav_suggest_slot: object,
    *,
    active_page: object,
    client_page: object,
    member_page: object,
    lobby_page: object,
    same_page: Callable[[object, object], bool],
) -> bool:
    nav_suggestions = list(nav_bundle.nav_suggestions) if nav_bundle else []
    nav_suggestion_map = dict(nav_bundle.nav_suggestion_map) if nav_bundle else {}
    nav_skip_submit = False

    if nav_suggestions:
        nav_pick = nav_suggest_slot.selectbox(
            "Nav suggestions",
            ["Select a match..."] + nav_suggestions,
            index=0,
            key="nav_suggestions_select",
            label_visibility="collapsed",
        )
        if nav_pick in nav_suggestion_map:
            nav_skip_submit = True
            target, value = nav_suggestion_map[nav_pick]
            nav_value = value if isinstance(value, str) else (value.get("name", "") or value.get("lobbyshort", ""))
            st.session_state.nav_search_query = nav_value
            st.session_state.nav_search_last = nav_value
            if target == "client":
                st.session_state.client_query = value
                st.session_state.client_query_input = value
                if not same_page(active_page, client_page):
                    st.switch_page(client_page)
                    st.stop()
            elif target == "member":
                st.session_state.member_query = value
                st.session_state.member_query_input = value
                if not same_page(active_page, member_page):
                    st.switch_page(member_page)
                    st.stop()
            else:
                sel = value if isinstance(value, dict) else {"lobbyshort": value, "name": value, "label": value, "filerid": None}
                sel_name = sel.get("name", "") or sel.get("lobbyshort", "")
                st.session_state.search_query = sel_name
                st.session_state.lobby_match_query = sel_name
                if sel.get("label"):
                    st.session_state.lobby_match_select = sel.get("label")
                if sel.get("filerid") is not None:
                    try:
                        st.session_state.lobby_filerid = int(sel.get("filerid"))
                    except Exception:
                        st.session_state.lobby_filerid = sel.get("filerid")
                if sel.get("lobbyshort"):
                    st.session_state.lobbyshort = sel.get("lobbyshort")
                if not same_page(active_page, lobby_page):
                    st.switch_page(lobby_page)
                    st.stop()
    else:
        nav_suggest_slot.empty()

    return nav_skip_submit


def handle_nav_search_submission(
    *,
    nav_query: str,
    nav_search_submitted: bool,
    nav_skip_submit: bool,
    active_page: object,
    client_page: object,
    member_page: object,
    lobby_page: object,
    same_page: Callable[[object, object], bool],
    path: str,
    build_cached: Callable[[NavQueryKey, object], NavSearchBundle],
    require_app_state: Callable[..., object],
) -> None:
    if not nav_search_submitted or nav_skip_submit or not nav_query:
        return

    nav_bundle = cached_nav_search_bundle(nav_query)
    if nav_bundle is None:
        nav_bundle = build_cached(
            NavQueryKey(nav_query),
            require_app_state(
                path,
                missing_path_message="Data path not configured. Set the DATA_PATH environment variable.",
                missing_file_message="Data path not found. Set DATA_PATH or place the parquet file in ./data.",
            ),
        )
        remember_nav_search_bundle(nav_bundle)

    if nav_bundle.bill_query:
        st.session_state.search_query = nav_bundle.bill_query
        st.session_state.lobbyshort = ""
        if not same_page(active_page, lobby_page):
            st.switch_page(lobby_page)
            st.stop()
        return

    resolved_client = nav_bundle.resolved_client
    client_suggestions = list(nav_bundle.client_suggestions)
    resolved_member = nav_bundle.resolved_member
    member_suggestions = list(nav_bundle.member_suggestions)
    lobby_candidates = list(nav_bundle.lobby_candidates)
    resolved_lobby = nav_bundle.resolved_lobby
    resolved_lobby_filer = nav_bundle.resolved_lobby_filer
    resolved_lobby_name = nav_bundle.resolved_lobby_name
    lobby_suggestions = list(nav_bundle.lobby_suggestions)

    target_page = lobby_page
    if resolved_client:
        target_page = client_page
        st.session_state.client_query = resolved_client
        st.session_state.client_query_input = resolved_client
    elif resolved_member:
        target_page = member_page
        st.session_state.member_query = resolved_member
        st.session_state.member_query_input = resolved_member
    elif resolved_lobby:
        target_page = lobby_page
        st.session_state.search_query = resolved_lobby_name or nav_query
        if resolved_lobby_filer is not None:
            st.session_state.lobby_filerid = resolved_lobby_filer
        if lobby_candidates:
            st.session_state.lobby_match_query = st.session_state.search_query
            st.session_state.lobby_match_select = lobby_candidates[0].get("label", "")
    else:
        if "," in nav_query and member_suggestions:
            target_page = member_page
        elif client_suggestions and not member_suggestions:
            target_page = client_page
        elif member_suggestions and not client_suggestions:
            target_page = member_page
        elif client_suggestions:
            target_page = client_page
        elif member_suggestions:
            target_page = member_page
        elif lobby_suggestions:
            target_page = lobby_page

        if target_page == client_page:
            st.session_state.client_query = nav_query
            st.session_state.client_query_input = nav_query
        elif target_page == member_page:
            st.session_state.member_query = nav_query
            st.session_state.member_query_input = nav_query
        else:
            st.session_state.search_query = nav_query

    if not same_page(target_page, active_page):
        st.switch_page(target_page)
        st.stop()
