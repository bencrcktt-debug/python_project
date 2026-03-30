from __future__ import annotations

import re
from typing import Any

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _SessionStateStub(dict):
        pass

    class _StreamlitStub:
        session_state: dict[str, Any] = _SessionStateStub()

        def __getattr__(self, name: str):
            raise AttributeError(name)

    st = _StreamlitStub()


def reset_filters(default_session: str) -> None:
    st.session_state.search_query = ""
    st.session_state.lobbyshort = ""
    st.session_state.lobby_filerid = None
    st.session_state.lobby_selected_key = ""
    st.session_state.lobby_all_matches = False
    st.session_state.lobby_merge_keys = []
    st.session_state.lobby_candidate_map = {}
    st.session_state.lobby_match_query = ""
    st.session_state.lobby_match_select = "No match"
    st.session_state.bill_search = ""
    st.session_state.activity_search = ""
    st.session_state.disclosure_search = ""
    st.session_state.lobby_policy_focus = {}
    st.session_state.filter_lobbyshort = ""
    st.session_state.scope = "This Session"
    st.session_state.session = default_session


def _remember_recent_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_lobby_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_lobby_searches = deduped[:6]


def reset_client_filters(default_session: str) -> None:
    st.session_state.client_query = ""
    st.session_state.client_name = ""
    st.session_state.client_bill_search = ""
    st.session_state.client_bill_search_seed = ""
    st.session_state.client_activity_search = ""
    st.session_state.client_disclosure_search = ""
    st.session_state.client_policy_focus = {}
    st.session_state.client_filter = ""
    st.session_state.client_scope = "This Session"
    st.session_state.client_session = default_session
    st.session_state.client_scope_radio = "This Session"
    st.session_state.client_session_select = _session_label(default_session)
    st.session_state.client_suggestions_select = "Select a client..."
    st.session_state.client_query_input = ""
    st.session_state.client_bill_search_input = ""
    st.session_state.client_activity_search_input = ""
    st.session_state.client_disclosure_search_input = ""
    st.session_state.client_filter_input = ""


def reset_member_filters(default_session: str) -> None:
    st.session_state.member_query = ""
    st.session_state.member_name = ""
    st.session_state.member_bill_search = ""
    st.session_state.member_witness_search = ""
    st.session_state.member_activity_search = ""
    st.session_state.member_filter = ""
    st.session_state.member_session = default_session
    st.session_state.member_session_select = _session_label(default_session)
    st.session_state.member_suggestions_select = "Select a legislator..."
    st.session_state.member_query_input = ""
    st.session_state.member_bill_search_input = ""
    st.session_state.member_witness_search_input = ""
    st.session_state.member_activity_search_input = ""
    st.session_state.member_filter_input = ""


def _remember_recent_client_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_client_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_client_searches = deduped[:6]


def _remember_recent_member_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_member_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_member_searches = deduped[:6]


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _session_label(session_val: str) -> str:
    s = str(session_val).strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    if s.isdigit():
        if len(s) >= 3:
            base = s[:-1]
            special = s[-1]
            if base.isdigit() and special.isdigit():
                return f"{base}R / {_ordinal(int(special))} Special"
        return _ordinal(int(s))
    return s


def _session_long_label(session_val: str | None) -> str:
    s = str(session_val or "").strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    if s.isdigit() and len(s) >= 3:
        base = s[:-1]
        special = s[-1]
        if base.isdigit() and special.isdigit():
            return f"{_ordinal(int(base))} {_ordinal(int(special))} Special Session"
    m = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if m:
        return f"{_ordinal(int(m.group(1)))} Regular Session"
    if s.isdigit():
        return f"{_ordinal(int(s))} Regular Session"
    m = re.search(r"(\d+).*(\d+)(?:st|nd|rd|th)?\s*Special", s, flags=re.IGNORECASE)
    if m:
        return f"{_ordinal(int(m.group(1)))} {_ordinal(int(m.group(2)))} Special Session"
    return s


def _session_base_number_series(s: pd.Series) -> pd.Series:
    base = s.fillna("").astype(str).str.strip().str.extract(r"^(\d+)", expand=False)
    base = base.where(base.str.len() <= 2, base.str[:-1])
    return pd.to_numeric(base, errors="coerce")


def _session_range_label(series: pd.Series) -> str:
    if series is None or series.empty:
        return "All Sessions"
    base_nums = _session_base_number_series(series)
    base_nums = base_nums.dropna().astype(int)
    if base_nums.empty:
        return "All Sessions"
    min_base = int(base_nums.min())
    max_base = int(base_nums.max())
    if min_base == max_base:
        return f"{_ordinal(min_base)} Regular Session"
    return f"{_ordinal(min_base)} to {_ordinal(max_base)} Sessions"


def _session_sort_key(session_val: str) -> tuple[int, int, int]:
    s = str(session_val).strip()
    if not s:
        return (0, 2, 0)
    if s.isdigit():
        base = int(s[:-1]) if len(s) >= 2 else int(s)
        special = int(s[-1]) if len(s) >= 2 else 0
        return (base, 1, special)
    m = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if m:
        return (int(m.group(1)), 0, 0)
    return (0, 2, 0)


def _default_session_from_list(sessions: list[str]) -> str:
    if not sessions:
        return ""
    if "89R" in sessions:
        return "89R"
    regular = [s for s in sessions if str(s).strip().upper().endswith("R") and str(s).strip()[:-1].isdigit()]
    if regular:
        return sorted(regular, key=_session_sort_key)[-1]
    return sorted(sessions, key=_session_sort_key)[-1]


def _session_base_label(base_val: float | int) -> str:
    if pd.isna(base_val):
        return ""
    return _ordinal(int(base_val))


__all__ = [
    "_default_session_from_list",
    "_ordinal",
    "_remember_recent_client_search",
    "_remember_recent_member_search",
    "_remember_recent_search",
    "_session_base_label",
    "_session_base_number_series",
    "_session_label",
    "_session_long_label",
    "_session_range_label",
    "_session_sort_key",
    "reset_client_filters",
    "reset_filters",
    "reset_member_filters",
]
