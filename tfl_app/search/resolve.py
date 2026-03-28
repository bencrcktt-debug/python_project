from __future__ import annotations

import difflib
import re
from typing import Any

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - test fallback when Streamlit is unavailable
    import functools

    class _CacheDataStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            hash_funcs = decorator_kwargs.get("hash_funcs", {})

            def decorator(func):
                cache: dict[object, object] = {}

                def hash_value(value):
                    for typ, hasher in hash_funcs.items():
                        if isinstance(value, typ):
                            return (typ.__name__, hasher(value))
                    if isinstance(value, dict):
                        return tuple(sorted((k, hash_value(v)) for k, v in value.items()))
                    if isinstance(value, (list, tuple)):
                        return tuple(hash_value(v) for v in value)
                    return value

                @functools.wraps(func)
                def wrapper(*args, **kwargs):
                    key = (
                        tuple(hash_value(arg) for arg in args),
                        tuple(sorted((k, hash_value(v)) for k, v in kwargs.items())),
                    )
                    if key not in cache:
                        cache[key] = func(*args, **kwargs)
                    return cache[key]

                wrapper.clear = cache.clear
                return wrapper

            return decorator

    class _StreamlitStub:
        cache_data = _CacheDataStub()

    st = _StreamlitStub()

from tfl_app.search.indexes import AppState
from tfl_app.search.models import NavQueryKey, NavSearchBundle
from tfl_app.shared.names import (
    _nickname_variants,
    norm_name,
    norm_name_series,
    norm_person_variants,
    norm_person_variants_with_nicknames,
    parse_member_name,
    parse_person_name,
)


def _candidate_label(short_code: str, short_to_names: dict[str, list[str]]) -> str:
    names = short_to_names.get(short_code, [])
    if names:
        return f"{short_code} - {names[0]}"
    return short_code


def format_lobbyist_label(name: str, lobbyshort: str, filer_id) -> str:
    base = str(name).strip() if name else str(lobbyshort).strip()
    short_value = str(lobbyshort).strip()
    details = []
    if short_value and name:
        details.append(f"Last name + first initial: {short_value}")
    if pd.notna(filer_id):
        try:
            filer_value = int(filer_id)
        except Exception:
            filer_value = str(filer_id)
        details.append(f"FilerID {filer_value}")
    if details:
        return f"{base} ({' | '.join(details)})" if base else " | ".join(details)
    return base


def lobby_candidate_key(candidate: dict[str, Any]) -> str:
    short = str(candidate.get("lobbyshort", "") or "").strip()
    filer_id = candidate.get("filerid", None)
    name = str(candidate.get("name", "") or "").strip()
    try:
        if pd.notna(filer_id):
            return f"fid:{int(filer_id)}"
    except Exception:
        pass
    if short and name:
        return f"short:{short}|name:{norm_name(name)}"
    if short:
        return f"short:{short}"
    if name:
        return f"name:{norm_name(name)}"
    return "unknown"


def resolve_client_name(user_text: str, client_index: pd.DataFrame) -> tuple[str, list[str]]:
    query = (user_text or "").strip()
    if not query or client_index.empty:
        return "", []
    query_norm = norm_name(query)
    if not query_norm:
        return "", []

    data = client_index
    exact = data[data["ClientNorm"] == query_norm]["Client"].dropna().astype(str).unique().tolist()
    if len(exact) == 1:
        return exact[0], []

    prefix = data[data["ClientNorm"].str.startswith(query_norm, na=False)]
    contains = data[data["ClientNorm"].str.contains(query_norm, na=False)]
    candidates = pd.concat([prefix, contains], ignore_index=True).drop_duplicates("Client")
    suggestions = candidates["Client"].dropna().astype(str).tolist()[:10]
    if len(suggestions) == 1 and len(query_norm) >= 4:
        return suggestions[0], []

    if not suggestions:
        norms = data["ClientNorm"].dropna().unique().tolist()
        close = difflib.get_close_matches(query_norm, norms, n=10, cutoff=0.78)
        if close:
            suggestions = (
                data[data["ClientNorm"].isin(close)]["Client"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()[:10]
            )
    return "", suggestions


def resolve_member_name(user_text: str, member_index: pd.DataFrame) -> tuple[str, list[str]]:
    query = (user_text or "").strip()
    if not query or member_index.empty:
        return "", []
    query_norms = {variant for variant in norm_person_variants(query) if variant}
    last_norm = parse_member_name(query).get("last_norm", "")
    if last_norm:
        query_norms.add(last_norm)
    query_norm = norm_name(query)
    if query_norm:
        query_norms.add(query_norm)
    if not query_norms:
        return "", []

    data = member_index
    exact = data[data["MemberNorm"].isin(query_norms)]["Member"].dropna().astype(str).unique().tolist()
    if len(exact) == 1:
        return exact[0], []

    prefix_mask = pd.Series(False, index=data.index)
    contains_mask = pd.Series(False, index=data.index)
    for query_norm_value in query_norms:
        if not query_norm_value:
            continue
        prefix_mask = prefix_mask | data["MemberNorm"].str.startswith(query_norm_value, na=False)
        contains_mask = contains_mask | data["MemberNorm"].str.contains(query_norm_value, na=False)

    prefix = data[prefix_mask]
    contains = data[contains_mask]
    candidates = pd.concat([prefix, contains], ignore_index=True).drop_duplicates("Member")
    suggestions = candidates["Member"].dropna().astype(str).tolist()[:10]
    if len(suggestions) == 1 and len(query_norm) >= 3:
        return suggestions[0], []

    if not suggestions:
        norms = data["MemberNorm"].dropna().unique().tolist()
        close = difflib.get_close_matches(query_norm, norms, n=10, cutoff=0.78) if query_norm else []
        if close:
            suggestions = (
                data[data["MemberNorm"].isin(close)]["Member"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()[:10]
            )
    return "", suggestions


def resolve_lobbyshort(
    user_text: str,
    lobby_index: pd.DataFrame,
    name_to_short: dict[str, str],
    known_shorts: set[str] | frozenset[str],
    short_to_names: dict[str, list[str]],
) -> tuple[str, list[str]]:
    query = (user_text or "").strip()
    if not query:
        return "", []

    scores: dict[str, int] = {}
    if query in known_shorts:
        scores[query] = 100

    query_norm = norm_name(query)
    norm_variants = {variant for variant in norm_person_variants_with_nicknames(query) if variant}
    if query_norm:
        norm_variants.add(query_norm)
    for variant in norm_variants:
        if variant in name_to_short:
            short = str(name_to_short[variant])
            if short and short.lower() not in {"nan", "none"}:
                scores[short] = max(scores.get(short, 0), 95)

    data = lobby_index
    if (not norm_variants or data.empty) and not scores:
        return "", []

    info = parse_person_name(query)
    query_first = info.get("first_norm", "")
    query_last = info.get("last_norm", "")
    query_initial = info.get("first_initial", "")
    query_first_variants = _nickname_variants(query_first) if query_first else set()

    if query_norm and "LobbyShortNorm" in data.columns:
        exact_short = data["LobbyShortNorm"] == query_norm
        for short in data.loc[exact_short, "LobbyShort"].dropna().unique().tolist():
            scores[short] = max(scores.get(short, 0), 95)

    if not data.empty and norm_variants:
        prefix_cols = [
            column
            for column in [
                "LobbyShortNorm",
                "LobbyNameNorm",
                "LobbyNameCleanNorm",
                "LastFirstNorm",
                "FirstLastNorm",
                "LastFirstInitialNorm",
            ]
            if column in data.columns
        ]
        if prefix_cols:
            prefix_mask = pd.Series(False, index=data.index)
            for variant in norm_variants:
                for column in prefix_cols:
                    prefix_mask = prefix_mask | data[column].str.startswith(variant, na=False)
            for short in data.loc[prefix_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 90)

    if not data.empty and norm_variants:
        contains_cols = [
            column
            for column in [
                "LobbyShortNorm",
                "LobbyNameNorm",
                "LobbyNameCleanNorm",
                "LastFirstNorm",
                "FirstLastNorm",
            ]
            if column in data.columns
        ]
        if contains_cols:
            contains_mask = pd.Series(False, index=data.index)
            for variant in norm_variants:
                for column in contains_cols:
                    contains_mask = contains_mask | data[column].str.contains(variant, na=False)
            for short in data.loc[contains_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 70)

    if query_last and "LastNorm" in data.columns:
        last_mask = data["LastNorm"] == query_last
        for short in data.loc[last_mask, "LobbyShort"].dropna().unique().tolist():
            scores[short] = max(scores.get(short, 0), 75)
        if query_first and "FirstNorm" in data.columns:
            exact_mask = last_mask & (data["FirstNorm"] == query_first)
            for short in data.loc[exact_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 96)
            if query_first_variants:
                nick_mask = last_mask & data["FirstNorm"].isin(query_first_variants)
                for short in data.loc[nick_mask, "LobbyShort"].dropna().unique().tolist():
                    scores[short] = max(scores.get(short, 0), 94)
            prefix_mask = last_mask & data["FirstNorm"].str.startswith(query_first, na=False)
            for short in data.loc[prefix_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 90)
        if query_initial and "FirstInitial" in data.columns:
            init_mask = last_mask & (data["FirstInitial"] == query_initial)
            for short in data.loc[init_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 86)

    if not data.empty and norm_variants:
        fuzzy_seed = max(norm_variants, key=len, default="")
        if len(fuzzy_seed) >= 3:
            name_norms = data.get("LobbyNameCleanNorm", data.get("LobbyNameNorm", pd.Series(dtype=object))).dropna().unique().tolist()
            close = difflib.get_close_matches(fuzzy_seed, name_norms, n=5, cutoff=0.78)
            if close:
                close_set = set(close)
                if "LobbyNameCleanNorm" in data.columns:
                    match_mask = data["LobbyNameCleanNorm"].isin(close_set)
                else:
                    match_mask = data["LobbyNameNorm"].isin(close_set)
                for short in data.loc[match_mask, "LobbyShort"].dropna().unique().tolist():
                    scores[short] = max(scores.get(short, 0), 60)

    if not scores:
        return "", []

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    top_score = ranked[0][1]
    top = [short for short, score in ranked if score == top_score]
    suggestions = [_candidate_label(short, short_to_names) for short, _ in ranked][:10]
    if len(top) == 1 and top_score >= 90:
        return top[0], suggestions
    return "", suggestions


def resolve_lobbyshort_from_wit(user_text: str, wit_all: pd.DataFrame, session_val: str | None) -> tuple[str, list[str]]:
    query = (user_text or "").strip()
    if not query or wit_all.empty or "LobbyShort" not in wit_all.columns:
        return "", []

    data = wit_all
    if session_val is not None and "Session" in data.columns:
        data = data[data["Session"].astype(str).str.strip() == str(session_val)]
    if data.empty:
        return "", []

    data = data[data["LobbyShort"].notna() & (data["LobbyShort"].astype(str).str.strip() != "")]
    if data.empty:
        return "", []

    if "LobbyShortNorm" not in data.columns:
        data = data.copy()
        data["LobbyShortNorm"] = norm_name_series(data["LobbyShort"])
    query_norms = {variant for variant in norm_person_variants_with_nicknames(query) if variant}
    query_norm = norm_name(query)
    if query_norm:
        query_norms.add(query_norm)
    if not query_norms:
        return "", []

    scores: dict[str, int] = {}
    prefix_mask = pd.Series(False, index=data.index)
    for variant in query_norms:
        prefix_mask = prefix_mask | data["LobbyShortNorm"].str.startswith(variant, na=False)
    for short in data.loc[prefix_mask, "LobbyShort"].dropna().unique().tolist():
        scores[short] = max(scores.get(short, 0), 90)

    contains_mask = pd.Series(False, index=data.index)
    for variant in query_norms:
        contains_mask = contains_mask | data["LobbyShortNorm"].str.contains(variant, na=False)
    for short in data.loc[contains_mask, "LobbyShort"].dropna().unique().tolist():
        scores[short] = max(scores.get(short, 0), 70)

    if "NameNorm" in data.columns or "name" in data.columns:
        name_norm = data.get("NameNorm", data["name"].fillna("").astype(str).map(norm_name))
        name_prefix = pd.Series(False, index=data.index)
        name_contains = pd.Series(False, index=data.index)
        for variant in query_norms:
            name_prefix = name_prefix | name_norm.str.startswith(variant, na=False)
            name_contains = name_contains | name_norm.str.contains(variant, na=False)
        for short in data.loc[name_prefix, "LobbyShort"].dropna().unique().tolist():
            scores[short] = max(scores.get(short, 0), 80)
        for short in data.loc[name_contains, "LobbyShort"].dropna().unique().tolist():
            scores[short] = max(scores.get(short, 0), 60)

    if not scores:
        return "", []

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    top_score = ranked[0][1]
    top = [short for short, score in ranked if score == top_score]
    if len(top) == 1 and top_score >= 90:
        return top[0], []
    suggestions = [short for short, _ in ranked][:10]
    return "", suggestions


def lobbyist_autocomplete_candidates(query: str, lobbyist_index: pd.DataFrame, limit: int = 12) -> list[dict[str, Any]]:
    search = (query or "").strip()
    if not search or lobbyist_index.empty:
        return []

    query_norm = norm_name(search)
    query_variants = {variant for variant in norm_person_variants_with_nicknames(search) if variant}
    if query_norm:
        query_variants.add(query_norm)

    info = parse_person_name(search)
    query_first = info.get("first_norm", "")
    query_last = info.get("last_norm", "")
    query_initial = info.get("first_initial", "")
    query_first_variants = _nickname_variants(query_first) if query_first else set()

    data = lobbyist_index
    scores = pd.Series(0, index=data.index, dtype="int16")

    def apply_score(mask: pd.Series, value: int) -> None:
        if mask.any():
            scores.loc[mask] = scores.loc[mask].clip(lower=value)

    if query_norm:
        apply_score(data["LobbyNameNorm"] == query_norm, 100)
        if "LobbyNameCleanNorm" in data.columns:
            apply_score(data["LobbyNameCleanNorm"] == query_norm, 100)
        apply_score(data["LobbyShortNorm"] == query_norm, 95)

    for variant in query_variants:
        if not variant:
            continue
        if "LobbyNameCleanNorm" in data.columns:
            apply_score(data["LobbyNameCleanNorm"] == variant, 98)
            apply_score(data["LobbyNameCleanNorm"].str.startswith(variant, na=False), 94)
            if len(variant) >= 3:
                apply_score(data["LobbyNameCleanNorm"].str.contains(variant, na=False), 80)
        apply_score(data["LobbyNameNorm"] == variant, 97)
        apply_score(data["LobbyNameNorm"].str.startswith(variant, na=False), 93)
        if len(variant) >= 3:
            apply_score(data["LobbyNameNorm"].str.contains(variant, na=False), 78)
            apply_score(data["LobbyShortNorm"].str.startswith(variant, na=False), 85)
            apply_score(data["LobbyShortNorm"].str.contains(variant, na=False), 65)
        if "LastFirstNorm" in data.columns:
            apply_score(data["LastFirstNorm"] == variant, 98)
            apply_score(data["FirstLastNorm"] == variant, 98)
        if "LastFirstInitialNorm" in data.columns:
            apply_score(data["LastFirstInitialNorm"] == variant, 88)

    if query_last:
        apply_score(data["LastNorm"] == query_last, 75)
        if query_first:
            apply_score((data["LastNorm"] == query_last) & (data["FirstNorm"] == query_first), 97)
            if query_first_variants:
                apply_score((data["LastNorm"] == query_last) & (data["FirstNorm"].isin(query_first_variants)), 95)
            apply_score((data["LastNorm"] == query_last) & (data["FirstNorm"].str.startswith(query_first, na=False)), 90)
        if query_initial:
            apply_score((data["LastNorm"] == query_last) & (data["FirstInitial"] == query_initial), 86)

    if query_norm and len(query_norm) >= 3:
        name_norms = data.get("LobbyNameCleanNorm", data.get("LobbyNameNorm", pd.Series(dtype=object))).dropna().unique().tolist()
        close = difflib.get_close_matches(query_norm, name_norms, n=8, cutoff=0.78)
        if close:
            if "LobbyNameCleanNorm" in data.columns:
                apply_score(data["LobbyNameCleanNorm"].isin(close), 70)
            else:
                apply_score(data["LobbyNameNorm"].isin(close), 70)

    hit = scores > 0
    if not hit.any():
        return []

    hit_rows = data.loc[hit].assign(Score=scores.loc[hit])
    hit_rows = hit_rows.sort_values(["Score", "Lobby Name", "LobbyShort"], ascending=[False, True, True])
    out = []
    for record in hit_rows.head(limit).to_dict("records"):
        out.append(
            {
                "label": format_lobbyist_label(record.get("Lobby Name", ""), record.get("LobbyShort", ""), record.get("FilerID", None)),
                "lobbyshort": record.get("LobbyShort", ""),
                "filerid": record.get("FilerID", None),
                "name": record.get("Lobby Name", ""),
                "score": int(record.get("Score", 0)),
            }
        )
    return out


def normalize_bill(text: str) -> str:
    value = (text or "").strip().upper()
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value)
    match = re.search(r"\b(HB|SB|HR|SR|HCR|SCR)\s*(\d+)\b", value)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return ""


def is_bill_query(text: str) -> bool:
    return bool(normalize_bill(text))


def _resolve_top_lobby_candidate(query: str, lobby_candidates: list[dict]) -> tuple[str, int | None, str]:
    if not lobby_candidates:
        return "", None, ""
    query_info = parse_person_name(query)
    query_first = query_info.get("first_norm", "")
    query_last = query_info.get("last_norm", "")
    query_full = bool(query_first and query_last and len(query_first) >= 2 and len(query_last) >= 2)
    top = lobby_candidates[0]
    top_score = top.get("score", 0)
    if top_score >= 95 or (top_score >= 92 and query_full):
        filer_id = top.get("filerid", None)
        try:
            filer_id = int(filer_id) if pd.notna(filer_id) else None
        except Exception:
            pass
        return str(top.get("lobbyshort", "")), filer_id, str(top.get("name", ""))
    return "", None, ""


def build_nav_search_bundle(query: str, app_state: AppState) -> NavSearchBundle:
    search = (query or "").strip()
    normalized_query = norm_name(search)
    bill_query = normalize_bill(search)
    if not search:
        return NavSearchBundle("", "", "", (), (), (), (), (), {})

    if bill_query:
        return NavSearchBundle(search, normalized_query, bill_query, (), (), (), (), (), {})

    resolved_client, client_suggestions = resolve_client_name(search, app_state.client_index)
    resolved_member, member_suggestions = resolve_member_name(search, app_state.member_index)
    lobby_candidates = lobbyist_autocomplete_candidates(search, app_state.lobbyist_index)
    resolved_lobby = ""
    resolved_lobby_filer = None
    resolved_lobby_name = ""
    lobby_suggestions: list[str] = []
    if lobby_candidates:
        resolved_lobby, resolved_lobby_filer, resolved_lobby_name = _resolve_top_lobby_candidate(search, lobby_candidates)
    else:
        resolved_lobby, lobby_suggestions = resolve_lobbyshort(
            search,
            app_state.lobby_index,
            app_state.name_to_short,
            app_state.known_shorts,
            app_state.short_to_names,
        )

    nav_suggestions: list[str] = []
    nav_suggestion_map: dict[str, tuple[str, Any]] = {}
    for suggestion in client_suggestions:
        label = f"Client: {suggestion}"
        nav_suggestions.append(label)
        nav_suggestion_map[label] = ("client", suggestion)
    for suggestion in member_suggestions:
        label = f"Legislator: {suggestion}"
        nav_suggestions.append(label)
        nav_suggestion_map[label] = ("member", suggestion)
    if lobby_candidates:
        for candidate in lobby_candidates[:10]:
            label = f"Lobbyist: {candidate['label']}"
            nav_suggestions.append(label)
            nav_suggestion_map[label] = ("lobbyist", candidate)
    else:
        for suggestion in lobby_suggestions:
            short_code = suggestion.split(" - ")[0]
            label = f"Lobbyist: {suggestion}"
            nav_suggestions.append(label)
            nav_suggestion_map[label] = (
                "lobbyist",
                {"lobbyshort": short_code, "name": short_code, "label": suggestion, "filerid": None},
            )

    return NavSearchBundle(
        query=search,
        normalized_query=normalized_query,
        bill_query=bill_query,
        client_suggestions=tuple(client_suggestions),
        member_suggestions=tuple(member_suggestions),
        lobby_candidates=tuple(dict(candidate) for candidate in lobby_candidates),
        lobby_suggestions=tuple(lobby_suggestions),
        nav_suggestions=tuple(nav_suggestions),
        nav_suggestion_map=nav_suggestion_map,
        resolved_client=resolved_client,
        resolved_member=resolved_member,
        resolved_lobby=resolved_lobby,
        resolved_lobby_filer=resolved_lobby_filer,
        resolved_lobby_name=resolved_lobby_name,
    )


def _build_nav_search_bundle_uncached(query: str, app_state: AppState) -> NavSearchBundle:
    return build_nav_search_bundle(query, app_state)


@st.cache_data(
    show_spinner=False,
    ttl=300,
    max_entries=64,
    hash_funcs={AppState: lambda state: f"{state.path}|{state.data_version}", NavQueryKey: lambda key: norm_name(key.raw)},
)
def build_nav_search_bundle_cached(query_key: NavQueryKey, app_state: AppState) -> NavSearchBundle:
    return _build_nav_search_bundle_uncached(str(query_key.raw or ""), app_state)


def can_reuse_nav_search_bundle(query: str, bundle: NavSearchBundle | None) -> bool:
    if not isinstance(bundle, NavSearchBundle):
        return False
    return bundle.normalized_query == norm_name(query)


__all__ = [
    "build_nav_search_bundle",
    "build_nav_search_bundle_cached",
    "can_reuse_nav_search_bundle",
    "format_lobbyist_label",
    "is_bill_query",
    "lobby_candidate_key",
    "lobbyist_autocomplete_candidates",
    "normalize_bill",
    "resolve_client_name",
    "resolve_lobbyshort",
    "resolve_lobbyshort_from_wit",
    "resolve_member_name",
]
