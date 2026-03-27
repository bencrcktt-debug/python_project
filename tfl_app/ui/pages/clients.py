from __future__ import annotations

import html
from typing import Any

import pandas as pd
from tfl_app.services import AppServices

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _StreamlitStub:
        session_state: dict[str, Any] = {}

    st = _StreamlitStub()

def render_page(*, services: AppServices, ctx: dict[str, Any] | None = None) -> None:
    del ctx
    PATH = services.require("PATH")
    _default_session_from_list = services.require("_default_session_from_list")
    _lobby_page = services.require("_lobby_page")
    _map_page = services.require("_map_page")
    _member_page = services.require("_member_page")
    _page_fragments = services.require("_page_fragments")
    _remember_recent_client_search = services.require("_remember_recent_client_search")
    _render_evidence_guardrails = services.require("_render_evidence_guardrails")
    _render_journey = services.require("_render_journey")
    _render_page_intro = services.require("_render_page_intro")
    _render_pdf_report_section = services.require("_render_pdf_report_section")
    _render_quickstart = services.require("_render_quickstart")
    _render_workspace_guide = services.require("_render_workspace_guide")
    _render_workspace_links = services.require("_render_workspace_links")
    _session_label = services.require("_session_label")
    _tfl_session_for_filter = services.require("_tfl_session_for_filter")
    data_health_table = services.require("data_health_table")
    get_app_tables = services.require("get_app_tables")
    get_app_tables_readonly = services.require("get_app_tables_readonly")
    get_table_manifest = services.require("get_table_manifest")
    get_client_scope_bundle = services.require("get_client_scope_bundle")
    require_app_state = services.require("require_app_state")
    reset_client_filters = services.require("reset_client_filters")
    resolve_client_name = services.require("resolve_client_name")

    if True:
        _render_page_intro(
        kicker="Client Workspace",
        title="Client Evidence View",
        subtitle=(
            "Trace each entity across contracted lobbyists, compensation ranges, bill activity, subject filings, and disclosures."
        ),
        pills=[
            "Search and confirm the exact entity",
            "Compare session vs all-session scope",
            "Export reproducible evidence tables",
        ],
    )
    _render_journey("client")
    _render_workspace_guide(
        question=(
            "For this entity, what lobbying footprint is reported and how does it connect to bills, policy subjects, and disclosures?"
        ),
        steps=[
            "Search and confirm the resolved entity name.",
            "Read Portfolio Snapshot before moving to detail tabs.",
            "Use Bill Activity and Policy Subjects together for legislative context.",
            "Export filtered tables when documenting findings.",
        ],
        method_note="Entity naming varies across filings. Confirm resolved matches before citing profile-level totals.",
    )
    _render_workspace_links(
        "client_top",
        [
            ("Open Lobbyists", _lobby_page, "Return to statewide baseline before entity comparisons."),
            ("Open Map & Address", _map_page, "Test local overlap for matched entities and jurisdictions."),
            ("Open Legislators", _member_page, "Connect entity exposure to authored bills and witnesses."),
        ],
    )
    _render_quickstart(
        "clients",
        [
            "Confirm the resolved entity name before interpreting totals.",
            "Check snapshot and detail tabs for consistency across metrics.",
            "Export with active filters when sharing externally.",
        ],
        note="Similar entity names can map differently by session and source format.",
    )
    _render_evidence_guardrails(
        can_answer=[
            "Which lobbyists are reported under contract for the selected entity.",
            "How reported compensation ranges, bill activity, and disclosures align by session.",
            "Whether the selected entity appears as taxpayer-funded in source records.",
        ],
        cannot_answer=[
            "Exact payment amounts beyond reported low/high ranges.",
            "Policy intent or institutional motive from filing data alone.",
        ],
        next_checks=[
            "Confirm entity resolution before citing totals.",
            "Use Lobbyists or Map & Address to validate context outside this profile.",
        ],
    )

    app_state = require_app_state(
        PATH,
        missing_path_message="Data path not configured. Set the DATA_PATH environment variable.",
        missing_file_message="Data path not found. Set DATA_PATH or place the parquet file in ./data.",
    )
    name_to_short = app_state.name_to_short
    short_to_names = app_state.short_to_names
    filerid_to_short = app_state.filerid_to_short
    tfl_sessions = set(app_state.tfl_sessions)

    if "client_scope" not in st.session_state:
        st.session_state.client_scope = "This Session"
    if "client_session" not in st.session_state:
        st.session_state.client_session = None
    if "client_query" not in st.session_state:
        st.session_state.client_query = ""
    if "client_name" not in st.session_state:
        st.session_state.client_name = ""
    if "client_bill_search" not in st.session_state:
        st.session_state.client_bill_search = ""
    if "client_activity_search" not in st.session_state:
        st.session_state.client_activity_search = ""
    if "client_disclosure_search" not in st.session_state:
        st.session_state.client_disclosure_search = ""
    if "client_filter" not in st.session_state:
        st.session_state.client_filter = ""
    if "recent_client_searches" not in st.session_state:
        st.session_state.recent_client_searches = []
    if "client_policy_focus" not in st.session_state:
        st.session_state.client_policy_focus = {}
    if "client_bill_search_seed" not in st.session_state:
        st.session_state.client_bill_search_seed = ""

    if "client_query_input" not in st.session_state:
        st.session_state.client_query_input = st.session_state.client_query
    if "client_bill_search_input" not in st.session_state:
        st.session_state.client_bill_search_input = st.session_state.client_bill_search
    if "client_activity_search_input" not in st.session_state:
        st.session_state.client_activity_search_input = st.session_state.client_activity_search
    if "client_disclosure_search_input" not in st.session_state:
        st.session_state.client_disclosure_search_input = st.session_state.client_disclosure_search
    if "client_filter_input" not in st.session_state:
        st.session_state.client_filter_input = st.session_state.client_filter

    pending_client_bill_search = str(st.session_state.get("client_bill_search_seed", "")).strip()
    if pending_client_bill_search:
        st.session_state.client_bill_search = pending_client_bill_search
        st.session_state.client_bill_search_input = pending_client_bill_search
        st.session_state.client_bill_search_seed = ""

    st.sidebar.header("Filters")
    st.session_state.client_scope = st.sidebar.radio(
        "Overview scope",
        ["This Session", "All Sessions"],
        index=0,
        key="client_scope_radio",
        help="Switch between the selected session only or totals across all sessions.",
    )

    sessions = list(app_state.shared_sessions)
    if not sessions:
        st.error("No sessions found in the workbook.")
        st.stop()

    with st.sidebar.expander("Data health", expanded=False):
        st.caption(f"Data path: {PATH}")
        health = data_health_table(str(PATH))
        st.dataframe(health, width="stretch", height=260, hide_index=True)

    st.markdown('<div id="filter-bar-marker"></div>', unsafe_allow_html=True)
    top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

    with top1:
        st.session_state.client_query = st.text_input(
            "Search client",
            placeholder="e.g., City of Austin",
            key="client_query_input",
            help="Search by client name. Suggestions appear when close matches exist.",
        )

    with top2:
        label_to_session = {}
        session_labels = []
        for s in sessions:
            lab = _session_label(s)
            session_labels.append(lab)
            label_to_session[lab] = s

        default_session = app_state.default_shared_session or _default_session_from_list(sessions)
        default_label = _session_label(default_session)

        if st.session_state.client_session is None or str(st.session_state.client_session).strip().lower() in {"none", "nan", "null", ""}:
            st.session_state.client_session = default_session

        current_label = _session_label(st.session_state.client_session)
        if current_label not in session_labels:
            current_label = default_label if default_label in session_labels else session_labels[0]

        chosen_label = st.selectbox(
            "Session",
            session_labels,
            index=session_labels.index(current_label),
            key="client_session_select",
            help="Choose the legislative session used for filters and totals.",
        )
        st.session_state.client_session = label_to_session.get(chosen_label, default_session)

    client_index = app_state.client_index
    resolved_client, client_suggestions = resolve_client_name(
        st.session_state.client_query,
        client_index,
    )

    if client_suggestions:
        pick = st.selectbox(
            "Suggestions",
            ["Select a client..."] + client_suggestions,
            index=0,
            key="client_suggestions_select",
            help="Pick a suggested client to populate the selection.",
        )
        if pick in client_suggestions:
            resolved_client = pick

    st.session_state.client_name = resolved_client or ""
    if st.session_state.client_name:
        _remember_recent_client_search(st.session_state.client_name)

    with top3:
        st.markdown('<div class="small-muted">Client</div>', unsafe_allow_html=True)
        if st.session_state.client_name:
            st.write(st.session_state.client_name)
        else:
            st.write("-")

    def _reuse_recent_client_search(value: str) -> None:
        rec = str(value).strip()
        if not rec:
            return
        st.session_state.client_query = rec
        st.session_state.client_query_input = rec
        st.session_state.client_name = ""
        st.session_state.client_suggestions_select = "Select a client..."
        st.session_state.client_bill_search = ""
        st.session_state.client_bill_search_input = ""
        st.session_state.client_bill_search_seed = ""
        st.session_state.client_activity_search = ""
        st.session_state.client_activity_search_input = ""
        st.session_state.client_disclosure_search = ""
        st.session_state.client_disclosure_search_input = ""
        st.session_state.client_policy_focus = {}
        st.session_state.client_filter = ""
        st.session_state.client_filter_input = ""

    recent = st.session_state.get("recent_client_searches", [])
    if recent:
        st.markdown('<div class="section-sub">Recent lookups</div>', unsafe_allow_html=True)
        recent_cols = st.columns(min(len(recent), 4))
        for idx, rec in enumerate(recent[:8]):
            col = recent_cols[idx % len(recent_cols)]
            label = rec if len(rec) <= 28 else rec[:25] + "..."
            col.button(
                f"Reuse {label}",
                key=f"recent_client_lookup_{idx}",
                help="Reuse a recent client search",
                width="stretch",
                on_click=_reuse_recent_client_search,
                args=(rec,),
            )

    tfl_session_val = _tfl_session_for_filter(st.session_state.client_session, tfl_sessions)

    active_parts = [
        f"Session: {_session_label(st.session_state.client_session)}",
        f"Scope: {st.session_state.client_scope}",
    ]
    if st.session_state.client_name:
        active_parts.append(f"Client: {st.session_state.client_name}")
    chips_html = "".join([f'<span class="chip">{html.escape(c)}</span>' for c in active_parts])
    st.markdown('<div id="filter-summary-marker"></div>', unsafe_allow_html=True)
    f1, f2 = st.columns([3, 1])
    with f1:
        st.markdown(
            f'<div class="filter-summary"><span class="filter-summary-label">Active filters</span>{chips_html}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Selected client: {st.session_state.client_name or '-'}")
    with f2:
        st.button(
            "Clear filters",
            width="stretch",
            help="Reset client search and primary filters to defaults.",
            on_click=reset_client_filters,
            args=(default_session,),
        )
    st.markdown(
        '<div class="app-note"><strong>Interpretation:</strong> Client totals reflect reported low-high compensation ranges, not audited exact spend. Keep session and scope aligned when comparing entities.</div>',
        unsafe_allow_html=True,
    )

    focus_label = "All Clients"
    if st.session_state.client_name:
        focus_label = f"Client: {st.session_state.client_name}"

    def _load_client_report_tables() -> dict[str, pd.DataFrame]:
        return get_app_tables_readonly(
            str(PATH),
            (
                "Lobby_TFL_Client_All",
                "Wit_All",
                "Bill_Status_All",
                "Lobby_Sub_All",
                "Staff_All",
                "Bill_Sub_All",
                "LaFood",
                "LaEnt",
                "LaTran",
                "LaGift",
                "LaEvnt",
                "LaAwrd",
                "LaCvr",
                "LaDock",
                "LaI4E",
                "LaSub",
            ),
        )

    focus_context = {
        "type": "client" if st.session_state.client_name else "",
        "name": st.session_state.client_name,
        "report_title": "Client Report",
        "lookups": {
            "name_to_short": name_to_short,
            "short_to_names": short_to_names,
            "filerid_to_short": filerid_to_short,
        },
    }
    _ = _render_pdf_report_section(
        key_prefix="client",
        session_val=st.session_state.client_session,
        scope_label=st.session_state.client_scope,
        focus_label=focus_label,
        tfl_session_val=tfl_session_val,
        report_table_loader=_load_client_report_tables,
        focus_context=focus_context,
    )
    _page_fragments.merge_fragment_session_context("_client_workspace_ctx", {
        "PATH": str(PATH),
        "client_scope": st.session_state.client_scope,
        "client_session": st.session_state.client_session,
        "client_name": st.session_state.client_name,
        "tfl_session_val": tfl_session_val,
    })
    _page_fragments.render_client_workspace_fragment("_client_workspace_ctx")
    return
