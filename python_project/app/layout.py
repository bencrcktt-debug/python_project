from typing import Dict, Iterable, Tuple

import streamlit as st

from .context import FilterState


def render_filter_bar(options: Dict[str, Iterable[str]]) -> FilterState:
    """
    Shared filter bar used by the explore view and the report builder.
    Keeps control labels consistent and returns a FilterState.
    """
    sessions = st.multiselect("Session", options.get("sessions", ()))
    scope = st.selectbox("Scope", options.get("scopes", ("default",)), index=0)
    lobbyist_match = st.text_input("Lobbyist (fuzzy)")
    client_match = st.text_input("Client / Agency (fuzzy)")
    taxpayer_only = st.toggle("Taxpayer-funded only", value=False)
    entity_types = st.multiselect("Entity type", options.get("entity_types", ()))
    policy_areas = st.multiselect("Policy areas", options.get("policy_areas", ()))
    stances = st.multiselect("Witness stance", options.get("stances", ()))

    # Date range uses strings for compatibility with duckdb until schema is locked.
    date_range: Tuple[str, str] | None = None
    if options.get("date_range"):
        date_range = st.date_input("Date range", options.get("date_range"))
        if isinstance(date_range, tuple) and len(date_range) == 2:
            date_range = (str(date_range[0]), str(date_range[1]))

    return FilterState(
        sessions=tuple(sessions),
        scope=scope,
        lobbyist_match=lobbyist_match or None,
        client_match=client_match or None,
        taxpayer_only=taxpayer_only,
        entity_types=tuple(entity_types),
        policy_areas=tuple(policy_areas),
        stances=tuple(stances),
        date_range=date_range,
    )
