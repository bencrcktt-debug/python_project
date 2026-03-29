from __future__ import annotations

from typing import Any

import pandas as pd

from tfl_app.services import WorkspaceServices

from . import _workspace_core as _core
from .context_adapters import merge_workspace_runtime_context, normalize_lobby_workspace_context

# Keep the shared helper namespace stable while this module owns the lobby renderer.
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
    return merge_workspace_runtime_context(normalize_lobby_workspace_context(ctx), services)


def _normalize_policy_mentions_frame(policy_mentions: Any) -> pd.DataFrame:
    out = policy_mentions.copy() if isinstance(policy_mentions, pd.DataFrame) else pd.DataFrame()
    if "Subject" not in out.columns:
        out["Subject"] = pd.Series(dtype="object")
    if "Mentions" not in out.columns:
        out["Mentions"] = pd.Series(dtype="float64")
    if "Share" not in out.columns:
        out["Share"] = pd.Series(dtype="float64")
    out["Subject"] = out["Subject"].fillna("").astype(str)
    out["Mentions"] = pd.to_numeric(out["Mentions"], errors="coerce").fillna(0)
    out["Share"] = pd.to_numeric(out["Share"], errors="coerce").fillna(0.0)
    return out

def render_lobby_workspace(ctx: Any, services: WorkspaceServices | None = None) -> None:
    ctx = _runtime_ctx(ctx, services)
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
                        policy_mentions = _normalize_policy_mentions_frame(policy_mentions)
                        chart_mentions = policy_mentions.copy()
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

