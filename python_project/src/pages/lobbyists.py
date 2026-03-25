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
    '_client_page',
    '_current_filter_parts',
    '_default_session_from_list',
    '_last_first_initial_key',
    '_map_page',
    '_member_page',
    '_page_fragments',
    '_remember_recent_search',
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
    'format_lobbyist_label',
    'get_lobby_scope_bundle',
    'html',
    'is_bill_query',
    'lobby_candidate_key',
    'lobbyist_autocomplete_candidates',
    'norm_name',
    'norm_person_variants_with_nicknames',
    'normalize_bill',
    'parse_person_name',
    'pd',
    're',
    'render_bill_search_results',
    'require_app_state',
    'reset_filters',
    'resolve_lobbyshort_from_wit',
)


def configure_helpers(**helpers: Any) -> None:
    _configure_helpers(globals(), **helpers)


def render_page(ctx: dict[str, Any] | None = None) -> None:
    _ctx = ctx or {}
    _previous = _push_context(globals(), _ctx)
    try:
        _render_page_intro(
            kicker="Lobbyist Workspace",
            title="Lobbyist Evidence View",
            subtitle=(
                "Search by lobbyist or bill, establish statewide context, then drill into reported positions, subjects, activities, and disclosures."
            ),
            pills=[
                "Session and scope aware",
                "Autocomplete with disambiguation",
                "CSV and PDF evidence export",
            ],
        )
        _render_journey("lobby")
        _render_workspace_guide(
            question=(
                "How much taxpayer-funded lobbying is reported, who is involved, and where does that activity appear in the legislative process?"
            ),
            steps=[
                "Set session and scope before searching.",
                "Confirm the exact lobbyist identity in autocomplete matches.",
                "Read Statewide Snapshot before profile-level tabs.",
                "Use bill mode when the investigation starts with a bill number.",
            ],
            method_note="When multiple names share a short code, use explicit match selection to avoid conflation.",
        )
        _render_quickstart(
            "lobby",
            [
                "Set session and scope before searching.",
                "Use autocomplete to confirm the exact lobbyist record.",
                "Review Statewide Snapshot before profile tabs and exports.",
            ],
            note="Bill-first searches route to a focused bill context with lobbyist linkage.",
        )
        _render_evidence_guardrails(
            can_answer=[
                "Which lobbyists report taxpayer-funded and private clients in the selected scope.",
                "How witness, activity, subject, disclosure, and staff-link records connect by session.",
                "Where taxpayer-funded share and concentration are highest in the current selection.",
            ],
            cannot_answer=[
                "Exact invoice-level compensation from range-based filings.",
                "Intent or legal conclusions without corroborating evidence.",
            ],
            next_checks=[
                "Confirm the selected lobbyist identity before profile-level exports.",
                "Pivot to Clients or Legislators to verify downstream claims.",
            ],
        )
        _render_workspace_links(
            "lobby_top",
            [
                ("Open Clients", _client_page, "Validate entity-level contracts, activity, and disclosures."),
                ("Open Legislators", _member_page, "Connect results to authored bills and witness records."),
                ("Open Map & Address", _map_page, "Check local overlap by jurisdiction and street address."),
                ("Open Policy Context", _solutions_page, "Review policy framework against observed patterns."),
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
        Fiscal_Impact = data["Fiscal_Impact"]
        Bill_Sub_All = data["Bill_Sub_All"]
        Lobby_Sub_All = data["Lobby_Sub_All"]
        Lobby_TFL_Client_All = data["Lobby_TFL_Client_All"]
        Staff_All = data["Staff_All"]
        LaCvr = data["LaCvr"]
        LaDock = data["LaDock"]
        LaI4E = data["LaI4E"]
        LaSub = data["LaSub"]
        name_to_short = app_state.name_to_short
        short_to_names = app_state.short_to_names
        lobby_index = app_state.lobby_index
        lobbyist_index = app_state.lobbyist_index
        known_shorts = app_state.known_shorts
        tfl_sessions = set(app_state.tfl_sessions)

        if "scope" not in st.session_state:
            st.session_state.scope = "This Session"
        if "session" not in st.session_state:
            st.session_state.session = None
        if "lobbyshort" not in st.session_state:
            st.session_state.lobbyshort = ""
        if "lobby_filerid" not in st.session_state:
            st.session_state.lobby_filerid = None
        if "lobby_selected_key" not in st.session_state:
            st.session_state.lobby_selected_key = ""
        if "lobby_all_matches" not in st.session_state:
            st.session_state.lobby_all_matches = False
        if "lobby_merge_keys" not in st.session_state:
            st.session_state.lobby_merge_keys = []
        if "lobby_candidate_map" not in st.session_state:
            st.session_state.lobby_candidate_map = {}
        if "lobby_override_same" not in st.session_state:
            st.session_state.lobby_override_same = {}
        if "lobby_override_diff" not in st.session_state:
            st.session_state.lobby_override_diff = {}
        if "lobby_match_query" not in st.session_state:
            st.session_state.lobby_match_query = ""
        if "lobby_match_select" not in st.session_state:
            st.session_state.lobby_match_select = "No match"
        if "search_query" not in st.session_state:
            st.session_state.search_query = ""
        if "bill_search" not in st.session_state:
            st.session_state.bill_search = ""
        if "activity_search" not in st.session_state:
            st.session_state.activity_search = ""
        if "disclosure_search" not in st.session_state:
            st.session_state.disclosure_search = ""
        if "filter_lobbyshort" not in st.session_state:
            st.session_state.filter_lobbyshort = ""
        if "recent_lobby_searches" not in st.session_state:
            st.session_state.recent_lobby_searches = []
        if "lobby_policy_focus" not in st.session_state:
            st.session_state.lobby_policy_focus = {}

        st.sidebar.header("Data")

        sessions = list(app_state.shared_sessions)
        if not sessions:
            st.error("No sessions found in the workbook.")
            st.stop()
        default_session = app_state.default_shared_session or _default_session_from_list(sessions)
        default_label = _session_label(default_session)

        with st.sidebar.expander("Data health", expanded=False):
            st.caption(f"Data path: {PATH}")
            health = data_health_table(data)
            st.dataframe(health, width="stretch", height=260, hide_index=True)

        st.markdown('<div id="filter-bar-marker"></div>', unsafe_allow_html=True)
        top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

        with top1:
            st.session_state.search_query = st.text_input(
                "Search lobbyist or bill",
                value=st.session_state.search_query,
                placeholder="e.g., Abbott or HB 4",
                help="Type a lobbyist name as Last, First or First Last. Use Autocomplete matches to pick the exact match.",
            )

        with top2:
            label_to_session = {}
            session_labels = []
            for s in sessions:
                lab = _session_label(s)
                session_labels.append(lab)
                label_to_session[lab] = s

            if st.session_state.session is None or str(st.session_state.session).strip().lower() in {"none", "nan", "null", ""}:
                st.session_state.session = default_session

            current_label = _session_label(st.session_state.session)
            if current_label not in session_labels:
                current_label = default_label if default_label in session_labels else session_labels[0]

            chosen_label = st.selectbox(
                "Session",
                session_labels,
                index=session_labels.index(current_label),
                help="Choose the legislative session used for filters and totals.",
            )
            st.session_state.session = label_to_session.get(chosen_label, default_session)

        with top3:
            scope_opts = ["This Session", "All Sessions"]
            scope_index = scope_opts.index(st.session_state.scope) if st.session_state.scope in scope_opts else 0
            st.session_state.scope = st.radio(
                "Overview scope",
                scope_opts,
                index=scope_index,
                horizontal=True,
                help="Switch between the selected session only or totals across all sessions.",
            )

        recent = st.session_state.get("recent_lobby_searches", [])
        if recent:
            st.markdown('<div class="section-sub">Recent lookups</div>', unsafe_allow_html=True)
            recent_cols = st.columns(min(len(recent), 4))
            for idx, rec in enumerate(recent[:8]):
                col = recent_cols[idx % len(recent_cols)]
                label = rec if len(rec) <= 28 else rec[:25] + "..."
                if col.button(
                    f"Reuse {label}",
                    key=f"recent_lookup_{idx}",
                    help="Reuse a recent lobbyist or bill search",
                    width="stretch",
                ):
                    st.session_state.search_query = rec
                    st.session_state.lobbyshort = ""
                    st.session_state.lobby_filerid = None
                    st.session_state.lobby_selected_key = ""
                    st.session_state.lobby_all_matches = False
                    st.session_state.lobby_merge_keys = []
                    st.session_state.lobby_candidate_map = {}
                    st.session_state.lobby_match_query = rec
                    st.session_state.lobby_match_select = "No match"
                    st.session_state.bill_search = ""
                    st.session_state.activity_search = ""
                    st.session_state.disclosure_search = ""
                    st.session_state.lobby_policy_focus = {}
                    st.session_state.filter_lobbyshort = ""

        tfl_session_val = _tfl_session_for_filter(st.session_state.session, tfl_sessions)

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        bill_mode = is_bill_query(st.session_state.search_query)
        typed_norms = norm_person_variants_with_nicknames(st.session_state.search_query) if not bill_mode else set()
        typed_init_key = _last_first_initial_key(st.session_state.search_query) if not bill_mode else ""
        if typed_init_key:
            typed_norms.add(typed_init_key)

        resolved_short = ""
        resolved_filerid = None
        match_candidates = []
        candidate_map = {}
        fallback_short = ""
        q_norm = norm_name(st.session_state.search_query)
        query_info = parse_person_name(st.session_state.search_query)
        q_first = query_info.get("first_norm", "")
        q_last = query_info.get("last_norm", "")
        selected_match = None

        if not bill_mode and st.session_state.search_query.strip():
            match_candidates = lobbyist_autocomplete_candidates(st.session_state.search_query, lobbyist_index)

            if q_norm and not lobbyist_index.empty:
                short_hits = lobbyist_index.loc[
                    lobbyist_index["LobbyShortNorm"] == q_norm, "LobbyShort"
                ].dropna().unique().tolist()
                if len(short_hits) == 1:
                    fallback_short = short_hits[0]

            if not match_candidates:
                resolved_from_wit, wit_suggestions = resolve_lobbyshort_from_wit(
                    st.session_state.search_query,
                    Wit_All,
                    st.session_state.session,
                )
                if resolved_from_wit:
                    fallback_short = resolved_from_wit
                for s in wit_suggestions:
                    name_hint = short_to_names.get(s, [])
                    display_name = name_hint[0] if name_hint else s
                    label = format_lobbyist_label(display_name, s, None)
                    match_candidates.append({
                        "label": label,
                        "lobbyshort": s,
                        "filerid": None,
                        "name": display_name,
                        "score": 60,
                    })

            if match_candidates:
                match_candidates = sorted(
                    match_candidates,
                    key=lambda x: (-int(x.get("score", 0)), str(x.get("label", "")))
                )
                for cand in match_candidates:
                    cand["key"] = lobby_candidate_key(cand)
                    if cand.get("key") and not cand.get("all_matches"):
                        candidate_map[cand["key"]] = cand
                diff_map = st.session_state.lobby_override_diff or {}
                diff_keys_all = set()
                for keys in diff_map.values():
                    diff_keys_all |= set(keys or [])
                shorts_with_diff = set()
                if diff_keys_all:
                    for key in diff_keys_all:
                        cand = candidate_map.get(key, {})
                        short = cand.get("lobbyshort", "")
                        if short:
                            shorts_with_diff.add(short)
                short_groups = {}
                for cand in match_candidates:
                    short = cand.get("lobbyshort", "")
                    if not short:
                        continue
                    entry = short_groups.get(short, {"count": 0, "score": 0})
                    entry["count"] += 1
                    entry["score"] = max(entry["score"], cand.get("score", 0))
                    short_groups[short] = entry

                short_candidates = []
                for short, meta in short_groups.items():
                    if meta["count"] > 1:
                        if short in shorts_with_diff:
                            label = f"{short} (all matches: {meta['count']} variants, overrides set)"
                        else:
                            label = f"{short} (all matches: {meta['count']} variants)"
                        short_candidates.append({
                            "label": label,
                            "lobbyshort": short,
                            "filerid": None,
                            "name": "",
                            "score": meta["score"],
                            "all_matches": True,
                            "group_size": meta["count"],
                            "has_diff_override": short in shorts_with_diff,
                            "key": f"all:{short}",
                        })

                preferred_all = None
                if short_candidates:
                    eligible = [c for c in short_candidates if not c.get("has_diff_override")]
                    if eligible:
                        preferred_all = sorted(eligible, key=lambda x: (-x["score"], x["label"]))[0]

                auto_match = preferred_all
                if auto_match is None:
                    if len(match_candidates) == 1:
                        auto_match = match_candidates[0]
                    if auto_match is None and q_norm:
                        exact_name = [
                            c for c in match_candidates
                            if c.get("name") and norm_name(c.get("name")) == q_norm
                        ]
                        if len(exact_name) == 1:
                            auto_match = exact_name[0]
                    if auto_match is None and q_norm and short_candidates:
                        for cand in short_candidates:
                            if norm_name(cand["lobbyshort"]) == q_norm:
                                if not cand.get("has_diff_override"):
                                    auto_match = cand
                                break
                    if auto_match is None:
                        top_score = match_candidates[0]["score"]
                        top = [c for c in match_candidates if c["score"] == top_score]
                        q_full = bool(q_first and q_last and len(q_first) >= 2 and len(q_last) >= 2)
                        if len(top) == 1 and (top_score >= 95 or (top_score >= 92 and q_full)):
                            auto_match = top[0]
                if auto_match is not None and auto_match.get("all_matches") and auto_match.get("has_diff_override"):
                    auto_match = None

                match_options = []
                match_map = {}
                for cand in sorted(short_candidates, key=lambda x: (-x["score"], x["label"])):
                    match_options.append(cand["label"])
                    match_map[cand["label"]] = cand
                for cand in match_candidates:
                    if cand["label"] in match_map:
                        continue
                    match_options.append(cand["label"])
                    match_map[cand["label"]] = cand

                if match_options:
                    match_labels = ["No match"] + match_options
                    default_label = auto_match["label"] if auto_match else "No match"
                    if st.session_state.lobby_match_query != st.session_state.search_query:
                        st.session_state.lobby_match_query = st.session_state.search_query
                        st.session_state.lobby_match_select = default_label if default_label in match_labels else "No match"
                    if st.session_state.lobby_match_select not in match_labels:
                        st.session_state.lobby_match_select = default_label if default_label in match_labels else "No match"

                    pick = st.selectbox(
                        "Autocomplete matches (choose one)",
                        match_labels,
                        key="lobby_match_select",
                        help="Pick the exact lobbyist entry. '(all matches)' merges name variants.",
                    )
                    st.caption("Each option lists the last name + first initial (and FilerID when available).")
                    if pick in match_map:
                        chosen = match_map[pick]
                        selected_match = chosen
                        st.session_state.lobby_selected_key = chosen.get("key", "")
                        st.session_state.lobby_all_matches = bool(chosen.get("all_matches"))
                        resolved_short = chosen.get("lobbyshort", "")
                        resolved_filerid = chosen.get("filerid", None)
                    else:
                        resolved_short = ""
                        st.session_state.lobby_selected_key = ""
                        st.session_state.lobby_all_matches = False
                    if st.session_state.search_query.strip() and not resolved_short:
                        st.caption("Select a match to load results. Choose the '(all matches)' option to combine name variants that share the same last name + first initial.")

                    if selected_match and selected_match.get("lobbyshort") and not selected_match.get("all_matches"):
                        canon_key = st.session_state.lobby_selected_key
                        if not canon_key:
                            canon_key = "unknown"
                        canon_key_safe = re.sub(r"[^A-Za-z0-9_]+", "_", canon_key)
                        same_map = st.session_state.lobby_override_same or {}
                        diff_map = st.session_state.lobby_override_diff or {}
                        same_keys = set(same_map.get(canon_key, []))
                        diff_keys = set(diff_map.get(canon_key, []))
                        override_candidates = [
                            c for c in match_candidates
                            if not c.get("all_matches")
                            and c.get("lobbyshort") == selected_match.get("lobbyshort")
                            and c.get("key") != canon_key
                        ]
                        if override_candidates:
                            used = {}
                            option_labels = []
                            label_to_key = {}
                            for cand in override_candidates:
                                base_label = (cand.get("label") or cand.get("name") or cand.get("lobbyshort") or "").strip()
                                label = base_label if base_label else "Unknown"
                                if label in used:
                                    used[label] += 1
                                    label = f"{label} ({used[label]})"
                                else:
                                    used[label] = 1
                                option_labels.append(label)
                                label_to_key[label] = cand.get("key", lobby_candidate_key(cand))

                            with st.expander("Match overrides", expanded=False):
                                st.caption("Use this when you know two names refer to the same lobbyist or are definitely different.")
                                same_default = [lab for lab in option_labels if label_to_key.get(lab) in same_keys]
                                diff_default = [lab for lab in option_labels if label_to_key.get(lab) in diff_keys]

                                same_pick = st.multiselect(
                                    "Same lobbyist (merge these into the selection)",
                                    option_labels,
                                    default=same_default,
                                    key=f"lobby_override_same_select_{canon_key_safe}",
                                    help="Treat these names as the same person and merge results.",
                                )
                                diff_pick = st.multiselect(
                                    "Different lobbyist (keep these separate)",
                                    option_labels,
                                    default=diff_default,
                                    key=f"lobby_override_diff_select_{canon_key_safe}",
                                    help="Force these names to remain separate from the selection.",
                                )

                                new_same_keys = {label_to_key.get(lab) for lab in same_pick if label_to_key.get(lab)}
                                new_diff_keys = {label_to_key.get(lab) for lab in diff_pick if label_to_key.get(lab)}
                                new_same_keys = new_same_keys - new_diff_keys

                                same_map[canon_key] = sorted(new_same_keys)
                                diff_map[canon_key] = sorted(new_diff_keys)
                                st.session_state.lobby_override_same = same_map
                                st.session_state.lobby_override_diff = diff_map
                                st.session_state.lobby_merge_keys = sorted(new_same_keys)
                        else:
                            st.session_state.lobby_merge_keys = []
                    else:
                        st.session_state.lobby_merge_keys = []
                else:
                    resolved_short = fallback_short
            else:
                resolved_short = fallback_short
        else:
            st.session_state.lobby_selected_key = ""
            st.session_state.lobby_all_matches = False
            st.session_state.lobby_merge_keys = []

        st.session_state.lobbyshort = resolved_short or ""
        st.session_state.lobby_filerid = resolved_filerid
        st.session_state.lobby_candidate_map = candidate_map
        if st.session_state.lobby_filerid and not lobbyist_index.empty:
            filer_series = pd.to_numeric(lobbyist_index.get("FilerID", pd.Series(dtype=float)), errors="coerce")
            match_row = lobbyist_index[
                (lobbyist_index["LobbyShort"].astype(str).str.strip() == st.session_state.lobbyshort) &
                (filer_series == int(st.session_state.lobby_filerid))
            ]
            if not match_row.empty:
                typed_norms |= norm_person_variants_with_nicknames(match_row["Lobby Name"].iloc[0])
        merge_keys = st.session_state.lobby_merge_keys or []
        candidate_map = st.session_state.lobby_candidate_map or {}
        for key in merge_keys:
            cand = candidate_map.get(key, {})
            name = cand.get("name", "")
            if name:
                typed_norms |= norm_person_variants_with_nicknames(name)

        if st.session_state.lobbyshort:
            _remember_recent_search(st.session_state.search_query or st.session_state.lobbyshort)
        elif st.session_state.search_query.strip():
            _remember_recent_search(st.session_state.search_query)

        match_line = "No match selected"
        if st.session_state.lobbyshort:
            if st.session_state.lobby_filerid and not lobbyist_index.empty:
                filer_series = pd.to_numeric(lobbyist_index.get("FilerID", pd.Series(dtype=float)), errors="coerce")
                match_row = lobbyist_index[
                    (lobbyist_index["LobbyShort"].astype(str).str.strip() == str(st.session_state.lobbyshort)) &
                    (filer_series == int(st.session_state.lobby_filerid))
                ]
                if not match_row.empty:
                    match_name = match_row["Lobby Name"].iloc[0]
                    match_line = format_lobbyist_label(match_name, st.session_state.lobbyshort, st.session_state.lobby_filerid)
                else:
                    match_line = st.session_state.lobbyshort
            else:
                match_line = st.session_state.lobbyshort

        extra_parts = ["Mode: Bill search"] if bill_mode else []
        active_parts = _current_filter_parts(extra_parts)
        chips_html = "".join([f'<span class="chip">{html.escape(c)}</span>' for c in active_parts])

        st.markdown('<div id="filter-summary-marker"></div>', unsafe_allow_html=True)
        f1, f2 = st.columns([3, 1])
        with f1:
            st.markdown(
                f'<div class="filter-summary"><span class="filter-summary-label">Active filters</span>{chips_html}</div>',
                unsafe_allow_html=True,
            )
            st.caption(f"Selected match: {match_line}")
            merge_names = []
            if st.session_state.lobby_merge_keys:
                cand_map = st.session_state.lobby_candidate_map or {}
                for key in st.session_state.lobby_merge_keys:
                    cand = cand_map.get(key, {})
                    name = cand.get("name", "")
                    short = cand.get("lobbyshort", "")
                    fid = cand.get("filerid", None)
                    if name or short:
                        merge_names.append(format_lobbyist_label(name, short, fid))
            if merge_names:
                st.caption("Merged variants: " + ", ".join(merge_names[:4]))
                st.caption("Use Autocomplete matches to change the selection.")
            names_hint = short_to_names.get(st.session_state.lobbyshort, []) if st.session_state.lobbyshort else []
            if names_hint:
                st.caption("Also seen as: " + ", ".join(names_hint[:6]))
        with f2:
            if st.button(
                "Clear filters",
                width="stretch",
                help="Reset search, match, and table filters to defaults.",
            ):
                reset_filters(default_session)
        st.markdown(
            '<div class="app-note"><strong>Interpretation:</strong> Match selection controls identity resolution. Confirm the selected lobbyist label before using profile-level outputs or exported evidence.</div>',
            unsafe_allow_html=True,
        )
        if st.session_state.lobbyshort and not st.session_state.lobby_filerid and not lobbyist_index.empty:
            dup = lobbyist_index[lobbyist_index["LobbyShort"].astype(str).str.strip() == st.session_state.lobbyshort]
            if dup["FilerID"].nunique(dropna=True) > 1 or dup["Lobby Name"].nunique() > 1:
                if not st.session_state.lobby_all_matches:
                    st.caption("Note: multiple name variants share this last name + first initial. Choose a specific match above to narrow results. Witness-list and bill activity remain combined.")

        focus_label = "All Lobbyists"
        if st.session_state.lobbyshort:
            display_name = ""
            if st.session_state.lobby_filerid and not lobbyist_index.empty:
                filer_series = pd.to_numeric(lobbyist_index.get("FilerID", pd.Series(dtype=float)), errors="coerce")
                match_row = lobbyist_index[
                    (lobbyist_index["LobbyShort"].astype(str).str.strip() == str(st.session_state.lobbyshort)) &
                    (filer_series == int(st.session_state.lobby_filerid))
                ]
                if not match_row.empty:
                    display_name = match_row["Lobby Name"].iloc[0]
            if not display_name:
                name_hint = short_to_names.get(st.session_state.lobbyshort, []) if isinstance(short_to_names, dict) else []
                display_name = name_hint[0] if name_hint else st.session_state.lobbyshort
            if display_name != st.session_state.lobbyshort:
                focus_label = f"Lobbyist: {display_name} ({st.session_state.lobbyshort})"
            else:
                focus_label = f"Lobbyist: {st.session_state.lobbyshort}"
        elif st.session_state.search_query.strip():
            focus_label = f"Lobbyist search: {st.session_state.search_query.strip()}"

        report_title = "Bill Report" if bill_mode and st.session_state.search_query.strip() else "Lobbyist Report"
        focus_tables = {
            "Staff_All": Staff_All,
            "Lobby_Sub_All": Lobby_Sub_All,
            "LaFood": data.get("LaFood", pd.DataFrame()),
            "LaEnt": data.get("LaEnt", pd.DataFrame()),
            "LaTran": data.get("LaTran", pd.DataFrame()),
            "LaGift": data.get("LaGift", pd.DataFrame()),
            "LaEvnt": data.get("LaEvnt", pd.DataFrame()),
            "LaAwrd": data.get("LaAwrd", pd.DataFrame()),
            "LaCvr": LaCvr,
            "LaDock": LaDock,
            "LaI4E": LaI4E,
            "LaSub": LaSub,
        }
        focus_lookups = {
            "name_to_short": name_to_short,
            "short_to_names": short_to_names,
            "filerid_to_short": data.get("filerid_to_short", {}),
        }

        focus_context = {
            "type": "",
            "report_title": report_title,
            "tables": focus_tables,
            "lookups": focus_lookups,
        }
        if bill_mode and st.session_state.search_query.strip():
            bill_id = ""
            try:
                bill_id = normalize_bill(st.session_state.search_query.strip())
            except Exception:
                bill_id = ""
            focus_context.update(
                {
                    "type": "bill",
                    "bill": bill_id or st.session_state.search_query.strip(),
                    "query": st.session_state.search_query.strip(),
                }
            )
        elif st.session_state.lobbyshort:
            focus_context.update(
                {
                    "type": "lobbyist",
                    "lobbyshort": st.session_state.lobbyshort,
                    "display_name": display_name,
                }
            )

        _ = _render_pdf_report_section(
            key_prefix="lobby",
            session_val=st.session_state.session,
            scope_label=st.session_state.scope,
            focus_label=focus_label,
            Lobby_TFL_Client_All=Lobby_TFL_Client_All,
            Wit_All=Wit_All,
            Bill_Status_All=Bill_Status_All,
            Bill_Sub_All=Bill_Sub_All,
            tfl_session_val=tfl_session_val,
            focus_context=focus_context,
        )

        lobby_scope_bundle = get_lobby_scope_bundle(
            str(PATH),
            st.session_state.scope,
            tfl_session_val,
        )
        all_pivot = lobby_scope_bundle.all_pivot
        all_stats = lobby_scope_bundle.all_stats

        if bill_mode:
            st.subheader("Bill Search Results")
            render_bill_search_results(
                st.session_state.search_query,
                st.session_state.session,
                tfl_session_val,
                Wit_All,
                Bill_Status_All,
                Lobby_TFL_Client_All,
                short_to_names,
            )
            st.caption("Clear search to return to lobbyist view.")
            st.stop()

        st.session_state["_lobby_workspace_ctx"] = {
            "lobby_scope_bundle": lobby_scope_bundle,
            "all_pivot": all_pivot,
            "all_stats": all_stats,
            "tfl_session_val": tfl_session_val,
            "typed_norms": typed_norms,
            "data": data,
            "Wit_All": Wit_All,
            "Bill_Status_All": Bill_Status_All,
            "Fiscal_Impact": Fiscal_Impact,
            "Bill_Sub_All": Bill_Sub_All,
            "Lobby_Sub_All": Lobby_Sub_All,
            "Lobby_TFL_Client_All": Lobby_TFL_Client_All,
            "Staff_All": Staff_All,
            "LaCvr": LaCvr,
            "LaDock": LaDock,
            "LaI4E": LaI4E,
            "LaSub": LaSub,
            "name_to_short": name_to_short,
            "short_to_names": short_to_names,
            "lobbyist_index": lobbyist_index,
        }
        _page_fragments.render_lobby_workspace_fragment("_lobby_workspace_ctx")
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
        st.markdown(
            """
<script>
(function(){
  /* Ctrl+K or / to focus nav search bar */
  document.addEventListener('keydown', function(e){
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      var navInput = document.querySelector('input[aria-label="Nav search"]');
      if (navInput) navInput.focus();
    }
    if (e.key === '/' && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) {
      e.preventDefault();
      var navInput = document.querySelector('input[aria-label="Nav search"]');
      if (navInput) navInput.focus();
    }
  });

  /* Scroll to top on fresh page load */
  if (!window.__tflScrollInit) {
    window.__tflScrollInit = true;
    window.scrollTo({top: 0, behavior: 'instant'});
  }
})();
</script>
""",
            unsafe_allow_html=True,
        )
        st.stop()
    finally:
        _pop_context(globals(), _previous, _ctx)
