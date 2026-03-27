from __future__ import annotations

from typing import Any
import html
import re
from datetime import datetime

import pandas as pd
import plotly.express as px
import tfl_app.charts.runtime as _chart_runtime

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _StreamlitStub:
        session_state: dict[str, Any] = {}
    st = _StreamlitStub()

_MISSING = object()

def _push_context(ctx: dict[str, Any]) -> dict[str, Any]:
    previous: dict[str, Any] = {}
    for key, value in ctx.items():
        previous[key] = globals().get(key, _MISSING)
        globals()[key] = value
    return previous

def _pop_context(previous: dict[str, Any], ctx: dict[str, Any]) -> None:
    for key in ctx.keys():
        old_value = previous.get(key, _MISSING)
        if old_value is _MISSING:
            globals().pop(key, None)
        else:
            globals()[key] = old_value


def _resolve_workspace_table(ctx: dict[str, Any], key: str) -> pd.DataFrame:
    ctx_value = ctx.get(key, _MISSING)
    if isinstance(ctx_value, pd.DataFrame):
        return ctx_value

    data = ctx.get("data", {})
    if isinstance(data, dict):
        data_value = data.get(key, _MISSING)
        if isinstance(data_value, pd.DataFrame):
            return data_value

    global_value = globals().get(key, _MISSING)
    if isinstance(global_value, pd.DataFrame):
        return global_value

    single_loader = globals().get("get_app_table")
    path = str(ctx.get("PATH", "")).strip()
    if path and callable(single_loader):
        try:
            loaded = single_loader(path, key)
        except Exception:
            loaded = None
        if isinstance(loaded, pd.DataFrame):
            return loaded

    loader = globals().get("get_app_tables")
    path = str(ctx.get("PATH", "")).strip()
    if path and callable(loader):
        try:
            loaded = loader(path, (key,))
        except Exception:
            return pd.DataFrame()
        loaded_value = loaded.get(key, _MISSING)
        if isinstance(loaded_value, pd.DataFrame):
            return loaded_value

    return pd.DataFrame()


def _workspace_data_with_lazy_tables(ctx: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    data = dict(ctx.get("data", {}) or {})
    if "filerid_to_short" in ctx and "filerid_to_short" not in data:
        data["filerid_to_short"] = ctx.get("filerid_to_short", {}) or {}
    for key in keys:
        table = _resolve_workspace_table(ctx, key)
        if isinstance(table, pd.DataFrame):
            data[key] = table
    return data


def _fmt_usd_series(series: pd.Series) -> pd.Series:
    cleaned = series.fillna("").astype(str).str.strip()
    cleaned = cleaned.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    cleaned = cleaned.str.replace("$", "", regex=False).str.replace(",", "", regex=False)
    cleaned = cleaned.where(~cleaned.str.lower().isin({"", "nan", "none"}), "")
    numeric = pd.to_numeric(cleaned, errors="coerce").fillna(0.0)
    return numeric.map(fmt_usd)


def _staff_metrics(
    staff_rows: pd.DataFrame,
    bills_df: pd.DataFrame,
    session_val: str,
    bill_status_all: pd.DataFrame,
) -> pd.DataFrame:
    if staff_rows.empty or bills_df.empty:
        return pd.DataFrame(columns=["Legislator", "% Against that Failed", "% For that Passed"])

    legs = sorted(staff_rows["Legislator"].dropna().astype(str).unique().tolist())
    out = []
    bs = bill_status_all[bill_status_all["Session"].astype(str).str.strip() == str(session_val)]

    for leg in legs:
        authored = bs[bs["Author"].fillna("").astype(str).str.contains(leg, case=False, na=False)][
            ["Session", "Bill", "Status"]
        ]
        if authored.empty:
            out.append({"Legislator": leg, "% Against that Failed": None, "% For that Passed": None})
            continue

        joined = authored.merge(
            bills_df[["Session", "Bill", "Position", "Status"]],
            on=["Session", "Bill"],
            how="inner",
            suffixes=("_authored", "_witness"),
        )
        if joined.empty:
            out.append({"Legislator": leg, "% Against that Failed": None, "% For that Passed": None})
            continue
        status_col = "Status"
        if status_col not in joined.columns:
            if "Status_authored" in joined.columns:
                status_col = "Status_authored"
            elif "Status_witness" in joined.columns:
                status_col = "Status_witness"

        against = joined[joined["Position"].astype(str).str.contains("Against", na=False)]
        denom_a = len(against)
        pct_against_failed = (against[status_col].eq("Failed").sum() / denom_a) if denom_a else None

        for_ = joined[joined["Position"].astype(str).str.contains(r"\bFor\b", regex=True, na=False)]
        denom_f = len(for_)
        pct_for_passed = (for_[status_col].eq("Passed").sum() / denom_f) if denom_f else None

        out.append(
            {
                "Legislator": leg,
                "% Against that Failed": pct_against_failed,
                "% For that Passed": pct_for_passed,
            }
        )

    return pd.DataFrame(out)


def render_client_workspace(ctx: dict[str, Any]) -> None:
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

            def _first_nonempty(series: pd.Series) -> str:
                if series is None or len(series) == 0:
                    return ""
                s = series.dropna().astype(str).str.strip()
                s = s[s != ""]
                return s.iloc[0] if not s.empty else ""

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

def render_member_workspace(ctx: dict[str, Any]) -> None:
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

def render_lobby_workspace(ctx: dict[str, Any]) -> None:
    _previous = _push_context(ctx)
    try:
        path = str(ctx.get("PATH", "")).strip()
        get_app_state = globals().get("get_app_state")
        app_state = None
        if path and callable(get_app_state):
            try:
                app_state = get_app_state(path)
            except Exception:
                app_state = None

        Lobby_TFL_Client_All = _resolve_workspace_table(ctx, "Lobby_TFL_Client_All")
        Bill_Status_All = _resolve_workspace_table(ctx, "Bill_Status_All")
        Wit_All = _resolve_workspace_table(ctx, "Wit_All")
        Staff_All = _resolve_workspace_table(ctx, "Staff_All")
        Bill_Sub_All = _resolve_workspace_table(ctx, "Bill_Sub_All")
        name_to_short = dict(ctx.get("name_to_short", {}) or getattr(app_state, "name_to_short", {}) or {})
        lobbyist_index = ctx.get("lobbyist_index")
        if not isinstance(lobbyist_index, pd.DataFrame):
            lobbyist_index = getattr(app_state, "lobbyist_index", pd.DataFrame())
        tfl_session_val = ctx.get("tfl_session_val")

        lobby_scope_bundle = ctx.get("lobby_scope_bundle")
        all_pivot = ctx.get("all_pivot", pd.DataFrame())
        all_stats = ctx.get("all_stats", {})
        if (
            lobby_scope_bundle is None
            or not isinstance(all_pivot, pd.DataFrame)
            or not isinstance(all_stats, dict)
        ):
            get_lobby_scope_bundle = globals().get("get_lobby_scope_bundle")
            scope = ctx.get("scope", st.session_state.get("scope"))
            if path and scope is not None and callable(get_lobby_scope_bundle):
                try:
                    lobby_scope_bundle = get_lobby_scope_bundle(path, scope, tfl_session_val)
                except Exception:
                    lobby_scope_bundle = None
        if lobby_scope_bundle is not None:
            if not isinstance(all_pivot, pd.DataFrame):
                all_pivot = getattr(lobby_scope_bundle, "all_pivot", pd.DataFrame())
            if not isinstance(all_stats, dict):
                all_stats = getattr(lobby_scope_bundle, "all_stats", {}) or {}
        if lobby_scope_bundle is None:
            lobby_scope_bundle = type(
                "_LobbyScopeBundleFallback",
                (),
                {
                    "all_pivot": pd.DataFrame(),
                    "all_stats": {},
                    "trend_group": pd.DataFrame(),
                    "lobby_display": pd.DataFrame(),
                    "top_clients": pd.DataFrame(),
                },
            )()
        if not isinstance(all_pivot, pd.DataFrame):
            all_pivot = pd.DataFrame()
        if not isinstance(all_stats, dict):
            all_stats = {}

        tab_all, tab_overview, tab_bills, tab_policy, tab_activities, tab_disclosures, tab_staff = st.tabs(
            [
                "1. Statewide Baseline (Read First)",
                "2. Selected Lobbyist",
                "3. Bills & Outcomes",
                "4. Policy Subjects",
                "5. Spending Activity",
                "6. Disclosures",
                "7. Staff Links",
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

        # -----------------------------
        # TAB: ALL LOBBYISTS (ALWAYS POPULATES)
        # -----------------------------
        with tab_all:
            st.markdown('<div class="section-title">All Lobbyists Overview</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="section-sub">Scope: {st.session_state.scope}</div>', unsafe_allow_html=True)
            st.markdown(
                """
        <div class="callout fade-up">
          <div class="callout-title">What this means</div>
        <div class="callout-body">Totals are reported compensation ranges from Texas Ethics Commission lobby filings. Use Scope to switch between session-only and all-session aggregates, then narrow by last name + initial below.</div>
        </div>
        """,
                unsafe_allow_html=True,
            )

            if not require_columns(
                Lobby_TFL_Client_All,
                ["Session", "LobbyShort"],
                "All Lobbyists overview",
                "Check Texas Ethics Commission lobby filings in Data health.",
            ):
                st.info("This view needs Texas Ethics Commission lobby filings with Session and LobbyShort columns.")
            elif all_pivot.empty:
                st.info("No Texas Ethics Commission lobby filing rows found for the selected scope/session. Try a different session or verify the data path.")
            else:
                total_low = all_stats.get("tfl_low_total", 0.0) + all_stats.get("pri_low_total", 0.0)
                total_high = all_stats.get("tfl_high_total", 0.0) + all_stats.get("pri_high_total", 0.0)
                tfl_mid = (all_stats.get("tfl_low_total", 0.0) + all_stats.get("tfl_high_total", 0.0)) / 2
                pri_mid = (all_stats.get("pri_low_total", 0.0) + all_stats.get("pri_high_total", 0.0)) / 2
                total_mid = tfl_mid + pri_mid
                tfl_share_pct = (tfl_mid / total_mid * 100) if total_mid else 0.0
                lobby_total = all_stats.get("total_lobbyists", 0) or 0
                lobby_with_tfl = all_stats.get("has_tfl", 0) or 0
                lobby_with_tfl_pct = (lobby_with_tfl / lobby_total * 100) if lobby_total else 0.0
                mixed_pct = (all_stats.get("mixed", 0) / lobby_total * 100) if lobby_total else 0.0
                only_tfl_pct = (all_stats.get("only_tfl", 0) / lobby_total * 100) if lobby_total else 0.0

                insight_items = [
                    f"Reported compensation ranges total {fmt_usd(total_low)} to {fmt_usd(total_high)} across this scope.",
                    f"Taxpayer-funded clients account for about {tfl_share_pct:.0f}% of midpoint totals.",
                    f"{lobby_with_tfl:,} lobbyists ({lobby_with_tfl_pct:.0f}%) work for at least one taxpayer-funded client.",
                    f"Only taxpayer-funded: {only_tfl_pct:.0f}% of lobbyists; mixed funding: {mixed_pct:.0f}%.",
                ]
                insight_html = "".join([f"<li>{html.escape(item)}</li>" for item in insight_items])
                st.markdown(
                    f"""
        <div class="insight-panel fade-up">
          <div class="insight-card">
            <div class="insight-kicker">Statewide Snapshot</div>
            <div class="insight-title">Taxpayer-funded lobbying footprint</div>
            <ul class="insight-list">{insight_html}</ul>
          </div>
          <div class="insight-card">
            <div class="insight-kicker">Key ratios</div>
            <div class="mini-kpi-grid">
              <div class="mini-kpi">
                <div class="label">TFL Share</div>
                <div class="value">{tfl_share_pct:.0f}%</div>
                <div class="sub">Midpoint of total compensation</div>
              </div>
              <div class="mini-kpi">
                <div class="label">TFL Lobbyists</div>
                <div class="value">{lobby_with_tfl:,}</div>
                <div class="sub">{lobby_with_tfl_pct:.0f}% of all lobbyists</div>
              </div>
              <div class="mini-kpi">
                <div class="label">Only TFL</div>
                <div class="value">{all_stats.get('only_tfl', 0):,}</div>
                <div class="sub">{only_tfl_pct:.0f}% of all lobbyists</div>
              </div>
              <div class="mini-kpi">
                <div class="label">Mixed Funding</div>
                <div class="value">{all_stats.get('mixed', 0):,}</div>
                <div class="sub">{mixed_pct:.0f}% of all lobbyists</div>
              </div>
            </div>
          </div>
        </div>
        """,
                    unsafe_allow_html=True,
                )

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
                        "Total Lobbyists",
                        f"{all_stats.get('total_lobbyists', 0):,}",
                        help_text="Unique lobbyists in the selected scope.",
                    )
                    kpi_card(
                        "Lobbyists w/ >=1 Taxpayer Funded client",
                        f"{all_stats.get('has_tfl', 0):,}",
                        help_text="Lobbyists with at least one taxpayer-funded client in this scope.",
                    )
                with a4:
                    kpi_card(
                        "Only Private",
                        f"{all_stats.get('only_private', 0):,}",
                        help_text="Lobbyists with only private clients in this scope.",
                    )
                    kpi_card(
                        "Only Taxpayer Funded",
                        f"{all_stats.get('only_tfl', 0):,}",
                        f"Mixed: {all_stats.get('mixed', 0):,}",
                        help_text="Lobbyists with only taxpayer-funded clients; mixed count shown below.",
                    )

                lobby_chart_payload = _chart_runtime.build_lobby_scope_chart_payload(
                    _chart_runtime.stable_json_signature(
                        {
                            "scope": st.session_state.get("scope", ""),
                            "session": st.session_state.get("session", ""),
                            "trend_rows": int(len(lobby_scope_bundle.trend_group)),
                        }
                    ),
                    lobby_scope_bundle.trend_group,
                    all_stats,
                )
                st.markdown('<div class="section-sub">Funding Mix (Midpoint)</div>', unsafe_allow_html=True)
                mix_df = lobby_chart_payload["mix_df"]
                if mix_df["Total"].sum() > 0:
                    fig_mix = px.pie(
                        mix_df,
                        names="Funding",
                        values="Total",
                        hole=0.6,
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
                    st.markdown(
                        '<div class="section-caption">Funding mix uses midpoint totals to compare taxpayer-funded vs private compensation ranges.</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("No totals available for funding mix in this scope.")

                st.markdown('<div class="section-sub">Taxpayer Funded Compensation Trend (85th-89th)</div>', unsafe_allow_html=True)
                trend_long = lobby_chart_payload["trend_long"]
                if not trend_long.empty:
                    session_labels = lobby_chart_payload["session_labels"]
                    fig_trend = px.line(
                        trend_long,
                        x="SessionLabel",
                        y="Total",
                        color="Estimate",
                        markers=True,
                        category_orders={"SessionLabel": session_labels},
                        color_discrete_map=TREND_COLOR_MAP,
                    )
                    fig_trend.update_traces(mode="lines+markers", line=dict(width=3), marker=dict(size=6))
                    _apply_plotly_layout(fig_trend, showlegend=True, legend_title="", margin_top=16)
                    fig_trend.update_layout(hovermode="x unified")
                    fig_trend.update_yaxes(
                        tickprefix="$",
                        tickformat="~s",
                        showgrid=True,
                        gridcolor="rgba(255,255,255,0.08)",
                    )
                    st.plotly_chart(fig_trend, width="stretch", config=PLOTLY_CONFIG)
                    st.markdown('<div class="section-caption">Trend uses midpoint totals for taxpayer-funded clients across the 85th-89th sessions.</div>', unsafe_allow_html=True)
                else:
                    st.info("No taxpayer funded totals available for 85th-89th sessions.")

                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

                t1, t2 = st.columns(2)
                with t1:
                    st.markdown('<div class="section-title">Top 5 Taxpayer Funded<br>Lobbyists</div>', unsafe_allow_html=True)
                    top_lobbyists = all_pivot
                    if not top_lobbyists.empty:
                        top_lobbyists = top_lobbyists[top_lobbyists.get("Clients_TFL", 0) > 0]
                        top_lobbyists = top_lobbyists.sort_values(["High_TFL", "Low_TFL"], ascending=[False, False]).head(5)
                        lobby_display = lobby_scope_bundle.lobby_display
                        top_lobbyists = top_lobbyists.merge(lobby_display, on="LobbyShort", how="left")
                        top_lobbyists["Lobbyist"] = top_lobbyists["LobbyNameDisplay"].fillna(top_lobbyists["LobbyShort"])
                        top_lobbyists["Taxpayer Funded Total"] = top_lobbyists["Low_TFL"].map(fmt_usd) + " - " + top_lobbyists["High_TFL"].map(fmt_usd)
                        st.dataframe(
                            top_lobbyists[["Lobbyist", "Taxpayer Funded Total"]],
                            width="stretch",
                            height=240,
                            hide_index=True,
                        )
                    else:
                        st.info("No taxpayer funded lobbyists found for the selected scope/session.")

                with t2:
                    st.markdown('<div class="section-title">Top 5 Taxpayer Funding<br>Governments/Entities</div>', unsafe_allow_html=True)
                    top_clients = lobby_scope_bundle.top_clients
                    if not top_clients.empty:
                        st.dataframe(
                            top_clients[["Client", "Taxpayer Funded Total"]],
                            width="stretch",
                            height=240,
                            hide_index=True,
                        )
                    else:
                        st.info("No taxpayer funded clients found for the selected scope/session.")

                st.session_state.filter_lobbyshort = st.text_input(
                    "Filter last name + first initial (contains)",
                    value=st.session_state.filter_lobbyshort,
                    placeholder="e.g., Abbott",
                    help="Filter the All Lobbyists table by a name substring.",
                )
                st.markdown('<div class="section-caption">Tip: Use the table filters to narrow the list; CSV exports include the active scope and session.</div>', unsafe_allow_html=True)
                flt = st.session_state.filter_lobbyshort
                c1, c2, c3 = st.columns(3)
                with c1:
                    only_tfl = st.checkbox(
                        "Only taxpayer funded",
                        value=False,
                        help="Show lobbyists with taxpayer-funded clients only.",
                    )
                with c2:
                    only_private = st.checkbox(
                        "Only private",
                        value=False,
                        help="Show lobbyists with private clients only.",
                    )
                with c3:
                    mixed_only = st.checkbox(
                        "Mixed only",
                        value=False,
                        help="Show lobbyists with both taxpayer-funded and private clients.",
                    )

                view = all_pivot.copy()
                if flt.strip():
                    view = view[view["LobbyShort"].astype(str).str.contains(flt.strip(), case=False, na=False)]
                if only_tfl:
                    view = view[view.get("Only_TFL", False)]
                if only_private:
                    view = view[view.get("Only_Private", False)]
                if mixed_only:
                    view = view[view.get("Mixed", False)]

                threshold_col1, threshold_col2 = st.columns(2)
                with threshold_col1:
                    max_mid = int(view["Total_Mid"].max()) if not view.empty else 0
                    min_mid = 0
                    if max_mid > 0:
                        step = max(int(max_mid / 50), 1000)
                        step = min(step, max_mid)
                        min_mid = st.slider(
                            "Minimum midpoint total",
                            0,
                            max_mid,
                            0,
                            step=step,
                            format="$%d",
                            help="Filter lobbyists by midpoint totals (uses low/high averages).",
                        )
                    else:
                        st.caption("No compensation totals available for threshold filtering.")
                with threshold_col2:
                    share_opts = {"Any": 0.0, ">= 50% TFL": 0.5, ">= 75% TFL": 0.75}
                    share_choice = st.selectbox(
                        "Taxpayer-funded share filter",
                        list(share_opts.keys()),
                        index=0,
                        help="Limit lobbyists by share of taxpayer-funded midpoint totals.",
                    )
                    share_threshold = share_opts.get(share_choice, 0.0)

                if min_mid > 0:
                    view = view[view["Total_Mid"] >= min_mid]
                if share_threshold > 0:
                    view = view[view["TFL_Share"] >= share_threshold]

                view_disp = view.copy()
                for c in ["Low_TFL", "High_TFL", "Low_Private", "High_Private"]:
                    if c in view_disp.columns:
                        view_disp[c] = _fmt_usd_series(view_disp[c])
                if "Total_Mid" in view_disp.columns:
                    view_disp["Total_Mid"] = _fmt_usd_series(view_disp["Total_Mid"])
                if "TFL_Share" in view_disp.columns:
                    view_disp["TFL_Share"] = (
                        (view_disp["TFL_Share"].fillna(0) * 100).round(0).astype("Int64").astype(str) + "%"
                    )

                rename_cols = {
                    "LobbyShort": "Last name + first initial",
                    "Has_TFL": "Has Taxpayer Funded",
                    "Only_TFL": "Only Taxpayer Funded",
                    "Clients_TFL": "Taxpayer Funded Clients",
                    "Low_TFL": "Taxpayer Funded Low",
                    "High_TFL": "Taxpayer Funded High",
                    "Total_Mid": "Midpoint Total",
                    "TFL_Share": "Taxpayer Funded Share",
                }
                view_disp = view_disp.rename(columns=rename_cols)

                cols = [
                    "LobbyShort",
                    "Has_TFL", "Has_Private", "Only_TFL", "Only_Private", "Mixed",
                    "Total_Mid", "TFL_Share",
                    "Clients_TFL", "Low_TFL", "High_TFL",
                    "Clients_Private", "Low_Private", "High_Private",
                ]
                cols = [rename_cols.get(c, c) for c in cols]
                cols = [c for c in cols if c in view_disp.columns]

                sort_cols = [c for c in ["Has Taxpayer Funded", "Mixed", "Last name + first initial"] if c in view_disp.columns]
                if sort_cols:
                    view_disp = view_disp.sort_values(sort_cols, ascending=[False, False, True][:len(sort_cols)])
                st.dataframe(
                    view_disp[cols],
                    width="stretch",
                    height=560,
                    hide_index=True,
                )
                export_context = []
                if flt.strip():
                    export_context.append(f"Name filter: {_shorten_text(flt, 24)}")
                if only_tfl:
                    export_context.append("Only taxpayer funded")
                if only_private:
                    export_context.append("Only private")
                if mixed_only:
                    export_context.append("Mixed only")
                if min_mid > 0:
                    export_context.append(f"Min midpoint: {fmt_usd(min_mid)}")
                if share_threshold > 0:
                    export_context.append(f"TFL share: {share_choice}")
                _ = export_dataframe(
                    view_disp[cols],
                    "all_lobbyists_overview.csv",
                    label="Download overview CSV",
                    context=export_context,
                )

        # -----------------------------
        # Per-lobbyist tabs: only compute when lobbyist is selected AND session != All
        # -----------------------------
        def _no_lobbyist_msg():
            st.info("Type a lobbyist name at the top to view details. Use Clear filters to reset or switch to All Lobbyists for a full overview.")

        def _need_specific_session_msg():
            st.info("Select a specific session (e.g., 89th) to view lobbyist details. Use All Sessions for high-level totals only.")

        if st.session_state.session is None:
            with tab_overview:
                _need_specific_session_msg()
            with tab_bills:
                _need_specific_session_msg()
            with tab_policy:
                _need_specific_session_msg()
            with tab_staff:
                _need_specific_session_msg()
            with tab_activities:
                _need_specific_session_msg()
            with tab_disclosures:
                _need_specific_session_msg()
        else:
            if not st.session_state.lobbyshort:
                with tab_overview:
                    _no_lobbyist_msg()
                with tab_bills:
                    _no_lobbyist_msg()
                with tab_policy:
                    _no_lobbyist_msg()
                with tab_staff:
                    _no_lobbyist_msg()
                with tab_activities:
                    _no_lobbyist_msg()
                with tab_disclosures:
                    _no_lobbyist_msg()
            else:
                session = str(st.session_state.session).strip()
                lobbyshort = str(st.session_state.lobbyshort).strip()
                if ctx.get("_prepared_lobby_workspace"):
                    typed_norms_tuple = tuple(ctx.get("typed_norms_tuple", ()) or ())
                    typed_norms = set(ctx.get("typed_norms", set()) or set())
                    selected_filer_ids = set(ctx.get("selected_filer_ids", ()) or ())
                    lobbyist_label = str(ctx.get("lobbyist_label", lobbyshort)).strip()
                    selected_names = list(ctx.get("selected_names", ()) or [])
                    wit = ctx.get("wit", pd.DataFrame())
                    witness_match_note = str(ctx.get("witness_match_note", "")).strip()
                    bills = ctx.get("bills", pd.DataFrame())
                    mentions = ctx.get("mentions", pd.DataFrame())
                    bill_subjects = ctx.get("bill_subjects", pd.DataFrame())
                    lobby_sub_counts = ctx.get("lobby_sub_counts", pd.DataFrame())
                    subject_non_empty = float(ctx.get("subject_non_empty", 0.0) or 0.0)
                    lt = ctx.get("lt", pd.DataFrame())
                    has_tfl = bool(ctx.get("has_tfl", False))
                    has_private = bool(ctx.get("has_private", False))
                    tfl_clients = list(ctx.get("tfl_clients", []) or [])
                    private_clients = list(ctx.get("private_clients", []) or [])
                    tfl_low = float(ctx.get("tfl_low", 0.0) or 0.0)
                    tfl_high = float(ctx.get("tfl_high", 0.0) or 0.0)
                    pri_low = float(ctx.get("pri_low", 0.0) or 0.0)
                    pri_high = float(ctx.get("pri_high", 0.0) or 0.0)
                    staff_pick = ctx.get("staff_pick", pd.DataFrame())
                    staff_pick_session = ctx.get("staff_pick_session", pd.DataFrame())
                    staff_stats = ctx.get("staff_stats", pd.DataFrame())
                    activities = ctx.get("activities", pd.DataFrame())
                    disclosures = ctx.get("disclosures", pd.DataFrame())
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

                    typed_norms_tuple = tuple(sorted(typed_norms))
                    selected_filer_ids = set()
                    if st.session_state.lobby_filerid is not None:
                        try:
                            selected_filer_ids = {int(st.session_state.lobby_filerid)}
                        except Exception:
                            selected_filer_ids = set()
                    lobbyist_label = lobbyshort
                    selected_names = []
                    candidate_map = st.session_state.lobby_candidate_map or {}
                    merge_keys = st.session_state.lobby_merge_keys or []
                    if st.session_state.lobby_filerid and not lobbyist_index.empty:
                        filer_series = pd.to_numeric(lobbyist_index.get("FilerID", pd.Series(dtype=float)), errors="coerce")
                        match_row = lobbyist_index[
                            (lobbyist_index["LobbyShort"].astype(str).str.strip() == lobbyshort) &
                            (filer_series == int(st.session_state.lobby_filerid))
                        ]
                        if not match_row.empty:
                            lobbyist_label = match_row["Lobby Name"].iloc[0]
                            selected_names = match_row["Lobby Name"].dropna().astype(str).unique().tolist()

                    if merge_keys:
                        for key in merge_keys:
                            cand = candidate_map.get(key, {})
                            name = cand.get("name", "")
                            if name and name not in selected_names:
                                selected_names.append(name)
                            fid = cand.get("filerid", None)
                            if fid is not None:
                                try:
                                    selected_filer_ids.add(int(fid))
                                except Exception:
                                    pass

                    lobbyshort_norm = norm_name(lobbyshort)
                    wit_all = ensure_cols(
                        Wit_All,
                        {"Session": "", "Bill": "", "LobbyShort": "", "IsFor": 0, "IsAgainst": 0, "IsOn": 0},
                    )
                    if "LobbyShortNorm" not in wit_all.columns:
                        wit_all = wit_all.copy()
                        wit_all["LobbyShortNorm"] = norm_name_series(wit_all["LobbyShort"])
                    session_col = wit_all["Session"].astype(str).str.strip()
                    base_wit = wit_all[session_col == session]
                    witness_match_note = ""
                    if selected_names:
                        name_variants = set()
                        name_pairs = []
                        for name in selected_names:
                            if not name:
                                continue
                            name_variants |= norm_person_variants_with_nicknames(name)
                            info = parse_person_name(name)
                            first_norm = info.get("first_norm", "")
                            last_norm = info.get("last_norm", "")
                            first_initial = info.get("first_initial", "")
                            if first_norm and last_norm:
                                name_pairs.append((first_norm, last_norm, first_initial))

                        name_mask = pd.Series(False, index=base_wit.index)
                        if name_variants:
                            name_norm = base_wit.get("NameNorm")
                            if not isinstance(name_norm, pd.Series):
                                name_norm = base_wit.get("name", pd.Series([""] * len(base_wit))).fillna("").astype(str).map(norm_name)
                            name_mask = name_mask | name_norm.isin(name_variants)
                        if name_pairs and "NameLastNorm" in base_wit.columns:
                            name_last = base_wit.get("NameLastNorm")
                            name_first = base_wit.get("NameFirstNorm")
                            name_first_initial = base_wit.get("NameFirstInitialNorm")
                            if isinstance(name_last, pd.Series) and isinstance(name_first, pd.Series):
                                for first_norm, last_norm, first_initial in name_pairs:
                                    first_match = name_first == first_norm
                                    if first_initial and isinstance(name_first_initial, pd.Series):
                                        first_match = first_match | (name_first_initial == first_initial)
                                    name_mask = name_mask | ((name_last == last_norm) & first_match)

                        if "LobbyShortNorm" in base_wit.columns:
                            short_norm = base_wit["LobbyShortNorm"].fillna("")
                            short_mask = short_norm == lobbyshort_norm
                            if short_mask.any():
                                name_mask = name_mask & (short_mask | (short_norm == ""))

                        if name_mask.any():
                            wit = base_wit[name_mask]
                            wit["LobbyShort"] = lobbyshort
                            wit["LobbyShortNorm"] = lobbyshort_norm
                            witness_match_note = "Witness list filtered to the selected name."
                        else:
                            wit = base_wit.iloc[0:0]
                            witness_match_note = "No witness-list rows matched the selected name. Clear the specific match to see all rows for that last name + first initial."
                    else:
                        if "LobbyShortNorm" in base_wit.columns:
                            wit = base_wit[base_wit["LobbyShortNorm"] == lobbyshort_norm]
                            if not wit.empty:
                                wit["LobbyShort"] = lobbyshort
                        else:
                            wit = base_wit[
                                base_wit["LobbyShort"].astype(str).str.strip() == lobbyshort
                            ]

                    bills = build_bills_with_status(wit, Bill_Status_All, Fiscal_Impact, session)
                    mentions = build_policy_mentions(bills, Bill_Sub_All, session)
                    bill_subjects = pd.DataFrame(columns=["Session", "Bill", "Subject"])
                    if (
                        isinstance(Bill_Sub_All, pd.DataFrame)
                        and {"Session", "Bill", "Subject"}.issubset(Bill_Sub_All.columns)
                        and isinstance(bills, pd.DataFrame)
                        and {"Session", "Bill"}.issubset(bills.columns)
                        and not bills.empty
                    ):
                        bill_subjects = Bill_Sub_All[
                            Bill_Sub_All["Session"].astype(str).str.strip() == session
                        ].merge(
                            bills[["Session", "Bill"]].drop_duplicates(),
                            on=["Session", "Bill"],
                            how="inner",
                        )
                        bill_subjects = bill_subjects[
                            bill_subjects["Subject"].fillna("").astype(str).str.strip() != ""
                        ]

                    lobby_sub_counts, subject_non_empty = build_lobby_subject_counts(
                        Lobby_Sub_All,
                        session,
                        lobbyshort,
                        lobbyshort_norm,
                        tuple(sorted(selected_filer_ids)) if selected_filer_ids else tuple(),
                    )

                    tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
                    lt = Lobby_TFL_Client_All[
                        (Lobby_TFL_Client_All["Session"].astype(str).str.strip() == tfl_session) &
                        (Lobby_TFL_Client_All["LobbyShort"].astype(str).str.strip() == lobbyshort)
                    ]
                    if selected_filer_ids and "FilerID" in lt.columns:
                        fid = pd.to_numeric(lt["FilerID"], errors="coerce").fillna(-1).astype(int)
                        lt = lt[fid.isin(selected_filer_ids)]
                    lt = ensure_cols(lt, {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0})

                    has_tfl = bool((lt["IsTFL"] == 1).any()) if not lt.empty else False
                    has_private = bool((lt["IsTFL"] == 0).any()) if not lt.empty else False

                    tfl_clients = sorted(lt.loc[lt["IsTFL"] == 1, "Client"].dropna().astype(str).unique().tolist())
                    private_clients = sorted(lt.loc[lt["IsTFL"] == 0, "Client"].dropna().astype(str).unique().tolist())

                    tfl_low = float(lt.loc[lt["IsTFL"] == 1, "Low_num"].sum()) if not lt.empty else 0.0
                    tfl_high = float(lt.loc[lt["IsTFL"] == 1, "High_num"].sum()) if not lt.empty else 0.0
                    pri_low = float(lt.loc[lt["IsTFL"] == 0, "Low_num"].sum()) if not lt.empty else 0.0
                    pri_high = float(lt.loc[lt["IsTFL"] == 0, "High_num"].sum()) if not lt.empty else 0.0

                    staff_df = Staff_All
                    _session_col = staff_df.get("Session")
                    if _session_col is not None:
                        staff_session = _session_col.astype(str).str.strip() == str(session)
                    else:
                        staff_session = pd.Series(False, index=staff_df.index)
                    if typed_norms:
                        typed_last_norm = last_name_norm_from_text(st.session_state.search_query)
                        lobbyshort_norm = norm_name(lobbyshort)
                        match_mask = (
                            staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(typed_norms) |
                            staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(typed_norms)
                        )
                        if typed_last_norm:
                            match_mask = match_mask | (staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)) == typed_last_norm)
                        if lobbyshort_norm:
                            match_mask = match_mask | (staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm)
                    else:
                        lobbyshort_norm = norm_name(lobbyshort)
                        lobby_last_norm = last_name_norm_from_text(lobbyshort)
                        match_mask = pd.Series(False, index=staff_df.index)
                        if lobbyshort_norm:
                            match_mask = match_mask | (staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm)
                        if lobby_last_norm:
                            match_mask = match_mask | (staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)) == lobby_last_norm)

                    staff_pick = staff_df[match_mask]
                    staff_pick_session = staff_df[staff_session & match_mask]
                    staff_stats = _staff_metrics(staff_pick_session, bills, session, Bill_Status_All) if not staff_pick_session.empty else pd.DataFrame()

                    activities = build_activities(
                        data["LaFood"], data["LaEnt"], data["LaTran"], data["LaGift"], data["LaEvnt"], data["LaAwrd"],
                        lobbyshort=lobbyshort,
                        session=session,
                        name_to_short=name_to_short,
                        lobbyist_norms_tuple=typed_norms_tuple,
                        filerid_to_short=data.get("filerid_to_short", {}),
                        filer_ids=tuple(sorted(selected_filer_ids)) if selected_filer_ids else None,
                    )

                    disclosures = build_disclosures(
                        LaCvr, LaDock, LaI4E, LaSub,
                        lobbyshort=lobbyshort,
                        session=session,
                        name_to_short=name_to_short,
                        lobbyist_norms_tuple=typed_norms_tuple,
                        filerid_to_short=data.get("filerid_to_short", {}),
                        filer_ids=tuple(sorted(selected_filer_ids)) if selected_filer_ids else None,
                    )

                # ---- Overview tab
                with tab_overview:
                    st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)
                    st.markdown(
                        """
        <div class="callout fade-up">
          <div class="callout-title">What this means</div>
          <div class="callout-body">Client totals are reported ranges (low-high). Funding mix uses midpoints to show relative share, not exact spend.</div>
        </div>
        """,
                        unsafe_allow_html=True,
                    )
                    _ = require_columns(
                        Lobby_TFL_Client_All,
                        ["Client", "IsTFL"],
                        "Overview",
                        "Texas Ethics Commission lobby filings are required for compensation and client totals.",
                    )
                    passed = int((bills.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not bills.empty else 0
                    failed = int((bills.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not bills.empty else 0
                    total_clients = len(set(tfl_clients + private_clients))
                    total_low = tfl_low + pri_low
                    total_high = tfl_high + pri_high
                    tfl_mid = (tfl_low + tfl_high) / 2
                    pri_mid = (pri_low + pri_high) / 2
                    total_mid = tfl_mid + pri_mid
                    tfl_share_pct = (tfl_mid / total_mid * 100) if total_mid else 0.0
                    top_clients = build_top_clients(lt, top_n=10)
                    top_client_label = ""
                    top_client_range = ""
                    if not top_clients.empty:
                        top_row = top_clients.iloc[0]
                        top_client_label = str(top_row.get("Client", "")).strip()
                        top_client_range = f"{fmt_usd(float(top_row.get('Low', 0.0)))} - {fmt_usd(float(top_row.get('High', 0.0)))}"
                    top_subject = ""
                    top_subject_pct = None
                    if not mentions.empty:
                        top_subject = str(mentions.iloc[0].get("Subject", "")).strip()
                        try:
                            top_subject_pct = float(mentions.iloc[0].get("Share", 0.0)) * 100
                        except Exception:
                            top_subject_pct = None
                    top_author = ""
                    if not bills.empty and "Author" in bills.columns:
                        author_series = bills["Author"].fillna("").astype(str).str.strip()
                        author_series = author_series[author_series != ""]
                        if not author_series.empty:
                            top_author = str(author_series.value_counts().index[0]).strip()

                    insight_items = []
                    if total_clients:
                        insight_items.append(
                            f"{total_clients} unique clients this session: {len(tfl_clients)} taxpayer funded and {len(private_clients)} private."
                        )
                    if total_mid > 0:
                        insight_items.append(
                            f"Reported compensation ranges total {fmt_usd(total_low)} to {fmt_usd(total_high)}; taxpayer funded share is about {tfl_share_pct:.0f}%."
                        )
                    if top_client_label:
                        insight_items.append(f"Largest client by midpoint: {top_client_label} ({top_client_range}).")
                    if top_subject:
                        if top_subject_pct is not None:
                            insight_items.append(f"Top policy area: {top_subject} ({top_subject_pct:.1f}% of witness-list bills).")
                        else:
                            insight_items.append(f"Top policy area: {top_subject}.")
                    if bills.empty:
                        insight_items.append("No witness-list bills recorded for this session.")

                    insight_html = "".join([f"<li>{html.escape(item)}</li>" for item in insight_items]) or "<li>No summary available.</li>"
                    focus_title = "Top Policy Area" if top_subject else "Top Client"
                    focus_value = _shorten_text(top_subject, 28) if top_subject else (_shorten_text(top_client_label, 28) if top_client_label else "--")
                    focus_sub = f"{top_subject_pct:.1f}% of bills" if top_subject and top_subject_pct is not None else (top_client_range if top_client_label else "")

                    st.markdown(
                        f"""
        <div class="insight-panel fade-up">
          <div class="insight-card">
            <div class="insight-kicker">Insight Briefing</div>
            <div class="insight-title">Session highlights for this lobbyist</div>
            <ul class="insight-list">{insight_html}</ul>
          </div>
          <div class="insight-card">
            <div class="insight-kicker">At a glance</div>
            <div class="mini-kpi-grid">
              <div class="mini-kpi">
                <div class="label">Clients</div>
                <div class="value">{total_clients:,}</div>
                <div class="sub">TFL {len(tfl_clients)} / Private {len(private_clients)}</div>
              </div>
              <div class="mini-kpi">
                <div class="label">Total Range</div>
                <div class="value">{fmt_usd(total_low)} - {fmt_usd(total_high)}</div>
                <div class="sub">Midpoint share {tfl_share_pct:.0f}% TFL</div>
              </div>
              <div class="mini-kpi">
                <div class="label">Bills</div>
                <div class="value">{len(bills):,}</div>
                <div class="sub">Passed {passed:,} / Failed {failed:,}</div>
              </div>
              <div class="mini-kpi">
                <div class="label">{focus_title}</div>
                <div class="value">{html.escape(focus_value) if focus_value else "--"}</div>
                <div class="sub">{html.escape(focus_sub) if focus_sub else ""}</div>
              </div>
            </div>
          </div>
        </div>
        """,
                        unsafe_allow_html=True,
                    )

                    if top_client_label:
                        st.markdown(
                            f"""
        <div class="handoff-card">
          <div class="handoff-kicker">Cross-Page Handoff</div>
          <div class="handoff-title">Validate The Largest Client Context</div>
          <div class="handoff-sub">Top client by midpoint in this profile: <strong>{html.escape(top_client_label, quote=True)}</strong> ({html.escape(top_client_range, quote=True)}).</div>
        </div>
        """,
                            unsafe_allow_html=True,
                        )
                        handoff_cols = st.columns(3 if top_author else 2)
                        with handoff_cols[0]:
                            if st.button("Open Client Profile", key="lobby_handoff_client_btn", width="stretch"):
                                st.session_state.client_query = top_client_label
                                st.session_state.client_query_input = top_client_label
                                st.session_state.client_name = ""
                                st.session_state.client_session = st.session_state.session
                                st.session_state.client_scope = st.session_state.scope
                                st.switch_page(_client_page)
                        with handoff_cols[1]:
                            if st.button("Open In Map & Address", key="lobby_handoff_map_btn", width="stretch"):
                                st.session_state.map_session = st.session_state.session
                                st.session_state.map_scope = st.session_state.scope
                                st.session_state.map_overlap_entity_filter = top_client_label
                                st.switch_page(_map_page)
                        if top_author:
                            with handoff_cols[2]:
                                if st.button("Open Top Author", key="lobby_handoff_member_btn", width="stretch"):
                                    st.session_state.member_query = top_author
                                    st.session_state.member_query_input = top_author
                                    st.session_state.member_name = ""
                                    st.session_state.member_session = st.session_state.session
                                    st.switch_page(_member_page)

                    o1, o2, o3, o4 = st.columns(4)
                    with o1:
                        kpi_card(
                            "Session",
                            session,
                            f"Scope: {st.session_state.scope}",
                            help_text="Session used for detail tables; scope shows whether totals are this session or all sessions.",
                        )
                    with o2:
                        kpi_card(
                            "Lobbyist",
                            lobbyist_label,
                            st.session_state.search_query.strip() or "--",
                            help_text="Resolved lobbyist selection; subtitle shows the search query.",
                        )
                    with o3:
                        kpi_card(
                            "Taxpayer Funded Totals",
                            f"{fmt_usd(tfl_low)} - {fmt_usd(tfl_high)}",
                            help_text="Sum of reported low/high totals for taxpayer-funded clients tied to this lobbyist.",
                        )
                    with o4:
                        kpi_card(
                            "Private Totals",
                            f"{fmt_usd(pri_low)} - {fmt_usd(pri_high)}",
                            help_text="Sum of reported low/high totals for private clients tied to this lobbyist.",
                        )

                    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

                    s1, s2, s3, s4 = st.columns(4)
                    with s1:
                        kpi_card(
                            "Taxpayer Funded?",
                            "Yes" if has_tfl else "No",
                            help_text="Whether this lobbyist has any taxpayer-funded clients in the selected scope.",
                        )
                    with s2:
                        kpi_card(
                            "Private Funded?",
                            "Yes" if has_private else "No",
                            help_text="Whether this lobbyist has any private clients in the selected scope.",
                        )
                    with s3:
                        kpi_card(
                            "Total Bills (Witness Lists)",
                            f"{len(bills):,}",
                            help_text="Witness list rows tied to this lobbyist in the selected session.",
                        )
                    with s4:
                        kpi_card(
                            "Passed / Failed",
                            f"{passed:,} / {failed:,}",
                            help_text="Bill outcomes among witness list rows in this view.",
                        )

                    st.markdown('<div class="section-sub">Activity & Filings tempo</div>', unsafe_allow_html=True)
                    act_rows = len(activities) if isinstance(activities, pd.DataFrame) else 0
                    disc_rows = len(disclosures) if isinstance(disclosures, pd.DataFrame) else 0
                    activity_timeline = build_timeline_counts(activities, "Date") if isinstance(activities, pd.DataFrame) else pd.DataFrame()
                    disclosure_timeline = build_timeline_counts(disclosures, "Date") if isinstance(disclosures, pd.DataFrame) else pd.DataFrame()
                    if not activity_timeline.empty or not disclosure_timeline.empty:
                        act_merge = activity_timeline.rename(columns={"Count": "Activities"})[["Period", "Label", "Activities"]] if not activity_timeline.empty else pd.DataFrame(columns=["Period", "Label", "Activities"])
                        disc_merge = disclosure_timeline.rename(columns={"Count": "Disclosures"})[["Period", "Label", "Disclosures"]] if not disclosure_timeline.empty else pd.DataFrame(columns=["Period", "Label", "Disclosures"])
                        tempo = act_merge.merge(disc_merge, on=["Period", "Label"], how="outer").fillna(0)
                        tempo = tempo.sort_values("Period")
                        tempo_long = tempo.melt(id_vars=["Period", "Label"], value_vars=["Activities", "Disclosures"], var_name="Type", value_name="Count")
                        tempo_long["Count"] = pd.to_numeric(tempo_long["Count"], errors="coerce").fillna(0)
                        fig_tempo = px.line(
                            tempo_long,
                            x="Period",
                            y="Count",
                            color="Type",
                            markers=True,
                            color_discrete_map={"Activities": "#00e0b8", "Disclosures": "#8cc9ff"},
                        )
                        fig_tempo.update_traces(
                            mode="lines+markers",
                            line=dict(width=3),
                            marker=dict(size=6),
                            hovertemplate="%{x|%b %Y}: %{y} %{fullData.name}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_tempo, showlegend=True, legend_title="", margin_top=8)
                        fig_tempo.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", title_text="")
                        fig_tempo.update_xaxes(title_text="")
                        st.plotly_chart(fig_tempo, width="stretch", config=PLOTLY_CONFIG)
                        st.caption(f"Activities: {act_rows:,} rows | Disclosures: {disc_rows:,} rows")
                    else:
                        st.info("No activities or disclosures recorded for this lobbyist/session.")

                    st.markdown('<div class="section-sub">Compensation Trend by Session (Midpoint)</div>', unsafe_allow_html=True)
                    trend_df = build_lobbyist_trend(
                        Lobby_TFL_Client_All,
                        lobbyshort,
                        tuple(sorted(selected_filer_ids)) if selected_filer_ids else None,
                    )
                    if not trend_df.empty:
                        session_order = sorted(trend_df["SessionBase"].dropna().unique().tolist())
                        session_labels = [_session_base_label(s) for s in session_order]
                        fig_trend = px.line(
                            trend_df,
                            x="SessionLabel",
                            y="Mid",
                            color="Funding",
                            markers=True,
                            category_orders={"SessionLabel": session_labels},
                            color_discrete_map=FUNDING_COLOR_MAP,
                        )
                        fig_trend.update_traces(
                            mode="lines+markers",
                            line=dict(width=3),
                            marker=dict(size=6),
                            hovertemplate="%{x} - %{fullData.name}: $%{y:,.0f}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_trend, showlegend=True, legend_title="", margin_top=12)
                        fig_trend.update_layout(hovermode="x unified")
                        fig_trend.update_yaxes(
                            tickprefix="$",
                            tickformat="~s",
                            showgrid=True,
                            gridcolor="rgba(255,255,255,0.08)",
                        )
                        fig_trend.update_xaxes(title_text="")
                        st.plotly_chart(fig_trend, width="stretch", config=PLOTLY_CONFIG)
                        st.markdown(
                            '<div class="section-caption">Trend shows midpoint totals for taxpayer funded vs private clients across sessions.</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.info("No multi-session trend available for this lobbyist.")

                    st.markdown('<div class="section-sub">Funding Mix (Midpoint)</div>', unsafe_allow_html=True)
                    lobby_mix = pd.DataFrame(
                        {
                            "Funding": ["Taxpayer Funded", "Private"],
                            "Total": [
                                (tfl_low + tfl_high) / 2,
                                (pri_low + pri_high) / 2,
                            ],
                        }
                    )
                    if lobby_mix["Total"].sum() > 0:
                        fig_lobby_mix = px.pie(
                            lobby_mix,
                            names="Funding",
                            values="Total",
                            hole=0.55,
                            color="Funding",
                            color_discrete_map=FUNDING_COLOR_MAP,
                        )
                        fig_lobby_mix.update_traces(
                            textposition="inside",
                            textinfo="percent+label",
                            insidetextorientation="radial",
                            marker=dict(line=dict(color="rgba(7,22,39,0.9)", width=2)),
                            hovertemplate="%{label}: %{percent}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_lobby_mix, showlegend=False, margin_top=12)
                        fig_lobby_mix.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
                        st.plotly_chart(fig_lobby_mix, width="stretch", config=PLOTLY_CONFIG)
                        st.markdown('<div class="section-caption">Funding mix uses midpoint values to highlight relative scale.</div>', unsafe_allow_html=True)
                    else:
                        st.info("No totals available for funding mix. Try selecting a different session or clearing the lobbyist filter.")

                    st.markdown('<div class="section-sub">Top Clients by Reported Compensation (Midpoint)</div>', unsafe_allow_html=True)
                    if not top_clients.empty:
                        top_clients = top_clients.sort_values("Mid", ascending=True)
                        fig_clients = px.bar(
                            top_clients,
                            x="Mid",
                            y="Client",
                            orientation="h",
                            color="Funding",
                            color_discrete_map=FUNDING_COLOR_MAP,
                            text="Mid",
                        )
                        fig_clients.update_traces(
                            texttemplate="$%{text:,.0f}",
                            textposition="outside",
                            cliponaxis=False,
                            hovertemplate="%{y}<br>%{fullData.name}: $%{x:,.0f}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_clients, showlegend=True, legend_title="", margin_top=12)
                        fig_clients.update_layout(margin=dict(l=8, r=48, t=12, b=8))
                        fig_clients.update_xaxes(
                            tickprefix="$",
                            tickformat="~s",
                            showgrid=True,
                            gridcolor="rgba(255,255,255,0.08)",
                            title_text="Midpoint total",
                        )
                        fig_clients.update_yaxes(title_text="")
                        st.plotly_chart(fig_clients, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("No client totals available to rank for this session.")

                    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                    cA, cB = st.columns(2)
                    with cA:
                        st.subheader("Taxpayer Funded Clients")
                        st.markdown(render_pill_list(tfl_clients, limit=14), unsafe_allow_html=True)
                    with cB:
                        st.subheader("Private Clients")
                        st.markdown(render_pill_list(private_clients, limit=14), unsafe_allow_html=True)

                # ---- Bills tab
                with tab_bills:
                    st.markdown('<div class="section-title">Bills with Witness-List Activity</div>', unsafe_allow_html=True)
                    st.markdown(
                        """
        <div class="callout fade-up">
          <div class="callout-title">What this means</div>
          <div class="callout-body">Witness-list rows indicate where a lobbyist filed testimony or positions. Use status/position filters to focus on the most relevant activity.</div>
        </div>
        """,
                        unsafe_allow_html=True,
                    )
                    if witness_match_note:
                        st.caption(witness_match_note)
                    if not require_columns(
                        bills,
                        ["Bill", "Position"],
                        "Bills view",
                        "Texas Legislature Online witness lists and bill status data are required for bill-level activity.",
                    ):
                        st.info("Bills view needs Texas Legislature Online witness-list data. Check the Data health panel.")
                    elif bills.empty:
                        st.info("No witness-list rows found for this lobbyist/session. Try another session or clear the specific match.")
                    else:
                        st.session_state.bill_search = st.text_input(
                            "Search bills (Bill / Author / Caption)",
                            value=st.session_state.bill_search,
                            placeholder="e.g., HB 4 or Bettencourt or housing",
                            help="Filter bills by bill number, author, or caption text.",
                        )
                        filtered = bills
                        if st.session_state.bill_search.strip():
                            q = st.session_state.bill_search.strip()
                            filtered = filtered[
                                filtered["Bill"].astype(str).str.contains(q, case=False, na=False) |
                                filtered["Author"].astype(str).str.contains(q, case=False, na=False) |
                                filtered["Caption"].astype(str).str.contains(q, case=False, na=False)
                            ]

                        f1, f2 = st.columns(2)
                        with f1:
                            status_opts = _clean_options(
                                filtered.get("Status", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                            )
                            status_opts = sorted(status_opts)
                            status_sel = st.multiselect(
                                "Filter by status",
                                status_opts,
                                default=status_opts,
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
                                help="Limit results to selected witness positions.",
                            )

                        if status_sel:
                            filtered = filtered[filtered["Status"].astype(str).isin(status_sel)]
                        if pos_sel:
                            filtered = filtered[filtered["Position"].astype(str).isin(pos_sel)]

                        bsum1, bsum2 = st.columns(2)
                        with bsum1:
                            if "Status" in filtered.columns:
                                status_counts = (
                                    filtered["Status"]
                                    .fillna("Unknown")
                                    .astype(str)
                                    .str.strip()
                                    .replace("", "Unknown")
                                    .value_counts()
                                    .reset_index()
                                )
                                status_counts = status_counts.set_axis(["Status", "Count"], axis=1)
                                fig_status = px.bar(
                                    status_counts.sort_values("Count"),
                                    x="Count",
                                    y="Status",
                                    orientation="h",
                                    text="Count",
                                )
                                fig_status.update_traces(
                                    textposition="outside",
                                    marker_color="#8cc9ff",
                                    cliponaxis=False,
                                    hovertemplate="%{y}: %{x}<extra></extra>",
                                )
                                _apply_plotly_layout(fig_status, showlegend=False, height=220, margin_top=8)
                                fig_status.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                                fig_status.update_xaxes(showgrid=False, title_text="")
                                fig_status.update_yaxes(title_text="")
                                st.plotly_chart(fig_status, width="stretch", config=PLOTLY_CONFIG)
                            else:
                                st.info("Status summary unavailable.")
                        with bsum2:
                            if "Position" in filtered.columns:
                                pos_counts = (
                                    filtered["Position"]
                                    .fillna("Unknown")
                                    .astype(str)
                                    .str.strip()
                                    .replace("", "Unknown")
                                    .value_counts()
                                    .reset_index()
                                )
                                pos_counts = pos_counts.set_axis(["Position", "Count"], axis=1)
                                fig_pos = px.bar(
                                    pos_counts.sort_values("Count"),
                                    x="Count",
                                    y="Position",
                                    orientation="h",
                                    text="Count",
                                )
                                fig_pos.update_traces(
                                    textposition="outside",
                                    marker_color="#1e90ff",
                                    cliponaxis=False,
                                    hovertemplate="%{y}: %{x}<extra></extra>",
                                )
                                _apply_plotly_layout(fig_pos, showlegend=False, height=220, margin_top=8)
                                fig_pos.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                                fig_pos.update_xaxes(showgrid=False, title_text="")
                                fig_pos.update_yaxes(title_text="")
                                st.plotly_chart(fig_pos, width="stretch", config=PLOTLY_CONFIG)
                            else:
                                st.info("Position summary unavailable.")

                        for col in ["Fiscal Impact H", "Fiscal Impact S"]:
                            if col in filtered.columns:
                                filtered[col] = pd.to_numeric(filtered[col], errors="coerce").fillna(0)

                        show_cols = ["Bill", "Author", "Caption", "Position", "Fiscal Impact H", "Fiscal Impact S", "Status"]
                        show_cols = [c for c in show_cols if c in filtered.columns]

                        st.caption(f"{len(filtered):,} bills")
                        st.dataframe(filtered[show_cols].sort_values(["Bill"]), width="stretch", height=520, hide_index=True)

                        top_filtered_author = ""
                        top_filtered_bill = ""
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
                            if "Bill" in filtered.columns:
                                bill_counts = (
                                    filtered["Bill"]
                                    .fillna("")
                                    .astype(str)
                                    .str.strip()
                                )
                                bill_counts = bill_counts[bill_counts != ""]
                                if not bill_counts.empty:
                                    top_filtered_bill = str(bill_counts.value_counts().index[0]).strip()

                        if top_filtered_author or top_filtered_bill:
                            handoff_bits = []
                            if top_filtered_author:
                                handoff_bits.append(f"Frequent author in current view: {top_filtered_author}.")
                            if top_filtered_bill:
                                handoff_bits.append(f"Most repeated bill in current view: {top_filtered_bill}.")
                            handoff_sub = " ".join(handoff_bits) if handoff_bits else "Carry this filtered slice into the next analysis step."
                            st.markdown(
                                f"""
        <div class="handoff-card">
          <div class="handoff-kicker">Intra-Page Bridge</div>
          <div class="handoff-title">Carry This Bill Slice Forward</div>
          <div class="handoff-sub">{html.escape(handoff_sub, quote=True)}</div>
        </div>
        """,
                                unsafe_allow_html=True,
                            )
                            bnav1, bnav2, bnav3 = st.columns(3)
                            with bnav1:
                                if st.button(
                                    "Open Frequent Author",
                                    key="lobby_bills_to_member_btn",
                                    width="stretch",
                                    disabled=not bool(top_filtered_author),
                                    help="Open the Legislators page with the most frequent author from this filtered bill set.",
                                ):
                                    st.session_state.member_query = top_filtered_author
                                    st.session_state.member_query_input = top_filtered_author
                                    st.session_state.member_name = ""
                                    st.session_state.member_session = st.session_state.session
                                    st.switch_page(_member_page)
                            with bnav2:
                                def _run_bill_mode_from_filtered_bill(bill_id: str) -> None:
                                    bill = str(bill_id).strip()
                                    if not bill:
                                        return
                                    st.session_state.search_query = bill
                                    st.session_state.lobbyshort = ""
                                    st.session_state.lobby_filerid = None
                                    st.session_state.lobby_selected_key = ""
                                    st.session_state.lobby_all_matches = False
                                    st.session_state.lobby_merge_keys = []
                                    st.session_state.lobby_candidate_map = {}
                                    st.session_state.lobby_match_query = bill
                                    st.session_state.lobby_match_select = "No match"
                                    st.session_state.bill_search = ""
                                    st.session_state.activity_search = ""
                                    st.session_state.disclosure_search = ""
                                    st.session_state.lobby_policy_focus = {}

                                st.button(
                                    "Run Top Bill In Bill Mode",
                                    key="lobby_bills_bill_mode_btn",
                                    width="stretch",
                                    disabled=not bool(top_filtered_bill),
                                    help="Switch this workspace into bill-first mode using the top bill in the current filtered view.",
                                    on_click=_run_bill_mode_from_filtered_bill,
                                    args=(top_filtered_bill,),
                                )
                            with bnav3:
                                if st.button(
                                    "Carry Filtered Bills To Policy",
                                    key="lobby_bills_focus_policy_btn",
                                    width="stretch",
                                    disabled=filtered.empty,
                                    help="Use this filtered bill set as the scope for the Policy Subjects tab.",
                                ):
                                    focus_bills = (
                                        filtered.get("Bill", pd.Series(dtype=object))
                                        .dropna()
                                        .astype(str)
                                        .str.strip()
                                    )
                                    focus_bills = focus_bills[focus_bills != ""].drop_duplicates().tolist()
                                    st.session_state.lobby_policy_focus = {
                                        "session": session,
                                        "lobbyshort": lobbyshort,
                                        "bill_ids": focus_bills[:500],
                                    }
                                    st.success(
                                        f"Policy Subjects is now focused to {len(focus_bills):,} bill(s) from this Bills tab view."
                                    )

                        export_context = []
                        if st.session_state.bill_search.strip():
                            export_context.append(f"Bill search: {_shorten_text(st.session_state.bill_search, 28)}")
                        if status_sel and len(status_sel) != len(status_opts):
                            status_label = ", ".join(status_sel[:3])
                            if len(status_sel) > 3:
                                status_label += "..."
                            export_context.append(f"Status: {status_label}")
                        if pos_sel and len(pos_sel) != len(pos_opts):
                            pos_label = ", ".join(pos_sel[:3])
                            if len(pos_sel) > 3:
                                pos_label += "..."
                            export_context.append(f"Position: {pos_label}")
                        _ = export_dataframe(filtered[show_cols], "bills.csv", context=export_context)

                # ---- Policy tab
                with tab_policy:
                    st.markdown('<div class="section-title">Policy Areas</div>', unsafe_allow_html=True)
                    st.markdown(
                        """
        <div class="callout fade-up">
          <div class="callout-title">What this means</div>
          <div class="callout-body">Policy areas are derived from subjects tied to bills where the lobbyist appeared on a witness list. Counts reflect unique bills, not dollars.</div>
        </div>
        """,
                        unsafe_allow_html=True,
                    )
                    policy_focus = st.session_state.get("lobby_policy_focus", {})
                    focus_bill_ids = []
                    focus_active = False
                    if isinstance(policy_focus, dict):
                        focus_session = str(policy_focus.get("session", "")).strip()
                        focus_lobbyshort = str(policy_focus.get("lobbyshort", "")).strip()
                        if focus_session == session and focus_lobbyshort == lobbyshort:
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
                            if st.button("Clear Bills Focus", key="lobby_policy_focus_clear_btn", width="stretch"):
                                st.session_state.lobby_policy_focus = {}
                                focus_active = False
                                focus_bill_ids = []
                    if not require_columns(
                        Bill_Sub_All,
                        ["Bill", "Subject"],
                        "Policy areas",
                        "Texas Legislature Online bill subject data is required for policy analysis.",
                    ):
                        st.info("Policy area view needs Texas Legislature Online bill subject data with Bill and Subject columns.")
                    else:
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
                                st.info(
                                    "No bill-subject rows matched the focused Bills-tab slice. Clear focus or broaden filters."
                                )
                            else:
                                st.info(
                                    "No subjects found (Texas Legislature Online bill subject data returned 0 rows). Try another session or clear the lobbyist filter."
                                )
                        chart_mentions = policy_mentions
                        chart_mentions["SharePct"] = (chart_mentions["Share"] * 100).round(1)
                        chart_mentions = chart_mentions.sort_values("Share", ascending=False)
                        top_mentions = chart_mentions.head(20)
                        if not top_mentions.empty:
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
                            _ = export_dataframe(m2, "policy_areas.csv", context=export_ctx)

                            top_policy_subject = str(top_mentions.iloc[0].get("Subject", "")).strip() if not top_mentions.empty else ""
                            if top_policy_subject:
                                st.markdown(
                                    f"""
        <div class="handoff-card">
          <div class="handoff-kicker">Intra-Page Bridge</div>
          <div class="handoff-title">Reconnect Policy Subjects To Bill Detail</div>
          <div class="handoff-sub">Top policy subject in this view: <strong>{html.escape(top_policy_subject, quote=True)}</strong>. Use actions below to continue the same analysis thread.</div>
        </div>
        """,
                                    unsafe_allow_html=True,
                                )
                                pnav1, pnav2 = st.columns(2)
                                with pnav1:
                                    if st.button(
                                        "Use Top Subject In Bills Tab",
                                        key="lobby_policy_to_bills_btn",
                                        width="stretch",
                                        help="Prefill the Bills tab search box with the top subject from this view.",
                                    ):
                                        st.session_state.bill_search = top_policy_subject
                                        st.success("Bills tab search has been prefilled with the top policy subject.")
                                with pnav2:
                                    if st.button(
                                        "Open Policy Context Page",
                                        key="lobby_policy_open_context_btn",
                                        width="stretch",
                                        help="Open the policy context page to connect this subject trend to drafting options.",
                                    ):
                                        st.switch_page(_solutions_page)

                    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                    st.subheader("Reported Subject Matters (Texas Ethics Commission filings)")
                    if lobby_sub_counts.empty:
                        st.info("No Texas Ethics Commission subject-matter rows found for this lobbyist/session. Try a different session or verify the Texas Ethics Commission subject-matter data in Data health.")
                    else:
                        if subject_non_empty < 0.05:
                            st.caption("Note: Subject Matter is largely blank for this session in the source data. Showing Other Subject Matter Description or Unnamed: 0 when available.")
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
                        _ = export_dataframe(lobby_sub_counts, "reported_subject_matters.csv")

                # ---- Staff tab
                with tab_staff:
                    st.markdown('<div class="section-title">Legislative Staffer History</div>', unsafe_allow_html=True)
                    st.markdown(
                        """
        <div class="callout fade-up">
          <div class="callout-title">What this means</div>
          <div class="callout-body">Staff history shows overlap between lobbyist names and legislative staff records. Use it to identify staff-to-lobbyist transitions.</div>
        </div>
        """,
                        unsafe_allow_html=True,
                    )
                    if not require_columns(
                        Staff_All,
                        ["Legislator", "Staffer"],
                        "Staff history",
                        "House Research Organization staff lists are required for staff history.",
                    ):
                        st.info("Staff view needs House Research Organization staff lists with Legislator and Staffer columns.")
                    elif staff_pick.empty:
                        st.info("No staff-history rows matched for this lobbyist. Try a broader lobbyist match or check House Research Organization staff data.")
                    else:
                        st.caption("Showing staff history across all sessions.")
                        cols = ["Session", "Legislator", "Title", "Staffer"]
                        staff_view = staff_pick[cols].drop_duplicates().sort_values(["Session", "Legislator", "Title"])
                        st.dataframe(staff_view, width="stretch", height=380, hide_index=True)
                        _ = export_dataframe(staff_view, "staff_history.csv")

                    if staff_pick_session.empty:
                        st.caption("Session-specific staff metrics are not shown because there are no matches for the selected session.")
                    elif not staff_stats.empty:
                        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                        st.caption("Computed from authored bills intersected with this lobbyist's witness activity.")
                        s2 = staff_stats
                        for col in ["% Against that Failed", "% For that Passed"]:
                            s2[col] = pd.to_numeric(s2[col], errors="coerce")
                            s2[col] = (s2[col] * 100).round(0)
                        st.dataframe(s2, width="stretch", height=320, hide_index=True)
                        _ = export_dataframe(s2, "staff_stats.csv")

                # ---- Activities tab
                with tab_activities:
                    st.markdown('<div class="section-title">Lobbying Expenditures / Activity</div>', unsafe_allow_html=True)
                    st.markdown(
                        """
        <div class="callout fade-up">
          <div class="callout-title">What this means</div>
          <div class="callout-body">Activity rows summarize reportable expenditures (food, travel, gifts, events). Use type and date filters to focus on a specific time window.</div>
        </div>
        """,
                        unsafe_allow_html=True,
                    )
                    if not require_columns(
                        activities,
                        ["Date", "Type", "Description"],
                        "Activities view",
                        "Texas Ethics Commission activity reports (Food, Entertainment, Travel, Gifts, Events, Awards) are required.",
                    ):
                        st.info("Activities view needs the Texas Ethics Commission activity reports listed in Data health.")
                    elif activities.empty:
                        st.info("No activity rows found for this lobbyist/session (after matching). Try a different session or clear the specific match.")
                        st.caption("If Excel still shows rows, your workbook may key activities on a different ID (e.g., filerID).")
                    else:
                        filt = activities
                        t_opts = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
                        t_opts = sorted(t_opts)
                        sel_types = st.multiselect(
                            "Filter by activity type",
                            t_opts,
                            default=t_opts,
                            help="Limit results to selected activity categories.",
                        )
                        if sel_types:
                            filt = filt[filt["Type"].isin(sel_types)]

                        st.session_state.activity_search = st.text_input(
                            "Search activities (filer, member, description)",
                            value=st.session_state.activity_search,
                            help="Search activity rows by filer, member, or description.",
                        )
                        if st.session_state.activity_search.strip():
                            q = st.session_state.activity_search.strip()
                            filt = filt[
                                filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                                filt["Member"].astype(str).str.contains(q, case=False, na=False) |
                                filt["Description"].astype(str).str.contains(q, case=False, na=False)
                            ]

                        date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                        d_from = None
                        d_to = None
                        if date_parsed.notna().any():
                            min_d = date_parsed.min().date()
                            max_d = date_parsed.max().date()
                            _date_val = st.date_input(
                                "Date range",
                                (min_d, max_d),
                                help="Restrict results to activities within this date range.",
                            )
                            d_from, d_to = (_date_val if isinstance(_date_val, (list, tuple)) and len(_date_val) == 2 else (min_d, max_d))
                            if d_from and d_to:
                                mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                                filt = filt[mask]

                        a1, a2 = st.columns(2)
                        with a1:
                            type_counts = (
                                filt["Type"]
                                .fillna("Unknown")
                                .astype(str)
                                .str.strip()
                                .replace("", "Unknown")
                                .value_counts()
                                .reset_index()
                            )
                            type_counts = type_counts.set_axis(["Type", "Count"], axis=1)
                            if not type_counts.empty:
                                fig_type = px.bar(
                                    type_counts.sort_values("Count"),
                                    x="Count",
                                    y="Type",
                                    orientation="h",
                                    text="Count",
                                )
                                fig_type.update_traces(
                                    textposition="outside",
                                    marker_color="#00e0b8",
                                    cliponaxis=False,
                                    hovertemplate="%{y}: %{x}<extra></extra>",
                                )
                                _apply_plotly_layout(fig_type, showlegend=False, height=220, margin_top=8)
                                fig_type.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                                fig_type.update_xaxes(showgrid=False, title_text="")
                                fig_type.update_yaxes(title_text="")
                                st.plotly_chart(fig_type, width="stretch", config=PLOTLY_CONFIG)
                            else:
                                st.info("No activity types to summarize.")
                        with a2:
                            timeline = build_timeline_counts(filt, "Date")
                            if not timeline.empty:
                                fig_time = px.line(
                                    timeline,
                                    x="Period",
                                    y="Count",
                                    markers=True,
                                )
                                fig_time.update_traces(
                                    line=dict(width=3, color="#1e90ff"),
                                    marker=dict(size=6),
                                    hovertemplate="%{x|%b %Y}: %{y}<extra></extra>",
                                )
                                _apply_plotly_layout(fig_time, showlegend=False, height=220, margin_top=8)
                                fig_time.update_layout(margin=dict(l=8, r=16, t=8, b=8))
                                fig_time.update_xaxes(title_text="")
                                fig_time.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", title_text="")
                                st.plotly_chart(fig_time, width="stretch", config=PLOTLY_CONFIG)
                            else:
                                st.info("No activity timeline available.")

                        st.caption(f"{len(filt):,} rows")
                        st.dataframe(filt, width="stretch", height=560, hide_index=True)
                        export_context = []
                        if sel_types and len(sel_types) != len(t_opts):
                            type_label = ", ".join(sel_types[:3])
                            if len(sel_types) > 3:
                                type_label += "..."
                            export_context.append(f"Types: {type_label}")
                        if st.session_state.activity_search.strip():
                            export_context.append(f"Search: {_shorten_text(st.session_state.activity_search, 28)}")
                        if d_from and d_to:
                            export_context.append(f"Dates: {d_from} to {d_to}")
                        _ = export_dataframe(filt, "activities.csv", context=export_context)

                # ---- Disclosures tab
                with tab_disclosures:
                    st.markdown('<div class="section-title">Disclosures & Subject Matter Filings</div>', unsafe_allow_html=True)
                    st.markdown(
                        """
        <div class="callout fade-up">
          <div class="callout-title">What this means</div>
          <div class="callout-body">Disclosures capture coverage, dockets, and subject-matter filings tied to lobbyist activity. Use date filters to align with the reporting period.</div>
        </div>
        """,
                        unsafe_allow_html=True,
                    )
                    if not require_columns(
                        disclosures,
                        ["Date", "Type", "Description"],
                        "Disclosures view",
                        "Texas Ethics Commission disclosure filings (Coverage, Docket, On Behalf, Subject Matter) are required.",
                    ):
                        st.info("Disclosures view needs Texas Ethics Commission disclosure filings (Coverage, Docket, On Behalf, Subject Matter) in the workbook.")
                    elif disclosures.empty:
                        st.info("No disclosure rows found for this lobbyist/session. Try another session or clear the specific match.")
                    else:
                        filt = disclosures
                        d_types = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
                        d_types = sorted(d_types)
                        sel_types = st.multiselect(
                            "Filter by disclosure type",
                            d_types,
                            default=d_types,
                            help="Limit results to selected disclosure categories.",
                        )
                        if sel_types:
                            filt = filt[filt["Type"].isin(sel_types)]

                        st.session_state.disclosure_search = st.text_input(
                            "Search disclosures (filer, description, entity)",
                            value=st.session_state.disclosure_search,
                            help="Search disclosure rows by filer, description, or entity.",
                        )
                        if st.session_state.disclosure_search.strip():
                            q = st.session_state.disclosure_search.strip()
                            filt = filt[
                                filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                                filt["Description"].astype(str).str.contains(q, case=False, na=False) |
                                filt["Entity"].astype(str).str.contains(q, case=False, na=False)
                            ]

                        date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                        d_from = None
                        d_to = None
                        if date_parsed.notna().any():
                            min_d = date_parsed.min().date()
                            max_d = date_parsed.max().date()
                            _date_val = st.date_input(
                                "Date range",
                                (min_d, max_d),
                                key="disclosure_dates",
                                help="Restrict results to disclosures within this date range.",
                            )
                            d_from, d_to = (_date_val if isinstance(_date_val, (list, tuple)) and len(_date_val) == 2 else (min_d, max_d))
                            if d_from and d_to:
                                mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                                filt = filt[mask]

                        d1, d2 = st.columns(2)
                        with d1:
                            type_counts = (
                                filt["Type"]
                                .fillna("Unknown")
                                .astype(str)
                                .str.strip()
                                .replace("", "Unknown")
                                .value_counts()
                                .reset_index()
                            )
                            type_counts = type_counts.set_axis(["Type", "Count"], axis=1)
                            if not type_counts.empty:
                                fig_type = px.bar(
                                    type_counts.sort_values("Count"),
                                    x="Count",
                                    y="Type",
                                    orientation="h",
                                    text="Count",
                                )
                                fig_type.update_traces(
                                    textposition="outside",
                                    marker_color="#1e90ff",
                                    cliponaxis=False,
                                    hovertemplate="%{y}: %{x}<extra></extra>",
                                )
                                _apply_plotly_layout(fig_type, showlegend=False, height=220, margin_top=8)
                                fig_type.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                                fig_type.update_xaxes(showgrid=False, title_text="")
                                fig_type.update_yaxes(title_text="")
                                st.plotly_chart(fig_type, width="stretch", config=PLOTLY_CONFIG)
                            else:
                                st.info("No disclosure types to summarize.")
                        with d2:
                            timeline = build_timeline_counts(filt, "Date")
                            if not timeline.empty:
                                fig_time = px.line(
                                    timeline,
                                    x="Period",
                                    y="Count",
                                    markers=True,
                                )
                                fig_time.update_traces(
                                    line=dict(width=3, color="#00e0b8"),
                                    marker=dict(size=6),
                                    hovertemplate="%{x|%b %Y}: %{y}<extra></extra>",
                                )
                                _apply_plotly_layout(fig_time, showlegend=False, height=220, margin_top=8)
                                fig_time.update_layout(margin=dict(l=8, r=16, t=8, b=8))
                                fig_time.update_xaxes(title_text="")
                                fig_time.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", title_text="")
                                st.plotly_chart(fig_time, width="stretch", config=PLOTLY_CONFIG)
                            else:
                                st.info("No disclosure timeline available.")

                        st.caption(f"{len(filt):,} rows")
                        st.dataframe(filt, width="stretch", height=560, hide_index=True)
                        export_context = []
                        if sel_types and len(sel_types) != len(d_types):
                            type_label = ", ".join(sel_types[:3])
                            if len(sel_types) > 3:
                                type_label += "..."
                            export_context.append(f"Types: {type_label}")
                        if st.session_state.disclosure_search.strip():
                            export_context.append(f"Search: {_shorten_text(st.session_state.disclosure_search, 28)}")
                        if d_from and d_to:
                            export_context.append(f"Dates: {d_from} to {d_to}")
                        _ = export_dataframe(filt, "disclosures.csv", context=export_context)
    finally:
        _pop_context(_previous, ctx)

