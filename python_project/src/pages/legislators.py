from __future__ import annotations

from typing import Any

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _StreamlitStub:
        session_state: dict[str, Any] = {}

    st = _StreamlitStub()

from ._runtime import configure_helpers as _configure_helpers
from ._runtime import pop_context as _pop_context
from ._runtime import push_context as _push_context

HELPER_KEYS = (
    'PATH',
    '_MEMBER_WORKSPACE_CTX_KEYS',
    '_client_page',
    '_default_session_from_list',
    '_lobby_page',
    '_page_fragments',
    '_remember_recent_member_search',
    '_render_evidence_guardrails',
    '_render_journey',
    '_render_page_intro',
    '_render_pdf_report_section',
    '_render_quickstart',
    '_render_workspace_guide',
    '_render_workspace_links',
    '_session_label',
    '_solutions_page',
    '_tfl_session_for_filter',
    'data_health_table',
    'get_app_tables',
    'get_member_session_bundle',
    'html',
    'pd',
    'require_app_state',
    'reset_member_filters',
    'resolve_member_name',
)


def configure_helpers(**helpers: Any) -> None:
    _configure_helpers(globals(), **helpers)


def render_page(ctx: dict[str, Any] | None = None) -> None:
    _ctx = ctx or {}
    _previous = _push_context(globals(), _ctx)
    try:
        _render_page_intro(
            kicker="Legislator Workspace",
            title="Legislator Evidence View",
            subtitle=(
                "Review authored bills, witness activity, lobbying links, and staff-to-lobbyist history for a selected session."
            ),
            pills=[
                "Bill authorship",
                "Witness activity",
                "Staff transition context",
            ],
        )
        _render_journey("member")
        _render_workspace_guide(
            question=(
                "For this legislator, what bill activity drew lobbying attention and what staffing links appear in the records?"
            ),
            steps=[
                "Search and confirm the resolved legislator name.",
                "Read Session Snapshot before member-specific tabs.",
                "Review Bills and Witness Activity together to avoid partial interpretation.",
                "Treat Staff Connections as contextual linkage, not proof of intent.",
            ],
            method_note="Witness and staff records come from separate sources and should be interpreted as linkage context.",
        )
        _render_workspace_links(
            "member_top",
            [
                ("Open Lobbyists", _lobby_page, "Return to statewide lobbyist context and totals."),
                ("Open Clients", _client_page, "Inspect entity-side funding and disclosures."),
                ("Open Policy Context", _solutions_page, "Review drafting framework tied to observed patterns."),
            ],
        )
        _render_quickstart(
            "members",
            [
                "Select legislator and confirm session before reading trends.",
                "Review Bills and Witness Activity together to avoid one-sided interpretation.",
                "Use Staff Connections as context and corroborate with additional records.",
            ],
            note="Witness and staff tables describe linkage, not intent.",
        )
        _render_evidence_guardrails(
            can_answer=[
                "How authored bills, witness activity, and activity filings align for the selected legislator.",
                "Which lobbyists and staff-link records appear in the same session context.",
            ],
            cannot_answer=[
                "Personal motive or direction from correlated filing activity.",
                "Causality between witness activity and bill outcomes without external evidence.",
            ],
            next_checks=[
                "Cross-check major findings in Lobbyists and Clients views.",
                "Separate descriptive linkage from causal interpretation in published claims.",
            ],
        )

        app_state = require_app_state(
            PATH,
            missing_path_message="Data path not configured. Set the DATA_PATH environment variable.",
            missing_file_message="Data path not found. Set DATA_PATH or place the parquet file in ./data.",
        )
        data = app_state.data

        Wit_All = data["Wit_All"]
        Bill_Status_All = data["Bill_Status_All"]
        Lobby_TFL_Client_All = data["Lobby_TFL_Client_All"]
        name_to_short = app_state.name_to_short
        short_to_names = app_state.short_to_names
        filerid_to_short = app_state.filerid_to_short
        tfl_sessions = set(app_state.tfl_sessions)

        if "member_session" not in st.session_state:
            st.session_state.member_session = None
        if "member_query" not in st.session_state:
            st.session_state.member_query = ""
        if "member_name" not in st.session_state:
            st.session_state.member_name = ""
        if "member_bill_search" not in st.session_state:
            st.session_state.member_bill_search = ""
        if "member_witness_search" not in st.session_state:
            st.session_state.member_witness_search = ""
        if "member_activity_search" not in st.session_state:
            st.session_state.member_activity_search = ""
        if "member_filter" not in st.session_state:
            st.session_state.member_filter = ""
        if "recent_member_searches" not in st.session_state:
            st.session_state.recent_member_searches = []

        if "member_query_input" not in st.session_state:
            st.session_state.member_query_input = st.session_state.member_query
        if "member_bill_search_input" not in st.session_state:
            st.session_state.member_bill_search_input = st.session_state.member_bill_search
        if "member_witness_search_input" not in st.session_state:
            st.session_state.member_witness_search_input = st.session_state.member_witness_search
        if "member_activity_search_input" not in st.session_state:
            st.session_state.member_activity_search_input = st.session_state.member_activity_search
        if "member_filter_input" not in st.session_state:
            st.session_state.member_filter_input = st.session_state.member_filter

        st.sidebar.header("Filters")

        sessions = list(app_state.shared_sessions)
        if not sessions:
            st.error("No sessions found in the workbook.")
            st.stop()

        with st.sidebar.expander("Data health", expanded=False):
            st.caption(f"Data path: {PATH}")
            health = data_health_table(app_state.table_manifest)
            st.dataframe(health, width="stretch", height=260, hide_index=True)

        st.markdown('<div id="filter-bar-marker"></div>', unsafe_allow_html=True)
        top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

        with top1:
            st.session_state.member_query = st.text_input(
                "Search legislator",
                placeholder="e.g., Bell, Keith",
                key="member_query_input",
                help="Search by legislator name. Suggestions appear when close matches exist.",
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

            if st.session_state.member_session is None or str(st.session_state.member_session).strip().lower() in {"none", "nan", "null", ""}:
                st.session_state.member_session = default_session

            current_label = _session_label(st.session_state.member_session)
            if current_label not in session_labels:
                current_label = default_label if default_label in session_labels else session_labels[0]

            chosen_label = st.selectbox(
                "Session",
                session_labels,
                index=session_labels.index(current_label),
                key="member_session_select",
                help="Choose the legislative session used for filters and totals.",
            )
            st.session_state.member_session = label_to_session.get(chosen_label, default_session)

        author_bills_all = app_state.author_bills_all
        member_index = app_state.member_index
        resolved_member, member_suggestions = resolve_member_name(
            st.session_state.member_query,
            member_index,
        )

        if member_suggestions:
            pick = st.selectbox(
                "Suggestions",
                ["Select a legislator..."] + member_suggestions,
                index=0,
                key="member_suggestions_select",
                help="Pick a suggested legislator to populate the selection.",
            )
            if pick in member_suggestions:
                resolved_member = pick

        st.session_state.member_name = resolved_member or ""
        if st.session_state.member_name:
            _remember_recent_member_search(st.session_state.member_name)

        with top3:
            st.markdown('<div class="small-muted">Member</div>', unsafe_allow_html=True)
            if st.session_state.member_name:
                st.write(st.session_state.member_name)
            else:
                st.write("-")

        def _reuse_recent_member_search(value: str) -> None:
            rec = str(value).strip()
            if not rec:
                return
            st.session_state.member_query = rec
            st.session_state.member_query_input = rec
            st.session_state.member_name = ""
            st.session_state.member_suggestions_select = "Select a legislator..."
            st.session_state.member_bill_search = ""
            st.session_state.member_bill_search_input = ""
            st.session_state.member_witness_search = ""
            st.session_state.member_witness_search_input = ""
            st.session_state.member_activity_search = ""
            st.session_state.member_activity_search_input = ""
            st.session_state.member_filter = ""
            st.session_state.member_filter_input = ""

        recent = st.session_state.get("recent_member_searches", [])
        if recent:
            st.markdown('<div class="section-sub">Recent lookups</div>', unsafe_allow_html=True)
            recent_cols = st.columns(min(len(recent), 4))
            for idx, rec in enumerate(recent[:8]):
                col = recent_cols[idx % len(recent_cols)]
                label = rec if len(rec) <= 28 else rec[:25] + "..."
                col.button(
                    f"Reuse {label}",
                    key=f"recent_member_lookup_{idx}",
                    help="Reuse a recent legislator search",
                    width="stretch",
                    on_click=_reuse_recent_member_search,
                    args=(rec,),
                )

        tfl_session_val = _tfl_session_for_filter(st.session_state.member_session, tfl_sessions)

        active_parts = [f"Session: {_session_label(st.session_state.member_session)}"]
        if st.session_state.member_name:
            active_parts.append(f"Member: {st.session_state.member_name}")
        chips_html = "".join([f'<span class="chip">{html.escape(c)}</span>' for c in active_parts])
        st.markdown('<div id="filter-summary-marker"></div>', unsafe_allow_html=True)
        f1, f2 = st.columns([3, 1])
        with f1:
            st.markdown(
                f'<div class="filter-summary"><span class="filter-summary-label">Active filters</span>{chips_html}</div>',
                unsafe_allow_html=True,
            )
            st.caption(f"Selected member: {st.session_state.member_name or '-'}")
        with f2:
            st.button(
                "Clear filters",
                width="stretch",
                help="Reset legislator search and primary filters to defaults.",
                on_click=reset_member_filters,
                args=(default_session,),
            )
        st.markdown(
            '<div class="app-note"><strong>Interpretation:</strong> Bills, witness rows, and staff records are linked for context. Correlation in these records does not establish motive or direction.</div>',
            unsafe_allow_html=True,
        )

        focus_label = "All Legislators"
        if st.session_state.member_name:
            focus_label = f"Legislator: {st.session_state.member_name}"
        focus_context = {
            "type": "legislator" if st.session_state.member_name else "",
            "name": st.session_state.member_name,
            "report_title": "Legislator Report",
            "tables": {
                "Staff_All": data["Staff_All"],
            },
            "lookups": {
                "name_to_short": name_to_short,
                "short_to_names": short_to_names,
                "filerid_to_short": filerid_to_short,
            },
            "table_loader": get_app_tables,
            "table_loader_path": str(PATH),
            "table_loader_keys": (
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
        }
        _ = _render_pdf_report_section(
            key_prefix="member",
            session_val=st.session_state.member_session,
            scope_label="Selected Session",
            focus_label=focus_label,
            Lobby_TFL_Client_All=Lobby_TFL_Client_All,
            Wit_All=Wit_All,
            Bill_Status_All=Bill_Status_All,
            Bill_Sub_All=pd.DataFrame(),
            tfl_session_val=tfl_session_val,
            focus_context=focus_context,
        )
        _page_fragments.merge_fragment_session_context("_member_workspace_ctx", {
            "PATH": str(PATH),
            "member_session": st.session_state.member_session,
            "member_name": st.session_state.member_name,
            "tfl_session_val": tfl_session_val,
        })
        _page_fragments.render_member_workspace_fragment("_member_workspace_ctx")
        return
    finally:
        _pop_context(globals(), _previous, _ctx)
