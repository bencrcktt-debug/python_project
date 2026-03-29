from __future__ import annotations

from typing import Any

from tfl_app.services import WorkspaceServices

from . import _workspace_core as _core
from .context_adapters import merge_workspace_runtime_context, normalize_client_workspace_context

# Keep the shared helper namespace stable while this module owns the client renderer.
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
    return merge_workspace_runtime_context(normalize_client_workspace_context(ctx), services)

def render_client_workspace(ctx: Any, services: WorkspaceServices | None = None) -> None:
    ctx = _runtime_ctx(ctx, services)
    _previous = _push_context(ctx)
    try:
        tab_all, tab_overview, tab_lobbyists, tab_bills, tab_policy, tab_activities, tab_disclosures, tab_staff = st.tabs(
            [
                "1. Portfolio Baseline (Read First)",
                "2. Selected Client",
                "3. Contracted Lobbyists",
                "4. Bills & Outcomes",
                "5. Policy Subjects",
                "6. Spending Activity",
                "7. Disclosures",
                "8. Staff Links",
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
            st.markdown('<div class="section-title">All Clients Overview</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="section-sub">Scope: {st.session_state.client_scope}</div>', unsafe_allow_html=True)

            if all_clients.empty:
                st.info("No Texas Ethics Commission lobby filing rows found for the selected scope/session.")
            else:
                a1, a2, a3, a4 = st.columns(4)
                with a1:
                    kpi_card(
                        "Total Taxpayer Funded",
                        f"{fmt_usd(all_stats.get('tfl_low_total', 0.0))} - {fmt_usd(all_stats.get('tfl_high_total', 0.0))}",
                        help_text="Sum of reported low/high compensation for taxpayer-funded clients in this scope.",
                    )
                with a2:
                    kpi_card(
                        "Total Private",
                        f"{fmt_usd(all_stats.get('pri_low_total', 0.0))} - {fmt_usd(all_stats.get('pri_high_total', 0.0))}",
                        help_text="Sum of reported low/high compensation for private clients in this scope.",
                    )
                with a3:
                    kpi_card(
                        "Total Clients",
                        f"{all_stats.get('total_clients', 0):,}",
                        help_text="Unique client count in the selected scope.",
                    )
                    kpi_card(
                        "Taxpayer Funded Clients",
                        f"{all_stats.get('tfl_clients', 0):,}",
                        help_text="Count of clients marked as taxpayer-funded in this scope.",
                    )
                with a4:
                    kpi_card(
                        "Private Clients",
                        f"{all_stats.get('private_clients', 0):,}",
                        help_text="Count of clients marked as private in this scope.",
                    )

                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                st.markdown('<div class="section-title">Political Subdivision Matching</div>', unsafe_allow_html=True)
                st.markdown(
                    """
            <div class="callout geo-note">
              <div class="callout-title">Cross-Page Workflow</div>
              <div class="callout-body">Use <b>Map &amp; Address</b> to test jurisdiction overlap, then return here to validate each matched entity's contracts, bills, and disclosures.</div>
            </div>
            """,
                    unsafe_allow_html=True,
                )
                if st.button("Open Map & Address page", key="client_open_map_page_btn", width="content"):
                    st.switch_page(_map_page)
                st.caption(f"Source web app: [TEA School District Locator]({TEA_ARCGIS_WEBAPP_URL}).")

                client_chart_payload = _chart_runtime.build_client_overview_chart_payload(
                    _chart_runtime.stable_json_signature(
                        {
                            "scope": st.session_state.get("client_scope", ""),
                            "session": st.session_state.get("client_session", ""),
                            "category_rows": int(len(client_scope_bundle.category_chart_data)),
                        }
                    ),
                    client_scope_bundle.category_chart_data,
                    all_stats,
                )
                mix_left, mix_right = st.columns([1, 2])
                with mix_left:
                    st.markdown('<div class="section-sub">Funding Mix (Midpoint)</div>', unsafe_allow_html=True)
                    mix_df = client_chart_payload["mix_df"]
                    if mix_df["Total"].sum() > 0:
                        fig_mix = px.pie(
                            mix_df,
                            names="Funding",
                            values="Total",
                            hole=0.55,
                            color="Funding",
                            color_discrete_map=FUNDING_COLOR_MAP,
                        )
                        fig_mix.update_traces(
                            textposition="inside",
                            textinfo="percent+label",
                            insidetextorientation="radial",
                            marker=dict(line=dict(color="rgba(7,22,39,0.9)", width=2)),
                            hovertemplate="%{label}: %{percent}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_mix, showlegend=False, margin_top=12)
                        fig_mix.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
                        st.plotly_chart(fig_mix, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("No totals available for funding mix.")

                with mix_right:
                    st.markdown('<div class="section-sub">Expenditure by Category (85th-89th, Taxpayer Funded)</div>', unsafe_allow_html=True)
                    cat_group = client_chart_payload["cat_group"]
                    if not cat_group.empty:
                        session_labels = client_chart_payload["session_labels"]
                        cat_order = client_chart_payload["category_order"]
                        fig_cat = px.bar(
                            cat_group,
                            x="SessionLabel",
                            y="Total",
                            color="Category",
                            barmode="stack",
                            category_orders={"SessionLabel": session_labels, "Category": cat_order},
                            color_discrete_sequence=CHART_COLORS,
                        )
                        fig_cat.update_traces(
                            hovertemplate="%{x}<br>%{fullData.name}: $%{y:,.0f}<extra></extra>"
                        )
                        _apply_plotly_layout(fig_cat, showlegend=True, legend_title="Category", margin_top=16)
                        fig_cat.update_layout(
                            bargap=0.22,
                            hovermode="x unified",
                            legend=dict(
                                orientation="h",
                                yanchor="top",
                                y=-0.22,
                                xanchor="left",
                                x=0,
                                font=dict(size=11, color="rgba(235,245,255,0.75)"),
                            ),
                        )
                        fig_cat.update_yaxes(
                            tickprefix="$",
                            tickformat="~s",
                            showgrid=True,
                            gridcolor="rgba(255,255,255,0.08)",
                        )
                        fig_cat.update_xaxes(title_text="", tickfont=dict(color="rgba(235,245,255,0.8)"))
                        st.plotly_chart(fig_cat, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("No taxpayer funded category totals available for 85th-89th sessions.")

                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

                t1, t2 = st.columns(2)
                with t1:
                    st.markdown('<div class="section-title">Top 5 Taxpayer Funded Clients</div>', unsafe_allow_html=True)
                    top_tfl = all_clients[all_clients["IsTFL"] == 1]
                    if not top_tfl.empty:
                        top_tfl = top_tfl.sort_values(["High", "Low"], ascending=[False, False]).head(5)
                        top_tfl["Taxpayer Funded Total"] = top_tfl["Low"].map(fmt_usd) + " - " + top_tfl["High"].map(fmt_usd)
                        st.dataframe(
                            top_tfl[["Client", "Taxpayer Funded Total"]],
                            width="stretch",
                            height=240,
                            hide_index=True,
                        )
                    else:
                        st.info("No taxpayer funded clients found for the selected scope/session.")

                with t2:
                    st.markdown('<div class="section-title">Top 5 Private Clients</div>', unsafe_allow_html=True)
                    top_pri = all_clients[all_clients["IsTFL"] == 0]
                    if not top_pri.empty:
                        top_pri = top_pri.sort_values(["High", "Low"], ascending=[False, False]).head(5)
                        top_pri["Private Total"] = top_pri["Low"].map(fmt_usd) + " - " + top_pri["High"].map(fmt_usd)
                        st.dataframe(
                            top_pri[["Client", "Private Total"]],
                            width="stretch",
                            height=240,
                            hide_index=True,
                        )
                    else:
                        st.info("No private clients found for the selected scope/session.")

                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                st.markdown('<div class="section-title">Taxpayer Funded Breakdown</div>', unsafe_allow_html=True)

                tfl_breakdown = all_clients[all_clients["IsTFL"] == 1]
                if tfl_breakdown.empty:
                    st.info("No taxpayer funded clients found for the selected scope/session.")
                else:
                    tfl_breakdown = ensure_cols(tfl_breakdown, {"Category": "Other", "Entity Type": "Other"})
                    tfl_breakdown["Category"] = tfl_breakdown["Category"].fillna("Other").astype(str)
                    tfl_breakdown["Entity Type"] = tfl_breakdown["Entity Type"].fillna("Other").astype(str)

                    by_category = (
                        tfl_breakdown.groupby("Category", as_index=False)
                        .agg(Clients=("Client", "nunique"), Low=("Low", "sum"), High=("High", "sum"))
                        .sort_values(["Clients", "High", "Low"], ascending=[False, False, False])
                    )
                    by_type = (
                        tfl_breakdown.groupby("Entity Type", as_index=False)
                        .agg(Clients=("Client", "nunique"), Low=("Low", "sum"), High=("High", "sum"))
                        .sort_values(["Clients", "High", "Low"], ascending=[False, False, False])
                    )

                    for df in (by_category, by_type):
                        df["Total Compensation"] = df["Low"].map(fmt_usd) + " - " + df["High"].map(fmt_usd)

                    b1, b2 = st.columns(2)
                    with b1:
                        st.markdown('<div class="section-sub">By Category</div>', unsafe_allow_html=True)
                        st.dataframe(
                            by_category[["Category", "Clients", "Total Compensation"]],
                            width="stretch",
                            height=360,
                            hide_index=True,
                        )
                    with b2:
                        st.markdown('<div class="section-sub">By Entity Type</div>', unsafe_allow_html=True)
                        st.dataframe(
                            by_type[["Entity Type", "Clients", "Total Compensation"]],
                            width="stretch",
                            height=360,
                            hide_index=True,
                        )

                st.session_state.client_filter = st.text_input(
                    "Filter client (contains)",
                    placeholder="e.g., Austin",
                    key="client_filter_input",
                    help="Filter the All Clients table by a name substring.",
                )

                view = all_clients
                if st.session_state.client_filter.strip():
                    view = view[
                        view["Client"].astype(str).str.contains(st.session_state.client_filter.strip(), case=False, na=False)
                    ]

                view_disp = view.copy()
                view_disp["Taxpayer Funded"] = view_disp["IsTFL"].map({1: "Yes", 0: "No"})
                view_disp["Low"] = _fmt_usd_series(view_disp["Low"])
                view_disp["High"] = _fmt_usd_series(view_disp["High"])

                show_cols = ["Client", "Taxpayer Funded", "Lobbyists", "Low", "High"]
                st.dataframe(
                    view_disp[show_cols].sort_values(["Taxpayer Funded", "Client"], ascending=[False, True]),
                    width="stretch",
                    height=560,
                    hide_index=True,
                )
                _ = export_dataframe(view_disp[show_cols], "all_clients_overview.csv", label="Download overview CSV")

        def _no_client_msg():
            st.info("Type a client name at the top to view details. The All Clients tab is available without a selection.")

        if not st.session_state.client_name:
            with tab_overview:
                _no_client_msg()
            with tab_lobbyists:
                _no_client_msg()
            with tab_bills:
                _no_client_msg()
            with tab_policy:
                _no_client_msg()
            with tab_staff:
                _no_client_msg()
            with tab_activities:
                _no_client_msg()
            with tab_disclosures:
                _no_client_msg()
            return

        session = str(st.session_state.client_session).strip()
        client_norm = str(ctx.get("client_norm", "")).strip() or norm_name(st.session_state.client_name)
        if ctx.get("_prepared_client_workspace"):
            client_rows_all = ctx.get("client_rows_all", pd.DataFrame())
            client_lt = ctx.get("client_lt", pd.DataFrame())
            if not ctx.get("client_has_rows", False):
                with tab_overview:
                    if not client_rows_all.empty:
                        st.info("No rows found for this client in the selected session. Try another session.")
                    else:
                        st.info("No rows found for this client.")
                with tab_lobbyists:
                    _no_client_msg()
                with tab_bills:
                    _no_client_msg()
                with tab_policy:
                    _no_client_msg()
                with tab_staff:
                    _no_client_msg()
                with tab_activities:
                    _no_client_msg()
                with tab_disclosures:
                    _no_client_msg()
                return

            lobbyist_totals = ctx.get("lobbyist_totals", pd.DataFrame())
            top_lobbyist_label = str(ctx.get("top_lobbyist_label", "")).strip()
            top_lobbyist_short = str(ctx.get("top_lobbyist_short", "")).strip()
            lobbyshorts = list(ctx.get("lobbyshorts", []) or [])
            lobbyshort_norms = set(ctx.get("lobbyshort_norms", set()) or set())
            lobbyshort_to_name = dict(ctx.get("lobbyshort_to_name", {}) or {})
            lobbyist_names = list(ctx.get("lobbyist_names", []) or [])
            lobbyist_norms = set(ctx.get("lobbyist_norms", set()) or set())
            lobbyist_norms_tuple = tuple(ctx.get("lobbyist_norms_tuple", ()) or ())
            client_is_tfl = bool(ctx.get("client_is_tfl", False))
            total_low = float(ctx.get("total_low", 0.0) or 0.0)
            total_high = float(ctx.get("total_high", 0.0) or 0.0)
            wit = ctx.get("wit", pd.DataFrame())
            bills = ctx.get("bills", pd.DataFrame())
            bill_subjects = ctx.get("bill_subjects", pd.DataFrame())
            mentions = ctx.get("mentions", pd.DataFrame())
            lobby_sub_counts = ctx.get("lobby_sub_counts", pd.DataFrame())
            activities = ctx.get("activities", pd.DataFrame())
            disclosures = ctx.get("disclosures", pd.DataFrame())
            staff_pick = ctx.get("staff_pick", pd.DataFrame())
            staff_pick_session = ctx.get("staff_pick_session", pd.DataFrame())
            staff_stats = ctx.get("staff_stats", pd.DataFrame())
        else:
            data = _workspace_data_with_lazy_tables(
                ctx,
                (
                    "Fiscal_Impact",
                    "Bill_Sub_All",
                    "Lobby_Sub_All",
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
            Fiscal_Impact = data["Fiscal_Impact"]
            Bill_Sub_All = data["Bill_Sub_All"]
            Lobby_Sub_All = data["Lobby_Sub_All"]
            LaCvr = data["LaCvr"]
            LaDock = data["LaDock"]
            LaI4E = data["LaI4E"]
            LaSub = data["LaSub"]

            _client_norms = norm_name_series(Lobby_TFL_Client_All["Client"])
            client_rows_all = Lobby_TFL_Client_All[_client_norms == client_norm]

            tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
            client_lt = client_rows_all[client_rows_all["Session"].astype(str).str.strip() == tfl_session]
            client_lt = ensure_cols(
                client_lt,
                {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0, "LobbyShort": "", "Lobby Name": ""},
            )

            if client_lt.empty:
                with tab_overview:
                    if not client_rows_all.empty:
                        st.info("No rows found for this client in the selected session. Try another session.")
                    else:
                        st.info("No rows found for this client.")
                with tab_lobbyists:
                    _no_client_msg()
                with tab_bills:
                    _no_client_msg()
                with tab_policy:
                    _no_client_msg()
                with tab_staff:
                    _no_client_msg()
                with tab_activities:
                    _no_client_msg()
                with tab_disclosures:
                    _no_client_msg()
                return

            lobbyist_totals = (
                client_lt.groupby("LobbyShort", as_index=False)
                .agg(
                    Low=("Low_num", "sum"),
                    High=("High_num", "sum"),
                    LobbyName=("Lobby Name", _first_nonempty),
                )
            )
            lobbyist_totals = lobbyist_totals.rename(columns={"LobbyName": "Lobby Name"})
            lobbyist_totals["Lobbyist"] = lobbyist_totals["Lobby Name"].fillna("").astype(str).str.strip()
            lobbyist_totals["Lobbyist"] = lobbyist_totals["Lobbyist"].where(
                lobbyist_totals["Lobbyist"] != "", lobbyist_totals["LobbyShort"]
            )
            lobbyist_totals = lobbyist_totals.sort_values(["High", "Low"], ascending=[False, False])
            top_lobbyist_label = ""
            top_lobbyist_short = ""
            if not lobbyist_totals.empty:
                top_lobby_row = lobbyist_totals.iloc[0]
                top_lobbyist_label = str(top_lobby_row.get("Lobbyist", "")).strip()
                top_lobbyist_short = str(top_lobby_row.get("LobbyShort", "")).strip()

            lobbyshorts = lobbyist_totals["LobbyShort"].dropna().astype(str).unique().tolist()
            lobbyshort_norms = {norm_name(s) for s in lobbyshorts if s}
            lobbyshort_to_name = dict(zip(lobbyist_totals["LobbyShort"], lobbyist_totals["Lobbyist"]))

            lobbyist_names = lobbyist_totals["Lobbyist"].dropna().astype(str).tolist()
            lobbyist_norms = set()
            for name in lobbyist_names + lobbyshorts:
                lobbyist_norms |= norm_person_variants(name)
                init_key = _last_first_initial_key(name)
                if init_key:
                    lobbyist_norms.add(init_key)
            lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))

            client_is_tfl = bool((client_lt["IsTFL"] == 1).any())
            total_low = float(client_lt["Low_num"].sum()) if not client_lt.empty else 0.0
            total_high = float(client_lt["High_num"].sum()) if not client_lt.empty else 0.0

            wit_all = Wit_All
            if "LobbyShortNorm" not in wit_all.columns:
                wit_all = wit_all.copy()
                wit_all["LobbyShortNorm"] = norm_name_series(wit_all["LobbyShort"])
            session_col = wit_all["Session"].astype(str).str.strip()
            wit = wit_all[(session_col == session) & (wit_all["LobbyShortNorm"].isin(lobbyshort_norms))]
            if not wit.empty:
                norm_to_short = {norm_name(s): s for s in lobbyshorts if s}
                wit["LobbyShort"] = wit["LobbyShortNorm"].map(norm_to_short).fillna(wit["LobbyShort"])

            bill_pos = bill_position_from_flags(wit)
            bills = (
                bill_pos.merge(Bill_Status_All, on=["Session", "Bill"], how="left")
                if not bill_pos.empty else
                pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Position", "Author", "Caption", "Status"])
            )

            if not wit.empty and "org" in wit.columns:
                orgs = wit
                orgs["Organization"] = orgs.get("org", "").fillna("").astype(str).str.strip()
                orgs = orgs.groupby(["Session", "Bill", "LobbyShort"])["Organization"].apply(
                    lambda s: ", ".join(sorted({x for x in s if x}))
                ).reset_index()
                bills = bills.merge(orgs, on=["Session", "Bill", "LobbyShort"], how="left")

            if not bills.empty:
                fi = Fiscal_Impact[Fiscal_Impact["Session"].astype(str).str.strip() == session]
                if not fi.empty and {"Version", "EstimatedTwoYearNetImpactGR"}.issubset(fi.columns):
                    fi["Version"] = fi["Version"].astype(str).str.upper().str.strip()
                    fi["EstimatedTwoYearNetImpactGR"] = pd.to_numeric(fi["EstimatedTwoYearNetImpactGR"], errors="coerce").fillna(0)
                    fi_p = (
                        fi.groupby(["Session", "Bill", "Version"], as_index=False)["EstimatedTwoYearNetImpactGR"]
                          .sum()
                          .pivot(index=["Session", "Bill"], columns="Version", values="EstimatedTwoYearNetImpactGR")
                          .reset_index()
                          .rename(columns={"H": "Fiscal Impact H", "S": "Fiscal Impact S"})
                    )
                    bills = bills.merge(fi_p, on=["Session", "Bill"], how="left")

            bills = ensure_cols(bills, {"LobbyShort": "", "Organization": "", "Fiscal Impact H": 0, "Fiscal Impact S": 0})
            bills["Lobbyist"] = bills.get("LobbyShort", "").map(lobbyshort_to_name).fillna(bills.get("LobbyShort", ""))

            bill_subjects = Bill_Sub_All[Bill_Sub_All["Session"].astype(str).str.strip() == session].merge(
                bills[["Session", "Bill"]].drop_duplicates(), on=["Session", "Bill"], how="inner"
            )
            if not bill_subjects.empty:
                mentions = (
                    bill_subjects.groupby("Subject")["Bill"]
                    .nunique()
                    .reset_index(name="Mentions")
                    .sort_values("Mentions", ascending=False)
                )
                total_mentions = int(mentions["Mentions"].sum()) or 1
                mentions["Share"] = (mentions["Mentions"] / total_mentions).fillna(0)
            else:
                mentions = pd.DataFrame(columns=["Subject", "Mentions", "Share"])

            lobby_sub = Lobby_Sub_All
            if "Session" in lobby_sub.columns:
                lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == session]
            elif "session" in lobby_sub.columns:
                lobby_sub = lobby_sub[lobby_sub["session"].astype(str).str.strip() == session]
            if "LobbyShortNorm" in lobby_sub.columns:
                lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"].isin(lobbyshort_norms)]
            elif "LobbyShort" in lobby_sub.columns:
                lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip().isin(lobbyshorts)]
            else:
                lobby_sub = lobby_sub.iloc[0:0]

            if not lobby_sub.empty:
                lobby_sub = lobby_sub.assign(
                    Subject=lobby_sub.get("Subject Matter", "").fillna("").astype(str).str.strip(),
                    Other=lobby_sub.get("Other Subject Matter Description", "").fillna("").astype(str).str.strip(),
                )
                for col in ["Subject", "Other"]:
                    series = lobby_sub[col]
                    lobby_sub[col] = series.where(~series.str.lower().isin(["nan", "none"]), "")

                unnamed0 = lobby_sub.get("Unnamed: 0")
                if not isinstance(unnamed0, pd.Series):
                    unnamed0 = lobby_sub.get("Column1")
                if not isinstance(unnamed0, pd.Series):
                    unnamed0 = pd.Series([""] * len(lobby_sub), index=lobby_sub.index)
                unnamed0 = unnamed0.fillna("").astype(str).str.strip()
                unnamed0 = unnamed0.where(~unnamed0.str.lower().isin(["nan", "none"]), "")

                topic = lobby_sub["Subject"]
                topic = topic.where(topic != "", lobby_sub["Other"])
                topic = topic.where(topic != "", unnamed0)
                topic = topic.where(topic != "", "Unspecified")
                lobby_sub["Topic"] = topic

                lobby_sub_counts = (
                    lobby_sub.groupby("Topic")
                    .size()
                    .reset_index(name="Mentions")
                    .sort_values("Mentions", ascending=False)
                )
            else:
                lobby_sub_counts = pd.DataFrame(columns=["Topic", "Mentions"])

            activities = build_activities_multi(
                data["LaFood"], data["LaEnt"], data["LaTran"], data["LaGift"], data["LaEvnt"], data["LaAwrd"],
                lobbyshorts=lobbyshorts,
                session=session,
                name_to_short=name_to_short,
                lobbyist_norms_tuple=lobbyist_norms_tuple,
                filerid_to_short=data.get("filerid_to_short", {}),
                lobbyshort_to_name=lobbyshort_to_name,
            )

            disclosures = build_disclosures_multi(
                LaCvr, LaDock, LaI4E, LaSub,
                lobbyshorts=lobbyshorts,
                session=session,
                name_to_short=name_to_short,
                lobbyist_norms_tuple=lobbyist_norms_tuple,
                filerid_to_short=data.get("filerid_to_short", {}),
                lobbyshort_to_name=lobbyshort_to_name,
            )

            staff_df = Staff_All
            staff_session = staff_df["Session"].astype(str).str.strip() == session if "Session" in staff_df.columns else pd.Series(False, index=staff_df.index)

            last_names = {last_name_norm_from_text(n) for n in lobbyist_names if last_name_norm_from_text(n)}
            init_map = {k: v for k, v in ((_last_first_initial_key(n), n) for n in lobbyist_names) if k}
            full_map = {norm_name(n): n for n in lobbyist_names if n}
            last_map = {k: v for k, v in ((last_name_norm_from_text(n), n) for n in lobbyist_names) if k}

            match_mask = pd.Series(False, index=staff_df.index)
            if lobbyist_norms:
                match_mask = match_mask | staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
            if last_names:
                match_mask = match_mask | staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)).isin(last_names)
            if lobbyshort_norms:
                match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyshort_norms)

            staff_pick = staff_df[match_mask]
            staff_pick_session = staff_df[staff_session & match_mask]

            if not staff_pick.empty:
                staff_pick["Matched Lobbyist"] = (
                    staff_pick.get("StaffNameNorm", pd.Series([""] * len(staff_pick))).map(full_map)
                    .fillna(staff_pick.get("StaffLastInitialNorm", pd.Series([""] * len(staff_pick))).map(init_map))
                    .fillna(staff_pick.get("StaffLastNorm", pd.Series([""] * len(staff_pick))).map(last_map))
                )

            staff_stats = _staff_metrics(staff_pick_session, bills, session, Bill_Status_All) if not staff_pick_session.empty else pd.DataFrame()

        with tab_overview:
            st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)
            o1, o2, o3, o4 = st.columns(4)
            with o1:
                kpi_card(
                    "Session",
                    session,
                    f"Scope: {st.session_state.client_scope}",
                    help_text="Session used for detail tables; scope shows whether totals are this session or all sessions.",
                )
            with o2:
                kpi_card(
                    "Client",
                    st.session_state.client_name,
                    help_text="Resolved client selection from search or suggestions.",
                )
            with o3:
                kpi_card(
                    "Taxpayer Funded?",
                    "Yes" if client_is_tfl else "No",
                    help_text="Whether the selected client is marked as taxpayer-funded in the data.",
                )
            with o4:
                kpi_card(
                    "Total Compensation",
                    f"{fmt_usd(total_low)} - {fmt_usd(total_high)}",
                    help_text="Sum of reported low/high compensation for this client in the selected scope.",
                )

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

            s1, s2, s3, s4 = st.columns(4)
            with s1:
                kpi_card(
                    "Lobbyists",
                    f"{len(lobbyshorts):,}",
                    help_text="Unique lobbyists tied to this client in the selected session.",
                )
            with s2:
                kpi_card(
                    "Total Bills (Witness Lists)",
                    f"{len(bills):,}",
                    help_text="Witness list rows tied to this client in the selected session.",
                )
            with s3:
                passed = int((bills.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not bills.empty else 0
                failed = int((bills.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not bills.empty else 0
                kpi_card(
                    "Passed / Failed",
                    f"{passed:,} / {failed:,}",
                    help_text="Bill outcomes among witness list rows in this view.",
                )
            with s4:
                kpi_card(
                    "Sessions with Client",
                    f"{client_rows_all['Session'].astype(str).nunique():,}",
                    help_text="Number of sessions where this client appears in the data.",
                )

            top_author = ""
            if not bills.empty and "Author" in bills.columns:
                author_series = bills["Author"].fillna("").astype(str).str.strip()
                author_series = author_series[author_series != ""]
                if not author_series.empty:
                    top_author = str(author_series.value_counts().index[0]).strip()

            if top_lobbyist_label:
                st.markdown(
                    f"""
            <div class="handoff-card">
              <div class="handoff-kicker">Cross-Page Handoff</div>
              <div class="handoff-title">Validate Contract And Bill Context</div>
              <div class="handoff-sub">Top contracted lobbyist by midpoint: <strong>{html.escape(top_lobbyist_label, quote=True)}</strong>. Use linked pages to corroborate entity-level findings.</div>
            </div>
            """,
                    unsafe_allow_html=True,
                )
                handoff_cols = st.columns(3 if top_author else 2)
                with handoff_cols[0]:
                    if st.button("Open Top Lobbyist", key="client_handoff_lobby_btn", width="stretch"):
                        search_value = top_lobbyist_label or top_lobbyist_short
                        st.session_state.search_query = search_value
                        st.session_state.session = st.session_state.client_session
                        st.session_state.scope = st.session_state.client_scope
                        st.session_state.lobbyshort = top_lobbyist_short or ""
                        st.session_state.lobby_filerid = None
                        st.switch_page(_lobby_page)
                with handoff_cols[1]:
                    if st.button("Open In Map & Address", key="client_handoff_map_btn", width="stretch"):
                        st.session_state.map_session = st.session_state.client_session
                        st.session_state.map_scope = st.session_state.client_scope
                        st.session_state.map_overlap_entity_filter = st.session_state.client_name
                        st.switch_page(_map_page)
                if top_author:
                    with handoff_cols[2]:
                        if st.button("Open Top Author", key="client_handoff_member_btn", width="stretch"):
                            st.session_state.member_query = top_author
                            st.session_state.member_query_input = top_author
                            st.session_state.member_name = ""
                            st.session_state.member_session = st.session_state.client_session
                            st.switch_page(_member_page)

            st.markdown('<div class="section-sub">Funding Mix (Midpoint)</div>', unsafe_allow_html=True)
            client_tfl_low = float(client_lt.loc[client_lt["IsTFL"] == 1, "Low_num"].sum()) if not client_lt.empty else 0.0
            client_tfl_high = float(client_lt.loc[client_lt["IsTFL"] == 1, "High_num"].sum()) if not client_lt.empty else 0.0
            client_pri_low = float(client_lt.loc[client_lt["IsTFL"] == 0, "Low_num"].sum()) if not client_lt.empty else 0.0
            client_pri_high = float(client_lt.loc[client_lt["IsTFL"] == 0, "High_num"].sum()) if not client_lt.empty else 0.0
            client_mix = pd.DataFrame(
                {
                    "Funding": ["Taxpayer Funded", "Private"],
                    "Total": [
                        (client_tfl_low + client_tfl_high) / 2,
                        (client_pri_low + client_pri_high) / 2,
                    ],
                }
            )
            if client_mix["Total"].sum() > 0:
                fig_client_mix = px.pie(
                    client_mix,
                    names="Funding",
                    values="Total",
                    hole=0.55,
                    color="Funding",
                    color_discrete_map=FUNDING_COLOR_MAP,
                )
                fig_client_mix.update_traces(
                    textposition="inside",
                    textinfo="percent+label",
                    insidetextorientation="radial",
                    marker=dict(line=dict(color="rgba(7,22,39,0.9)", width=2)),
                    hovertemplate="%{label}: %{percent}<extra></extra>",
                )
                _apply_plotly_layout(fig_client_mix, showlegend=False, margin_top=12)
                fig_client_mix.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
                st.plotly_chart(fig_client_mix, width="stretch", config=PLOTLY_CONFIG)
            else:
                st.info("No totals available for funding mix.")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.subheader("Lobbyists Under Contract")
            st.write(", ".join(lobbyist_totals["Lobbyist"].tolist()) if not lobbyist_totals.empty else "-")

        with tab_lobbyists:
            st.markdown('<div class="section-title">Lobbyists</div>', unsafe_allow_html=True)
            if lobbyist_totals.empty:
                st.info("No lobbyists found for this client in the selected session.")
            else:
                view = lobbyist_totals.copy()
                view["Low"] = _fmt_usd_series(view["Low"])
                view["High"] = _fmt_usd_series(view["High"])
                view_disp = view.rename(columns={"LobbyShort": "Last name + first initial"})
                show_cols = ["Lobbyist", "Last name + first initial", "Low", "High"]
                show_cols = [c for c in show_cols if c in view_disp.columns]
                st.dataframe(view_disp[show_cols], width="stretch", height=520, hide_index=True)
                _ = export_dataframe(view_disp[show_cols], "client_lobbyists.csv")
                if top_lobbyist_label:
                    st.markdown(
                        f"""
            <div class="handoff-card">
              <div class="handoff-kicker">Intra-Page Bridge</div>
              <div class="handoff-title">Use Contracted Lobbyist Detail In Bill Analysis</div>
              <div class="handoff-sub">Largest contracted lobbyist in this profile: <strong>{html.escape(top_lobbyist_label, quote=True)}</strong>. Move directly to lobbyist profile or prefill Bills-tab filters.</div>
            </div>
            """,
                        unsafe_allow_html=True,
                    )
                    lnav1, lnav2 = st.columns(2)
                    with lnav1:
                        if st.button("Open Top Lobbyist", key="client_lobby_tab_open_lobby_btn", width="stretch"):
                            search_value = top_lobbyist_label or top_lobbyist_short
                            st.session_state.search_query = search_value
                            st.session_state.session = st.session_state.client_session
                            st.session_state.scope = st.session_state.client_scope
                            st.session_state.lobbyshort = top_lobbyist_short or ""
                            st.session_state.lobby_filerid = None
                            st.switch_page(_lobby_page)
                    with lnav2:
                        if st.button("Use In Bills Tab Search", key="client_lobby_tab_seed_bills_btn", width="stretch"):
                            st.session_state.client_bill_search = top_lobbyist_label
                            st.session_state.client_bill_search_input = top_lobbyist_label
                            st.success("Bills tab search is prefilled with the top contracted lobbyist.")

        with tab_bills:
            st.markdown('<div class="section-title">Bills with Witness-List Activity</div>', unsafe_allow_html=True)
            if bills.empty:
                st.info("No witness-list rows found for lobbyists tied to this client/session.")
            else:
                st.session_state.client_bill_search = st.text_input(
                    "Search bills (Bill / Author / Caption / Organization)",
                    placeholder="e.g., HB 4 or housing",
                    key="client_bill_search_input",
                    help="Filter bills by bill number, author, caption, organization, or lobbyist.",
                )
                filtered = bills
                if st.session_state.client_bill_search.strip():
                    q = st.session_state.client_bill_search.strip()
                    filtered = filtered[
                        filtered["Bill"].astype(str).str.contains(q, case=False, na=False) |
                        filtered["Author"].astype(str).str.contains(q, case=False, na=False) |
                        filtered["Caption"].astype(str).str.contains(q, case=False, na=False) |
                        filtered["Organization"].astype(str).str.contains(q, case=False, na=False) |
                        filtered["Lobbyist"].astype(str).str.contains(q, case=False, na=False)
                    ]

                f1, f2, f3 = st.columns(3)
                with f1:
                    status_opts = _clean_options(
                        filtered.get("Status", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                    )
                    status_opts = sorted(status_opts)
                    status_sel = st.multiselect(
                        "Filter by status",
                        status_opts,
                        default=status_opts,
                        key="client_status_filter",
                        help="Limit results to selected bill statuses.",
                    )
                with f2:
                    pos_opts = _clean_options(
                        filtered.get("Position", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                    )
                    pos_opts = sorted(pos_opts)
                    pos_sel = st.multiselect(
                        "Filter by position",
                        pos_opts,
                        default=pos_opts,
                        key="client_position_filter",
                        help="Limit results to selected witness positions.",
                    )
                with f3:
                    lobby_opts = _clean_options(
                        filtered.get("Lobbyist", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                    )
                    lobby_opts = sorted(lobby_opts)
                    lobby_sel = st.multiselect(
                        "Filter by lobbyist",
                        lobby_opts,
                        default=lobby_opts,
                        key="client_lobbyist_filter",
                        help="Limit results to selected lobbyists.",
                    )

                if status_sel:
                    filtered = filtered[filtered["Status"].astype(str).isin(status_sel)]
                if pos_sel:
                    filtered = filtered[filtered["Position"].astype(str).isin(pos_sel)]
                if lobby_sel:
                    filtered = filtered[filtered["Lobbyist"].astype(str).isin(lobby_sel)]

                for col in ["Fiscal Impact H", "Fiscal Impact S"]:
                    if col in filtered.columns:
                        filtered[col] = pd.to_numeric(filtered[col], errors="coerce").fillna(0)

                show_cols = ["Bill", "Lobbyist", "Organization", "Position", "Author", "Caption", "Fiscal Impact H", "Fiscal Impact S", "Status"]
                show_cols = [c for c in show_cols if c in filtered.columns]
                st.dataframe(filtered[show_cols].sort_values(["Bill", "Lobbyist"]), width="stretch", height=520, hide_index=True)
                top_filtered_author = ""
                top_filtered_lobby_label = ""
                top_filtered_lobby_short = ""
                if not filtered.empty:
                    if "Author" in filtered.columns:
                        author_counts = (
                            filtered["Author"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                        )
                        author_counts = author_counts[author_counts != ""]
                        if not author_counts.empty:
                            top_filtered_author = str(author_counts.value_counts().index[0]).strip()
                    if "Lobbyist" in filtered.columns:
                        lobby_counts = (
                            filtered["Lobbyist"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                        )
                        lobby_counts = lobby_counts[lobby_counts != ""]
                        if not lobby_counts.empty:
                            top_filtered_lobby_label = str(lobby_counts.value_counts().index[0]).strip()
                            if "LobbyShort" in filtered.columns:
                                short_match = (
                                    filtered.loc[
                                        filtered["Lobbyist"].fillna("").astype(str).str.strip() == top_filtered_lobby_label,
                                        "LobbyShort",
                                    ]
                                    .dropna()
                                    .astype(str)
                                    .str.strip()
                                )
                                short_match = short_match[short_match != ""]
                                if not short_match.empty:
                                    top_filtered_lobby_short = str(short_match.iloc[0]).strip()

                if top_filtered_author or top_filtered_lobby_label:
                    handoff_bits = []
                    if top_filtered_author:
                        handoff_bits.append(f"Frequent author: {top_filtered_author}.")
                    if top_filtered_lobby_label:
                        handoff_bits.append(f"Most active lobbyist in current slice: {top_filtered_lobby_label}.")
                    st.markdown(
                        f"""
            <div class="handoff-card">
              <div class="handoff-kicker">Cross-Tab Continuity</div>
              <div class="handoff-title">Carry This Bills Slice Across Workspaces</div>
              <div class="handoff-sub">{html.escape(' '.join(handoff_bits), quote=True)}</div>
            </div>
            """,
                        unsafe_allow_html=True,
                    )
                    bnav1, bnav2, bnav3 = st.columns(3)
                    with bnav1:
                        if st.button(
                            "Open Frequent Author",
                            key="client_bills_to_member_btn",
                            width="stretch",
                            disabled=not bool(top_filtered_author),
                        ):
                            st.session_state.member_query = top_filtered_author
                            st.session_state.member_query_input = top_filtered_author
                            st.session_state.member_name = ""
                            st.session_state.member_session = st.session_state.client_session
                            st.switch_page(_member_page)
                    with bnav2:
                        if st.button(
                            "Open Top Lobbyist",
                            key="client_bills_to_lobby_btn",
                            width="stretch",
                            disabled=not bool(top_filtered_lobby_label),
                        ):
                            st.session_state.search_query = top_filtered_lobby_label or top_filtered_lobby_short
                            st.session_state.session = st.session_state.client_session
                            st.session_state.scope = st.session_state.client_scope
                            st.session_state.lobbyshort = top_filtered_lobby_short or ""
                            st.session_state.lobby_filerid = None
                            st.switch_page(_lobby_page)
                    with bnav3:
                        if st.button(
                            "Carry Filtered Bills To Policy",
                            key="client_bills_focus_policy_btn",
                            width="stretch",
                            disabled=filtered.empty,
                        ):
                            focus_bills = (
                                filtered.get("Bill", pd.Series(dtype=object))
                                .dropna()
                                .astype(str)
                                .str.strip()
                            )
                            focus_bills = focus_bills[focus_bills != ""].drop_duplicates().tolist()
                            st.session_state.client_policy_focus = {
                                "session": session,
                                "client_norm": client_norm,
                                "bill_ids": focus_bills[:500],
                            }
                            st.success(
                                f"Policy tab is now focused to {len(focus_bills):,} bill(s) from this Bills view."
                            )
                _ = export_dataframe(filtered[show_cols], "client_bills.csv")

        with tab_policy:
            st.markdown('<div class="section-title">Policy Areas</div>', unsafe_allow_html=True)
            policy_focus = st.session_state.get("client_policy_focus", {})
            focus_bill_ids = []
            focus_active = False
            if isinstance(policy_focus, dict):
                focus_session = str(policy_focus.get("session", "")).strip()
                focus_client_norm = str(policy_focus.get("client_norm", "")).strip()
                if focus_session == session and focus_client_norm == client_norm:
                    focus_bill_ids = [
                        str(b).strip()
                        for b in policy_focus.get("bill_ids", [])
                        if str(b).strip()
                    ]
                    focus_active = bool(focus_bill_ids)
            if focus_active:
                p_focus_left, p_focus_right = st.columns([4, 1])
                with p_focus_left:
                    st.caption(
                        f"Focused to {len(focus_bill_ids):,} bill(s) carried from Bills tab filters."
                    )
                with p_focus_right:
                    if st.button("Clear Bills Focus", key="client_policy_focus_clear_btn", width="stretch"):
                        st.session_state.client_policy_focus = {}
                        focus_active = False
                        focus_bill_ids = []

            policy_mentions = mentions
            if focus_active:
                focus_norm = {
                    re.sub(r"\s+", " ", bill.upper()).strip()
                    for bill in focus_bill_ids
                    if bill
                }
                focus_subjects = bill_subjects
                if not focus_subjects.empty and focus_norm:
                    focus_subjects["BillNorm"] = (
                        focus_subjects["Bill"]
                        .fillna("")
                        .astype(str)
                        .str.upper()
                        .str.replace(r"\s+", " ", regex=True)
                        .str.strip()
                    )
                    focus_subjects = focus_subjects[focus_subjects["BillNorm"].isin(focus_norm)]
                    focus_subjects = focus_subjects[focus_subjects["Subject"].fillna("").astype(str).str.strip() != ""]
                    if not focus_subjects.empty:
                        policy_mentions = (
                            focus_subjects.groupby("Subject")["Bill"]
                            .nunique()
                            .reset_index(name="Mentions")
                            .sort_values("Mentions", ascending=False)
                        )
                        total_mentions = int(policy_mentions["Mentions"].sum()) or 1
                        policy_mentions["Share"] = (policy_mentions["Mentions"] / total_mentions).fillna(0)
                    else:
                        policy_mentions = pd.DataFrame(columns=["Subject", "Mentions", "Share"])
                else:
                    policy_mentions = pd.DataFrame(columns=["Subject", "Mentions", "Share"])

            if policy_mentions.empty:
                if focus_active:
                    st.info("No bill-subject rows matched the focused Bills-tab slice. Clear focus or broaden filters.")
                else:
                    st.info("No subjects found (Texas Legislature Online bill subject data returned 0 rows).")
            else:
                chart_mentions = policy_mentions
                chart_mentions["SharePct"] = (chart_mentions["Share"] * 100).round(1)
                chart_mentions = chart_mentions.sort_values("Share", ascending=False)
                top_mentions = chart_mentions.head(20)
                c1, c2 = st.columns(2)
                with c1:
                    fig_share = px.bar(
                        top_mentions,
                        x="SharePct",
                        y="Subject",
                        orientation="h",
                        text="SharePct",
                    )
                    fig_share.update_traces(
                        texttemplate="%{text:.1f}%",
                        textposition="outside",
                        marker_color="#1e90ff",
                        cliponaxis=False,
                        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
                    )
                    _apply_plotly_layout(fig_share, showlegend=False, margin_top=12)
                    fig_share.update_layout(margin=dict(l=8, r=36, t=12, b=8))
                    fig_share.update_xaxes(
                        showgrid=True,
                        gridcolor="rgba(255,255,255,0.08)",
                        ticksuffix="%",
                        title_text="Share (%)",
                    )
                    fig_share.update_yaxes(title_text="", categoryorder="total descending")
                    st.plotly_chart(fig_share, width="stretch", config=PLOTLY_CONFIG)
                with c2:
                    fig_tree = px.treemap(
                        top_mentions,
                        path=["Subject"],
                        values="Mentions",
                        color="SharePct",
                        color_continuous_scale=["#0b1a2b", "#1e90ff", "#00e0b8"],
                    )
                    fig_tree.update_traces(
                        hovertemplate="%{label}<br>%{value} mentions (%{color:.1f}%)<extra></extra>"
                    )
                    _apply_plotly_layout(fig_tree, showlegend=False, margin_top=12)
                    fig_tree.update_layout(coloraxis_showscale=False)
                    st.plotly_chart(fig_tree, width="stretch", config=PLOTLY_CONFIG)

                m2 = policy_mentions
                m2["Share"] = (m2["Share"] * 100).round(0).astype("Int64").astype(str) + "%"
                m2 = m2.rename(columns={"Subject": "Policy Area"})
                st.dataframe(m2[["Policy Area", "Mentions", "Share"]], width="stretch", height=520, hide_index=True)
                export_ctx = [f"Bills-tab focus: {len(focus_bill_ids):,} bill(s)"] if focus_active else None
                _ = export_dataframe(m2, "client_policy_areas.csv", context=export_ctx)

                top_policy_subject = str(top_mentions.iloc[0].get("Subject", "")).strip() if not top_mentions.empty else ""
                if top_policy_subject:
                    st.markdown(
                        f"""
            <div class="handoff-card">
              <div class="handoff-kicker">Intra-Page Bridge</div>
              <div class="handoff-title">Reconnect Policy Subjects To Bill Rows</div>
              <div class="handoff-sub">Top policy subject in this view: <strong>{html.escape(top_policy_subject, quote=True)}</strong>. Prefill Bills-tab search or move to policy context.</div>
            </div>
            """,
                        unsafe_allow_html=True,
                    )
                    pnav1, pnav2 = st.columns(2)
                    with pnav1:
                        if st.button("Use Top Subject In Bills Tab", key="client_policy_to_bills_btn", width="stretch"):
                            st.session_state.client_bill_search_seed = top_policy_subject
                            st.rerun()
                    with pnav2:
                        if st.button("Open Policy Context Page", key="client_policy_open_context_btn", width="stretch"):
                            st.switch_page(_solutions_page)

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.subheader("Reported Subject Matters (Texas Ethics Commission filings)")
            if lobby_sub_counts.empty:
                st.info("No Texas Ethics Commission subject-matter rows found for lobbyists tied to this client/session.")
            else:
                top_topics = lobby_sub_counts.head(12)
                max_mentions = int(top_topics["Mentions"].max()) if not top_topics.empty else 0
                topic_chunks = [top_topics.iloc[i:i + 4] for i in range(0, len(top_topics), 4)]
                if topic_chunks:
                    cols = st.columns(len(topic_chunks))
                    for col, chunk in zip(cols, topic_chunks):
                        fig_topic = px.bar(
                            chunk.sort_values("Mentions"),
                            x="Mentions",
                            y="Topic",
                            orientation="h",
                            text="Mentions",
                        )
                        fig_topic.update_traces(
                            textposition="outside",
                            marker_color="#8cc9ff",
                            cliponaxis=False,
                            hovertemplate="%{y}: %{x}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_topic, showlegend=False, height=220, margin_top=8)
                        fig_topic.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                        fig_topic.update_xaxes(
                            showticklabels=False,
                            showgrid=False,
                            range=[0, max_mentions * 1.15] if max_mentions else None,
                            title_text="",
                        )
                        fig_topic.update_yaxes(
                            title_text="",
                            categoryorder="total ascending",
                            tickfont=dict(size=11, color="rgba(235,245,255,0.75)"),
                        )
                        col.plotly_chart(fig_topic, width="stretch", config=PLOTLY_CONFIG)

                st.dataframe(
                    lobby_sub_counts.rename(columns={"Topic": "Subject Matter"}),
                    width="stretch",
                    height=420,
                    hide_index=True,
                )
                _ = export_dataframe(lobby_sub_counts, "client_reported_subject_matters.csv")

        with tab_staff:
            st.markdown('<div class="section-title">Legislative Staffer History</div>', unsafe_allow_html=True)
            if staff_pick.empty:
                st.info("No staff-history rows matched for lobbyists tied to this client.")
            else:
                st.caption("Showing staff history across all sessions.")
                cols = ["Session", "Legislator", "Title", "Staffer", "Matched Lobbyist"]
                cols = [c for c in cols if c in staff_pick.columns]
                staff_view = staff_pick[cols].drop_duplicates()
                sort_cols = [c for c in ["Session", "Legislator", "Title"] if c in staff_view.columns]
                if sort_cols:
                    staff_view = staff_view.sort_values(sort_cols)
                st.dataframe(staff_view, width="stretch", height=380, hide_index=True)
                _ = export_dataframe(staff_view, "client_staff_history.csv")

            if staff_pick_session.empty:
                st.caption("Session-specific staff metrics are not shown because there are no matches for the selected session.")
            elif not staff_stats.empty:
                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                st.caption("Computed from authored bills intersected with this client's lobbyist witness activity.")
                s2 = staff_stats
                for col in ["% Against that Failed", "% For that Passed"]:
                    s2[col] = pd.to_numeric(s2[col], errors="coerce")
                    s2[col] = (s2[col] * 100).round(0)
                st.dataframe(s2, width="stretch", height=320, hide_index=True)
                _ = export_dataframe(s2, "client_staff_stats.csv")

        with tab_activities:
            st.markdown('<div class="section-title">Lobbying Expenditures / Activity</div>', unsafe_allow_html=True)
            if activities.empty:
                st.info("No activity rows found for lobbyists tied to this client/session.")
            else:
                filt = activities
                t_opts = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
                t_opts = sorted(t_opts)
                sel_types = st.multiselect(
                    "Filter by activity type",
                    t_opts,
                    default=t_opts,
                    key="client_activity_types",
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
                    key="client_activity_lobbyist",
                    help="Limit results to selected lobbyists.",
                )
                if sel_lobby:
                    filt = filt[filt["Lobbyist"].isin(sel_lobby)]

                st.session_state.client_activity_search = st.text_input(
                    "Search activities (lobbyist, filer, member, description)",
                    key="client_activity_search_input",
                    help="Search activity rows by lobbyist, filer, member, or description.",
                )
                if st.session_state.client_activity_search.strip():
                    q = st.session_state.client_activity_search.strip()
                    filt = filt[
                        filt["Lobbyist"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Member"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Description"].astype(str).str.contains(q, case=False, na=False)
                    ]

                date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                if date_parsed.notna().any():
                    min_d = date_parsed.min().date()
                    max_d = date_parsed.max().date()
                    _date_val = st.date_input(
                        "Date range",
                        (min_d, max_d),
                        key="client_activity_dates",
                        help="Restrict results to activities within this date range.",
                    )
                    d_from, d_to = (_date_val if isinstance(_date_val, (list, tuple)) and len(_date_val) == 2 else (min_d, max_d))
                    if d_from and d_to:
                        mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                        filt = filt[mask]

                st.caption(f"{len(filt):,} rows")
                st.dataframe(filt, width="stretch", height=560, hide_index=True)
                _ = export_dataframe(filt, "client_activities.csv")

        with tab_disclosures:
            st.markdown('<div class="section-title">Disclosures & Subject Matter Filings</div>', unsafe_allow_html=True)
            if disclosures.empty:
                st.info("No disclosure rows found for lobbyists tied to this client/session.")
            else:
                filt = disclosures
                d_types = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
                d_types = sorted(d_types)
                sel_types = st.multiselect(
                    "Filter by disclosure type",
                    d_types,
                    default=d_types,
                    key="client_disclosure_types",
                    help="Limit results to selected disclosure categories.",
                )
                if sel_types:
                    filt = filt[filt["Type"].isin(sel_types)]

                lobby_opts = _clean_options(filt["Lobbyist"].dropna().astype(str).unique().tolist())
                lobby_opts = sorted(lobby_opts)
                sel_lobby = st.multiselect(
                    "Filter by lobbyist",
                    lobby_opts,
                    default=lobby_opts,
                    key="client_disclosure_lobbyist",
                    help="Limit results to selected lobbyists.",
                )
                if sel_lobby:
                    filt = filt[filt["Lobbyist"].isin(sel_lobby)]

                st.session_state.client_disclosure_search = st.text_input(
                    "Search disclosures (lobbyist, filer, description, entity)",
                    key="client_disclosure_search_input",
                    help="Search disclosure rows by lobbyist, filer, description, or entity.",
                )
                if st.session_state.client_disclosure_search.strip():
                    q = st.session_state.client_disclosure_search.strip()
                    filt = filt[
                        filt["Lobbyist"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Description"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Entity"].astype(str).str.contains(q, case=False, na=False)
                    ]

                date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                if date_parsed.notna().any():
                    min_d = date_parsed.min().date()
                    max_d = date_parsed.max().date()
                    _date_val = st.date_input(
                        "Date range",
                        (min_d, max_d),
                        key="client_disclosure_dates",
                        help="Restrict results to disclosures within this date range.",
                    )
                    d_from, d_to = (_date_val if isinstance(_date_val, (list, tuple)) and len(_date_val) == 2 else (min_d, max_d))
                    if d_from and d_to:
                        mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                        filt = filt[mask]

                st.caption(f"{len(filt):,} rows")
                st.dataframe(filt, width="stretch", height=560, hide_index=True)
                _ = export_dataframe(filt, "client_disclosures.csv")

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
    finally:
        _pop_context(_previous, ctx)

