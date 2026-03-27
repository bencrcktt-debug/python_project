from __future__ import annotations

from typing import Any
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import plotly.express as px
import tfl_app.charts.runtime as _chart_runtime
from tfl_app.services import MapServices

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _CacheStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
                func = decorator_args[0]
                func.clear = lambda: None
                return func

            def decorator(func):
                func.clear = lambda: None
                return func

            return decorator

    class _StreamlitStub:
        session_state: dict[str, Any] = {}
        cache_data = _CacheStub()
    st = _StreamlitStub()

_MISSING = object()
query_texas_subdivisions_for_point = None
build_overlap_map_points = None
build_address_overlap_spending_rows = None
classify_requested_entity_type = lambda value: ""
_mp5_miles = lambda *args, **kwargs: float("nan")
_mp5_method_weight = lambda value: 0.0
_mp5_confidence_weight = lambda value: 0.0

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


def _hash_mapping(value: dict[str, Any]) -> str:
    normalized: dict[str, Any] = {}
    for key, item in sorted((value or {}).items(), key=lambda pair: str(pair[0])):
        if isinstance(item, pd.DataFrame):
            normalized[str(key)] = _chart_runtime.hash_dataframe_for_cache(item)
        else:
            normalized[str(key)] = item
    return _chart_runtime.stable_json_signature(normalized)


@st.cache_data(
    show_spinner=False,
    ttl=300,
    max_entries=128,
    hash_funcs={pd.DataFrame: _chart_runtime.hash_dataframe_for_cache, dict: _hash_mapping},
)
def _build_overlap_probe_cached(
    atlas_signature: str,
    lat: float,
    lon: float,
    subdivision_matches: pd.DataFrame,
    tfl_spend: pd.DataFrame,
    prepared_overlap_pools: dict[str, pd.DataFrame],
    spend_lookup: dict[str, dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    del atlas_signature
    overlap_sub = query_texas_subdivisions_for_point(round(float(lon), 6), round(float(lat), 6))
    overlap_points = build_overlap_map_points(
        overlap_subdivisions=overlap_sub,
        subdivision_matches=subdivision_matches,
        prepared_overlap_pools=prepared_overlap_pools,
    )
    overlap_spend = build_address_overlap_spending_rows(
        overlap_subdivisions=overlap_sub,
        subdivision_matches=subdivision_matches,
        tfl_spending=tfl_spend,
        prepared_overlap_pools=prepared_overlap_pools,
        spend_lookup=spend_lookup,
    )
    return overlap_points, overlap_spend


@st.cache_data(
    show_spinner=False,
    ttl=300,
    max_entries=128,
    hash_funcs={pd.DataFrame: _chart_runtime.hash_dataframe_for_cache},
)
def _build_overlap_evidence_rows_cached(
    atlas_signature: str,
    lat: float,
    lon: float,
    overlap_points: pd.DataFrame,
    overlap_spend: pd.DataFrame,
) -> pd.DataFrame:
    del atlas_signature
    rows = overlap_spend.copy()
    rows["Low"] = pd.to_numeric(rows["Low"], errors="coerce").fillna(0.0)
    rows["High"] = pd.to_numeric(rows["High"], errors="coerce").fillna(0.0)
    rows["Mid"] = pd.to_numeric(rows["Mid"], errors="coerce").fillna(0.0)
    rows["Entity Type"] = rows.get("Entity Type", "").fillna("").astype(str).str.strip()
    missing_type = rows["Entity Type"] == ""
    rows.loc[missing_type, "Entity Type"] = rows.loc[
        missing_type, "TFL Entity"
    ].map(classify_requested_entity_type)

    dist_lookup: dict[tuple[str, str, str], float] = {}
    if isinstance(overlap_points, pd.DataFrame) and not overlap_points.empty:
        for point in overlap_points.itertuples(index=False):
            key = (
                str(getattr(point, "subdivision_type", "")).strip(),
                str(getattr(point, "subdivision_name", "")).strip(),
                str(getattr(point, "subdivision_code", "")).strip(),
            )
            dist_lookup[key] = _mp5_miles(
                float(lat),
                float(lon),
                float(getattr(point, "lat", 0.0)),
                float(getattr(point, "lon", 0.0)),
            )

    row_keys = list(
        zip(
            rows.get("Subdivision Type", pd.Series("", index=rows.index)).fillna("").astype(str).str.strip(),
            rows.get("Subdivision", pd.Series("", index=rows.index)).fillna("").astype(str).str.strip(),
            rows.get("Code", pd.Series("", index=rows.index)).fillna("").astype(str).str.strip(),
        )
    )
    rows["Distance Miles"] = pd.Series([dist_lookup.get(key, float("nan")) for key in row_keys], index=rows.index)
    rows["Method Weight"] = rows["Match Method"].map(_mp5_method_weight)
    rows["Confidence Weight"] = rows["Match Confidence"].map(_mp5_confidence_weight)
    rows["Boundary Match"] = rows["Match Method"].astype(str).str.lower().str.startswith("spatial boundary")
    row_distance = rows["Distance Miles"].astype(float)
    dist_factor = (1.0 / (1.0 + (row_distance.clip(lower=0.0) / 70.0))).fillna(0.72)
    rows["Row Signal"] = rows["High"] * rows["Method Weight"] * rows["Confidence Weight"] * dist_factor
    return rows

def render_map_workspace(ctx: dict[str, Any], services: MapServices | None = None) -> None:
    runtime_ctx = dict(getattr(services, "values", {}))
    runtime_ctx.update(dict(ctx or {}))
    _previous = _push_context(runtime_ctx)
    try:
        tab_cov, tab_forensics, tab_docket = st.tabs([
            _atlas_label,
            _forensics_label,
            _docket_label,
        ])

        # ------------------------------------------------------------------
        # TAB 1 â€” COVERAGE ATLAS
        # ------------------------------------------------------------------
        with tab_cov:
            # -- cross-context banner -------------------------------------
            _render_cross_context_banner("atlas")
            # -- section hero ---------------------------------------------
            st.markdown(
                f"""
            <div class="mp5-section-hero">
              <div class="mp5-section-num">1</div>
              <div class="mp5-title">Coverage Atlas</div>
              <div class="mp5-sub">Explore statewide subdivision coverage patterns and anchor a context for downstream address forensics. Filter by type, match depth, and name to narrow the investigation area.</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            if subdivision_matches.empty:
                st.info("No mapped subdivision matches found for this scope.")
            else:
                all_types = sorted({
                    str(v).strip()
                    for v in subdivision_matches.get(
                        "subdivision_type", pd.Series(dtype=object),
                    ).dropna().tolist()
                    if str(v).strip()
                })
                if not st.session_state.get("map_subdivision_types_filter"):
                    st.session_state.map_subdivision_types_filter = list(all_types)
                st.session_state.map_subdivision_types_filter = [
                    str(v) for v in st.session_state.get("map_subdivision_types_filter", [])
                    if str(v) in all_types
                ] or list(all_types)

                max_match = int(max(
                    1,
                    pd.to_numeric(
                        subdivision_matches.get("match_count", 1), errors="coerce",
                    ).fillna(1).max(),
                ))
                st.session_state.map_min_match_count = min(
                    max(1, int(st.session_state.get("map_min_match_count", 1))),
                    max_match,
                )
                sort_options = [
                    "Highest Signal",
                    "Highest High",
                    "Most Matched Entities",
                    "Subdivision A-Z",
                ]
                if st.session_state.get("map_subdivision_sort_v4") not in sort_options:
                    st.session_state.map_subdivision_sort_v4 = "Highest Signal"

                # -- atlas filters ----------------------------------------
                st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)

                # quick-filter presets
                _core_types = {"School District", "County", "City"}
                _special_types = set(all_types) - _core_types
                _pq1, _pq2, _pq3, _pq4 = st.columns(4, gap="small")
                with _pq1:
                    if st.button("All Types", key="map_preset_all_types", use_container_width=True):
                        st.session_state.map_subdivision_types_filter = list(all_types)
                        st.rerun()
                with _pq2:
                    if st.button("Core Only", key="map_preset_core_types", use_container_width=True, help="School District, County, City"):
                        st.session_state.map_subdivision_types_filter = [t for t in all_types if t in _core_types]
                        st.rerun()
                with _pq3:
                    if st.button("Special Districts", key="map_preset_special_types", use_container_width=True, help="All types excluding School District, County, City"):
                        st.session_state.map_subdivision_types_filter = [t for t in all_types if t in _special_types]
                        st.rerun()
                with _pq4:
                    if st.button("High-Spend Only", key="map_preset_high_spend", use_container_width=True, help="Min 2 matched entities"):
                        st.session_state.map_subdivision_types_filter = list(all_types)
                        st.session_state.map_min_match_count = min(2, max_match)
                        st.rerun()

                f1, f2, f3, f4 = st.columns([1.8, 0.9, 1.3, 1.0], gap="small")
                with f1:
                    st.multiselect("Subdivision types", all_types, key="map_subdivision_types_filter")
                with f2:
                    st.slider("Min entities", 1, max_match, key="map_min_match_count")
                with f3:
                    st.text_input(
                        "Name / entity contains",
                        key="map_subdivision_name_filter",
                        placeholder="City, county, district, or clientâ€¦",
                    )
                with f4:
                    st.selectbox("Sort", sort_options, key="map_subdivision_sort_v4")

                # -- apply filters ----------------------------------------
                selected_types = st.session_state.get("map_subdivision_types_filter", [])
                query = str(st.session_state.get("map_subdivision_name_filter", "")).strip().lower()
                sort_mode = st.session_state.get("map_subdivision_sort_v4", "Highest Signal")
                atlas_filter_signature = _chart_runtime.stable_json_signature(
                    {
                        "atlas_signature": atlas_bundle.map_payload_signature,
                        "selected_types": sorted(str(v) for v in selected_types),
                        "min_match_count": int(st.session_state.get("map_min_match_count", 1)),
                        "query": query,
                        "sort_mode": sort_mode,
                    }
                )
                atlas_filter_bundle = _chart_runtime.build_filtered_atlas_bundle(
                    atlas_filter_signature,
                    subdivision_matches,
                    selected_types=[str(v) for v in selected_types],
                    min_match_count=int(st.session_state.get("map_min_match_count", 1)),
                    query=query,
                    sort_mode=sort_mode,
                )
                filtered_cov = atlas_filter_bundle["filtered_cov"]
                cov_total_high_filtered = float(atlas_filter_bundle["cov_total_high_filtered"] or 0.0)
                cov_total_low_filtered = float(atlas_filter_bundle["cov_total_low_filtered"] or 0.0)
                cov_entity_count = int(atlas_filter_bundle["cov_entity_count"] or 0)
                _cov_type_count = int(atlas_filter_bundle["cov_type_count"] or 0)
                _cov_avg_match = float(atlas_filter_bundle["cov_avg_match"] or 0.0)
                _cov_filter_pct = float(atlas_filter_bundle["cov_filter_pct"] or 0.0)

                st.markdown(
                    f"""
            <div class="mp5-metrics">
              <div class="mp5-card"><div class="mp5-card-lbl">Filtered Subdivisions</div><div class="mp5-card-val">{len(filtered_cov):,}</div><div class="mp5-card-sub">{_cov_filter_pct:.0f}% of atlas</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Unique Entities</div><div class="mp5-card-val">{cov_entity_count:,}</div><div class="mp5-card-sub">across {_cov_type_count} subdivision types</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Spend Range</div><div class="mp5-card-val">{fmt_usd(cov_total_high_filtered)}</div><div class="mp5-card-sub">Low: {fmt_usd(cov_total_low_filtered)}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Avg Entity Depth</div><div class="mp5-card-val">{_cov_avg_match:.1f}</div><div class="mp5-card-sub">entities per subdivision</div></div>
            </div>
            """,
                    unsafe_allow_html=True,
                )

                # -- map + context picker ---------------------------------
                left, right = st.columns([1.65, 1.0], gap="large")
                with left:
                    if filtered_cov.empty:
                        st.warning("No subdivisions remain after filters.")
                    else:
                        render_subdivision_map_legend(
                            filtered_cov["subdivision_type"].value_counts().to_dict(),
                        )
                        active_basemap = MAP_BASEMAP_OPTIONS.get(
                            st.session_state.get("map_basemap_label", ""), "gray-vector",
                        )
                        cap = max(100, min(
                            1600,
                            int(st.session_state.get("map_subdivision_map_cap", 550) or 550),
                        ))
                        render_tfl_subdivision_arcgis_map(
                            filtered_cov.head(cap), height=630, basemap=active_basemap,
                        )
                        # -- Invisible bridge: receives addresses from map and routes to session state --
                        _bridge_result = _atlas_bridge(default=None, key="_tfl_atlas_bridge_v2")
                        if _bridge_result and isinstance(_bridge_result, dict):
                            _br_nonce = _bridge_result.get("nonce", 0)
                            if _br_nonce != st.session_state.get("_tfl_bridge_last_nonce"):
                                st.session_state["_tfl_bridge_last_nonce"] = _br_nonce
                                _br_action = _bridge_result.get("action", "")
                                if _br_action == "forensics":
                                    _br_addr = str(_bridge_result.get("address", "")).strip()
                                    if _br_addr:
                                        st.session_state.map_overlap_input_mode = "Street Address"
                                        st.session_state.map_overlap_address_input = _br_addr
                                        st.session_state.map_overlap_address_query = _br_addr
                                        recent = [_br_addr] + [
                                            str(v).strip()
                                            for v in st.session_state.get("map_recent_addresses", [])
                                            if str(v).strip() and str(v).strip().lower() != _br_addr.lower()
                                        ]
                                        st.session_state.map_recent_addresses = recent[:10]
                                        st.rerun()
                                elif _br_action == "batch":
                                    _br_addrs = _bridge_result.get("addresses", [])
                                    if _br_addrs:
                                        _new_batch = "\n".join(str(a).strip() for a in _br_addrs if str(a).strip())
                                        existing_batch = str(st.session_state.get("map_batch_input_v4", "")).strip()
                                        st.session_state.map_batch_input_v4 = (
                                            f"{existing_batch}\n{_new_batch}" if existing_batch else _new_batch
                                        )
                                        st.rerun()

                with right:
                    st.markdown(
                        '<div class="mp5-kicker" style="margin-bottom:6px">'
                        "Investigation Context</div>",
                        unsafe_allow_html=True,
                    )
                    labels_atlas, rows_atlas = [], []
                    for row in filtered_cov.head(350).itertuples(index=False):
                        code = str(getattr(row, "subdivision_code", "")).strip() or "N/A"
                        label = (
                            f"{str(getattr(row, 'subdivision_type', '')).strip()} â€” "
                            f"{str(getattr(row, 'subdivision_name', '')).strip()} ({code})"
                        )
                        labels_atlas.append(label)
                        rows_atlas.append(row)

                    opts_atlas = [""] + labels_atlas
                    if st.session_state.get("map_subdivision_pick_v4", "") not in opts_atlas:
                        st.session_state.map_subdivision_pick_v4 = ""
                    pick = st.selectbox(
                        "Select subdivision",
                        opts_atlas,
                        key="map_subdivision_pick_v4",
                    )
                    b1, b2 = st.columns(2, gap="small")
                    with b1:
                        set_ctx = st.button(
                            "Set Context",
                            key="map_set_context_btn_v4",
                            use_container_width=True,
                            disabled=not bool(pick),
                        )
                    with b2:
                        clear_ctx = st.button(
                            "Clear Context",
                            key="map_clear_context_btn_v4",
                            use_container_width=True,
                        )

                    if set_ctx and pick in labels_atlas:
                        row = rows_atlas[labels_atlas.index(pick)]
                        clients = sorted({
                            str(v).strip()
                            for v in (
                                getattr(row, "match_clients", [])
                                if isinstance(getattr(row, "match_clients", []), list)
                                else []
                            )
                            if str(v).strip()
                        })
                        st.session_state.map_selected_subdivision_context = {
                            "subdivision_type": str(getattr(row, "subdivision_type", "")).strip(),
                            "subdivision_name": str(getattr(row, "subdivision_name", "")).strip(),
                            "subdivision_code": str(getattr(row, "subdivision_code", "")).strip(),
                            "match_count": int(getattr(row, "match_count", 0) or 0),
                            "high_total": float(getattr(row, "high_total", 0.0) or 0.0),
                            "clients": clients,
                        }
                        st.rerun()
                    if clear_ctx:
                        st.session_state.map_selected_subdivision_context = {}
                        st.rerun()

                    ctx = st.session_state.get("map_selected_subdivision_context", {})
                    if isinstance(ctx, dict) and str(ctx.get("subdivision_name", "")).strip():
                        _ctx_clients_list = [str(v).strip() for v in ctx.get("clients", []) if str(v).strip()]
                        _ctx_preview = ", ".join(_ctx_clients_list[:6])
                        if len(_ctx_clients_list) > 6:
                            _ctx_preview += f" +{len(_ctx_clients_list) - 6} more"
                        st.markdown(
                            f"""
            <div class="mp5-anchor">
              <strong>{html.escape(str(ctx.get("subdivision_type", "")), quote=True)} â€” {html.escape(str(ctx.get("subdivision_name", "")), quote=True)}</strong><br>
              Code: {html.escape(str(ctx.get("subdivision_code", "") or "N/A"), quote=True)}<br>
              Matched entities: <strong>{int(ctx.get("match_count", 0) or 0):,}</strong> â€” High estimate: <strong>{fmt_usd(float(ctx.get("high_total", 0.0) or 0.0))}</strong><br>
              <span style="font-size:.74rem;color:rgba(195,220,236,.72)">Clients: {html.escape(_ctx_preview or "None", quote=True)}</span>
            </div>
            """,
                            unsafe_allow_html=True,
                        )
                        st.caption("Context is active. Switch to Address Forensics to investigate this subdivision's overlap.")
                        _ctxlink1, _ctxlink2 = st.columns(2, gap="small")
                        with _ctxlink1:
                            if st.button("\U0001F50D Investigate in Forensics", key="atlas_ctx_to_forensics_inline", use_container_width=True):
                                st.info("Switch to the **Address Forensics** tab â€” your context is loaded.")
                        with _ctxlink2:
                            _ctx_client_list = ctx.get("clients", [])
                            if st.button(
                                f"\U0001F4CB Promote {len(_ctx_client_list):,} Entities to Docket",
                                key="atlas_ctx_promote_inline",
                                use_container_width=True,
                                disabled=not _ctx_client_list,
                            ):
                                _watch = st.session_state.get("map_watchlist", [])
                                if not isinstance(_watch, list):
                                    _watch = []
                                _existing_keys = {str(r.get("TFL Entity", "")).strip().lower() for r in _watch if isinstance(r, dict)}
                                _stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                                _added_n = 0
                                for _ent in _ctx_client_list:
                                    _ek = str(_ent).strip().lower()
                                    if not _ek or _ek in _existing_keys:
                                        continue
                                    _watch.append({
                                        "Added": _stamp,
                                        "TFL Entity": str(_ent).strip(),
                                        "Priority": "Tier 2",
                                        "Lead Score": 0.0,
                                        "Signal Score": 0.0,
                                        "High": float(ctx.get("high_total", 0.0) or 0.0),
                                        "High Confidence Share": 0.0,
                                        "Boundary Share": 0.0,
                                        "Avg Distance (mi)": float("nan"),
                                        "Overlap Rows": 0,
                                        "Source Query": f"Coverage Atlas: {str(ctx.get('subdivision_type', '')).strip()} â€” {str(ctx.get('subdivision_name', '')).strip()}",
                                        "Status": "New",
                                        "Notes": "",
                                    })
                                    _existing_keys.add(_ek)
                                    _added_n += 1
                                st.session_state.map_watchlist = _watch
                                if _added_n:
                                    st.success(f"Promoted {_added_n:,} entities to Case Docket.")
                                else:
                                    st.info("All context entities already in docket.")
                    else:
                        st.markdown(
                            '<div class="mp5-anchor-empty">No context anchor. '
                            "Select a subdivision above to scope Address Forensics.</div>",
                            unsafe_allow_html=True,
                        )

                    # entity type distribution for filtered set
                    if not filtered_cov.empty:
                        _atlas_type_summary = (
                            filtered_cov.groupby(
                                filtered_cov["subdivision_type"].astype(str).str.strip(),
                                as_index=False,
                            ).agg(
                                Count=("subdivision_name", "size"),
                                High=("high_total", "sum"),
                            )
                            .sort_values("High", ascending=False)
                        )
                        if not _atlas_type_summary.empty:
                            _atlas_type_summary["High"] = _atlas_type_summary["High"].map(fmt_usd)
                            st.markdown(
                                '<div class="mp5-kicker" style="margin-top:10px;margin-bottom:4px">Type Summary</div>',
                                unsafe_allow_html=True,
                            )
                            st.dataframe(_atlas_type_summary, use_container_width=True, height=min(200, len(_atlas_type_summary) * 40 + 40), hide_index=True)

                # -- atlas charts -----------------------------------------
                st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)
                _atlas_chart_left, _atlas_chart_right = st.columns(2, gap="medium")
                atlas_chart_payload = _chart_runtime.build_map_atlas_chart_payload(
                    atlas_filter_signature,
                    filtered_cov,
                )

                with _atlas_chart_left:
                    # Treemap â€” spend concentration by subdivision type â†’ subdivision
                    tree_df = atlas_chart_payload["tree_df"]
                    if not tree_df.empty and len(filtered_cov) > 1:
                        if not tree_df.empty:
                            fig_tree = px.treemap(
                                tree_df,
                                path=["_type", "_name"],
                                values="high_total",
                                color="high_total",
                                color_continuous_scale="tealgrn",
                                title="Spend Concentration Treemap",
                            )
                            fig_tree.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)",
                                font_color="rgba(210,230,245,.88)",
                                title_font_size=13,
                                margin=dict(l=4, r=4, t=36, b=4),
                                height=300,
                                coloraxis_colorbar=dict(thickness=10, len=0.5),
                            )
                            st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                            st.plotly_chart(fig_tree, use_container_width=True, key="mp5_atlas_treemap")
                            st.markdown('</div>', unsafe_allow_html=True)

                with _atlas_chart_right:
                    # Histogram â€” distribution of matched-entity counts
                    hist_vals = atlas_chart_payload["hist_vals"]
                    if not hist_vals.empty and len(filtered_cov) > 2:
                        if len(hist_vals) > 2:
                            fig_hist = px.histogram(
                                hist_vals,
                                nbins=min(30, int(hist_vals.max())),
                                title="Matched-Entity Count Distribution",
                                labels={"value": "Matched Entities per Subdivision", "count": "Subdivisions"},
                                color_discrete_sequence=["rgba(0,224,184,.65)"],
                            )
                            fig_hist.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                font_color="rgba(210,230,245,.88)",
                                title_font_size=13,
                                margin=dict(l=10, r=10, t=36, b=10),
                                height=300,
                                showlegend=False,
                            )
                            fig_hist.update_xaxes(showgrid=False)
                            fig_hist.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                            st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                            st.plotly_chart(fig_hist, use_container_width=True, key="mp5_atlas_hist")
                            st.markdown('</div>', unsafe_allow_html=True)

                # -- atlas data table -------------------------------------
                cov_view = filtered_cov[
                    ["subdivision_type", "subdivision_name", "subdivision_code", "match_count", "high_total", "source_name"]
                ].rename(columns={
                    "subdivision_type": "Type",
                    "subdivision_name": "Subdivision",
                    "subdivision_code": "Code",
                    "match_count": "Matched Entities",
                    "high_total": "Matched High",
                    "source_name": "Map Source",
                })
                st.dataframe(cov_view, use_container_width=True, height=300, hide_index=True)
                _ = export_dataframe(cov_view, "coverage_atlas.csv", label="Download Coverage Atlas CSV")

                # -- atlas cross-navigation strip -------------------------
                st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)
                st.markdown(
                    '<div class="mp5-crosslink">'
                    '<span class="mp5-crosslink-title">Cross-Navigation</span>'
                    '<span class="mp5-crosslink-sep"></span>'
                    '<span class="mp5-crosslink-hint">Continue investigation in Address Forensics or promote to Case Docket</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                _atlas_ctx = st.session_state.get("map_selected_subdivision_context", {})
                _atlas_has_ctx = isinstance(_atlas_ctx, dict) and str(_atlas_ctx.get("subdivision_name", "")).strip()
                _ax1, _ax2, _ax3 = st.columns([1.2, 1.2, 1.0], gap="small")
                with _ax1:
                    if st.button(
                        "\U0001F50D Investigate in Address Forensics" if _atlas_has_ctx else "\U0001F50D Open Address Forensics",
                        key="atlas_to_forensics_btn",
                        use_container_width=True,
                        help="Switch to Address Forensics with the current subdivision context loaded." if _atlas_has_ctx else "Switch to Address Forensics tab.",
                    ):
                        st.info("Switch to the **Address Forensics** tab above. Your subdivision context is active and will scope the forensic analysis.")
                with _ax2:
                    _atlas_promote_available = _atlas_has_ctx and isinstance(_atlas_ctx.get("clients"), list) and len(_atlas_ctx.get("clients", [])) > 0
                    if st.button(
                        f"\U0001F4CB Promote Context Entities to Docket ({len(_atlas_ctx.get('clients', [])):,})" if _atlas_promote_available else "\U0001F4CB Promote to Docket",
                        key="atlas_promote_to_docket_btn",
                        use_container_width=True,
                        disabled=not _atlas_promote_available,
                        help="Add all matched entities from the current subdivision context directly to the Case Docket for tracking." if _atlas_promote_available else "Set a subdivision context first to promote its entities.",
                    ):
                        watch = st.session_state.get("map_watchlist", [])
                        if not isinstance(watch, list):
                            watch = []
                        existing = {str(r.get("TFL Entity", "")).strip().lower() for r in watch if isinstance(r, dict)}
                        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                        ctx_name = str(_atlas_ctx.get("subdivision_name", "")).strip()
                        ctx_type = str(_atlas_ctx.get("subdivision_type", "")).strip()
                        added = 0
                        for entity in _atlas_ctx.get("clients", []):
                            k = str(entity).strip().lower()
                            if not k or k in existing:
                                continue
                            watch.append({
                                "Added": stamp,
                                "TFL Entity": str(entity).strip(),
                                "Priority": "Tier 2",
                                "Lead Score": 0.0,
                                "Signal Score": 0.0,
                                "High": float(_atlas_ctx.get("high_total", 0.0) or 0.0),
                                "High Confidence Share": 0.0,
                                "Boundary Share": 0.0,
                                "Avg Distance (mi)": float("nan"),
                                "Overlap Rows": 0,
                                "Source Query": f"Coverage Atlas: {ctx_type} â€” {ctx_name}",
                                "Status": "New",
                                "Notes": f"Promoted from Coverage Atlas ({ctx_type} â€” {ctx_name})",
                            })
                            existing.add(k)
                            added += 1
                        st.session_state.map_watchlist = watch
                        if added:
                            st.success(f"Promoted {added:,} entities to Case Docket from {ctx_type} â€” {ctx_name}.")
                        else:
                            st.info("All entities from this context are already in the docket.")
                with _ax3:
                    _docket_n = len(st.session_state.get("map_watchlist", []))
                    if st.button(
                        f"\U0001F4CB View Case Docket ({_docket_n:,})" if _docket_n else "\U0001F4CB View Case Docket",
                        key="atlas_to_docket_btn",
                        use_container_width=True,
                        help="Switch to the Case Docket tab to review promoted entities.",
                    ):
                        st.info("Switch to the **Case Docket** tab above to review and manage your queued entities.")

        # ------------------------------------------------------------------
        # TAB 2 â€” ADDRESS FORENSICS
        # ------------------------------------------------------------------
        with tab_forensics:
            # -- cross-context banner -------------------------------------
            _render_cross_context_banner("forensics")
            # -- section hero ---------------------------------------------
            st.markdown(
                f"""
            <div class="mp5-section-hero">
              <div class="mp5-section-num">2</div>
              <div class="mp5-title">Address Forensics</div>
              <div class="mp5-sub">Resolve a specific Texas address or coordinate pair, identify which political subdivisions overlap that point, and rank matched taxpayer-funded entities by evidence strength. Results are scored using geocode quality, match method weight, confidence level, and proximity.</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

            ctx = (
                st.session_state.get("map_selected_subdivision_context", {})
                if isinstance(st.session_state.get("map_selected_subdivision_context", {}), dict)
                else {}
            )
            selected_type = str(ctx.get("subdivision_type", "")).strip()
            selected_name = str(ctx.get("subdivision_name", "")).strip()
            selected_clients = (
                [str(v).strip() for v in ctx.get("clients", []) if str(v).strip()]
                if isinstance(ctx.get("clients", []), list)
                else []
            )

            if st.session_state.get("map_overlap_input_mode") not in {"Street Address", "Coordinates"}:
                st.session_state.map_overlap_input_mode = "Street Address"

            analysis_point = None
            geocode_message = ""
            overlap_points = pd.DataFrame()
            overlap_spend = pd.DataFrame()

            # -- input panel + context sidebar ----------------------------
            lcol, rcol = st.columns([1.1, 1.7], gap="large")
            with lcol:
                # context badge
                if selected_name:
                    _ctx_client_preview = ", ".join(selected_clients[:4])
                    if len(selected_clients) > 4:
                        _ctx_client_preview += f" +{len(selected_clients) - 4}"
                    st.markdown(
                        f'<div class="mp5-anchor"><strong>{html.escape(selected_type, quote=True)} â€” '
                        f"{html.escape(selected_name, quote=True)}</strong><br>"
                        f"Context clients: <strong>{len(selected_clients):,}</strong><br>"
                        f'<span style="font-size:.72rem;color:rgba(195,220,236,.68)">{html.escape(_ctx_client_preview or "â€”", quote=True)}</span></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="mp5-anchor-empty">No active context â€” results will be unscoped. '
                        'Set context in Coverage Atlas for focused filtering.</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("\U0001F5FA Set Context in Coverage Atlas", key="forensics_set_ctx_atlas_btn", use_container_width=True):
                        st.info("Switch to the **Coverage Atlas** tab above to select a subdivision context.")

                mode = st.radio(
                    "Lookup mode",
                    ["Street Address", "Coordinates"],
                    key="map_overlap_input_mode",
                    horizontal=True,
                )
                if mode == "Street Address":
                    with st.form("map_addr_form_v4"):
                        st.text_input(
                            "Street address",
                            key="map_overlap_address_input",
                            placeholder="e.g. 1100 Congress Ave, Austin, TX",
                        )
                        run_addr = st.form_submit_button("Run Address Forensics", use_container_width=True)
                    if run_addr:
                        q = str(st.session_state.get("map_overlap_address_input", "")).strip()
                        st.session_state.map_overlap_address_query = q
                        if q:
                            recent = [q] + [
                                str(v).strip()
                                for v in st.session_state.get("map_recent_addresses", [])
                                if str(v).strip() and str(v).strip().lower() != q.lower()
                            ]
                            st.session_state.map_recent_addresses = recent[:10]

                    recent_options = [
                        str(v).strip()
                        for v in st.session_state.get("map_recent_addresses", [])
                        if str(v).strip()
                    ]
                    if recent_options:
                        recent_pick = st.selectbox(
                            "Recent queries", [""] + recent_options, key="map_recent_pick_v4",
                        )
                        if st.button("Use Recent", key="map_use_recent_btn_v4", use_container_width=True) and recent_pick:
                            st.session_state.map_overlap_address_query = recent_pick

                    active_query = str(st.session_state.get("map_overlap_address_query", "")).strip()
                    if active_query:
                        geo = geocode_address_arcgis(active_query)
                        if geo:
                            analysis_point = {
                                "query": active_query,
                                "matched_address": str(geo.get("matched_address", active_query)).strip(),
                                "lat": float(geo.get("lat", 0.0)),
                                "lon": float(geo.get("lon", 0.0)),
                                "score": float(geo.get("score", 0.0)),
                            }
                            score = float(analysis_point["score"])
                            floor = float(st.session_state.get("map_geocode_floor", 82))
                            geocode_message = f"Geocode score: {score:.1f}"
                            if score < floor:
                                geocode_message += f" (below floor {int(floor)})"
                        else:
                            st.warning("Address could not be geocoded.")
                else:
                    with st.form("map_coord_form_v4"):
                        cc1, cc2 = st.columns(2, gap="small")
                        with cc1:
                            st.number_input(
                                "Latitude", min_value=25.0, max_value=37.0,
                                step=0.0001, format="%.6f",
                                key="map_overlap_coord_lat",
                            )
                        with cc2:
                            st.number_input(
                                "Longitude", min_value=-107.0, max_value=-93.0,
                                step=0.0001, format="%.6f",
                                key="map_overlap_coord_lon",
                            )
                        run_coord = st.form_submit_button("Run Coordinate Forensics", use_container_width=True)
                    if run_coord:
                        st.session_state.map_overlap_query_lat = float(st.session_state.get("map_overlap_coord_lat", 31.0))
                        st.session_state.map_overlap_query_lon = float(st.session_state.get("map_overlap_coord_lon", -99.0))
                    if (
                        st.session_state.get("map_overlap_query_lat") is not None
                        and st.session_state.get("map_overlap_query_lon") is not None
                    ):
                        lat_q = float(st.session_state.get("map_overlap_query_lat"))
                        lon_q = float(st.session_state.get("map_overlap_query_lon"))
                        analysis_point = {
                            "query": f"{lat_q:.6f}, {lon_q:.6f}",
                            "matched_address": f"Coordinates: {lat_q:.6f}, {lon_q:.6f}",
                            "lat": lat_q,
                            "lon": lon_q,
                            "score": None,
                        }
                        geocode_message = "Coordinate mode â€” no geocode confidence score"

                if analysis_point is not None:
                    overlap_points, overlap_spend = _build_overlap_probe_cached(
                        str(getattr(atlas_bundle, "map_payload_signature", "")),
                        float(analysis_point["lat"]),
                        float(analysis_point["lon"]),
                        subdivision_matches,
                        tfl_spend,
                        atlas_bundle.prepared_overlap_pools,
                        atlas_bundle.spend_lookup,
                    )

            # -- results panel --------------------------------------------
            filtered = pd.DataFrame()
            leads = pd.DataFrame()
            with rcol:
                if analysis_point is None:
                    st.markdown(
                        '<div class="mp5-anchor-empty" style="text-align:center;padding:40px 16px">'
                        "Enter an address or coordinates to generate overlap evidence.</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    # geocode badge
                    floor_val = float(st.session_state.get("map_geocode_floor", 82))
                    st.markdown(
                        _mp5_geocode_badge(analysis_point.get("score"), floor_val),
                        unsafe_allow_html=True,
                    )

                    active_basemap = MAP_BASEMAP_OPTIONS.get(
                        st.session_state.get("map_basemap_label", ""), "gray-vector",
                    )
                    render_address_overlap_arcgis_map(
                        float(analysis_point["lon"]),
                        float(analysis_point["lat"]),
                        str(analysis_point.get("matched_address", analysis_point.get("query", ""))),
                        overlap_points,
                        height=520,
                        basemap=active_basemap,
                    )
                    if overlap_spend.empty:
                        st.info("No matched entities at this location.")
                    else:
                        rows_source_signature = (
                            str(getattr(atlas_bundle, "map_payload_signature", "")),
                            round(float(analysis_point.get("lat", 0.0)), 6),
                            round(float(analysis_point.get("lon", 0.0)), 6),
                        )
                        rows = _build_overlap_evidence_rows_cached(
                            rows_source_signature[0],
                            float(analysis_point["lat"]),
                            float(analysis_point["lon"]),
                            overlap_points,
                            overlap_spend,
                        )

                        # -- evidence filters (in left column) ------------
                        conf_opts = [
                            c for c in ["High", "Medium", "Low", "Unknown"]
                            if c in rows["Match Confidence"].astype(str).value_counts().to_dict()
                        ]
                        method_opts = sorted({
                            str(v).strip()
                            for v in rows["Match Method"].dropna().astype(str).tolist()
                            if str(v).strip()
                        })
                        if conf_opts:
                            st.session_state.map_overlap_confidence_filter = [
                                str(v) for v in st.session_state.get("map_overlap_confidence_filter", [])
                                if str(v) in conf_opts
                            ] or list(conf_opts)
                        if method_opts:
                            st.session_state.map_overlap_method_filter = [
                                str(v) for v in st.session_state.get("map_overlap_method_filter", [])
                                if str(v) in method_opts
                            ] or list(method_opts)

                        with lcol:
                            st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)
                            st.markdown(
                                '<div class="mp5-kicker" style="margin-bottom:4px">Evidence Filters</div>',
                                unsafe_allow_html=True,
                            )
                            st.selectbox(
                                "Sort",
                                ["Signal Score", "Highest High", "Closest Distance", "Entity A-Z"],
                                key="map_overlap_sort_v4",
                            )
                            st.multiselect("Confidence", conf_opts, key="map_overlap_confidence_filter")
                            st.multiselect("Method", method_opts, key="map_overlap_method_filter")
                            st.text_input("Entity contains", key="map_overlap_entity_filter")
                            st.checkbox(
                                "Focus active subdivision",
                                key="map_overlap_focus_selected_subdivision",
                                disabled=not bool(selected_name),
                            )
                            st.checkbox(
                                "Focus context entities only",
                                key="map_overlap_focus_selected_clients",
                                disabled=not bool(selected_clients),
                            )
                            st.toggle(
                                "Show advanced charts",
                                key="map_forensics_show_charts",
                                help="Keeps the page fast by rendering Plotly charts only when enabled.",
                            )

                        # -- apply evidence filters -----------------------
                        q_entity = str(st.session_state.get("map_overlap_entity_filter", "")).strip().lower()
                        min_high = float(st.session_state.get("map_probe_min_high", 0.0) or 0.0)
                        dist_cap = float(st.session_state.get("map_distance_cap_miles", 160) or 160)
                        sort_mode = st.session_state.get("map_overlap_sort_v4", "Signal Score")
                        forensics_filter_signature = _chart_runtime.stable_json_signature(
                            {
                                "rows_key": rows_source_signature,
                                "confidence_filters": list(st.session_state.get("map_overlap_confidence_filter", [])),
                                "method_filters": list(st.session_state.get("map_overlap_method_filter", [])),
                                "entity_query": q_entity,
                                "min_high": round(min_high, 2),
                                "dist_cap": round(dist_cap, 4),
                                "focus_selected_subdivision": bool(st.session_state.get("map_overlap_focus_selected_subdivision", False)),
                                "selected_type": selected_type,
                                "selected_name": selected_name,
                                "focus_selected_clients": bool(st.session_state.get("map_overlap_focus_selected_clients", False)),
                                "selected_clients": sorted(selected_clients),
                                "sort_mode": sort_mode,
                            }
                        )
                        forensics_filter_bundle = _chart_runtime.build_filtered_forensics_bundle(
                            forensics_filter_signature,
                            rows,
                            confidence_filters=list(st.session_state.get("map_overlap_confidence_filter", [])),
                            method_filters=list(st.session_state.get("map_overlap_method_filter", [])),
                            entity_query=q_entity,
                            min_high=min_high,
                            dist_cap=dist_cap,
                            focus_selected_subdivision=bool(st.session_state.get("map_overlap_focus_selected_subdivision", False)),
                            selected_type=selected_type,
                            selected_name=selected_name,
                            focus_selected_clients=bool(st.session_state.get("map_overlap_focus_selected_clients", False)),
                            selected_clients=selected_clients,
                            sort_mode=sort_mode,
                        )
                        filtered = forensics_filter_bundle["filtered"]
                        leads = forensics_filter_bundle["leads"]

                        # -- evidence KPIs --------------------------------
                        if filtered.empty:
                            st.warning("All overlap rows were removed by current filters.")
                        else:
                            n_filtered = len(filtered)
                            n_entities = int(filtered["TFL Entity"].astype(str).nunique())
                            filtered_high = float(filtered["High"].sum())
                            hc_share = float((filtered["Match Confidence"].astype(str) == "High").mean())
                            boundary_share = float(filtered["Boundary Match"].fillna(False).astype(bool).mean())
                            _avg_signal = float(filtered["Row Signal"].mean()) if "Row Signal" in filtered.columns else 0.0
                            _max_signal = float(filtered["Row Signal"].max()) if "Row Signal" in filtered.columns else 0.0

                            # composite evidence quality score (0-100)
                            _eq_score = min(100.0, hc_share * 40 + boundary_share * 30 + min(_avg_signal / max(_max_signal, 1) * 30, 30))
                            _eq_pct = max(0, min(100, int(round(_eq_score))))
                            _eq_dash = int(round(251.2 * (1 - _eq_pct / 100)))
                            _eq_color = "#6ee7b7" if _eq_pct >= 65 else ("#fcd34d" if _eq_pct >= 40 else "#fca5a5")

                            # quality narrative
                            if hc_share >= 0.6 and boundary_share >= 0.5:
                                quality_note = "Strong evidence mix â€” majority high-confidence and boundary-matched."
                                _eq_label = "Strong"
                            elif hc_share >= 0.4:
                                quality_note = "Moderate evidence quality. Review low-confidence rows before promoting."
                                _eq_label = "Moderate"
                            else:
                                quality_note = "Weak evidence mix â€” most rows lack high confidence. Apply stricter filters."
                                _eq_label = "Weak"

                            # evidence quality meter + narrative side-by-side
                            _meter_left, _meter_right = st.columns([1, 3], gap="small")
                            with _meter_left:
                                st.markdown(f"""
            <div class="mp5-meter">
              <svg viewBox="0 0 90 90" style="width:100%;max-width:110px;display:block;margin:auto">
        <circle cx="45" cy="45" r="40" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="7"/>
        <circle cx="45" cy="45" r="40" fill="none" stroke="{_eq_color}" stroke-width="7"
                stroke-dasharray="251.2" stroke-dashoffset="{_eq_dash}"
                stroke-linecap="round" transform="rotate(-90 45 45)"
                style="transition:stroke-dashoffset .6s ease"/>
        <text x="45" y="42" text-anchor="middle" fill="{_eq_color}" font-size="18" font-weight="700">{_eq_pct}</text>
        <text x="45" y="56" text-anchor="middle" fill="rgba(210,230,245,.6)" font-size="8">{_eq_label}</text>
              </svg>
              <div style="text-align:center;font-size:.7rem;color:rgba(210,230,245,.55);margin-top:2px">Evidence Quality</div>
            </div>
            """, unsafe_allow_html=True)
                            with _meter_right:
                                st.markdown(f'<div class="mp5-narrative" style="margin-top:12px">{quality_note}</div>', unsafe_allow_html=True)
                                # breakdown bars
                                st.markdown(f"""
            <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:6px">
              <div style="flex:1;min-width:120px">
        <div style="font-size:.7rem;color:rgba(210,230,245,.55);margin-bottom:2px">High-Confidence Share</div>
        <div class="mp5-health-track"><div class="mp5-health-fill" style="width:{hc_share*100:.0f}%;background:{'#6ee7b7' if hc_share>=0.6 else '#fcd34d' if hc_share>=0.3 else '#fca5a5'}"></div></div>
        <div style="font-size:.72rem;color:rgba(210,230,245,.7);margin-top:1px">{hc_share:.0%}</div>
              </div>
              <div style="flex:1;min-width:120px">
        <div style="font-size:.7rem;color:rgba(210,230,245,.55);margin-bottom:2px">Boundary Match Share</div>
        <div class="mp5-health-track"><div class="mp5-health-fill" style="width:{boundary_share*100:.0f}%;background:{'#6ee7b7' if boundary_share>=0.5 else '#fcd34d' if boundary_share>=0.3 else '#fca5a5'}"></div></div>
        <div style="font-size:.72rem;color:rgba(210,230,245,.7);margin-top:1px">{boundary_share:.0%}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

                            st.markdown(
                                f"""
            <div class="mp5-metrics">
              <div class="mp5-card"><div class="mp5-card-lbl">Evidence Rows</div><div class="mp5-card-val">{n_filtered:,}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Unique Entities</div><div class="mp5-card-val">{n_entities:,}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Filtered High</div><div class="mp5-card-val">{fmt_usd(filtered_high)}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">High-Conf Share</div><div class="mp5-card-val">{hc_share:.0%}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Boundary Share</div><div class="mp5-card-val">{boundary_share:.0%}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Avg Signal</div><div class="mp5-card-val">{_avg_signal:.1f}</div></div>
            </div>
            """,
                                unsafe_allow_html=True,
                            )

                        # -- evidence table --------------------------------
                        probe_view = filtered[
                            [
                                "Subdivision Type", "Subdivision", "Entity Type",
                                "TFL Entity", "Match Method", "Match Confidence",
                                "Low", "High", "Mid", "Distance Miles", "Row Signal",
                            ]
                        ].rename(columns={"Mid": "Midpoint"})
                        st.dataframe(probe_view, use_container_width=True, height=300, hide_index=True)
                        _ = export_dataframe(filtered, "address_forensics_rows.csv", label="Download Evidence CSV")
                        show_charts = bool(st.session_state.get("map_forensics_show_charts", False))
                        if not show_charts:
                            st.caption("Advanced charts are disabled for faster reruns. Enable **Show advanced charts** in Evidence Filters.")
                        forensics_chart_payload = (
                            _chart_runtime.build_map_forensics_chart_payload(
                                forensics_filter_signature,
                                filtered,
                                leads,
                            )
                            if show_charts and not filtered.empty
                            else {}
                        )

                        # -- signal scatter chart -------------------------
                        if show_charts and not filtered.empty and len(filtered) > 1:
                            chart_df = forensics_chart_payload["chart_df"]
                            fig_scatter = px.scatter(
                                chart_df,
                                x="Distance Miles",
                                y="Row Signal",
                                size="High",
                                color="Confidence",
                                hover_name="TFL Entity",
                                color_discrete_map={
                                    "High": "#6ee7b7",
                                    "Medium": "#fcd34d",
                                    "Low": "#fca5a5",
                                    "Unknown": "#94a3b8",
                                },
                                title="Evidence Quality â€” Signal vs Distance",
                                labels={
                                    "Row Signal": "Row Signal Score",
                                    "Distance Miles": "Distance (mi)",
                                },
                            )
                            fig_scatter.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                font_color="rgba(210,230,245,.88)",
                                title_font_size=13,
                                margin=dict(l=10, r=10, t=36, b=10),
                                height=260,
                                legend=dict(
                                    orientation="h", yanchor="bottom", y=1.02,
                                    xanchor="right", x=1,
                                ),
                            )
                            fig_scatter.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                            fig_scatter.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                            st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                            st.plotly_chart(fig_scatter, use_container_width=True, key="mp5_evidence_scatter")
                            st.markdown("</div>", unsafe_allow_html=True)

                        # -- confidence â€” method heatmap + entity-type spend --
                        if show_charts and not filtered.empty and len(filtered) > 2:
                            _fc_left, _fc_right = st.columns(2, gap="medium")
                            with _fc_left:
                                # Heatmap â€” confidence vs method row counts
                                heat_pivot = forensics_chart_payload["heat_pivot"]
                                if len(heat_pivot) > 1:
                                    fig_heat = px.imshow(
                                        heat_pivot,
                                        color_continuous_scale="tealgrn",
                                        title="Confidence â€” Method (row count)",
                                        aspect="auto",
                                    )
                                    fig_heat.update_layout(
                                        paper_bgcolor="rgba(0,0,0,0)",
                                        plot_bgcolor="rgba(0,0,0,0)",
                                        font_color="rgba(210,230,245,.88)",
                                        title_font_size=13,
                                        margin=dict(l=10, r=10, t=36, b=10),
                                        height=280,
                                        coloraxis_colorbar=dict(thickness=10, len=0.5),
                                    )
                                    st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                                    st.plotly_chart(fig_heat, use_container_width=True, key="mp5_conf_method_heat")
                                    st.markdown('</div>', unsafe_allow_html=True)

                            with _fc_right:
                                # Grouped bar â€” spend by entity type
                                etype_melt = forensics_chart_payload["etype_melt"]
                                if not etype_melt.empty and len(etype_melt) > 1:
                                    fig_etype = px.bar(
                                        etype_melt,
                                        x="Entity Type",
                                        y="Amount",
                                        color="Estimate",
                                        barmode="group",
                                        color_discrete_map={"Low": "#94a3b8", "High": "#6ee7b7"},
                                        title="Spend by Entity Type",
                                    )
                                    fig_etype.update_layout(
                                        paper_bgcolor="rgba(0,0,0,0)",
                                        plot_bgcolor="rgba(0,0,0,0)",
                                        font_color="rgba(210,230,245,.88)",
                                        title_font_size=13,
                                        margin=dict(l=10, r=10, t=36, b=10),
                                        height=280,
                                        legend=dict(
                                            orientation="h", yanchor="bottom", y=1.02,
                                            xanchor="right", x=1,
                                        ),
                                    )
                                    fig_etype.update_xaxes(showgrid=False, tickangle=-35)
                                    fig_etype.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                                    st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                                    st.plotly_chart(fig_etype, use_container_width=True, key="mp5_etype_spend")
                                    st.markdown('</div>', unsafe_allow_html=True)

                        # --- RANKED LEADS --------------------------------
                        if not leads.empty:
                            st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)
                            st.markdown(
                                '<div class="mp5-section-hero">' 
                                '<span class="mp5-section-num">2B</span>'
                                '<span style="font-size:1.05rem;font-weight:600;">Ranked Leads</span>'
                                '<span style="font-size:.78rem;color:rgba(210,230,245,.55);margin-left:8px;">'
                                'Entities ranked by composite lead score â€” promote top signals to Case Docket</span>'
                                '</div>',
                                unsafe_allow_html=True,
                            )

                            # lead tier summary
                            t1 = int((leads["Priority"] == "Tier 1").sum())
                            t2 = int((leads["Priority"] == "Tier 2").sum())
                            t3 = int((leads["Priority"] == "Tier 3").sum())
                            _top_lead_name = str(leads.iloc[0]["TFL Entity"]) if not leads.empty else "â€”"
                            _top_lead_score = float(leads.iloc[0]["LeadScore"]) if not leads.empty else 0.0
                            st.markdown(
                                f"""
            <div class="mp5-metrics">
              <div class="mp5-card"><div class="mp5-card-lbl">Total Leads</div><div class="mp5-card-val">{len(leads):,}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Tier 1</div><div class="mp5-card-val mp5-tier1">{t1}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Tier 2</div><div class="mp5-card-val mp5-tier2">{t2}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Tier 3</div><div class="mp5-card-val mp5-tier3">{t3}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Top Lead</div><div class="mp5-card-val" style="font-size:.82rem">{_top_lead_name[:28]}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Top Score</div><div class="mp5-card-val">{_top_lead_score:.1f}</div></div>
            </div>
            """,
                                unsafe_allow_html=True,
                            )

                            st.dataframe(
                                leads[
                                    [
                                        "Priority", "TFL Entity", "EntityType",
                                        "Low", "High", "Midpoint", "LeadScore",
                                        "SignalScore", "HighShare", "BoundaryShare",
                                        "AvgDistance", "OverlapRows",
                                    ]
                                ].rename(columns={
                                    "EntityType": "Entity Type",
                                    "LeadScore": "Lead Score",
                                    "SignalScore": "Signal Score",
                                    "HighShare": "High Conf %",
                                    "BoundaryShare": "Boundary %",
                                    "AvgDistance": "Avg Dist (mi)",
                                    "OverlapRows": "Rows",
                                }),
                                use_container_width=True,
                                height=260,
                                hide_index=True,
                            )
                            _ = export_dataframe(leads, "address_ranked_leads.csv", label="Download Ranked Leads CSV")

                            # -- lead score bar chart ---------------------
                            if show_charts and len(leads) > 1:
                                chart_leads = forensics_chart_payload["chart_leads"]
                                fig_leads = px.bar(
                                    chart_leads,
                                    x="LeadScore",
                                    y="Entity",
                                    color="Priority",
                                    orientation="h",
                                    color_discrete_map={
                                        "Tier 1": "#6ee7b7",
                                        "Tier 2": "#fcd34d",
                                        "Tier 3": "#fca5a5",
                                    },
                                    title="Top 20 Leads by Score",
                                )
                                fig_leads.update_layout(
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    font_color="rgba(210,230,245,.88)",
                                    title_font_size=13,
                                    margin=dict(l=10, r=10, t=36, b=10),
                                    height=max(220, len(chart_leads) * 22 + 60),
                                    yaxis=dict(autorange="reversed"),
                                    legend=dict(
                                        orientation="h", yanchor="bottom", y=1.02,
                                        xanchor="right", x=1,
                                    ),
                                )
                                fig_leads.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                                fig_leads.update_yaxes(showgrid=False)
                                st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                                st.plotly_chart(fig_leads, use_container_width=True, key="mp5_lead_bar")
                                st.markdown("</div>", unsafe_allow_html=True)

                            # -- promote + open ---------------------------
                            st.markdown(
                                '<div class="mp5-action-strip" style="margin-top:8px">'
                                '<span style="font-weight:600;font-size:.82rem;">Actions</span>'
                                '<span style="font-size:.72rem;color:rgba(210,230,245,.5);margin-left:6px">'
                                'Promote high-signal leads to Case Docket or open in Client Look-Up</span>'
                                '</div>',
                                unsafe_allow_html=True,
                            )
                            add_opts = [
                                str(v).strip()
                                for v in leads["TFL Entity"].dropna().astype(str).tolist()
                                if str(v).strip()
                            ]
                            a1, a2 = st.columns([3.0, 1.0], gap="small")
                            with a1:
                                add_pick = st.multiselect(
                                    "Promote to Case Docket",
                                    add_opts,
                                    key="map_watch_add_from_probe_v4",
                                )
                            with a2:
                                add_btn = st.button("Promote", key="map_watch_add_btn_v4", use_container_width=True)
                            if add_btn and add_pick:
                                watch = st.session_state.get("map_watchlist", [])
                                existing = {
                                    str(r.get("TFL Entity", "")).strip().lower()
                                    for r in watch if isinstance(r, dict)
                                }
                                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                                for entity in add_pick:
                                    k = str(entity).strip().lower()
                                    if not k or k in existing:
                                        continue
                                    row = leads[leads["TFL Entity"].astype(str) == str(entity)].head(1)
                                    if row.empty:
                                        continue
                                    rec = row.iloc[0]
                                    watch.append({
                                        "Added": stamp,
                                        "TFL Entity": str(entity).strip(),
                                        "Priority": str(rec.get("Priority", "Tier 3")),
                                        "Lead Score": float(rec.get("LeadScore", 0.0) or 0.0),
                                        "Signal Score": float(rec.get("SignalScore", 0.0) or 0.0),
                                        "High": float(rec.get("High", 0.0) or 0.0),
                                        "High Confidence Share": float(rec.get("HighShare", 0.0) or 0.0),
                                        "Boundary Share": float(rec.get("BoundaryShare", 0.0) or 0.0),
                                        "Avg Distance (mi)": float(rec.get("AvgDistance", 0.0) or 0.0),
                                        "Overlap Rows": int(rec.get("OverlapRows", 0) or 0),
                                        "Source Query": str(analysis_point.get("query", "")),
                                    })
                                    existing.add(k)
                                st.session_state.map_watchlist = watch
                                st.success(f"Case Docket â†’ {len(watch):,} entities.")

                            open_entity = (
                                st.selectbox(
                                    "Open in Client Look-Up",
                                    add_opts,
                                    key="map_open_client_pick_v4",
                                )
                                if add_opts
                                else ""
                            )
                            if st.button("Open Client", key="map_open_client_from_probe_btn_v4", use_container_width=True) and open_entity:
                                _open_client(open_entity)

            # -- batch triage ---------------------------------------------
            with st.expander("Batch Address Triage", expanded=False):
                st.markdown(
                    '<div style="font-size:.72rem;color:rgba(210,230,245,.45);margin-bottom:6px">'
                    'Use <strong>Send to Batch</strong> on the Coverage Atlas map to auto-populate addresses here, or enter them manually below.</div>',
                    unsafe_allow_html=True,
                )
                st.text_area(
                    "Street addresses (one per line)",
                    key="map_batch_input_v4",
                    height=130,
                    placeholder="1100 Congress Ave, Austin, TX\n500 E San Antonio Ave, El Paso, TX",
                )
                bb1, bb2 = st.columns([1.3, 1.0], gap="small")
                with bb1:
                    st.number_input("Max addresses", min_value=1, max_value=20, step=1, key="map_batch_max_v4")
                with bb2:
                    run_batch = st.button("Run Batch Triage", key="map_batch_run_btn_v4", use_container_width=True)

                if run_batch:
                    raw_lines = [
                        str(v).strip()
                        for v in str(st.session_state.get("map_batch_input_v4", "")).splitlines()
                    ]
                    deduped: list[str] = []
                    seen: set[str] = set()
                    for line in raw_lines:
                        key = line.lower()
                        if line and key not in seen:
                            deduped.append(line)
                            seen.add(key)
                    deduped = deduped[: int(st.session_state.get("map_batch_max_v4", 8) or 8)]

                    batch_rows: list[dict] = []
                    def _triage_one_address(addr: str) -> dict:
                        addr_val = str(addr).strip()
                        if not addr_val:
                            return {
                                "Input": "",
                                "Status": "Geocode Failed",
                                "Matched Address": "",
                                "Geocode Score": 0.0,
                                "Overlap Rows": 0,
                                "Unique Entities": 0,
                                "Combined High": 0.0,
                                "High Confidence Share": 0.0,
                                "Triage Score": 0.0,
                                "Top Entity": "",
                            }
                        try:
                            geo = geocode_address_arcgis(addr_val)
                            if not geo:
                                return {
                                    "Input": addr_val,
                                    "Status": "Geocode Failed",
                                    "Matched Address": "",
                                    "Geocode Score": 0.0,
                                    "Overlap Rows": 0,
                                    "Unique Entities": 0,
                                    "Combined High": 0.0,
                                    "High Confidence Share": 0.0,
                                    "Triage Score": 0.0,
                                    "Top Entity": "",
                                }

                            lon_i = float(geo.get("lon", 0.0))
                            lat_i = float(geo.get("lat", 0.0))
                            overlap_sub_i = query_texas_subdivisions_for_point(round(lon_i, 6), round(lat_i, 6))
                            overlap_rows_i = build_address_overlap_spending_rows(
                                overlap_subdivisions=overlap_sub_i,
                                subdivision_matches=subdivision_matches,
                                tfl_spending=tfl_spend,
                                prepared_overlap_pools=atlas_bundle.prepared_overlap_pools,
                                spend_lookup=atlas_bundle.spend_lookup,
                            )
                            if overlap_rows_i.empty:
                                return {
                                    "Input": addr_val,
                                    "Status": "No Overlap",
                                    "Matched Address": str(geo.get("matched_address", addr_val)).strip(),
                                    "Geocode Score": float(geo.get("score", 0.0) or 0.0),
                                    "Overlap Rows": 0,
                                    "Unique Entities": 0,
                                    "Combined High": 0.0,
                                    "High Confidence Share": 0.0,
                                    "Triage Score": 0.0,
                                    "Top Entity": "",
                                }

                            overlap_rows_i["High"] = pd.to_numeric(
                                overlap_rows_i.get("High", 0.0), errors="coerce",
                            ).fillna(0.0)
                            high_total_i = float(overlap_rows_i["High"].sum())
                            entity_totals_i = (
                                overlap_rows_i.groupby("TFL Entity", as_index=False)["High"]
                                .sum()
                                .sort_values("High", ascending=False)
                            )
                            top_entity_i = str(entity_totals_i.iloc[0]["TFL Entity"]).strip() if not entity_totals_i.empty else ""
                            high_share_i = float((overlap_rows_i["Match Confidence"].astype(str) == "High").mean())
                            triage_i = (
                                (math.log10(high_total_i + 1.0) * 34.0)
                                + (high_share_i * 45.0)
                                + (int(overlap_rows_i["TFL Entity"].astype(str).nunique()) * 1.7)
                            )
                            return {
                                "Input": addr_val,
                                "Status": "Matched",
                                "Matched Address": str(geo.get("matched_address", addr_val)).strip(),
                                "Geocode Score": float(geo.get("score", 0.0) or 0.0),
                                "Overlap Rows": int(len(overlap_rows_i)),
                                "Unique Entities": int(overlap_rows_i["TFL Entity"].astype(str).nunique()),
                                "Combined High": high_total_i,
                                "High Confidence Share": high_share_i,
                                "Triage Score": float(triage_i),
                                "Top Entity": top_entity_i,
                            }
                        except Exception:
                            return {
                                "Input": addr_val,
                                "Status": "Error",
                                "Matched Address": "",
                                "Geocode Score": 0.0,
                                "Overlap Rows": 0,
                                "Unique Entities": 0,
                                "Combined High": 0.0,
                                "High Confidence Share": 0.0,
                                "Triage Score": 0.0,
                                "Top Entity": "",
                            }

                    if deduped:
                        _workers = max(1, min(6, len(deduped)))
                        ordered_rows: list[dict | None] = [None] * len(deduped)
                        with ThreadPoolExecutor(max_workers=_workers) as pool:
                            future_map = {
                                pool.submit(_triage_one_address, addr): idx
                                for idx, addr in enumerate(deduped)
                            }
                            for future in as_completed(future_map):
                                idx = future_map[future]
                                try:
                                    ordered_rows[idx] = future.result()
                                except Exception:
                                    ordered_rows[idx] = {
                                        "Input": str(deduped[idx]).strip(),
                                        "Status": "Error",
                                        "Matched Address": "",
                                        "Geocode Score": 0.0,
                                        "Overlap Rows": 0,
                                        "Unique Entities": 0,
                                        "Combined High": 0.0,
                                        "High Confidence Share": 0.0,
                                        "Triage Score": 0.0,
                                        "Top Entity": "",
                                    }
                        batch_rows = [r for r in ordered_rows if isinstance(r, dict)]

                    st.session_state.map_batch_results_v4 = batch_rows

                batch_results = st.session_state.get("map_batch_results_v4", [])
                if isinstance(batch_results, list) and batch_results:
                    batch_df = pd.DataFrame(batch_results)
                    batch_df["Triage Score"] = pd.to_numeric(batch_df.get("Triage Score", 0.0), errors="coerce").fillna(0.0)
                    batch_df["Combined High"] = pd.to_numeric(batch_df.get("Combined High", 0.0), errors="coerce").fillna(0.0)
                    batch_df = batch_df.sort_values(
                        ["Triage Score", "Combined High"], ascending=[False, False],
                    ).reset_index(drop=True)
                    st.dataframe(batch_df, use_container_width=True, height=250, hide_index=True)
                    _ = export_dataframe(batch_df, "batch_address_triage.csv", label="Download Batch Triage CSV")
                    top = batch_df.iloc[0]
                    can_promote = str(top.get("Status", "")).strip().lower() == "matched"
                    if st.button(
                        "Use top result in Address Forensics",
                        key="map_batch_promote_top_btn_v4",
                        disabled=not can_promote,
                    ):
                        st.session_state.map_overlap_input_mode = "Street Address"
                        st.session_state.map_overlap_address_input = str(top.get("Input", "")).strip()
                        st.session_state.map_overlap_address_query = str(top.get("Input", "")).strip()
                        st.rerun()

            # -- forensics cross-navigation strip -------------------------
            st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)
            st.markdown(
                '<div class="mp5-crosslink">'
                '<span class="mp5-crosslink-title">Cross-Navigation</span>'
                '<span class="mp5-crosslink-sep"></span>'
                '<span class="mp5-crosslink-hint">Return to Coverage Atlas to refine context, or review queued entities in the Case Docket</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            _fx_ctx = st.session_state.get("map_selected_subdivision_context", {})
            _fx_has_ctx = isinstance(_fx_ctx, dict) and str(_fx_ctx.get("subdivision_name", "")).strip()
            _fx_docket_n = len(st.session_state.get("map_watchlist", []))
            _fx1, _fx2, _fx3 = st.columns(3, gap="small")
            with _fx1:
                _fx_atlas_label = (
                    f"\U0001F5FA Refine in Atlas ({html.escape(str(_fx_ctx.get('subdivision_type', '')).strip()[:20], quote=True)})"
                    if _fx_has_ctx
                    else "\U0001F5FA Open Coverage Atlas"
                )
                if st.button(
                    _fx_atlas_label,
                    key="forensics_to_atlas_btn",
                    use_container_width=True,
                    help="Switch to Coverage Atlas to adjust the subdivision context or explore other subdivisions.",
                ):
                    st.info("Switch to the **Coverage Atlas** tab above to refine your subdivision context and filters.")
            with _fx2:
                if st.button(
                    f"\U0001F4CB View Case Docket ({_fx_docket_n:,})" if _fx_docket_n else "\U0001F4CB Open Case Docket",
                    key="forensics_to_docket_btn",
                    use_container_width=True,
                    help="Switch to the Case Docket tab to manage promoted entities.",
                ):
                    st.info("Switch to the **Case Docket** tab above to review and manage your queued entities.")
            with _fx3:
                _fx_last_query = ""
                _fx_recent = st.session_state.get("map_recent_addresses", [])
                if isinstance(_fx_recent, list) and _fx_recent:
                    _fx_last_query = str(_fx_recent[0]).strip()
                if st.button(
                    "\U0001F4E4 Send Query to Batch Triage" if _fx_last_query else "\U0001F4E4 Open Batch Triage",
                    key="forensics_to_batch_btn",
                    use_container_width=True,
                    help="Initialize the Batch Address Triage with your most recent query address.",
                    disabled=not _fx_last_query,
                ):
                    if _fx_last_query:
                        current_batch = str(st.session_state.get("map_batch_input_v4", "")).strip()
                        if _fx_last_query.lower() not in current_batch.lower():
                            st.session_state.map_batch_input_v4 = (
                                f"{_fx_last_query}\n{current_batch}" if current_batch else _fx_last_query
                            )
                        st.info("Your last query has been added to Batch Triage. Expand the section above to run it.")

        # ------------------------------------------------------------------
        # TAB 3 â€” CASE DOCKET
        # ------------------------------------------------------------------
        with tab_docket:
            # -- cross-context banner -------------------------------------
            _render_cross_context_banner("docket")
            st.markdown(
                '<div class="mp5-section-hero">'
                '<span class="mp5-section-num">3</span>'
                '<span style="font-size:1.08rem;font-weight:600;">Case Docket</span>'
                '<span style="font-size:.78rem;color:rgba(210,230,245,.55);margin-left:8px;">'
                'Track promoted entities through investigation stages â€” assign status, add notes, and manage your queue</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            watch = st.session_state.get("map_watchlist", [])
            if not isinstance(watch, list) or not watch:
                st.markdown(
                    '<div class="mp5-anchor-empty" style="text-align:center;padding:30px 16px">'
                    '<div style="font-size:1.3rem;margin-bottom:8px;">\U0001F4CB</div>'
                    "Case Docket is empty. Promote entities from Address Forensics or Coverage Atlas to begin."
                    '<div style="font-size:.72rem;color:rgba(210,230,245,.45);margin-top:6px">'
                    "Use the Ranked Leads section in Address Forensics, or promote context entities from Coverage Atlas.</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                _empty_dkt1, _empty_dkt2 = st.columns(2, gap="small")
                with _empty_dkt1:
                    if st.button("\U0001F50D Open Address Forensics", key="docket_empty_to_forensics_btn", use_container_width=True):
                        st.info("Switch to the **Address Forensics** tab to resolve addresses and promote ranked leads.")
                with _empty_dkt2:
                    if st.button("\U0001F5FA Open Coverage Atlas", key="docket_empty_to_atlas_btn", use_container_width=True):
                        st.info("Switch to the **Coverage Atlas** tab to explore subdivisions and promote context entities.")
            else:
                wd = pd.DataFrame(watch)
                defaults_queue = {
                    "Added": "",
                    "TFL Entity": "",
                    "Priority": "Tier 3",
                    "Lead Score": 0.0,
                    "Signal Score": 0.0,
                    "High": 0.0,
                    "High Confidence Share": 0.0,
                    "Boundary Share": 0.0,
                    "Avg Distance (mi)": float("nan"),
                    "Overlap Rows": 0,
                    "Source Query": "",
                    "Status": "New",
                    "Notes": "",
                }
                for c_name, c_default in defaults_queue.items():
                    if c_name not in wd.columns:
                        wd[c_name] = c_default
                wd["Status"] = wd["Status"].fillna("New").replace("", "New")
                wd["Notes"] = wd["Notes"].fillna("")
                wd["Lead Score"] = pd.to_numeric(wd["Lead Score"], errors="coerce").fillna(0.0)
                wd["Signal Score"] = pd.to_numeric(wd["Signal Score"], errors="coerce").fillna(0.0)
                wd["High"] = pd.to_numeric(wd["High"], errors="coerce").fillna(0.0)
                wd["High Confidence Share"] = pd.to_numeric(wd["High Confidence Share"], errors="coerce").fillna(0.0)
                wd["Boundary Share"] = pd.to_numeric(wd["Boundary Share"], errors="coerce").fillna(0.0)
                wd["Avg Distance (mi)"] = pd.to_numeric(wd["Avg Distance (mi)"], errors="coerce")
                wd["Overlap Rows"] = pd.to_numeric(wd["Overlap Rows"], errors="coerce").fillna(0).astype(int)
                wd["Added TS"] = pd.to_datetime(wd["Added"], errors="coerce")

                p_opts = [
                    p for p in ["Tier 1", "Tier 2", "Tier 3"]
                    if p in wd["Priority"].astype(str).tolist()
                ]
                if not st.session_state.get("map_queue_priority_filter_v4"):
                    st.session_state.map_queue_priority_filter_v4 = list(dict.fromkeys(p_opts))
                st.session_state.map_queue_priority_filter_v4 = [
                    str(v) for v in st.session_state.get("map_queue_priority_filter_v4", [])
                    if str(v) in p_opts
                ] or list(dict.fromkeys(p_opts))

                # status options
                _status_opts = ["New", "Investigating", "Resolved"]
                _s_opts_present = [s for s in _status_opts if s in wd["Status"].astype(str).tolist()] or _status_opts
                if not st.session_state.get("map_queue_status_filter_v4"):
                    st.session_state.map_queue_status_filter_v4 = list(_s_opts_present)

                q1, q2, q3, q4 = st.columns([1.2, 1.0, 1.0, 0.8], gap="small")
                with q1:
                    st.multiselect("Priority", list(dict.fromkeys(p_opts)), key="map_queue_priority_filter_v4")
                with q2:
                    st.multiselect("Status", _status_opts, key="map_queue_status_filter_v4")
                with q3:
                    st.text_input("Search entity / query", key="map_queue_search_v4")
                with q4:
                    st.selectbox("Sort", ["Lead Score", "Signal Score", "Highest High", "Newest"], key="map_queue_sort_v4")

                qv = wd
                qv = qv[
                    qv["Priority"].astype(str).isin(
                        st.session_state.get("map_queue_priority_filter_v4", []),
                    )
                ]
                _sel_statuses = st.session_state.get("map_queue_status_filter_v4", _status_opts)
                if _sel_statuses:
                    qv = qv[qv["Status"].astype(str).isin(_sel_statuses)]
                q_text = str(st.session_state.get("map_queue_search_v4", "")).strip().lower()
                if q_text:
                    qv = qv[
                        qv["TFL Entity"].astype(str).str.lower().str.contains(q_text, na=False)
                        | qv["Source Query"].astype(str).str.lower().str.contains(q_text, na=False)
                    ]

                q_sort = st.session_state.get("map_queue_sort_v4", "Lead Score")
                if q_sort == "Signal Score":
                    qv = qv.sort_values(["Signal Score", "Lead Score", "High"], ascending=[False, False, False])
                elif q_sort == "Highest High":
                    qv = qv.sort_values(["High", "Lead Score"], ascending=[False, False])
                elif q_sort == "Newest":
                    qv = qv.sort_values(["Added TS", "Lead Score"], ascending=[False, False], na_position="last")
                else:
                    qv = qv.sort_values(["Lead Score", "Signal Score", "High"], ascending=[False, False, False])
                qv = qv.reset_index(drop=True)

                # -- docket KPIs ------------------------------------------
                docket_entities = int(qv["TFL Entity"].astype(str).nunique()) if not qv.empty else 0
                docket_t1 = int((qv["Priority"].astype(str) == "Tier 1").sum()) if not qv.empty else 0
                docket_avg = float(qv["Lead Score"].mean()) if not qv.empty else 0.0
                docket_high = float(qv["High"].sum()) if not qv.empty else 0.0
                _d_new = int((qv["Status"].astype(str) == "New").sum()) if not qv.empty else 0
                _d_investigating = int((qv["Status"].astype(str) == "Investigating").sum()) if not qv.empty else 0
                _d_resolved = int((qv["Status"].astype(str) == "Resolved").sum()) if not qv.empty else 0

                st.markdown(
                    f"""
            <div class="mp5-metrics">
              <div class="mp5-card"><div class="mp5-card-lbl">Queued Entities</div><div class="mp5-card-val">{docket_entities:,}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Tier 1</div><div class="mp5-card-val mp5-tier1">{docket_t1:,}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Avg Lead Score</div><div class="mp5-card-val">{docket_avg:.1f}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl">Total High</div><div class="mp5-card-val">{fmt_usd(docket_high)}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl"><span class="mp5-status mp5-status-new">New</span></div><div class="mp5-card-val">{_d_new}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl"><span class="mp5-status mp5-status-investigating">Investigating</span></div><div class="mp5-card-val">{_d_investigating}</div></div>
              <div class="mp5-card"><div class="mp5-card-lbl"><span class="mp5-status mp5-status-resolved">Resolved</span></div><div class="mp5-card-val">{_d_resolved}</div></div>
            </div>
            """,
                    unsafe_allow_html=True,
                )

                # -- docket priority distribution chart -------------------
                if not qv.empty and len(qv) > 1:
                    tier_counts = qv["Priority"].value_counts().reset_index()
                    tier_counts = tier_counts.set_axis(["Priority", "Count"], axis=1)
                    fig_tier = px.pie(
                        tier_counts,
                        names="Priority",
                        values="Count",
                        color="Priority",
                        color_discrete_map={
                            "Tier 1": "#6ee7b7",
                            "Tier 2": "#fcd34d",
                            "Tier 3": "#fca5a5",
                        },
                        title="Docket Priority Mix",
                        hole=0.45,
                    )
                    fig_tier.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color="rgba(210,230,245,.88)",
                        title_font_size=13,
                        margin=dict(l=10, r=10, t=36, b=10),
                        height=220,
                        showlegend=True,
                        legend=dict(
                            orientation="h", yanchor="bottom", y=-0.15,
                            xanchor="center", x=0.5,
                        ),
                    )
                    st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                    st.plotly_chart(fig_tier, use_container_width=True, key="mp5_docket_pie")
                    st.markdown("</div>", unsafe_allow_html=True)

                # -- docket scatter + source bar --------------------------
                if not qv.empty and len(qv) > 1:
                    _dq_left, _dq_right = st.columns(2, gap="medium")
                    with _dq_left:
                        # Scatter â€” Lead Score vs High estimate
                        fig_dq_scatter = px.scatter(
                            qv,
                            x="High",
                            y="Lead Score",
                            size="Overlap Rows",
                            color="Priority",
                            hover_name="TFL Entity",
                            color_discrete_map={
                                "Tier 1": "#6ee7b7",
                                "Tier 2": "#fcd34d",
                                "Tier 3": "#fca5a5",
                            },
                            title="Lead Score vs High Estimate",
                            labels={"High": "High Estimate ($)", "Lead Score": "Lead Score"},
                        )
                        fig_dq_scatter.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font_color="rgba(210,230,245,.88)",
                            title_font_size=13,
                            margin=dict(l=10, r=10, t=36, b=10),
                            height=280,
                            legend=dict(
                                orientation="h", yanchor="bottom", y=1.02,
                                xanchor="right", x=1,
                            ),
                        )
                        fig_dq_scatter.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                        fig_dq_scatter.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                        st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                        st.plotly_chart(fig_dq_scatter, use_container_width=True, key="mp5_docket_scatter")
                        st.markdown('</div>', unsafe_allow_html=True)

                    with _dq_right:
                        # Bar â€” spend by source query
                        src_df = (
                            qv.groupby(qv["Source Query"].astype(str).str.strip())
                            .agg(Entities=("TFL Entity", "nunique"), High=("High", "sum"))
                            .reset_index()
                        )
                        src_df = src_df.set_axis(["Source Query", "Entities", "High"], axis=1)
                        src_df = src_df[src_df["Source Query"] != ""].sort_values("High", ascending=False).head(10)
                        if not src_df.empty and len(src_df) > 0:
                            fig_src = px.bar(
                                src_df,
                                x="High",
                                y="Source Query",
                                color="Entities",
                                orientation="h",
                                color_continuous_scale="tealgrn",
                                title="Docket Spend by Source Query",
                                labels={"High": "High Estimate ($)", "Entities": "Entities"},
                            )
                            fig_src.update_layout(
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                font_color="rgba(210,230,245,.88)",
                                title_font_size=13,
                                margin=dict(l=10, r=10, t=36, b=10),
                                height=280,
                                yaxis=dict(autorange="reversed"),
                                coloraxis_colorbar=dict(thickness=10, len=0.5),
                            )
                            fig_src.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,.06)")
                            fig_src.update_yaxes(showgrid=False)
                            st.markdown('<div class="mp5-chart-wrap">', unsafe_allow_html=True)
                            st.plotly_chart(fig_src, use_container_width=True, key="mp5_docket_source_bar")
                            st.markdown('</div>', unsafe_allow_html=True)

                st.dataframe(
                    qv[
                        [
                            "Added", "Status", "Priority", "TFL Entity", "Lead Score",
                            "Signal Score", "High", "High Confidence Share",
                            "Boundary Share", "Avg Distance (mi)", "Overlap Rows",
                            "Source Query", "Notes",
                        ]
                    ],
                    use_container_width=True,
                    height=340,
                    hide_index=True,
                )
                _ = export_dataframe(
                    qv.drop(columns=["Added TS"], errors="ignore"),
                    "case_docket.csv",
                    label="Download Case Docket CSV",
                )

                # -- bulk status update + notes ---------------------------
                st.markdown(
                    '<div class="mp5-action-strip" style="margin-top:10px">'
                    '<span style="font-weight:600;font-size:.82rem;">Case Management</span>'
                    '<span style="font-size:.72rem;color:rgba(210,230,245,.5);margin-left:6px">'
                    'Update status, add investigation notes, or manage queue</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )

                # -- docket actions ---------------------------------------
                open_opts = [
                    str(v).strip()
                    for v in qv.get("TFL Entity", pd.Series(dtype=object)).dropna().astype(str).tolist()
                    if str(v).strip()
                ]
                remove_opts = list(dict.fromkeys(open_opts))

                # status update row
                _su1, _su2, _su3 = st.columns([2.0, 1.2, 0.8], gap="small")
                with _su1:
                    _status_entity_pick = st.multiselect(
                        "Select entities to update",
                        remove_opts,
                        key="map_docket_status_entity_v4",
                    )
                with _su2:
                    _new_status = st.selectbox(
                        "New status",
                        ["New", "Investigating", "Resolved"],
                        key="map_docket_new_status_v4",
                    )
                with _su3:
                    if st.button("Update Status", key="map_docket_status_btn_v4", use_container_width=True):
                        if _status_entity_pick:
                            _upd_set = {str(v).strip().lower() for v in _status_entity_pick}
                            for rec in st.session_state.get("map_watchlist", []):
                                if isinstance(rec, dict) and str(rec.get("TFL Entity", "")).strip().lower() in _upd_set:
                                    rec["Status"] = _new_status
                            st.rerun()

                # notes row
                _n1, _n2, _n3 = st.columns([2.0, 1.5, 0.5], gap="small")
                with _n1:
                    _note_entity = st.selectbox(
                        "Entity for notes",
                        [""] + remove_opts,
                        key="map_docket_note_entity_v4",
                    )
                with _n2:
                    _note_text = st.text_input(
                        "Investigation note",
                        key="map_docket_note_text_v4",
                        placeholder="Add observation or finding...",
                    )
                with _n3:
                    if st.button("Save Note", key="map_docket_note_btn_v4", use_container_width=True):
                        if _note_entity and _note_text:
                            _nk = str(_note_entity).strip().lower()
                            for rec in st.session_state.get("map_watchlist", []):
                                if isinstance(rec, dict) and str(rec.get("TFL Entity", "")).strip().lower() == _nk:
                                    _prev = str(rec.get("Notes", "")).strip()
                                    _stamp = datetime.now().strftime("%m/%d %H:%M")
                                    rec["Notes"] = f"{_stamp}: {_note_text}" + (f" | {_prev}" if _prev else "")
                            st.rerun()

                st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)

                o1, o2 = st.columns([1.7, 1.3], gap="small")
                with o1:
                    open_pick = (
                        st.selectbox("Open in Client Look-Up", open_opts, key="map_watch_open_entity_v4")
                        if open_opts
                        else ""
                    )
                with o2:
                    remove_pick = (
                        st.multiselect("Remove entities", remove_opts, key="map_watch_remove_pick_v4")
                        if remove_opts
                        else []
                    )
                b1, b2, b3 = st.columns(3, gap="small")
                with b1:
                    if st.button("Open Client", key="map_watch_open_btn_v4", use_container_width=True) and open_pick:
                        _open_client(open_pick)
                with b2:
                    if st.button("Remove Selected", key="map_watch_remove_btn_v4", use_container_width=True) and remove_pick:
                        remove_set = {str(v).strip().lower() for v in remove_pick if str(v).strip()}
                        st.session_state.map_watchlist = [
                            rec for rec in watch
                            if str((rec or {}).get("TFL Entity", "")).strip().lower() not in remove_set
                        ]
                        st.rerun()
                with b3:
                    if st.button("Clear Docket", key="map_watch_clear_btn_v4", use_container_width=True):
                        st.session_state.map_watchlist = []
                        st.rerun()

                # -- draw area & search map for docket --------------------
                st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)
                with st.expander("\U0001F5FA Draw Area & Search â€” Investigate Docket Addresses", expanded=False):
                    st.markdown(
                        '<div style="font-size:.78rem;color:rgba(210,230,245,.55);margin-bottom:6px">'
                        '<strong>Geographic investigation:</strong> Docket source addresses are shown as markers. '
                        'Click, search, or draw new areas to discover additional addresses for re-investigation. '
                        'Use <strong>Copy All</strong> to capture addresses for Address Forensics or Batch Triage.</div>',
                        unsafe_allow_html=True,
                    )
                    # Build markers from docket source queries (extract addresses from non-Atlas sources)
                    _dkt_markers: list[dict] = []
                    for _rec in watch:
                        if not isinstance(_rec, dict):
                            continue
                        _sq = str(_rec.get("Source Query", "")).strip()
                        _ent = str(_rec.get("TFL Entity", "")).strip()
                        if _sq and not _sq.startswith("Coverage Atlas:"):
                            _geo_dkt = geocode_address_arcgis(_sq)
                            if _geo_dkt and _geo_dkt.get("lat") and _geo_dkt.get("lon"):
                                _dkt_markers.append({
                                    "lat": float(_geo_dkt["lat"]),
                                    "lon": float(_geo_dkt["lon"]),
                                    "label": f"{_ent} ({_sq[:40]})",
                                })
                    _dkt_basemap = MAP_BASEMAP_OPTIONS.get(
                        st.session_state.get("map_basemap_label", ""), "gray-vector",
                    )
                    render_draw_area_search_map(
                        height=440,
                        basemap=_dkt_basemap,
                        map_id="tfl-draw-docket",
                        markers=_dkt_markers if _dkt_markers else None,
                    )
                    _dkt_draw_col1, _dkt_draw_col2 = st.columns(2, gap="small")
                    with _dkt_draw_col1:
                        _dkt_draw_paste = st.text_input(
                            "Paste address from map",
                            key="map_draw_paste_docket",
                            placeholder="Paste a collected address here...",
                        )
                    with _dkt_draw_col2:
                        if st.button(
                            "\U0001F50D Send to Address Forensics",
                            key="map_draw_docket_to_forensics_btn",
                            use_container_width=True,
                            disabled=not str(_dkt_draw_paste).strip(),
                        ):
                            st.session_state.map_overlap_input_mode = "Street Address"
                            st.session_state.map_overlap_address_input = str(_dkt_draw_paste).strip()
                            st.session_state.map_overlap_address_query = str(_dkt_draw_paste).strip()
                            recent = [str(_dkt_draw_paste).strip()] + [
                                str(v).strip()
                                for v in st.session_state.get("map_recent_addresses", [])
                                if str(v).strip() and str(v).strip().lower() != str(_dkt_draw_paste).strip().lower()
                            ]
                            st.session_state.map_recent_addresses = recent[:10]
                            st.info("Address loaded into Address Forensics. Switch to the **Address Forensics** tab to run the analysis.")
                    _dkt_draw_b1, _dkt_draw_b2 = st.columns(2, gap="small")
                    with _dkt_draw_b1:
                        _dkt_batch_paste = st.text_area(
                            "Paste addresses for batch (one per line)",
                            key="map_draw_paste_docket_batch",
                            height=60,
                            placeholder="Paste addresses from map's Copy All...",
                        )
                    with _dkt_draw_b2:
                        if st.button(
                            "\U0001F4E5 Send to Batch Triage",
                            key="map_draw_docket_to_batch_btn",
                            use_container_width=True,
                            disabled=not str(_dkt_batch_paste).strip(),
                        ):
                            existing_batch = str(st.session_state.get("map_batch_input_v4", "")).strip()
                            new_lines = str(_dkt_batch_paste).strip()
                            if existing_batch:
                                st.session_state.map_batch_input_v4 = f"{existing_batch}\n{new_lines}"
                            else:
                                st.session_state.map_batch_input_v4 = new_lines
                            st.info("Addresses added to Batch Triage. Switch to the **Address Forensics** tab and expand Batch Address Triage.")

                # -- docket cross-navigation strip ------------------------
                st.markdown('<hr class="mp5-divider">', unsafe_allow_html=True)
                st.markdown(
                    '<div class="mp5-crosslink">'
                    '<span class="mp5-crosslink-title">Cross-Navigation</span>'
                    '<span class="mp5-crosslink-sep"></span>'
                    '<span class="mp5-crosslink-hint">Re-investigate entities in Address Forensics or refine context in the Atlas</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                # build source query options from docket entries
                _dkt_source_queries = sorted({
                    str(r.get("Source Query", "")).strip()
                    for r in watch if isinstance(r, dict) and str(r.get("Source Query", "")).strip()
                })
                _dkt_reinv_entities = remove_opts  # reuse existing entity list

                _dk1, _dk2, _dk3 = st.columns([1.5, 1.0, 1.0], gap="small")
                with _dk1:
                    _reinv_pick = st.selectbox(
                        "Re-investigate entity in Address Forensics",
                        [""] + _dkt_reinv_entities,
                        key="docket_reinvestigate_pick",
                        help="Select an entity to look up its source query address in Address Forensics.",
                    )
                    if st.button(
                        "\U0001F50D Re-investigate in Forensics",
                        key="docket_to_forensics_btn",
                        use_container_width=True,
                        disabled=not _reinv_pick,
                        help="Pre-fill Address Forensics with the source query from this entity and switch tabs.",
                    ):
                        if _reinv_pick:
                            # Find the source query for this entity
                            source_q = ""
                            for rec in watch:
                                if isinstance(rec, dict) and str(rec.get("TFL Entity", "")).strip() == str(_reinv_pick).strip():
                                    source_q = str(rec.get("Source Query", "")).strip()
                                    break
                            # Strip "Coverage Atlas: " prefix if present
                            if source_q.startswith("Coverage Atlas:"):
                                st.info(f"**{_reinv_pick}** was promoted from the Coverage Atlas, not from an address query. Set a subdivision context in the Atlas and then use Address Forensics.")
                            else:
                                if source_q:
                                    st.session_state.map_overlap_input_mode = "Street Address"
                                    st.session_state.map_overlap_address_input = source_q
                                    st.session_state.map_overlap_address_query = source_q
                                    st.session_state.map_overlap_entity_filter = str(_reinv_pick).strip()
                                st.info(f"Switch to the **Address Forensics** tab. The address **{source_q or 'N/A'}** and entity filter **{_reinv_pick}** have been pre-loaded.")
                with _dk2:
                    _dkt_ctx = st.session_state.get("map_selected_subdivision_context", {})
                    _dkt_has_ctx = isinstance(_dkt_ctx, dict) and str(_dkt_ctx.get("subdivision_name", "")).strip()
                    _dkt_atlas_label = (
                        f"\U0001F5FA View Atlas ({str(_dkt_ctx.get('subdivision_name', '')).strip()[:25]})"
                        if _dkt_has_ctx
                        else "\U0001F5FA Open Coverage Atlas"
                    )
                    if st.button(
                        _dkt_atlas_label,
                        key="docket_to_atlas_btn",
                        use_container_width=True,
                        help="Switch to the Coverage Atlas to view or adjust the subdivision context.",
                    ):
                        st.info("Switch to the **Coverage Atlas** tab above to explore subdivision coverage and set investigation context.")
                with _dk3:
                    # Quick summary of docket â†’ source query distribution
                    if _dkt_source_queries:
                        st.markdown(
                            '<div style="font-size:.72rem;color:rgba(210,230,245,.55);margin-bottom:4px">'
                            f'<strong>{len(_dkt_source_queries)}</strong> unique source quer{"y" if len(_dkt_source_queries) == 1 else "ies"} in docket'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        for sq in _dkt_source_queries[:5]:
                            sq_count = sum(1 for r in watch if isinstance(r, dict) and str(r.get("Source Query", "")).strip() == sq)
                            st.markdown(
                                f'<div style="font-size:.68rem;color:rgba(210,230,245,.42);padding:1px 0">'
                                f'\U0001F4CD {html.escape(sq[:50], quote=True)} ({sq_count})</div>',
                                unsafe_allow_html=True,
                            )
                        if len(_dkt_source_queries) > 5:
                            st.markdown(
                                f'<div style="font-size:.66rem;color:rgba(210,230,245,.35)">+{len(_dkt_source_queries) - 5} more</div>',
                                unsafe_allow_html=True,
                            )
    finally:
        _pop_context(_previous, runtime_ctx)

