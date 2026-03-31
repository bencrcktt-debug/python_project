from __future__ import annotations

import html
from typing import Any

import pandas as pd
import plotly.express as px
from tfl_app.services import AppServices
from tfl_app.ui.page_state import ensure_map_state

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _StreamlitStub:
        session_state: dict[str, Any] = {}

    st = _StreamlitStub()

def render_page(*, services: AppServices, ctx: dict[str, Any] | None = None) -> None:
    del ctx
    MAP_BASEMAP_OPTIONS = services.require("MAP_BASEMAP_OPTIONS")
    PATH = services.require("PATH")
    _map_fragments = services.require("_map_fragments")
    get_map_atlas_bundle = services.require("get_map_atlas_bundle")
    require_map_state = services.require("require_map_state")
    _build_mp5_css = services.require("_build_mp5_css")
    _client_page = services.require("_client_page")
    _default_session_from_list = services.require("_default_session_from_list")
    _lobby_page = services.require("_lobby_page")
    _member_page = services.require("_member_page")
    _render_page_intro = services.require("_render_page_intro")
    _render_workspace_guide = services.require("_render_workspace_guide")
    _render_workspace_links = services.require("_render_workspace_links")
    _session_label = services.require("_session_label")
    _tfl_session_for_filter = services.require("_tfl_session_for_filter")
    export_dataframe = services.require("export_dataframe")
    fmt_usd = services.require("fmt_usd")
    if True:

        """Map & Address — v5 ground-up redesign."""

        # -- page header --------------------------------------------------
        _render_page_intro(
            kicker="",
            title="Map & Address Workspace",
            subtitle=(
                "Coverage atlas, address-level overlap forensics, and an "
                "investigative case docket for taxpayer-funded entities."
            ),
            pills=["Coverage Atlas", "Address Forensics", "Case Docket"],
        )
        _render_workspace_guide(
            question=(
                "At this location, which taxpayer-funded entities show the "
                "strongest overlap signal and should advance to case review?"
            ),
            steps=[
                "Configure scope and quality thresholds.",
                "Explore the Coverage Atlas to anchor a subdivision context.",
                "Run Address Forensics for location-level evidence.",
                "Promote high-signal leads into the Case Docket.",
            ],
            method_note=(
                "Boundary overlap (spatial containment) is the strongest match "
                "method. Name-anchored fallback carries lower weight."
            ),
        )

        # -- v5 CSS design tokens (PERFORMANCE: built once, cached)
        st.markdown(_build_mp5_css(), unsafe_allow_html=True)
        # -- data gate ----------------------------------------------------
        map_state = require_map_state(
            PATH,
            missing_path_message="Data path not configured. Set DATA_PATH.",
            missing_file_message="Data path not found.",
        )
        base = map_state.lobby_tfl_client_all
        tfl_sessions = set(map_state.map_sessions)

        # -- session-state defaults ---------------------------------------
        defaults = ensure_map_state(next(iter(MAP_BASEMAP_OPTIONS.keys())))
        if st.session_state.get("map_basemap_label") not in MAP_BASEMAP_OPTIONS:
            st.session_state.map_basemap_label = next(iter(MAP_BASEMAP_OPTIONS.keys()))

        sessions = list(map_state.map_sessions)
        if not sessions:
            st.error("No sessions found in workbook.")
            st.stop()
        default_session = _default_session_from_list(sessions)
        if str(st.session_state.get("map_session", "")).strip().lower() in {
            "", "none", "nan", "null",
        }:
            st.session_state.map_session = default_session

        # -- workspace helpers --------------------------------------------
        def _reset_workspace() -> None:
            for key, default in defaults.items():
                if isinstance(default, list):
                    st.session_state[key] = []
                elif isinstance(default, dict):
                    st.session_state[key] = {}
                else:
                    st.session_state[key] = default
            st.session_state.map_session = default_session
            st.session_state.map_basemap_label = next(iter(MAP_BASEMAP_OPTIONS.keys()))

        def _open_client(entity_name: str) -> None:
            value = str(entity_name).strip()
            if not value:
                return
            st.session_state.client_query = value
            st.session_state.client_query_input = value
            st.session_state.client_name = ""
            st.session_state.client_session = st.session_state.map_session
            st.session_state.client_scope = st.session_state.map_scope
            st.switch_page(_client_page)

        def _render_cross_context_banner(tab_origin: str) -> None:
            """Render a shared context strip showing current subdivision context and docket count.
            Provides quick cross-navigation between Coverage Atlas, Address Forensics, and Case Docket."""
            ctx = st.session_state.get("map_selected_subdivision_context", {})
            docket = st.session_state.get("map_watchlist", [])
            docket_count = len(docket) if isinstance(docket, list) else 0
            recent = st.session_state.get("map_recent_addresses", [])
            last_query = str(recent[0]).strip() if isinstance(recent, list) and recent else ""
            has_ctx = isinstance(ctx, dict) and str(ctx.get("subdivision_name", "")).strip()
            ctx_name = html.escape(str(ctx.get("subdivision_name", "")).strip(), quote=True) if has_ctx else ""
            ctx_type = html.escape(str(ctx.get("subdivision_type", "")).strip(), quote=True) if has_ctx else ""
            ctx_badge = (
                f'<span class="mp5-context-badge">\U0001F4CD {ctx_type} — {ctx_name}</span>'
                if has_ctx
                else '<span class="mp5-context-badge empty">No subdivision context</span>'
            )
            docket_badge = (
                f'<span class="mp5-context-badge docket">\U0001F4CB {docket_count:,} in docket</span>'
                if docket_count
                else '<span class="mp5-context-badge empty">\U0001F4CB Docket empty</span>'
            )
            query_badge = (
                f'<span class="mp5-context-badge">\U0001F50D {html.escape(last_query[:40], quote=True)}</span>'
                if last_query
                else ""
            )
            st.markdown(
                f'<div class="mp5-context-strip">{ctx_badge}{docket_badge}{query_badge}</div>',
                unsafe_allow_html=True,
            )

        # ------------------------------------------------------------------
        # COMMAND DECK
        # ------------------------------------------------------------------
        st.markdown('<div class="mp5-glass">', unsafe_allow_html=True)
        st.markdown(
            '<div class="mp5-kicker">Command Deck</div>'
            '<div class="mp5-title">Scope, quality, and rendering controls</div>'
            '<div class="mp5-sub">These thresholds propagate to every tab — atlas filtering, '
            'evidence scoring, and lead ranking.</div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4, c5 = st.columns([1.5, 1.1, 1.0, 0.9, 0.7], gap="small")
        with c1:
            labels = [_session_label(s) for s in sessions]
            label_map = dict(zip(labels, sessions))
            current = _session_label(st.session_state.map_session)
            if current not in labels:
                current = _session_label(default_session)
            picked = st.selectbox(
                "Session", labels,
                index=labels.index(current),
                key="map_session_select_v4",
            )
            st.session_state.map_session = label_map.get(picked, default_session)
        with c2:
            st.session_state.map_scope = st.radio(
                "Scope",
                ["This Session", "All Sessions"],
                index=0 if st.session_state.map_scope == "This Session" else 1,
                key="map_scope_radio_v4",
                horizontal=True,
            )
        with c3:
            st.selectbox("Map style", list(MAP_BASEMAP_OPTIONS.keys()), key="map_basemap_label")
        with c4:
            st.slider("Geocode floor", 60, 99, key="map_geocode_floor")
        with c5:
            st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
            if st.button("? Reset", key="map_reset_workspace_btn_v4", use_container_width=True):
                _reset_workspace()
                st.rerun()

        with st.expander("Advanced thresholds", expanded=False):
            a1, a2, a3 = st.columns(3, gap="small")
            with a1:
                st.number_input("Min entity high ($)", min_value=0.0, step=25000.0, key="map_probe_min_high")
            with a2:
                st.slider("Distance cap (mi)", 10, 300, key="map_distance_cap_miles")
            with a3:
                st.number_input("Map point cap", min_value=100, max_value=1600, step=50, key="map_subdivision_map_cap")

        # -- active filter summary chips ----------------------------------
        _active_chips = [
            f"Session: {html.escape(_session_label(st.session_state.map_session))}",
            f"Scope: {html.escape(st.session_state.map_scope)}",
            f"Map: {html.escape(st.session_state.get('map_basemap_label', 'Gray Canvas'))}",
            f"Geocode floor: {int(st.session_state.get('map_geocode_floor', 82))}",
        ]
        _min_high_val = float(st.session_state.get("map_probe_min_high", 0.0) or 0.0)
        if _min_high_val > 0:
            _active_chips.append(f"Min high: {fmt_usd(_min_high_val)}")
        _dist_cap = int(st.session_state.get("map_distance_cap_miles", 160) or 160)
        if _dist_cap < 160:
            _active_chips.append(f"Distance cap: {_dist_cap} mi")
        _ctx_v6 = st.session_state.get("map_selected_subdivision_context", {})
        if isinstance(_ctx_v6, dict) and str(_ctx_v6.get("subdivision_name", "")).strip():
            _active_chips.append(f"Context: {html.escape(str(_ctx_v6.get('subdivision_type', '')).strip())} — {html.escape(str(_ctx_v6.get('subdivision_name', '')).strip())}")
        _watchlist_count = len(st.session_state.get("map_watchlist", []))
        if _watchlist_count > 0:
            _active_chips.append(f"Docket: {_watchlist_count:,} entities")
        _chip_html = " ".join(
            f'<span class="mp5-preset-btn">{c}</span>' for c in _active_chips
        )
        st.markdown(
            f'<div class="mp5-action-strip">'
            f'<span class="mp5-action-label">Active</span>{_chip_html}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)

        # -- scope + coverage data (CACHED) -------------------------------
        session_for_filter = _tfl_session_for_filter(
            st.session_state.map_session, tfl_sessions,
        )
        atlas_bundle = get_map_atlas_bundle(
            str(PATH),
            st.session_state.map_scope,
            session_for_filter,
        )
        totals = atlas_bundle.totals
        tfl_spend = atlas_bundle.tfl_spend
        subdivision_matches = atlas_bundle.subdivision_matches
        matched_clients = set(atlas_bundle.matched_clients)
        total_tfl = int(atlas_bundle.total_tfl or 0)
        total_high = float(atlas_bundle.total_high or 0.0)
        mapped_high = float(atlas_bundle.mapped_high or 0.0)
        mapped_rate = float(atlas_bundle.mapped_rate or 0.0)
        unmapped_count = int(atlas_bundle.unmapped_count or 0)
        hotspot_label = str(getattr(atlas_bundle, "hotspot_label", "—") or "—").replace(" - ", " — ")
        hotspot_high = float(getattr(atlas_bundle, "hotspot_high", 0.0) or 0.0)

        # ------------------------------------------------------------------
        # SITUATION DASHBOARD
        # ------------------------------------------------------------------
        st.markdown('<div class="mp5-glass-inner">', unsafe_allow_html=True)
        st.markdown(
            '<div class="mp5-kicker">Situation Dashboard</div>'
            '<div class="mp5-title">Statewide coverage baseline</div>',
            unsafe_allow_html=True,
        )

        # narrative callout
        if mapped_rate >= 0.75:
            coverage_narrative = (
                f"Strong coverage: <strong>{len(matched_clients):,}</strong> of "
                f"<strong>{total_tfl:,}</strong> TFL entities are mapped to at least one "
                f"political subdivision ({mapped_rate:.0%} entity rate, "
                f"{(mapped_high / total_high) if total_high else 0:.0%} by spend)."
            )
        elif mapped_rate >= 0.40:
            coverage_narrative = (
                f"Moderate coverage: <strong>{len(matched_clients):,}</strong> of "
                f"<strong>{total_tfl:,}</strong> entities mapped ({mapped_rate:.0%}). "
                f"<strong>{unmapped_count:,}</strong> entities have no subdivision anchor — "
                "address forensics will rely more on name-based fallback."
            )
        else:
            coverage_narrative = (
                f"Low coverage: only <strong>{len(matched_clients):,}</strong> of "
                f"<strong>{total_tfl:,}</strong> entities mapped ({mapped_rate:.0%}). "
                "Forensic results may be sparse; consider broadening scope or lowering "
                "the match-count threshold."
            )
        st.markdown(f'<div class="mp5-narrative">{coverage_narrative}</div>', unsafe_allow_html=True)

        # -- visual coverage health bar -----------------------------------
        _health_pct = min(100.0, mapped_rate * 100.0)
        _health_cls = "is-strong" if mapped_rate >= 0.70 else ("is-moderate" if mapped_rate >= 0.40 else "is-weak")
        _spend_pct = min(100.0, ((mapped_high / total_high) * 100.0) if total_high else 0.0)
        _spend_cls = "is-strong" if _spend_pct >= 70 else ("is-moderate" if _spend_pct >= 40 else "is-weak")
        st.markdown(
            f"""
    <div class="mp5-health">
      <div class="mp5-health-label"><span>Entity Coverage</span><span>{_health_pct:.1f}%</span></div>
      <div class="mp5-health-track"><div class="mp5-health-fill {_health_cls}" style="width:{_health_pct:.1f}%"></div></div>
    </div>
    <div class="mp5-health">
      <div class="mp5-health-label"><span>Spend Coverage</span><span>{_spend_pct:.1f}%</span></div>
      <div class="mp5-health-track"><div class="mp5-health-fill {_spend_cls}" style="width:{_spend_pct:.1f}%"></div></div>
    </div>
    """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
    <div class="mp5-metrics">
      <div class="mp5-card">
        <div class="mp5-card-lbl">Entity Coverage</div>
        <div class="mp5-card-val">{mapped_rate:.1%}</div>
        <div class="mp5-card-sub">{len(matched_clients):,} of {total_tfl:,} entities</div>
      </div>
      <div class="mp5-card">
        <div class="mp5-card-lbl">Spend Coverage</div>
        <div class="mp5-card-val">{(mapped_high / total_high) if total_high else 0:.1%}</div>
        <div class="mp5-card-sub">{fmt_usd(mapped_high)} of {fmt_usd(total_high)}</div>
      </div>
      <div class="mp5-card">
        <div class="mp5-card-lbl">Atlas Rows</div>
        <div class="mp5-card-val">{len(subdivision_matches):,}</div>
        <div class="mp5-card-sub">mapped subdivisions</div>
      </div>
      <div class="mp5-card">
        <div class="mp5-card-lbl">Top Hotspot</div>
        <div class="mp5-card-val" style="font-size:.94rem">{html.escape(hotspot_label, quote=True)}</div>
        <div class="mp5-card-sub">{fmt_usd(hotspot_high)} high estimate</div>
      </div>
      <div class="mp5-card">
        <div class="mp5-card-lbl">Unmapped</div>
        <div class="mp5-card-val">{unmapped_count:,}</div>
        <div class="mp5-card-sub">entities with no subdivision anchor</div>
      </div>
    </div>
    """,
            unsafe_allow_html=True,
        )

        # -- top coverage gaps alert --------------------------------------
        _unmapped_tfl_names = set()
        if not tfl_spend.empty:
            _all_tfl_names_dash = {
                str(v).strip()
                for v in tfl_spend["Client"].dropna().astype(str).tolist()
                if str(v).strip()
            }
            _unmapped_tfl_names = _all_tfl_names_dash - matched_clients
        if _unmapped_tfl_names:
            _gap_df = tfl_spend[tfl_spend["Client"].astype(str).isin(_unmapped_tfl_names)]
            _gap_df = _gap_df.sort_values("High", ascending=False).head(5)
            _gap_items_html = ""
            for _gap_rec in _gap_df.to_dict("records"):
                _gap_items_html += (
                    f'<div style="display:flex;justify-content:space-between;font-size:.76rem;'
                    f'padding:2px 0;border-bottom:1px solid rgba(255,255,255,.05)">'
                    f'<span style="color:rgba(255,220,223,.88)">{html.escape(str(_gap_rec["Client"]).strip())}</span>'
                    f'<span style="color:rgba(247,186,189,.78)">{fmt_usd(float(_gap_rec.get("High", 0.0) or 0.0))}</span>'
                    f'</div>'
                )
            st.markdown(
                f"""
    <div class="mp5-gap-alert">
      <div class="mp5-gap-icon">!</div>
      <div class="mp5-gap-body">
        <div class="mp5-gap-title">Top {min(5, len(_gap_df)):,} Unmapped Entities by Spend</div>
        <div class="mp5-gap-sub">These entities have no subdivision match. Address forensics may still detect them via name-based overlap.</div>
        {_gap_items_html}
      </div>
    </div>
    """,
                unsafe_allow_html=True,
            )

        # -- coverage distribution in two columns -------------------------
        _dash_left, _dash_right = st.columns([1.4, 1.0], gap="large")

        # -- coverage distribution mini-chart -----------------------------
        if not subdivision_matches.empty:
            type_dist = (
                subdivision_matches.groupby(
                    subdivision_matches["subdivision_type"].astype(str).str.strip(),
                )
                .agg(
                    subdivisions=("subdivision_name", "size"),
                    high_total=("high_total", "sum"),
                )
                .reset_index()
                .rename(columns={"subdivision_type": "Type"})
                .sort_values("high_total", ascending=False)
            )
            with _dash_left:
                if len(type_dist) > 1:
                    fig_dist = px.bar(
                        type_dist,
                        x="Type",
                        y="high_total",
                        color="subdivisions",
                        color_continuous_scale="tealgrn",
                        labels={"high_total": "High Estimate ($)", "subdivisions": "Count"},
                        title="Coverage by Subdivision Type",
                    )
                    fig_dist.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="rgba(210,230,245,.88)",
                        title_font_size=13,
                        margin=dict(l=10, r=10, t=36, b=10),
                        height=250,
                        coloraxis_colorbar=dict(thickness=12, len=0.6),
                    )
                    fig_dist.update_xaxes(showgrid=False, tickangle=-35)
                    fig_dist.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                    st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                    st.plotly_chart(fig_dist, use_container_width=True, key="mp5_cov_dist_chart")
                    st.markdown("</div>", unsafe_allow_html=True)

            with _dash_right:
                # -- entity type breakdown (top 8) ------------------------
                if not tfl_spend.empty and "Entity Type" in tfl_spend.columns:
                    _etype_summary = (
                        tfl_spend.groupby("Entity Type", as_index=False)
                        .agg(Entities=("Client", "nunique"), High=("High", "sum"))
                        .sort_values("High", ascending=False)
                        .head(8)
                    )
                    if not _etype_summary.empty:
                        fig_etype_dash = px.pie(
                            _etype_summary,
                            names="Entity Type",
                            values="High",
                            title="Spend by Entity Type",
                            hole=0.45,
                            color_discrete_sequence=px.colors.qualitative.Set3,
                        )
                        fig_etype_dash.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font_color="rgba(210,230,245,.88)",
                            title_font_size=13,
                            margin=dict(l=10, r=10, t=36, b=10),
                            height=250,
                            showlegend=True,
                            legend=dict(
                                orientation="h",
                                font_size=9,
                                yanchor="top",
                                y=-0.08,
                                xanchor="center",
                                x=0.5,
                            ),
                        )
                        st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                        st.plotly_chart(fig_etype_dash, use_container_width=True, key="mp5_etype_dash_chart")
                        st.markdown("</div>", unsafe_allow_html=True)
        else:
            with _dash_left:
                st.info("No subdivision matches available for chart.")

        st.markdown("</div>", unsafe_allow_html=True)

        # ------------------------------------------------------------------
        # TABS (with count badges)
        # ------------------------------------------------------------------
        _atlas_count = len(subdivision_matches) if not subdivision_matches.empty else 0
        _docket_count = len(st.session_state.get("map_watchlist", []))
        _atlas_label = f"\U0001f5fa\ufe0f Coverage Atlas ({_atlas_count:,})"
        _forensics_label = "\U0001f50d Address Forensics"
        _docket_label = f"\U0001f4cb Case Docket ({_docket_count:,})" if _docket_count else "\U0001f4cb Case Docket"

        _map_fragments.remember_map_workspace_transient_context(
            "_map_workspace_ctx",
            {
                "_open_client": _open_client,
                "_render_cross_context_banner": _render_cross_context_banner,
            },
        )
        _map_fragments.merge_fragment_session_context(
            "_map_workspace_ctx",
            {"PATH": str(PATH)},
        )
        _map_fragments.render_map_workspace_fragment("_map_workspace_ctx")
        return
