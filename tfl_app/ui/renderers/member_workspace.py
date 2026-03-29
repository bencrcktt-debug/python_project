from __future__ import annotations

from typing import Any

from tfl_app.services import WorkspaceServices

from . import _workspace_core as _core
from .context_adapters import merge_workspace_runtime_context, normalize_member_workspace_context

# Keep the shared helper namespace stable while this module owns the member renderer.
globals().update({name: getattr(_core, name) for name in dir(_core) if not name.startswith('__')})

_MISSING = object()


def _push_context(ctx: dict[str, Any]) -> dict[str, Any]:
    payload = dict(ctx or {})
    local_previous: dict[str, Any] = {}
    core_previous: dict[str, Any] = {}
    core_globals = vars(_core)
    for key, value in payload.items():
        local_previous[key] = globals().get(key, _MISSING)
        globals()[key] = value
        core_previous[key] = core_globals.get(key, _MISSING)
        core_globals[key] = value
    return {"payload": payload, "local": local_previous, "core": core_previous}


def _pop_context(previous: dict[str, Any], ctx: dict[str, Any]) -> None:
    del ctx
    payload = dict(previous.get("payload", {}) or {})
    local_previous = dict(previous.get("local", {}) or {})
    core_previous = dict(previous.get("core", {}) or {})
    core_globals = vars(_core)
    for key in payload.keys():
        old_value = local_previous.get(key, _MISSING)
        if old_value is _MISSING:
            globals().pop(key, None)
        else:
            globals()[key] = old_value
        old_core_value = core_previous.get(key, _MISSING)
        if old_core_value is _MISSING:
            core_globals.pop(key, None)
        else:
            core_globals[key] = old_core_value


def _runtime_ctx(ctx: Any, services: WorkspaceServices | None) -> dict[str, Any]:
    return merge_workspace_runtime_context(normalize_member_workspace_context(ctx), services)

def render_member_workspace(ctx: Any, services: WorkspaceServices | None = None) -> None:
    ctx = _runtime_ctx(ctx, services)
    _previous = _push_context(ctx)
    try:
        tab_all, tab_overview, tab_bills, tab_witness, tab_activities, tab_staff = st.tabs(
            [
                "1. Session Baseline (Read First)",
                "2. Selected Legislator",
                "3. Bills & Outcomes",
                "4. Witness Activity",
                "5. Spending Activity",
                "6. Staff Links",
            ]
        )

        def kpi_card(title: str, value: str, sub: str = "", help_text: str = ""):
            tooltip_attr = f' title="{html.escape(help_text, quote=True)}"' if help_text else ""
            st.markdown(
                f"""
            <div class="card"{tooltip_attr}>
              <div class="kpi-title">{title}</div>
              <div class="kpi-value">{value}</div>
              <div class="kpi-sub">{sub}</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with tab_all:
            st.markdown('<div class="section-title">All Legislators Overview</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="section-sub">Session: {_session_label(st.session_state.member_session)}</div>',
                unsafe_allow_html=True,
            )

            if all_legislators.empty:
                st.info("No authored bills found for the selected session.")
            else:
                a1, a2, a3, a4 = st.columns(4)
                with a1:
                    kpi_card(
                        "Total Legislators",
                        f"{all_leg_stats.get('total_legislators', 0):,}",
                        help_text="Unique legislators with authored bills in the selected session.",
                    )
                with a2:
                    kpi_card(
                        "Bills Authored",
                        f"{all_leg_stats.get('total_bills', 0):,}",
                        help_text="Unique bills with at least one listed author in the session.",
                    )
                with a3:
                    kpi_card(
                        "Passed / Failed",
                        f"{all_leg_stats.get('passed', 0):,} / {all_leg_stats.get('failed', 0):,}",
                        help_text="Bill outcomes for authored bills in the session.",
                    )
                with a4:
                    kpi_card(
                        "Witness Rows",
                        f"{all_leg_stats.get('witness_rows', 0):,}",
                        f"Lobbyists: {all_leg_stats.get('witness_lobbyists', 0):,}",
                        help_text="Witness list rows tied to authored bills in the session.",
                    )

                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

                t1, t2 = st.columns(2)
                with t1:
                    st.markdown('<div class="section-title">Top 5 by Bills Authored</div>', unsafe_allow_html=True)
                    top_bills = all_legislators.sort_values(["Bills", "Legislator"], ascending=[False, True]).head(5)
                    st.dataframe(
                        top_bills[["Legislator", "Bills", "Passed", "Failed"]],
                        width="stretch",
                        height=240,
                        hide_index=True,
                    )
                with t2:
                    st.markdown('<div class="section-title">Top 5 by Witness Rows</div>', unsafe_allow_html=True)
                    if all_legislators["WitnessRows"].sum() > 0:
                        top_witness = all_legislators.sort_values(
                            ["WitnessRows", "Legislator"], ascending=[False, True]
                        ).head(5)
                        top_witness = top_witness.rename(
                            columns={
                                "WitnessRows": "Witness Rows",
                                "WitnessLobbyists": "Unique Lobbyists",
                                "WitnessBills": "Bills w/ Witness",
                            }
                        )
                        st.dataframe(
                            top_witness[["Legislator", "Witness Rows", "Unique Lobbyists", "Bills w/ Witness"]],
                            width="stretch",
                            height=240,
                            hide_index=True,
                        )
                    else:
                        st.info("No witness-list rows found for authored bills in this session.")

                st.session_state.member_filter = st.text_input(
                    "Filter legislator (contains)",
                    placeholder="e.g., Johnson",
                    key="member_filter_input",
                    help="Filter the All Legislators table by a name substring.",
                )

                view = all_legislators
                if st.session_state.member_filter.strip():
                    view = view[
                        view["Legislator"].astype(str).str.contains(
                            st.session_state.member_filter.strip(), case=False, na=False
                        )
                    ]

                sort_cols = []
                sort_order = []
                if "Bills" in view.columns:
                    sort_cols.append("Bills")
                    sort_order.append(False)
                if "WitnessRows" in view.columns:
                    sort_cols.append("WitnessRows")
                    sort_order.append(False)
                if "Legislator" in view.columns:
                    sort_cols.append("Legislator")
                    sort_order.append(True)
                if sort_cols:
                    view = view.sort_values(sort_cols, ascending=sort_order)

                view_disp = view.rename(
                    columns={
                        "WitnessRows": "Witness Rows",
                        "WitnessLobbyists": "Unique Lobbyists",
                        "WitnessBills": "Bills w/ Witness",
                    }
                )
                show_cols = [
                    "Legislator",
                    "Bills",
                    "Passed",
                    "Failed",
                    "Bills w/ Witness",
                    "Witness Rows",
                    "Unique Lobbyists",
                ]
                show_cols = [c for c in show_cols if c in view_disp.columns]
                st.dataframe(
                    view_disp[show_cols],
                    width="stretch",
                    height=560,
                    hide_index=True,
                )
                _ = export_dataframe(view_disp[show_cols], "all_legislators_overview.csv", label="Download overview CSV")

        def _no_member_msg():
            st.info("Type a legislator name at the top to view details. The All Legislators tab is available without a selection.")

        if not st.session_state.member_name:
            with tab_overview:
                _no_member_msg()
            with tab_bills:
                _no_member_msg()
            with tab_witness:
                _no_member_msg()
            with tab_activities:
                _no_member_msg()
            with tab_staff:
                _no_member_msg()
            return

        session = str(st.session_state.member_session).strip()
        member_name = st.session_state.member_name
        if ctx.get("_prepared_member_workspace"):
            authored = ctx.get("authored", pd.DataFrame())
            lt = ctx.get("lt", pd.DataFrame())
            tfl_flag = ctx.get("tfl_flag", pd.DataFrame())
            lobbyshort_to_name = dict(ctx.get("lobbyshort_to_name", {}) or {})
            bill_list = list(ctx.get("bill_list", []) or [])
            wit = ctx.get("wit", pd.DataFrame())
            witness = ctx.get("witness", pd.DataFrame())
            activities = ctx.get("activities", pd.DataFrame())
            staff_matches = ctx.get("staff_matches", pd.DataFrame())
            staff_lobbyists = ctx.get("staff_lobbyists", pd.DataFrame())
            member_info = dict(ctx.get("member_info", {}) or {})
        else:
            member_norm = norm_name(member_name)
            member_info = parse_member_name(member_name)

            authored = author_bills_all
            authored = authored[authored["AuthorNorm"] == member_norm]
            authored = authored[authored["Session"].astype(str).str.strip() == session]
            authored = authored.drop_duplicates(subset=["Session", "Bill", "Author"])

            tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
            lt = Lobby_TFL_Client_All
            if "Session" in lt.columns:
                lt = lt[lt["Session"].astype(str).str.strip() == tfl_session]
            lt = ensure_cols(lt, {"LobbyShort": "", "IsTFL": 0})
            tfl_flag = (
                lt.groupby("LobbyShort", as_index=False)["IsTFL"]
                .max()
                .rename(columns={"IsTFL": "Has TFL Client"})
            )

            lobbyshort_to_name = {}
            if short_to_names:
                lobbyshort_to_name = {k: (v[0] if v else k) for k, v in short_to_names.items()}
            if not lobbyshort_to_name and not Lobby_TFL_Client_All.empty:
                tmp = Lobby_TFL_Client_All[["LobbyShort", "Lobby Name"]].dropna()
                tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
                tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
                lobbyshort_to_name = (
                    tmp.groupby("LobbyShort")["Lobby Name"]
                    .first()
                    .to_dict()
                )

            bill_list = authored["Bill"].dropna().astype(str).unique().tolist()
            wit_all = Wit_All
            if "LobbyShortNorm" not in wit_all.columns and "LobbyShort" in wit_all.columns:
                wit_all = wit_all.copy()
                wit_all["LobbyShortNorm"] = norm_name_series(wit_all["LobbyShort"])

            if bill_list:
                wit = wit_all[
                    (wit_all["Session"].astype(str).str.strip() == session) &
                    (wit_all["Bill"].astype(str).isin(bill_list))
                ]
            else:
                wit = wit_all.iloc[0:0]

            if "LobbyShort" in wit.columns:
                wit = wit[wit["LobbyShort"].notna() & (wit["LobbyShort"].astype(str).str.strip() != "")]

            witness = pd.DataFrame()
            if not wit.empty:
                positions = bill_position_from_flags(wit)

                orgs = pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Organization"])
                if "org" in wit.columns:
                    orgs = (
                        wit.assign(Organization=wit.get("org", "").fillna("").astype(str).str.strip())
                        .groupby(["Session", "Bill", "LobbyShort"])["Organization"]
                        .apply(lambda s: ", ".join(sorted({x for x in s if x})))
                        .reset_index()
                    )

                names = pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Witness Name"])
                if "name" in wit.columns:
                    names = (
                        wit.assign(WitnessName=wit.get("name", "").fillna("").astype(str).str.strip())
                        .groupby(["Session", "Bill", "LobbyShort"])["WitnessName"]
                        .apply(lambda s: ", ".join(sorted({x for x in s if x})))
                        .reset_index()
                        .rename(columns={"WitnessName": "Witness Name"})
                    )

                witness = positions.merge(orgs, on=["Session", "Bill", "LobbyShort"], how="left")
                witness = witness.merge(names, on=["Session", "Bill", "LobbyShort"], how="left")
                witness = witness.merge(tfl_flag, on="LobbyShort", how="left")
                witness["Has TFL Client"] = witness["Has TFL Client"].map({1: "Yes", 0: "No"}).fillna("Unknown")
                witness["Lobbyist"] = witness["LobbyShort"].map(lobbyshort_to_name).fillna(witness["LobbyShort"])

                authored_base_cols = [c for c in ["Session", "Bill", "Status", "Caption", "Link"] if c in authored.columns]
                authored_base = authored[authored_base_cols].drop_duplicates()
                witness = witness.merge(authored_base, on=["Session", "Bill"], how="left")

            activities = build_member_activities(
                data["LaFood"], data["LaEnt"], data["LaTran"], data["LaGift"], data["LaEvnt"], data["LaAwrd"],
                member_name=member_name,
                session=session,
                name_to_short=name_to_short,
                filerid_to_short=data.get("filerid_to_short", {}),
                lobbyshort_to_name=lobbyshort_to_name,
            )

            if not activities.empty:
                activities = activities.merge(tfl_flag, on="LobbyShort", how="left")
                activities["Has TFL Client"] = activities["Has TFL Client"].map({1: "Yes", 0: "No"}).fillna("Unknown")
            else:
                activities = pd.DataFrame(columns=["Session", "Date", "Type", "LobbyShort", "Lobbyist", "Filer", "Member", "Description", "Amount", "Has TFL Client"])

            staff_df = Staff_All
            staff_matches = pd.DataFrame()
            if not staff_df.empty and "Legislator" in staff_df.columns:
                leg_norm = staff_df.get("LegislatorNorm", norm_name_series(staff_df["Legislator"]))
                leg_last_norm = staff_df.get("LegislatorLastNorm", last_name_norm_series(staff_df["Legislator"]))
                leg_init_key = staff_df.get("LegislatorInitKey", staff_df["Legislator"].fillna("").astype(str).map(_last_first_initial_key))

                match = pd.Series(False, index=staff_df.index)
                last_norm = member_info.get("last_norm", "")
                if last_norm:
                    match = leg_last_norm == last_norm
                    if member_info.get("initial_key"):
                        match = match & (leg_init_key == member_info["initial_key"])

                full_norm = member_info.get("full_norm", "")
                if full_norm:
                    match = match | leg_norm.str.contains(full_norm, na=False)

                staff_matches = staff_df[match]

            staff_lobbyists = pd.DataFrame()
            if not staff_matches.empty and "Staffer" in staff_matches.columns:
                tmp_short = Lobby_TFL_Client_All[["LobbyShort"]].dropna()
                tmp_short["InitialKey"] = tmp_short["LobbyShort"].map(_last_first_initial_key)
                init_counts = (
                    tmp_short.groupby(["InitialKey", "LobbyShort"])
                    .size()
                    .reset_index(name="n")
                    .sort_values(["InitialKey", "n"], ascending=[True, False])
                    .drop_duplicates("InitialKey")
                )
                initial_to_short = dict(zip(init_counts["InitialKey"], init_counts["LobbyShort"]))

                def map_staffer(name: str) -> str:
                    if not name:
                        return ""
                    for v in norm_person_variants(name):
                        if v in name_to_short:
                            return str(name_to_short[v])
                    init_key = _last_first_initial_key(name)
                    if init_key and init_key in initial_to_short:
                        return str(initial_to_short[init_key])
                    return ""

                staff_lobbyists = staff_matches
                staff_lobbyists["LobbyShort"] = staff_lobbyists["Staffer"].fillna("").astype(str).map(map_staffer)
                staff_lobbyists = staff_lobbyists[staff_lobbyists["LobbyShort"].astype(str).str.strip() != ""]
                staff_lobbyists["Lobbyist"] = staff_lobbyists["LobbyShort"].map(lobbyshort_to_name).fillna(staff_lobbyists["LobbyShort"])

        with tab_overview:
            st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)

            if authored.empty:
                st.info("No authored bills found for this legislator/session in Texas Legislature Online bill status data.")
            else:
                bill_count = int(authored["Bill"].nunique())
                passed = int((authored.get("Status", pd.Series(dtype=object)) == "Passed").sum())
                failed = int((authored.get("Status", pd.Series(dtype=object)) == "Failed").sum())
                witness_rows = int(len(witness)) if isinstance(witness, pd.DataFrame) else 0
                lobbyist_count = int(witness.get("LobbyShort", pd.Series(dtype=object)).nunique()) if isinstance(witness, pd.DataFrame) and not witness.empty else 0
                tfl_count = int((witness.get("Has TFL Client", pd.Series(dtype=object)) == "Yes").sum()) if isinstance(witness, pd.DataFrame) and not witness.empty else 0

                o1, o2, o3, o4 = st.columns(4)
                with o1:
                    kpi_card(
                        "Session",
                        session,
                        help_text="Session used for authored bill counts and witness lists.",
                    )
                with o2:
                    kpi_card(
                        "Member",
                        member_name,
                        help_text="Resolved legislator selection from search or suggestions.",
                    )
                with o3:
                    kpi_card(
                        "Bills Authored",
                        f"{bill_count:,}",
                        help_text="Unique bills authored by this member in the session.",
                    )
                with o4:
                    kpi_card(
                        "Passed / Failed",
                        f"{passed:,} / {failed:,}",
                        help_text="Outcome counts for authored bills in the session.",
                    )

                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

                s1, s2, s3, s4 = st.columns(4)
                with s1:
                    kpi_card(
                        "Witness Rows",
                        f"{witness_rows:,}",
                        help_text="Witness list rows tied to this member's authored bills.",
                    )
                with s2:
                    kpi_card(
                        "Unique Lobbyists",
                        f"{lobbyist_count:,}",
                        help_text="Distinct lobbyists appearing in the witness lists.",
                    )
                with s3:
                    kpi_card(
                        "Lobbyists w/ TFL Clients",
                        f"{tfl_count:,}",
                        help_text="Witness rows marked as having a taxpayer-funded client.",
                    )
                with s4:
                    kpi_card(
                        "Activities Rows",
                        f"{len(activities):,}",
                        help_text="Activity rows where this member is the recipient.",
                    )

                top_witness_lobby_short = ""
                top_witness_lobby_label = ""
                top_related_client = ""
                witness_df = witness if isinstance(witness, pd.DataFrame) else pd.DataFrame()
                if not witness_df.empty and "LobbyShort" in witness_df.columns:
                    lobby_counts = (
                        witness_df["LobbyShort"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                    )
                    lobby_counts = lobby_counts[lobby_counts != ""]
                    if not lobby_counts.empty:
                        top_witness_lobby_short = str(lobby_counts.value_counts().index[0]).strip()
                        top_witness_lobby_label = str(
                            lobbyshort_to_name.get(top_witness_lobby_short, top_witness_lobby_short)
                        ).strip()
                if top_witness_lobby_short and not lt.empty:
                    top_client_rows = lt[lt["LobbyShort"].astype(str).str.strip() == top_witness_lobby_short]
                    if not top_client_rows.empty and "Client" in top_client_rows.columns:
                        top_client_rows = ensure_cols(top_client_rows, {"Low_num": 0.0, "High_num": 0.0, "Client": ""})
                        top_client_rows["Mid"] = (pd.to_numeric(top_client_rows["Low_num"], errors="coerce").fillna(0) + pd.to_numeric(top_client_rows["High_num"], errors="coerce").fillna(0)) / 2
                        top_client_rows = (
                            top_client_rows.groupby("Client", as_index=False)["Mid"]
                            .sum()
                            .sort_values("Mid", ascending=False)
                        )
                        if not top_client_rows.empty:
                            top_related_client = str(top_client_rows.iloc[0].get("Client", "")).strip()

                if top_witness_lobby_label:
                    st.markdown(
                        f"""
            <div class="handoff-card">
              <div class="handoff-kicker">Cross-Page Handoff</div>
              <div class="handoff-title">Follow The Most Active Witness Lobbyist</div>
              <div class="handoff-sub">Top witness lobbyist in this member profile: <strong>{html.escape(top_witness_lobby_label, quote=True)}</strong>.</div>
            </div>
            """,
                        unsafe_allow_html=True,
                    )
                    handoff_cols = st.columns(2 if top_related_client else 1)
                    with handoff_cols[0]:
                        if st.button("Open Top Lobbyist", key="member_handoff_lobby_btn", width="stretch"):
                            st.session_state.search_query = top_witness_lobby_label or top_witness_lobby_short
                            st.session_state.session = st.session_state.member_session
                            st.session_state.scope = "This Session"
                            st.session_state.lobbyshort = top_witness_lobby_short
                            st.session_state.lobby_filerid = None
                            st.switch_page(_lobby_page)
                    if top_related_client:
                        with handoff_cols[1]:
                            if st.button("Open Related Client", key="member_handoff_client_btn", width="stretch"):
                                st.session_state.client_query = top_related_client
                                st.session_state.client_query_input = top_related_client
                                st.session_state.client_name = ""
                                st.session_state.client_session = st.session_state.member_session
                                st.session_state.client_scope = "This Session"
                                st.switch_page(_client_page)

                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                st.markdown('<div class="section-sub">TFL Opposition Snapshot</div>', unsafe_allow_html=True)
                total_bills = int(bill_count)
                tfl_opposed = 0
                tfl_any = 0
                any_witness = 0
                if not witness_df.empty:
                    against_mask = witness_df.get("Position", pd.Series(dtype=object)).astype(str).str.contains("Against", case=False, na=False)
                    tfl_mask = witness_df.get("Has TFL Client", pd.Series(dtype=object)).astype(str) == "Yes"
                    tfl_opposed = int(witness_df.loc[against_mask & tfl_mask, "Bill"].dropna().astype(str).nunique())
                    tfl_any = int(witness_df.loc[tfl_mask, "Bill"].dropna().astype(str).nunique())
                    any_witness = int(witness_df.get("Bill", pd.Series(dtype=object)).dropna().astype(str).nunique())

                pie_df = pd.DataFrame(
                    {
                        "Outcome": ["Opposed by TFL lobbyist", "Not opposed by TFL lobbyist"],
                        "Bills": [tfl_opposed, max(total_bills - tfl_opposed, 0)],
                    }
                )
                if total_bills > 0:
                    c1, c2 = st.columns([1.1, 1])
                    with c1:
                        fig_tfl = px.pie(
                            pie_df,
                            names="Outcome",
                            values="Bills",
                            hole=0.55,
                            color="Outcome",
                            color_discrete_map=OPPOSITION_COLOR_MAP,
                        )
                        fig_tfl.update_traces(
                            textposition="inside",
                            textinfo="percent+label",
                            insidetextorientation="radial",
                            marker=dict(line=dict(color="rgba(7,22,39,0.9)", width=2)),
                            hovertemplate="%{label}: %{value} bills (%{percent})<extra></extra>",
                        )
                        _apply_plotly_layout(fig_tfl, showlegend=False, margin_top=12)
                        fig_tfl.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
                        st.plotly_chart(fig_tfl, width="stretch", config=PLOTLY_CONFIG)
                    with c2:
                        summary_df = pd.DataFrame(
                            {
                                "Metric": [
                                    "Bills authored",
                                    "Bills with any witness",
                                    "Bills with any TFL witness",
                                    "Bills opposed by TFL lobbyist",
                                ],
                                "Count": [total_bills, any_witness, tfl_any, tfl_opposed],
                            }
                        )
                        st.dataframe(summary_df, width="stretch", height=200, hide_index=True)

            with tab_bills:
                st.markdown('<div class="section-title">Bills Authored</div>', unsafe_allow_html=True)
                if authored.empty:
                    st.info("No authored bills found for this legislator/session.")
                else:
                    st.session_state.member_bill_search = st.text_input(
                        "Search bills (Bill / Caption / Status)",
                        placeholder="e.g., HB 1 or education",
                        key="member_bill_search_input",
                        help="Filter authored bills by bill number, caption, or status.",
                    )
                    bill_view = authored
                    if st.session_state.member_bill_search.strip():
                        q = st.session_state.member_bill_search.strip()
                        bill_view = bill_view[
                            bill_view["Bill"].astype(str).str.contains(q, case=False, na=False) |
                            bill_view.get("Caption", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False) |
                            bill_view.get("Status", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False)
                        ]

                    show_cols = [c for c in ["Bill", "Status", "Caption", "Chamber", "Link"] if c in bill_view.columns]
                    bill_view = bill_view.drop_duplicates(subset=["Bill"])
                    st.dataframe(
                        bill_view[show_cols].sort_values(["Bill"]),
                        width="stretch",
                        height=520,
                        hide_index=True,
                    )
                    _ = export_dataframe(bill_view[show_cols], "member_bills.csv")
                    top_bill = ""
                    if not bill_view.empty and "Bill" in bill_view.columns:
                        bill_counts = (
                            bill_view["Bill"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                        )
                        bill_counts = bill_counts[bill_counts != ""]
                        if not bill_counts.empty:
                            top_bill = str(bill_counts.value_counts().index[0]).strip()
                    witness_seed = st.session_state.member_bill_search.strip() or top_bill
                    if top_bill:
                        st.markdown(
                            f"""
            <div class="handoff-card">
              <div class="handoff-kicker">Cross-Tab Continuity</div>
              <div class="handoff-title">Carry Bill Focus Into Witness And Lobbyist Views</div>
              <div class="handoff-sub">Most frequent bill in this filtered authored view: <strong>{html.escape(top_bill, quote=True)}</strong>.</div>
            </div>
            """,
                            unsafe_allow_html=True,
                        )
                        bnav1, bnav2 = st.columns(2)
                        with bnav1:
                            if st.button("Run In Lobbyists Bill Mode", key="member_bills_to_lobby_bill_btn", width="stretch"):
                                st.session_state.search_query = top_bill
                                st.session_state.session = st.session_state.member_session
                                st.session_state.scope = "This Session"
                                st.session_state.lobbyshort = ""
                                st.session_state.lobby_filerid = None
                                st.session_state.lobby_selected_key = ""
                                st.session_state.lobby_all_matches = False
                                st.session_state.lobby_merge_keys = []
                                st.session_state.lobby_candidate_map = {}
                                st.session_state.lobby_match_query = top_bill
                                st.session_state.lobby_match_select = "No match"
                                st.switch_page(_lobby_page)
                        with bnav2:
                            if st.button(
                                "Use In Witness Tab Search",
                                key="member_bills_to_witness_seed_btn",
                                width="stretch",
                                disabled=not bool(witness_seed),
                            ):
                                st.session_state.member_witness_search = witness_seed
                                st.session_state.member_witness_search_input = witness_seed
                                st.success("Witness tab search has been prefilled from the Bills view.")

        with tab_witness:
            st.markdown('<div class="section-title">Witness Lists: Lobbyists and Organizations</div>', unsafe_allow_html=True)
            if witness.empty:
                st.info("No witness-list rows found for bills authored by this legislator in the selected session.")
            else:
                st.session_state.member_witness_search = st.text_input(
                    "Search witness list (Bill / Lobbyist / Organization)",
                    key="member_witness_search_input",
                    help="Filter witness list rows by bill, lobbyist, organization, or witness name.",
                )
                witness_view = witness
                if st.session_state.member_witness_search.strip():
                    q = st.session_state.member_witness_search.strip()
                    witness_view = witness_view[
                        witness_view["Bill"].astype(str).str.contains(q, case=False, na=False) |
                        witness_view.get("Lobbyist", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False) |
                        witness_view.get("Organization", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False) |
                        witness_view.get("Witness Name", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False)
                    ]

                f1, f2, f3 = st.columns(3)
                with f1:
                    pos_opts = _clean_options(
                        witness_view.get("Position", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                    )
                    pos_opts = sorted(pos_opts)
                    pos_sel = st.multiselect(
                        "Filter by position",
                        pos_opts,
                        default=pos_opts,
                        key="member_pos_filter",
                        help="Limit results to selected witness positions.",
                    )
                with f2:
                    tfl_opts = _clean_options(
                        witness_view.get("Has TFL Client", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                    )
                    tfl_opts = sorted(tfl_opts)
                    tfl_sel = st.multiselect(
                        "Filter by TFL",
                        tfl_opts,
                        default=tfl_opts,
                        key="member_tfl_filter",
                        help="Filter to rows marked as having a taxpayer-funded client.",
                    )
                with f3:
                    lob_opts = _clean_options(
                        witness_view.get("Lobbyist", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                    )
                    lob_opts = sorted(lob_opts)
                    lob_sel = st.multiselect(
                        "Filter by lobbyist",
                        lob_opts,
                        default=lob_opts,
                        key="member_lobbyist_filter",
                        help="Limit results to selected lobbyists.",
                    )

                if pos_sel:
                    witness_view = witness_view[witness_view["Position"].astype(str).isin(pos_sel)]
                if tfl_sel:
                    witness_view = witness_view[witness_view["Has TFL Client"].astype(str).isin(tfl_sel)]
                if lob_sel:
                    witness_view = witness_view[witness_view["Lobbyist"].astype(str).isin(lob_sel)]

                show_cols = [
                    "Bill",
                    "Lobbyist",
                    "Organization",
                    "Witness Name",
                    "Position",
                    "Has TFL Client",
                    "Status",
                    "Caption",
                ]
                show_cols = [c for c in show_cols if c in witness_view.columns]
                st.dataframe(
                    witness_view[show_cols].sort_values(["Bill", "Lobbyist"]),
                    width="stretch",
                    height=560,
                    hide_index=True,
                )
                _ = export_dataframe(witness_view[show_cols], "member_witness_lists.csv")
                top_witness_lobby_short_tab = ""
                top_witness_lobby_label_tab = ""
                top_related_client_tab = ""
                top_witness_bill_tab = ""
                if not witness_view.empty:
                    if "LobbyShort" in witness_view.columns:
                        short_counts = (
                            witness_view["LobbyShort"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                        )
                        short_counts = short_counts[short_counts != ""]
                        if not short_counts.empty:
                            top_witness_lobby_short_tab = str(short_counts.value_counts().index[0]).strip()
                            top_witness_lobby_label_tab = str(
                                lobbyshort_to_name.get(top_witness_lobby_short_tab, top_witness_lobby_short_tab)
                            ).strip()
                    elif "Lobbyist" in witness_view.columns:
                        lobby_counts = (
                            witness_view["Lobbyist"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                        )
                        lobby_counts = lobby_counts[lobby_counts != ""]
                        if not lobby_counts.empty:
                            top_witness_lobby_label_tab = str(lobby_counts.value_counts().index[0]).strip()

                    if "Bill" in witness_view.columns:
                        bill_counts = (
                            witness_view["Bill"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                        )
                        bill_counts = bill_counts[bill_counts != ""]
                        if not bill_counts.empty:
                            top_witness_bill_tab = str(bill_counts.value_counts().index[0]).strip()

                if top_witness_lobby_short_tab and not lt.empty:
                    top_client_rows = lt[lt["LobbyShort"].astype(str).str.strip() == top_witness_lobby_short_tab]
                    if not top_client_rows.empty and "Client" in top_client_rows.columns:
                        top_client_rows = ensure_cols(top_client_rows, {"Low_num": 0.0, "High_num": 0.0, "Client": ""})
                        top_client_rows["Mid"] = (
                            pd.to_numeric(top_client_rows["Low_num"], errors="coerce").fillna(0) +
                            pd.to_numeric(top_client_rows["High_num"], errors="coerce").fillna(0)
                        ) / 2
                        top_client_rows = (
                            top_client_rows.groupby("Client", as_index=False)["Mid"]
                            .sum()
                            .sort_values("Mid", ascending=False)
                        )
                        if not top_client_rows.empty:
                            top_related_client_tab = str(top_client_rows.iloc[0].get("Client", "")).strip()

                if top_witness_lobby_label_tab:
                    handoff_line = f"Most frequent lobbyist in this witness view: {top_witness_lobby_label_tab}."
                    if top_witness_bill_tab:
                        handoff_line += f" Most frequent bill: {top_witness_bill_tab}."
                    st.markdown(
                        f"""
            <div class="handoff-card">
              <div class="handoff-kicker">Cross-Tab Continuity</div>
              <div class="handoff-title">Follow Witness Activity Into Entity And Spending Views</div>
              <div class="handoff-sub">{html.escape(handoff_line, quote=True)}</div>
            </div>
            """,
                        unsafe_allow_html=True,
                    )
                    wnav1, wnav2, wnav3 = st.columns(3)
                    with wnav1:
                        if st.button("Open Top Lobbyist", key="member_witness_to_lobby_btn", width="stretch"):
                            st.session_state.search_query = top_witness_lobby_label_tab or top_witness_lobby_short_tab
                            st.session_state.session = st.session_state.member_session
                            st.session_state.scope = "This Session"
                            st.session_state.lobbyshort = top_witness_lobby_short_tab
                            st.session_state.lobby_filerid = None
                            st.switch_page(_lobby_page)
                    with wnav2:
                        if st.button(
                            "Open Related Client",
                            key="member_witness_to_client_btn",
                            width="stretch",
                            disabled=not bool(top_related_client_tab),
                        ):
                            st.session_state.client_query = top_related_client_tab
                            st.session_state.client_query_input = top_related_client_tab
                            st.session_state.client_name = ""
                            st.session_state.client_session = st.session_state.member_session
                            st.session_state.client_scope = "This Session"
                            st.switch_page(_client_page)
                    with wnav3:
                        if st.button(
                            "Use Top Lobbyist In Activities",
                            key="member_witness_to_activity_seed_btn",
                            width="stretch",
                        ):
                            seed = top_witness_lobby_label_tab or top_witness_lobby_short_tab
                            st.session_state.member_activity_search = seed
                            st.session_state.member_activity_search_input = seed
                            st.success("Activities tab search has been prefilled with the top witness lobbyist.")

        with tab_activities:
            st.markdown('<div class="section-title">Lobbyist Activity Benefiting the Member</div>', unsafe_allow_html=True)
            if activities.empty:
                st.info("No activity rows found where this legislator is the recipient.")
            else:
                filt = activities
                t_opts = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
                t_opts = sorted(t_opts)
                sel_types = st.multiselect(
                    "Filter by activity type",
                    t_opts,
                    default=t_opts,
                    key="member_activity_types",
                    help="Limit results to selected activity categories.",
                )
                if sel_types:
                    filt = filt[filt["Type"].isin(sel_types)]

                lobby_opts = _clean_options(filt["Lobbyist"].dropna().astype(str).unique().tolist())
                lobby_opts = sorted(lobby_opts)
                sel_lobby = st.multiselect(
                    "Filter by lobbyist",
                    lobby_opts,
                    default=lobby_opts,
                    key="member_activity_lobbyist",
                    help="Limit results to selected lobbyists.",
                )
                if sel_lobby:
                    filt = filt[filt["Lobbyist"].isin(sel_lobby)]

                st.session_state.member_activity_search = st.text_input(
                    "Search activities (lobbyist, description, filer)",
                    key="member_activity_search_input",
                    help="Search activity rows by lobbyist, description, or filer.",
                )
                if st.session_state.member_activity_search.strip():
                    q = st.session_state.member_activity_search.strip()
                    filt = filt[
                        filt["Lobbyist"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Description"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Filer"].astype(str).str.contains(q, case=False, na=False)
                    ]

                date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                if date_parsed.notna().any():
                    min_d = date_parsed.min().date()
                    max_d = date_parsed.max().date()
                    _date_val = st.date_input(
                        "Date range",
                        (min_d, max_d),
                        key="member_activity_dates",
                        help="Restrict results to activities within this date range.",
                    )
                    d_from, d_to = (_date_val if isinstance(_date_val, (list, tuple)) and len(_date_val) == 2 else (min_d, max_d))
                    if d_from and d_to:
                        mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                        filt = filt[mask]

                show_cols = ["Date", "Type", "Lobbyist", "Has TFL Client", "Description", "Amount"]
                show_cols = [c for c in show_cols if c in filt.columns]
                st.caption(f"{len(filt):,} rows")
                st.dataframe(filt[show_cols], width="stretch", height=560, hide_index=True)
                _ = export_dataframe(filt[show_cols], "member_activities.csv")

        with tab_staff:
            st.markdown('<div class="section-title">Staff Who Became Lobbyists</div>', unsafe_allow_html=True)
            if staff_lobbyists.empty:
                st.info("No staff matches found who appear in lobbyist records.")
            else:
                cols = ["Session", "Legislator", "Title", "Staffer", "Lobbyist", "LobbyShort", "source"]
                cols = [c for c in cols if c in staff_lobbyists.columns]
                staff_view = staff_lobbyists[cols].drop_duplicates().rename(columns={"LobbyShort": "Last name + first initial"})
                sort_cols = [c for c in ["Session", "Legislator", "Staffer"] if c in staff_view.columns]
                if sort_cols:
                    staff_view = staff_view.sort_values(sort_cols)
                st.dataframe(staff_view, width="stretch", height=420, hide_index=True)
                _ = export_dataframe(staff_view, "member_staff_to_lobbyists.csv")

        st.markdown(
            """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            [data-testid="stToolbar"] {visibility: hidden;}
            </style>
            """,
            unsafe_allow_html=True,
        )

            # =========================================================
    finally:
        _pop_context(_previous, ctx)

