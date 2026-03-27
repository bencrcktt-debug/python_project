from __future__ import annotations

from dataclasses import dataclass
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

_RE_NONWORD = re.compile(r"[^\w]+", flags=re.UNICODE)
_RE_WHITESPACE = re.compile(r"\s+")
_RE_PARENS = re.compile(r"\([^)]*\)")
_TITLE_WORDS = {"MR", "MRS", "MS", "MISS", "DR", "HON", "JR", "SR", "II", "III", "IV"}
_RE_TITLE_WORDS = re.compile(r"\b(" + "|".join(_TITLE_WORDS) + r")\b\.?", re.IGNORECASE)
_NICKNAME_MAP = {
    "CHUCK": {"CHARLES"},
    "CHARLIE": {"CHARLES"},
    "CHARLES": {"CHUCK", "CHARLIE"},
}


@dataclass(frozen=True)
class AppState:
    path: str
    data: dict[str, object]
    tables: dict[str, pd.DataFrame]
    table_manifest: dict[str, dict[str, Any]]
    client_index: pd.DataFrame
    author_bills_all: pd.DataFrame
    member_index: pd.DataFrame
    lobby_index: pd.DataFrame
    lobbyist_index: pd.DataFrame
    name_to_short: dict[str, str]
    short_to_names: dict[str, list[str]]
    known_shorts: frozenset[str]
    filerid_to_short: dict[int, str]
    shared_sessions: tuple[str, ...]
    default_shared_session: str | None
    map_sessions: tuple[str, ...]
    default_map_session: str | None
    tfl_sessions: frozenset[str]


@dataclass(frozen=True)
class NavSearchBundle:
    query: str
    normalized_query: str
    bill_query: str
    client_suggestions: tuple[str, ...]
    member_suggestions: tuple[str, ...]
    lobby_candidates: tuple[dict[str, Any], ...]
    lobby_suggestions: tuple[str, ...]
    nav_suggestions: tuple[str, ...]
    nav_suggestion_map: dict[str, tuple[str, Any]]
    resolved_client: str = ""
    resolved_member: str = ""
    resolved_lobby: str = ""
    resolved_lobby_filer: int | None = None
    resolved_lobby_name: str = ""


@dataclass(frozen=True)
class NavQueryKey:
    raw: str


def norm_name(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x).replace("\u00A0", " ").strip().upper()
    return _RE_NONWORD.sub("", s)


def norm_name_series(s: pd.Series) -> pd.Series:
    return (
        s.fillna("")
        .astype(str)
        .str.replace("\u00A0", " ", regex=False)
        .str.strip()
        .str.upper()
        .str.replace(_RE_NONWORD, "", regex=True)
    )


def clean_filer_name_series(s: pd.Series) -> pd.Series:
    cleaned = s.fillna("").astype(str)
    cleaned = cleaned.str.replace(_RE_PARENS, "", regex=True)
    cleaned = cleaned.str.replace(_RE_TITLE_WORDS, "", regex=True)
    cleaned = cleaned.str.replace(_RE_WHITESPACE, " ", regex=True).str.strip()
    return cleaned


def clean_person_name(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).replace("\u00A0", " ").strip()
    if not s:
        return ""
    s = _RE_PARENS.sub("", s)
    s = _RE_TITLE_WORDS.sub("", s)
    s = _RE_WHITESPACE.sub(" ", s).strip()
    return s


def last_name_norm_series(s: pd.Series) -> pd.Series:
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0] if s.shape[1] > 0 else pd.Series([], dtype="string")
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    s = (
        s.fillna("")
        .astype("string")
        .str.replace("\u00A0", " ", regex=False)
        .str.strip()
    )
    comma_mask = s.str.contains(",", na=False)
    last_from_comma = (
        s.where(comma_mask, "")
        .astype("string")
        .str.split(",", n=1)
        .str[0]
        .astype("string")
        .str.strip()
    )
    last_from_space = (
        s.where(~comma_mask, "")
        .astype("string")
        .str.split()
        .str[-1]
        .fillna("")
        .astype("string")
        .str.strip()
    )
    last = last_from_comma.where(comma_mask, last_from_space).fillna("")
    return norm_name_series(last)


def first_name_norm_series(s: pd.Series) -> pd.Series:
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0] if s.shape[1] > 0 else pd.Series([], dtype="string")
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    s = (
        s.fillna("")
        .astype("string")
        .str.replace("\u00A0", " ", regex=False)
        .str.strip()
    )
    comma_mask = s.str.contains(",", na=False)
    first_from_comma = (
        s.where(comma_mask, "")
        .astype("string")
        .str.split(",", n=1)
        .str[1]
        .fillna("")
        .astype("string")
        .str.strip()
        .str.split()
        .str[0]
        .fillna("")
        .astype("string")
        .str.strip()
    )
    first_from_space = (
        s.where(~comma_mask, "")
        .astype("string")
        .str.split()
        .str[0]
        .fillna("")
        .astype("string")
        .str.strip()
    )
    first = first_from_comma.where(comma_mask, first_from_space).fillna("")
    return norm_name_series(first)


def _last_first_initial_key(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).replace("\u00A0", " ").strip()
    if not s:
        return ""
    if "," in s:
        last, rest = [p.strip() for p in s.split(",", 1)]
        first = rest
    else:
        tokens = s.split()
        if len(tokens) < 2:
            return ""
        first, last = tokens[0], tokens[-1]
    initial = ""
    for char in first:
        if char.isalnum():
            initial = char
            break
    if not last or not initial:
        return ""
    return norm_name(f"{last} {initial}")


def norm_person_variants(user_text: str) -> set[str]:
    if not user_text:
        return set()
    text = clean_person_name(user_text)
    if not text:
        return set()

    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        last = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        first = rest.split()[0].strip() if rest else ""
    else:
        tokens = text.split()
        if len(tokens) == 1:
            first, last = "", tokens[0]
        else:
            first, last = tokens[0], tokens[-1]

    variants = {norm_name(text)}
    raw_norm = norm_name(user_text)
    if raw_norm:
        variants.add(raw_norm)
    if first and last:
        variants |= {
            norm_name(f"{first} {last}"),
            norm_name(f"{last}, {first}"),
            norm_name(f"{last} {first}"),
            norm_name(f"{first}{last}"),
            norm_name(f"{last}{first}"),
        }
    return {variant for variant in variants if variant}


def _nickname_variants(first_norm: str) -> set[str]:
    if not first_norm:
        return set()
    variants = {first_norm}
    if first_norm in _NICKNAME_MAP:
        variants |= _NICKNAME_MAP[first_norm]
    for base, nicknames in _NICKNAME_MAP.items():
        if first_norm in nicknames:
            variants.add(base)
            variants |= nicknames
    return {variant for variant in variants if variant}


def norm_person_variants_with_nicknames(user_text: str) -> set[str]:
    variants = norm_person_variants(user_text)
    if not user_text:
        return variants
    text = clean_person_name(user_text)
    if not text:
        return variants

    def add_nickname_variants(first_value: str, last_value: str) -> None:
        first_norm = norm_name(first_value)
        last_norm = norm_name(last_value)
        if not first_norm or not last_norm:
            return
        for nickname in _nickname_variants(first_norm):
            if nickname == first_norm:
                continue
            variants.add(f"{nickname}{last_norm}")
            variants.add(f"{last_norm}{nickname}")

    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        last = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        first = rest.split()[0].strip() if rest else ""
        add_nickname_variants(first, last)
    else:
        tokens = text.split()
        if len(tokens) < 2:
            return variants
        first, last = tokens[0], tokens[-1]
        add_nickname_variants(first, last)
        if len(tokens) == 2:
            add_nickname_variants(last, first)
    return {variant for variant in variants if variant}


def parse_member_name(member_name: str) -> dict:
    text = clean_person_name(member_name)
    if not text:
        return {"full_norm": "", "last_norm": "", "first_norm": "", "first_initial": "", "initial_key": ""}

    if "," in text:
        last, rest = [part.strip() for part in text.split(",", 1)]
        first = rest.split()[0].strip() if rest else ""
    else:
        tokens = text.split()
        if len(tokens) == 1:
            first, last = "", tokens[0]
        else:
            first, last = tokens[0], tokens[-1]

    first_norm = norm_name(first)
    last_norm = norm_name(last)
    first_initial = norm_name(first[0]) if first else ""
    initial_key = _last_first_initial_key(text)
    return {
        "full_norm": norm_name(text),
        "last_norm": last_norm,
        "first_norm": first_norm,
        "first_initial": first_initial,
        "initial_key": initial_key,
    }


def parse_person_name(person_name: str) -> dict:
    return parse_member_name(person_name)


def _candidate_label(short_code: str, short_to_names: dict) -> str:
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


def lobby_candidate_key(candidate: dict) -> str:
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


def build_client_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Client" not in df.columns:
        return pd.DataFrame(columns=["Client", "ClientNorm"])
    base = df[["Client"]].dropna().copy()
    base["Client"] = base["Client"].astype(str).str.strip()
    base = base[base["Client"] != ""].drop_duplicates()
    base["ClientNorm"] = base["Client"].map(norm_name)
    base = base[base["ClientNorm"] != ""].drop_duplicates()
    return base


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


def _split_authors(text: str) -> list[str]:
    if text is None:
        return []
    value = str(text).strip()
    if not value or value.lower() in {"nan", "none"}:
        return []
    parts = [part.strip() for part in value.split("|")]
    return [part for part in parts if part and part.lower() not in {"nan", "none"}]


def build_author_bill_index(bs: pd.DataFrame) -> pd.DataFrame:
    if bs.empty:
        return pd.DataFrame(columns=["Session", "Bill", "Author", "AuthorNorm", "Status", "Caption", "Link", "Chamber"])

    author_col = "Author" if "Author" in bs.columns else "Authors"
    if author_col not in bs.columns:
        return pd.DataFrame(columns=["Session", "Bill", "Author", "AuthorNorm", "Status", "Caption", "Link", "Chamber"])

    data = bs.copy()
    data["AuthorRaw"] = data[author_col].fillna("").astype(str)
    data["AuthorList"] = data["AuthorRaw"].map(_split_authors)
    data = data.explode("AuthorList")
    data["Author"] = data["AuthorList"].fillna("").astype(str).str.strip()
    data = data[data["Author"].astype(str).str.strip() != ""]
    data["AuthorNorm"] = data["Author"].map(norm_name)

    cols = [column for column in ["Session", "Bill", "Author", "AuthorNorm", "Status", "Caption", "Link", "Chamber"] if column in data.columns]
    return data[cols].drop_duplicates()


def build_member_index(author_bills: pd.DataFrame) -> pd.DataFrame:
    if author_bills.empty or "Author" not in author_bills.columns:
        return pd.DataFrame(columns=["Member", "MemberNorm"])
    base = author_bills[["Author", "AuthorNorm"]].dropna().copy()
    base = base.rename(columns={"Author": "Member", "AuthorNorm": "MemberNorm"})
    base = base[base["Member"].astype(str).str.strip() != ""].drop_duplicates()
    return base


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


def build_lobbyist_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "LobbyShort" not in df.columns or "Lobby Name" not in df.columns:
        return pd.DataFrame(
            columns=[
                "LobbyShort",
                "LobbyShortNorm",
                "Lobby Name",
                "LobbyNameNorm",
                "LobbyNameClean",
                "LobbyNameCleanNorm",
                "FirstNorm",
                "LastNorm",
                "FirstInitial",
                "FirstLastNorm",
                "LastFirstNorm",
                "LastFirstInitialNorm",
                "FilerID",
            ]
        )

    base = df[["LobbyShort", "Lobby Name", "FilerID"]].dropna(subset=["LobbyShort", "Lobby Name"]).copy()
    base["LobbyShort"] = base["LobbyShort"].astype(str).str.strip()
    base["Lobby Name"] = base["Lobby Name"].astype(str).str.strip()
    base = base[(base["LobbyShort"] != "") & (base["Lobby Name"] != "")]
    base = base.drop_duplicates()
    base["FilerID"] = pd.to_numeric(base["FilerID"], errors="coerce")
    base["LobbyShortNorm"] = base["LobbyShort"].map(norm_name)
    base["LobbyNameNorm"] = base["Lobby Name"].map(norm_name)
    base["LobbyNameClean"] = clean_filer_name_series(base["Lobby Name"])
    base["LobbyNameClean"] = base["LobbyNameClean"].where(base["LobbyNameClean"] != "", base["Lobby Name"])
    base["LobbyNameCleanNorm"] = norm_name_series(base["LobbyNameClean"])

    parsed = base["LobbyNameClean"].map(parse_person_name)
    base["FirstNorm"] = parsed.map(lambda payload: payload.get("first_norm", "")).fillna("")
    base["LastNorm"] = parsed.map(lambda payload: payload.get("last_norm", "")).fillna("")
    base["FirstInitial"] = parsed.map(lambda payload: payload.get("first_initial", "")).fillna("")
    base["FirstLastNorm"] = (base["FirstNorm"] + base["LastNorm"]).where((base["FirstNorm"] != "") & (base["LastNorm"] != ""), "")
    base["LastFirstNorm"] = (base["LastNorm"] + base["FirstNorm"]).where((base["FirstNorm"] != "") & (base["LastNorm"] != ""), "")
    base["LastFirstInitialNorm"] = (base["LastNorm"] + base["FirstInitial"]).where((base["LastNorm"] != "") & (base["FirstInitial"] != ""), "")
    return base


def _build_filerid_map(frames: list[tuple[pd.DataFrame, str, str]]) -> dict[int, str]:
    rows = []
    for df, fid_col, short_col in frames:
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        if fid_col not in df.columns or short_col not in df.columns:
            continue
        fid = pd.to_numeric(df[fid_col], errors="coerce")
        if fid.isna().all():
            continue
        short = df[short_col].fillna("").astype(str).str.strip()
        tmp = pd.DataFrame({"FilerID": fid, "LobbyShort": short})
        tmp = tmp.dropna(subset=["FilerID"])
        tmp["FilerID"] = tmp["FilerID"].astype(int)
        tmp = tmp[tmp["LobbyShort"].astype(str).str.strip() != ""]
        if not tmp.empty:
            rows.append(tmp)
    if not rows:
        return {}
    all_rows = pd.concat(rows, ignore_index=True)
    counts = (
        all_rows.groupby(["FilerID", "LobbyShort"])
        .size()
        .reset_index(name="n")
        .sort_values(["FilerID", "n"], ascending=[True, False])
        .drop_duplicates("FilerID")
    )
    return dict(zip(counts["FilerID"], counts["LobbyShort"]))


def _fill_missing_witness_lobbyshorts(
    wit_all: pd.DataFrame,
    *,
    name_to_short: dict[str, str],
) -> pd.DataFrame:
    if wit_all.empty:
        return wit_all

    data = wit_all.copy()
    if "LobbyShort" not in data.columns:
        data["LobbyShort"] = ""

    lobby_short = data["LobbyShort"].fillna("").astype(str).str.strip()
    blank_mask = lobby_short.eq("")
    if blank_mask.any() and name_to_short:
        blank_index = data.index[blank_mask]
        mapped = pd.Series("", index=blank_index, dtype="object")

        if "name" in data.columns:
            name_norm = norm_name_series(data.loc[blank_index, "name"].fillna("").astype(str))
            mapped = name_norm.map(name_to_short).fillna("")

        if "org" in data.columns:
            needs_org = mapped.astype(str).str.strip().eq("")
            if needs_org.any():
                org_index = mapped.index[needs_org]
                org_norm = norm_name_series(data.loc[org_index, "org"].fillna("").astype(str))
                mapped.loc[org_index] = org_norm.map(name_to_short).fillna("")

        data.loc[blank_index, "LobbyShort"] = mapped.fillna("")

    if "LobbyShortNorm" not in data.columns:
        data["LobbyShortNorm"] = norm_name_series(data["LobbyShort"])
    return data


def _derive_lobby_lookup_state(data: dict[str, object]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str], dict[str, list[str]], frozenset[str], dict[int, str]]:
    lobby_name_rows: list[pd.DataFrame] = []

    def _append_lobby_names(df: pd.DataFrame, name_col: str, short_col: str, fid_col: str) -> None:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return
        if name_col not in df.columns or short_col not in df.columns:
            return
        tmp = df[[name_col, short_col]].copy()
        tmp = tmp.rename(columns={name_col: "Lobby Name", short_col: "LobbyShort"})
        tmp["FilerID"] = df[fid_col] if fid_col in df.columns else pd.NA
        lobby_name_rows.append(tmp)

    _append_lobby_names(_dataframe_or_empty(data.get("Lobby_TFL_Client_All")), "Lobby Name", "LobbyShort", "FilerID")
    _append_lobby_names(_dataframe_or_empty(data.get("Lobby_Sub_All")), "Lobby Name", "LobbyShort", "FilerID")
    _append_lobby_names(_dataframe_or_empty(data.get("Lobbyist_Pol_Funds")), "Lobbyist", "LobbyShort", "FilerID")

    if lobby_name_rows:
        lobby_names = pd.concat(lobby_name_rows, ignore_index=True)
        lobby_names["LobbyShort"] = lobby_names["LobbyShort"].astype(str).str.strip()
        lobby_names["Lobby Name"] = lobby_names["Lobby Name"].astype(str).str.strip()
        lobby_names = lobby_names[(lobby_names["LobbyShort"] != "") & (lobby_names["Lobby Name"] != "")]
        lobby_names = lobby_names.drop_duplicates()
    else:
        lobby_names = pd.DataFrame(columns=["LobbyShort", "Lobby Name", "FilerID"])

    lobbyist_index = build_lobbyist_index(lobby_names)
    lobby_index = lobbyist_index.copy()
    name_to_short: dict[str, str] = {}
    short_to_names: dict[str, list[str]] = {}
    known_shorts: frozenset[str] = frozenset()
    initial_to_short: dict[str, str] = {}

    if not lobbyist_index.empty:
        known_shorts = frozenset(
            lobbyist_index["LobbyShort"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        tmp = lobbyist_index[["LobbyShort", "Lobby Name"]].dropna().copy()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str)
        short_to_names = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .agg(lambda values: sorted(set(map(str, values)))[:6])
            .to_dict()
        )

        key_frames = []
        for col in ["LobbyNameNorm", "LobbyNameCleanNorm", "LastFirstNorm", "FirstLastNorm", "LastFirstInitialNorm"]:
            if col in lobbyist_index.columns:
                key_frames.append(lobbyist_index[[col, "LobbyShort"]].rename(columns={col: "Key"}))
        if key_frames:
            all_keys = pd.concat(key_frames, ignore_index=True)
            all_keys["Key"] = all_keys["Key"].fillna("").astype(str).str.strip()
            all_keys = all_keys[all_keys["Key"] != ""]
            counts = (
                all_keys.groupby(["Key", "LobbyShort"])
                .size()
                .reset_index(name="n")
                .sort_values(["Key", "n"], ascending=[True, False])
                .drop_duplicates("Key")
            )
            name_to_short = dict(zip(counts["Key"], counts["LobbyShort"]))

        tmp_short = lobbyist_index[["LobbyShort"]].dropna().copy()
        tmp_short["InitialKey"] = tmp_short["LobbyShort"].map(_last_first_initial_key)
        tmp_short = tmp_short[tmp_short["InitialKey"].astype(str).str.strip() != ""]
        if not tmp_short.empty:
            init_counts = (
                tmp_short.groupby(["InitialKey", "LobbyShort"])
                .size()
                .reset_index(name="n")
                .sort_values(["InitialKey", "n"], ascending=[True, False])
                .drop_duplicates("InitialKey")
            )
            initial_to_short = dict(zip(init_counts["InitialKey"], init_counts["LobbyShort"]))

    filerid_to_short = _build_filerid_map(
        [
            (_dataframe_or_empty(data.get("Lobby_TFL_Client_All")), "FilerID", "LobbyShort"),
            (_dataframe_or_empty(data.get("Lobby_Sub_All")), "FilerID", "LobbyShort"),
            (_dataframe_or_empty(data.get("Lobbyist_Pol_Funds")), "FilerID", "LobbyShort"),
        ]
    )

    wit = _dataframe_or_empty(data.get("Wit_All"))
    if not wit.empty:
        data["Wit_All"] = _fill_missing_witness_lobbyshorts(
            wit,
            name_to_short=name_to_short,
        )

    for key in ["Lobby_TFL_Client_All", "Lobby_Sub_All"]:
        df = _dataframe_or_empty(data.get(key))
        if not df.empty and "LobbyShort" in df.columns:
            df = df.copy()
            df["LobbyShortNorm"] = norm_name_series(df["LobbyShort"])
            data[key] = df

    ls = _dataframe_or_empty(data.get("Lobby_Sub_All"))
    if not ls.empty and filerid_to_short and "FilerID" in ls.columns and "LobbyShort" in ls.columns:
        ls = ls.copy()
        fid = pd.to_numeric(ls["FilerID"], errors="coerce").fillna(-1).astype(int)
        missing = ls["LobbyShort"].isna() | ls["LobbyShort"].astype(str).str.strip().eq("")
        ls.loc[missing, "LobbyShort"] = fid.map(filerid_to_short)
        data["Lobby_Sub_All"] = ls

    data["name_to_short"] = name_to_short
    data["short_to_names"] = short_to_names
    data["lobby_index"] = lobby_index
    data["lobbyist_index"] = lobbyist_index
    data["known_shorts"] = known_shorts
    data["filerid_to_short"] = filerid_to_short
    return lobby_index, lobbyist_index, name_to_short, short_to_names, known_shorts, filerid_to_short


def resolve_lobbyshort(
    user_text: str,
    lobby_index: pd.DataFrame,
    name_to_short: dict,
    known_shorts: set[str] | frozenset[str],
    short_to_names: dict,
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


def lobbyist_autocomplete_candidates(query: str, lobbyist_index: pd.DataFrame, limit: int = 12) -> list[dict]:
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
        label = format_lobbyist_label(record.get("Lobby Name", ""), record.get("LobbyShort", ""), record.get("FilerID", None))
        out.append(
            {
                "label": label,
                "lobbyshort": record.get("LobbyShort", ""),
                "filerid": record.get("FilerID", None),
                "name": record.get("Lobby Name", ""),
                "score": int(record.get("Score", 0)),
            }
        )
    return out


def normalize_bill(query: str) -> str:
    text = (query or "").strip().upper()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    match = re.search(r"\b(HB|SB|HR|SR|HCR|SCR)\s*(\d+)\b", text)
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2)}"


def is_bill_query(query: str) -> bool:
    return bool(normalize_bill(query))


def _session_sort_key(session_val: str) -> tuple[int, int, int]:
    value = str(session_val).strip()
    if not value:
        return (0, 2, 0)
    if value.isdigit():
        base = int(value[:-1]) if len(value) >= 2 else int(value)
        special = int(value[-1]) if len(value) >= 2 else 0
        return (base, 1, special)
    match = re.match(r"^(\d+)\s*R$", value, flags=re.IGNORECASE)
    if match:
        return (int(match.group(1)), 0, 0)
    return (0, 2, 0)


def _default_session_from_list(sessions: list[str]) -> str:
    if not sessions:
        return ""
    if "89R" in sessions:
        return "89R"
    regular = [session for session in sessions if str(session).strip().upper().endswith("R") and str(session).strip()[:-1].isdigit()]
    if regular:
        return sorted(regular, key=_session_sort_key)[-1]
    return sorted(sessions, key=_session_sort_key)[-1]


def _dataframe_or_empty(value) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    return pd.DataFrame()


def _ensure_session_key_column(df: pd.DataFrame, *, source_column: str | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    if "SessionKey" in df.columns:
        return df
    candidates = [source_column] if source_column else ["Session", "session"]
    for column in candidates:
        if column and column in df.columns:
            data = df.copy()
            data["SessionKey"] = data[column].fillna("").astype(str).str.strip()
            return data
    return df


def _ensure_lobby_client_lookup_columns(lobby_tfl_client_all: pd.DataFrame) -> pd.DataFrame:
    if lobby_tfl_client_all.empty:
        return lobby_tfl_client_all

    required = {"SessionKey", "ClientNorm", "LobbyShortNorm", "Low_num", "High_num"}
    if required.issubset(set(lobby_tfl_client_all.columns)):
        return lobby_tfl_client_all

    data = lobby_tfl_client_all.copy()
    if "Session" in data.columns:
        data["Session"] = data["Session"].fillna("").astype(str).str.strip()
        data["SessionKey"] = data["Session"]
    elif "session" in data.columns:
        data["SessionKey"] = data["session"].fillna("").astype(str).str.strip()

    if "Client" in data.columns:
        data["Client"] = data["Client"].fillna("").astype(str).str.strip()
        data["ClientNorm"] = norm_name_series(data["Client"])
    if "LobbyShort" in data.columns:
        data["LobbyShort"] = data["LobbyShort"].fillna("").astype(str).str.strip()
        data["LobbyShortNorm"] = norm_name_series(data["LobbyShort"])
    if "Lobby Name" in data.columns:
        data["Lobby Name"] = data["Lobby Name"].fillna("").astype(str).str.strip()
    if "IsTFL" in data.columns:
        data["IsTFL"] = pd.to_numeric(data["IsTFL"], errors="coerce").fillna(0).astype(int)

    if "Low_num" in data.columns:
        data["Low_num"] = pd.to_numeric(data["Low_num"], errors="coerce").fillna(0.0)
    elif "Low" in data.columns:
        data["Low_num"] = pd.to_numeric(data["Low"], errors="coerce").fillna(0.0)
    if "High_num" in data.columns:
        data["High_num"] = pd.to_numeric(data["High_num"], errors="coerce").fillna(0.0)
    elif "High" in data.columns:
        data["High_num"] = pd.to_numeric(data["High"], errors="coerce").fillna(0.0)
    return data


def _clean_sessions(*series_list: pd.Series) -> tuple[str, ...]:
    if not series_list:
        return ()
    session_values = pd.concat(list(series_list), ignore_index=True).dropna().astype(str).str.strip().unique().tolist()
    clean = [value for value in session_values if value and value.lower() not in {"none", "nan", "null"}]
    return tuple(sorted(clean, key=_session_sort_key))


def _ensure_witness_search_columns(wit_all: pd.DataFrame) -> pd.DataFrame:
    if wit_all.empty:
        return wit_all
    required = {"LobbyShortNorm", "NameNorm", "NameLastNorm", "NameFirstNorm", "NameFirstInitialNorm"}
    if required.issubset(set(wit_all.columns)):
        return wit_all

    data = wit_all.copy()
    if "LobbyShort" in data.columns and "LobbyShortNorm" not in data.columns:
        data["LobbyShortNorm"] = norm_name_series(data["LobbyShort"])
    if "name" in data.columns:
        name_series = data["name"].fillna("").astype(str)
        if "NameNorm" not in data.columns:
            data["NameNorm"] = norm_name_series(name_series)
        if "NameLastNorm" not in data.columns:
            data["NameLastNorm"] = last_name_norm_series(name_series)
        if "NameFirstNorm" not in data.columns:
            data["NameFirstNorm"] = first_name_norm_series(name_series)
        if "NameFirstInitialNorm" not in data.columns:
            first_norm = data["NameFirstNorm"] if "NameFirstNorm" in data.columns else first_name_norm_series(name_series)
            data["NameFirstInitialNorm"] = first_norm.str.slice(0, 1)
    return data


def _ensure_staff_search_columns(staff_all: pd.DataFrame) -> pd.DataFrame:
    if staff_all.empty or "Legislator" not in staff_all.columns:
        return staff_all
    required = {"LegislatorNorm", "LegislatorLastNorm", "LegislatorInitKey"}
    if required.issubset(set(staff_all.columns)):
        return staff_all

    data = staff_all.copy()
    if "LegislatorNorm" not in data.columns:
        data["LegislatorNorm"] = norm_name_series(data["Legislator"])
    if "LegislatorLastNorm" not in data.columns:
        data["LegislatorLastNorm"] = last_name_norm_series(data["Legislator"])
    if "LegislatorInitKey" not in data.columns:
        data["LegislatorInitKey"] = data["Legislator"].fillna("").astype(str).map(_last_first_initial_key)
    return data


def build_app_state(path: str, workbook: dict[str, object]) -> AppState:
    data = dict(workbook or {})
    raw_manifest = data.pop("table_manifest", data.pop("__table_manifest__", {}))
    table_manifest = {
        str(key): dict(value)
        for key, value in dict(raw_manifest or {}).items()
        if isinstance(value, dict)
    }

    data["Wit_All"] = _ensure_session_key_column(_dataframe_or_empty(data.get("Wit_All")))
    data["Bill_Status_All"] = _ensure_session_key_column(_dataframe_or_empty(data.get("Bill_Status_All")))
    data["Lobby_TFL_Client_All"] = _ensure_lobby_client_lookup_columns(_dataframe_or_empty(data.get("Lobby_TFL_Client_All")))
    data["Lobby_Sub_All"] = _ensure_session_key_column(_dataframe_or_empty(data.get("Lobby_Sub_All")))
    data["Lobbyist_Pol_Funds"] = _ensure_session_key_column(_dataframe_or_empty(data.get("Lobbyist_Pol_Funds")))
    data["Staff_All"] = _ensure_session_key_column(_ensure_staff_search_columns(_dataframe_or_empty(data.get("Staff_All"))))
    for key in (
        "Fiscal_Impact",
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
    ):
        if key in data:
            data[key] = _ensure_session_key_column(_dataframe_or_empty(data.get(key)))

    lobby_index, lobbyist_index, name_to_short, short_to_names, known_shorts, filerid_to_short = _derive_lobby_lookup_state(data)
    client_index = build_client_index(data["Lobby_TFL_Client_All"])
    author_bills_all = build_author_bill_index(data["Bill_Status_All"])
    member_index = build_member_index(author_bills_all)

    shared_sessions = _clean_sessions(
        data["Wit_All"].get("Session", pd.Series(dtype=object)),
        data["Lobby_TFL_Client_All"].get("Session", pd.Series(dtype=object)),
        data["Bill_Status_All"].get("Session", pd.Series(dtype=object)),
    )
    map_sessions = _clean_sessions(data["Lobby_TFL_Client_All"].get("Session", pd.Series(dtype=object)))
    default_shared_session = _default_session_from_list(list(shared_sessions)) if shared_sessions else None
    default_map_session = _default_session_from_list(list(map_sessions)) if map_sessions else None
    tfl_sessions = frozenset(
        data["Lobby_TFL_Client_All"]
        .get("Session", pd.Series(dtype=object))
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    data["client_index"] = client_index
    data["author_bills_all"] = author_bills_all
    data["member_index"] = member_index
    tables = {key: value for key, value in data.items() if isinstance(value, pd.DataFrame)}

    return AppState(
        path=path,
        data=data,
        tables=tables,
        table_manifest=table_manifest,
        client_index=client_index,
        author_bills_all=author_bills_all,
        member_index=member_index,
        lobby_index=lobby_index,
        lobbyist_index=lobbyist_index,
        name_to_short=name_to_short,
        short_to_names=short_to_names,
        known_shorts=known_shorts,
        filerid_to_short=filerid_to_short,
        shared_sessions=shared_sessions,
        default_shared_session=default_shared_session,
        map_sessions=map_sessions,
        default_map_session=default_map_session,
        tfl_sessions=tfl_sessions,
    )


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


@st.cache_data(show_spinner=False, ttl=300, max_entries=64, hash_funcs={AppState: lambda state: state.path, NavQueryKey: lambda key: norm_name(key.raw)})
def build_nav_search_bundle_cached(query_key: NavQueryKey, app_state: AppState) -> NavSearchBundle:
    return _build_nav_search_bundle_uncached(str(query_key.raw or ""), app_state)


def can_reuse_nav_search_bundle(query: str, bundle: NavSearchBundle | None) -> bool:
    if not isinstance(bundle, NavSearchBundle):
        return False
    return bundle.normalized_query == norm_name(query)
