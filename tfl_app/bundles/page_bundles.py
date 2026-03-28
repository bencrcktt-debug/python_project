from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping

import pandas as pd
try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - test fallback when Streamlit is unavailable
    class _CacheDataStub:
        def __call__(self, *decorator_args, **decorator_kwargs):
            def decorator(func):
                func.clear = lambda: None
                return func
            return decorator

    class _StreamlitStub:
        cache_data = _CacheDataStub()

    st = _StreamlitStub()

from tfl_app.search.state import (
    _last_first_initial_key,
    clean_filer_name_series,
    last_name_norm_series,
    norm_name,
    norm_name_series,
    parse_member_name,
)
from tfl_app.shared.dataframes import ensure_cols
from tfl_app.shared.formatting import fmt_usd
from tfl_app.shared.names import last_name_norm_from_text
from tfl_app.shared.sessions import ordinal as _ordinal
from tfl_app.shared.sessions import session_base_label as _session_base_label
from tfl_app.shared.sessions import session_base_number_series as _session_base_number_series
from tfl_app.shared.sessions import session_series as _session_series
from tfl_app.shared.series import (
    vectorized_amount_display as _vectorized_amount_display,
    vectorized_person_display as _vectorized_person_display,
)


def build_data_health_table(data: dict, source_labels: Mapping[str, str]) -> pd.DataFrame:
    order = [
        "Wit_All",
        "Bill_Status_All",
        "Fiscal_Impact",
        "Bill_Sub_All",
        "Lobby_Sub_All",
        "Lobby_TFL_Client_All",
        "Staff_All",
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
    ]
    rows: list[dict[str, Any]] = []
    for key in order:
        label = source_labels.get(key, key)
        value = data.get(key)
        if isinstance(value, dict):
            rows.append(
                {
                    "Source": label,
                    "Rows": int(value.get("rows", 0) or 0),
                    "Cols": int(value.get("cols", 0) or 0),
                    "Has Session": "Yes" if bool(value.get("has_session", False)) else "No",
                    "Empty": "Yes" if bool(value.get("empty", True)) else "No",
                    "Sessions": int(value.get("sessions", 0) or 0),
                    "Last name + first initial": int(value.get("lobby_count", 0) or 0),
                }
            )
            continue

        df = value
        if isinstance(df, pd.DataFrame):
            sess_count = int(df["Session"].dropna().astype(str).nunique()) if "Session" in df.columns else 0
            lobby_count = int(df["LobbyShort"].dropna().astype(str).nunique()) if "LobbyShort" in df.columns else 0
            rows.append(
                {
                    "Source": label,
                    "Rows": int(len(df)),
                    "Cols": int(len(df.columns)),
                    "Has Session": "Yes" if "Session" in df.columns else "No",
                    "Empty": "Yes" if df.empty else "No",
                    "Sessions": sess_count,
                    "Last name + first initial": lobby_count,
                }
            )
        else:
            rows.append(
                {
                    "Source": label,
                    "Rows": 0,
                    "Cols": 0,
                    "Has Session": "No",
                    "Empty": "Yes",
                    "Sessions": 0,
                    "Last name + first initial": 0,
                }
            )
    return pd.DataFrame(rows)

def filter_filer_rows(
    df: pd.DataFrame,
    session: str | None,
    lobbyshort: str,
    name_to_short: dict,
    lobbyist_norms: set[str],
    filerid_to_short: dict | None,
    filer_ids: set[int] | tuple[int, ...] | None = None,
    loose: bool = False,
) -> pd.DataFrame:
    if df.empty:
        return df

    d = df.copy()
    if session is not None:
        d = d[_session_series(d) == str(session)]
    if d.empty:
        return d

    filerid_map = filerid_to_short or {}
    if "FilerID" in d.columns:
        d["FilerID"] = pd.to_numeric(d["FilerID"], errors="coerce").fillna(-1).astype(int)
    elif "filerIdent" in d.columns:
        d["FilerID"] = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
    else:
        d["FilerID"] = -1

    if "FilerShortFromId" not in d.columns:
        if filerid_map:
            d["FilerShortFromId"] = d["FilerID"].map(filerid_map)
        else:
            d["FilerShortFromId"] = ""

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]
    if "FilerNormRaw" not in d.columns:
        d["FilerNormRaw"] = norm_name_series(filer_name)
    if "FilerNormClean" not in d.columns:
        filer_clean = clean_filer_name_series(filer_name)
        d["FilerNormClean"] = norm_name_series(filer_clean)
    if "FilerSortNorm" not in d.columns:
        d["FilerSortNorm"] = norm_name_series(filer_sort)

    if "FilerShortMapped" not in d.columns:
        mapped = d["FilerNormRaw"].map(name_to_short)
        mapped = mapped.where(mapped.notna(), d["FilerNormClean"].map(name_to_short))
        mapped = mapped.where(mapped.notna(), d["FilerSortNorm"].map(name_to_short))
        d["FilerShortMapped"] = mapped

    lobbyshort_norm = norm_name(lobbyshort)
    d["FilerIsShort"] = (
        d["FilerNormClean"].eq(lobbyshort_norm) |
        d["FilerNormRaw"].eq(lobbyshort_norm)
    )

    ok = (
        (d["FilerShortFromId"].astype(str) == str(lobbyshort)) |
        (d["FilerShortMapped"].astype(str) == str(lobbyshort)) |
        (d["FilerNormRaw"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerNormClean"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerSortNorm"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerIsShort"])
    )
    if filer_ids:
        filer_ids_set = set()
        for x in filer_ids:
            try:
                if pd.isna(x):
                    continue
            except Exception:
                pass
            try:
                filer_ids_set.add(int(x))
            except Exception:
                try:
                    filer_ids_set.add(int(float(x)))
                except Exception:
                    continue
        if filer_ids_set:
            filer_match = d["FilerID"].isin(filer_ids_set)
            if filer_match.any():
                ok = filer_match
    if loose and not ok.any():
        loose_ok = pd.Series(False, index=d.index)

        if lobbyshort_norm and len(lobbyshort_norm) >= 4:
            loose_ok |= (
                d["FilerNormRaw"].str.contains(lobbyshort_norm, na=False) |
                d["FilerNormClean"].str.contains(lobbyshort_norm, na=False) |
                d["FilerSortNorm"].str.contains(lobbyshort_norm, na=False)
            )

        if lobbyist_norms:
            for n in lobbyist_norms:
                if n and len(n) >= 4:
                    loose_ok |= (
                        d["FilerNormRaw"].str.contains(n, na=False) |
                        d["FilerNormClean"].str.contains(n, na=False) |
                        d["FilerSortNorm"].str.contains(n, na=False)
                    )

        target_last = last_name_norm_from_text(lobbyshort)
        if target_last:
            last_raw = last_name_norm_series(filer_name)
            last_sort = last_name_norm_series(filer_sort)
            loose_ok |= last_raw.eq(target_last) | last_sort.eq(target_last)

        target_init = _last_first_initial_key(lobbyshort)
        if target_init:
            init_raw = filer_name.fillna("").astype(str).map(_last_first_initial_key)
            init_sort = filer_sort.fillna("").astype(str).map(_last_first_initial_key)
            loose_ok |= init_raw.eq(target_init) | init_sort.eq(target_init)

        ok = loose_ok

    return d.loc[ok]

def filter_filer_rows_multi(
    df: pd.DataFrame,
    session: str | None,
    lobbyshorts: list[str],
    name_to_short: dict,
    lobbyist_norms: set[str],
    filerid_to_short: dict | None,
    loose: bool = False,
) -> pd.DataFrame:
    if df.empty or not lobbyshorts:
        return df.iloc[0:0]

    lobbyshorts_set = {str(s).strip() for s in lobbyshorts if str(s).strip()}
    if not lobbyshorts_set:
        return df.iloc[0:0]

    d = df.copy()
    if session is not None:
        d = d[_session_series(d) == str(session)]
    if d.empty:
        return d

    lobbyshort_norms = {norm_name(s) for s in lobbyshorts_set if s}
    norm_to_short = {norm_name(s): s for s in lobbyshorts_set if s}
    filerid_map = filerid_to_short or {}

    if "FilerID" in d.columns:
        d["FilerID"] = pd.to_numeric(d["FilerID"], errors="coerce").fillna(-1).astype(int)
    elif "filerIdent" in d.columns:
        d["FilerID"] = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
    else:
        d["FilerID"] = -1
    if "FilerShortFromId" not in d.columns:
        if filerid_map:
            d["FilerShortFromId"] = d["FilerID"].map(filerid_map)
        else:
            d["FilerShortFromId"] = ""

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]
    if "FilerNormRaw" not in d.columns:
        d["FilerNormRaw"] = norm_name_series(filer_name)
    if "FilerNormClean" not in d.columns:
        filer_clean = clean_filer_name_series(filer_name)
        d["FilerNormClean"] = norm_name_series(filer_clean)
    if "FilerSortNorm" not in d.columns:
        d["FilerSortNorm"] = norm_name_series(filer_sort)

    if "FilerShortMapped" not in d.columns:
        mapped = d["FilerNormRaw"].map(name_to_short)
        mapped = mapped.where(mapped.notna(), d["FilerNormClean"].map(name_to_short))
        mapped = mapped.where(mapped.notna(), d["FilerSortNorm"].map(name_to_short))
        d["FilerShortMapped"] = mapped

    d["FilerIsShort"] = (
        d["FilerNormClean"].isin(lobbyshort_norms) |
        d["FilerNormRaw"].isin(lobbyshort_norms)
    )

    ok = (
        d["FilerShortFromId"].astype(str).isin(lobbyshorts_set) |
        d["FilerShortMapped"].astype(str).isin(lobbyshorts_set) |
        (d["FilerNormRaw"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerNormClean"].isin(lobbyist_norms) if lobbyist_norms else False) |
        (d["FilerSortNorm"].isin(lobbyist_norms) if lobbyist_norms else False) |
        d["FilerIsShort"]
    )

    if loose and not ok.any():
        patterns = [re.escape(n) for n in list(lobbyshort_norms) + list(lobbyist_norms) if n and len(n) >= 4]
        if patterns:
            pat = "|".join(patterns)
            loose_ok = (
                d["FilerNormRaw"].str.contains(pat, na=False) |
                d["FilerNormClean"].str.contains(pat, na=False) |
                d["FilerSortNorm"].str.contains(pat, na=False)
            )
            ok = loose_ok

    d = d.loc[ok]
    if d.empty:
        return d

    matched = d["FilerShortFromId"].where(d["FilerShortFromId"].astype(str).isin(lobbyshorts_set), "")
    mapped_short = d["FilerShortMapped"].where(d["FilerShortMapped"].astype(str).isin(lobbyshorts_set), "")
    matched = matched.where(matched.astype(str).str.strip() != "", mapped_short)
    norm_short = d["FilerNormClean"].map(norm_to_short)
    norm_short = norm_short.where(norm_short.notna(), d["FilerNormRaw"].map(norm_to_short))
    matched = matched.where(matched.astype(str).str.strip() != "", norm_short)
    d["MatchedLobbyShort"] = matched.fillna("")
    return d

def member_match_mask(df: pd.DataFrame, member_info: dict) -> pd.Series:
    if df.empty:
        return pd.Series([], dtype=bool)

    org = df.get("recipientNameOrganization", pd.Series([""] * len(df))).fillna("").astype(str)
    last = df.get("recipientNameLast", pd.Series([""] * len(df))).fillna("").astype(str)
    first = df.get("recipientNameFirst", pd.Series([""] * len(df))).fillna("").astype(str)

    org_norm = norm_name_series(org)
    last_norm = norm_name_series(last)
    first_norm = norm_name_series(first)

    last_target = member_info.get("last_norm", "")
    first_target = member_info.get("first_norm", "")
    first_initial = member_info.get("first_initial", "")
    full_norm = member_info.get("full_norm", "")

    mask = pd.Series(False, index=df.index)

    if last_target:
        if first_target:
            first_ok = (first_norm == first_target)
            if first_initial:
                first_ok = first_ok | first_norm.str.startswith(first_initial)
            mask = mask | ((last_norm == last_target) & first_ok)
        else:
            mask = mask | (last_norm == last_target)

        if full_norm:
            mask = mask | org_norm.str.contains(full_norm, na=False)
        elif len(last_target) >= 4:
            mask = mask | org_norm.str.contains(last_target, na=False)
    elif full_norm:
        mask = mask | org_norm.str.contains(full_norm, na=False)

    return mask

def map_filer_to_lobbyshort(df: pd.DataFrame, name_to_short: dict, filerid_to_short: dict | None) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    filerid_map = filerid_to_short or {}
    short = d.get("LobbyShort", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)

    if "FilerShortFromId" not in d.columns and "filerIdent" in d.columns and filerid_map:
        fid = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
        d["FilerShortFromId"] = fid.map(filerid_map).fillna("")
    elif "FilerShortFromId" not in d.columns:
        d["FilerShortFromId"] = ""

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]
    if "FilerNormRaw" not in d.columns:
        d["FilerNormRaw"] = norm_name_series(filer_name)
    if "FilerNormClean" not in d.columns:
        filer_clean = clean_filer_name_series(filer_name)
        d["FilerNormClean"] = norm_name_series(filer_clean)
    if "FilerSortNorm" not in d.columns:
        d["FilerSortNorm"] = norm_name_series(filer_sort)
    if "FilerShortMapped" not in d.columns:
        mapped = d["FilerNormRaw"].map(name_to_short)
        mapped = mapped.where(mapped.notna(), d["FilerNormClean"].map(name_to_short))
        mapped = mapped.where(mapped.notna(), d["FilerSortNorm"].map(name_to_short))
        d["FilerShortMapped"] = mapped

    short = short.where(short.astype(str).str.strip() != "", d["FilerShortFromId"])
    short = short.where(short.astype(str).str.strip() != "", d["FilerShortMapped"])
    d["LobbyShort"] = short.fillna("")
    return d

def build_member_activities(
    df_food,
    df_ent,
    df_tran,
    df_gift,
    df_evnt,
    df_awrd,
    member_name: str,
    session: str | None,
    name_to_short: dict,
    filerid_to_short: dict | None,
    lobbyshort_to_name: dict | None = None,
) -> pd.DataFrame:
    member_info = parse_member_name(member_name)
    lobbyshort_to_name = lobbyshort_to_name or {}

    def keep(df: pd.DataFrame) -> pd.DataFrame:
        d = df
        if session is not None and "Session" in d.columns:
            d = d[d["Session"].astype(str).str.strip() == str(session)]
        if d.empty:
            return d
        mask = member_match_mask(d, member_info)
        if not mask.any():
            return d.iloc[0:0]
        d = d[mask]
        d = map_filer_to_lobbyshort(d, name_to_short, filerid_to_short)
        return d

    def lobbyist_display(d: pd.DataFrame) -> pd.Series:
        short = d.get("LobbyShort", pd.Series([""] * len(d))).fillna("").astype(str)
        mapped = short.map(lobbyshort_to_name)
        mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), short)
        filer = d.get("filerName", pd.Series([""] * len(d))).fillna("").astype(str)
        return mapped.where(mapped.astype(str).str.strip().ne(""), filer)

    out = []

    d = keep(df_food)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Food",
            "LobbyShort": d.get("LobbyShort", ""),
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": member_name,
            "Description": d.get("restaurantName", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_ent)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Entertainment",
            "LobbyShort": d.get("LobbyShort", ""),
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": member_name,
            "Description": d.get("entertainmentName", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_tran)
    if not d.empty:
        desc = d.get("travelPurpose", pd.Series([""] * len(d))).fillna("").astype(str)
        fallback = d.get("transportationTypeDescr", pd.Series([""] * len(d))).fillna("").astype(str)
        desc = desc.where(desc.str.len() > 0, fallback)
        route = (d.get("departureCity", "").fillna("").astype(str) + " -> " + d.get("arrivalCity", "").fillna("").astype(str)).str.strip()
        desc2 = (desc + " | " + route).str.replace(r"\s+\|\s+$", "", regex=True)
        date = d.get("departureDt", d.get("checkInDt", d.get("periodStartDt", ""))).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Travel",
            "LobbyShort": d.get("LobbyShort", ""),
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": member_name,
            "Description": desc2,
            "Amount": "",
        }))

    d = keep(df_gift)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Gift",
            "LobbyShort": d.get("LobbyShort", ""),
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": member_name,
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_evnt)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Event",
            "LobbyShort": d.get("LobbyShort", ""),
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": member_name,
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": "",
        }))

    d = keep(df_awrd)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Award",
            "LobbyShort": d.get("LobbyShort", ""),
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": member_name,
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    if not out:
        return pd.DataFrame(columns=["Session", "Date", "Type", "LobbyShort", "Lobbyist", "Filer", "Member", "Description", "Amount"])

    result = pd.concat(out, ignore_index=True)
    for c in ["Session", "Date", "LobbyShort", "Lobbyist", "Filer", "Member", "Description", "Amount"]:
        result[c] = result[c].fillna("").astype(str)
    date_sort = pd.to_datetime(result["Date"], errors="coerce")
    result = result.assign(_date_sort=date_sort).sort_values(
        ["_date_sort", "Type", "Lobbyist", "Member"], ascending=[False, True, True, True]
    ).drop(columns=["_date_sort"])
    return result

def build_timeline_counts(df: pd.DataFrame, date_col: str, freq: str = "M") -> pd.DataFrame:
    if df.empty or date_col not in df.columns:
        return pd.DataFrame(columns=["Period", "Label", "Count"])
    date = pd.to_datetime(df[date_col], errors="coerce")
    base = df.assign(_date=date).dropna(subset=["_date"])
    if base.empty:
        return pd.DataFrame(columns=["Period", "Label", "Count"])
    if freq.upper() == "Q":
        period = base["_date"].dt.to_period("Q")
    else:
        period = base["_date"].dt.to_period("M")
    base = base.assign(Period=period.dt.to_timestamp(), Label=period.astype(str))
    timeline = (
        base.groupby(["Period", "Label"])
        .size()
        .reset_index(name="Count")
        .sort_values("Period")
    )
    return timeline

def bill_position_from_flags(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Position"])
    agg = (
        df.groupby(["Session", "Bill", "LobbyShort"], as_index=False)
          .agg(IsFor=("IsFor", "max"), IsAgainst=("IsAgainst", "max"), IsOn=("IsOn", "max"))
    )
    _is_for = agg["IsFor"].fillna(0).astype(int) == 1
    _is_against = agg["IsAgainst"].fillna(0).astype(int) == 1
    _is_on = agg["IsOn"].fillna(0).astype(int) == 1
    _parts = pd.Series("", index=agg.index)
    _parts = _parts.where(~_is_for, "For")
    _parts = _parts + (_is_against & (_parts != "")).map({True: ", ", False: ""}) + _is_against.map({True: "Against", False: ""})
    _parts = _parts + (_is_on & (_parts != "")).map({True: ", ", False: ""}) + _is_on.map({True: "On", False: ""})
    agg["Position"] = _parts
    return agg[["Session", "Bill", "LobbyShort", "Position"]]

def build_bills_with_status(
    wit: pd.DataFrame,
    bill_status_all: pd.DataFrame,
    fiscal_impact: pd.DataFrame,
    session_val: str,
) -> pd.DataFrame:
    if wit.empty:
        return pd.DataFrame(columns=["Session", "Bill", "Position", "Author", "Caption", "Status", "Fiscal Impact H", "Fiscal Impact S"])

    bill_pos = bill_position_from_flags(wit)
    if bill_pos.empty:
        return pd.DataFrame(columns=["Session", "Bill", "Position", "Author", "Caption", "Status", "Fiscal Impact H", "Fiscal Impact S"])

    bills = bill_pos
    if not bill_status_all.empty and {"Session", "Bill"}.issubset(bill_status_all.columns):
        bills = bill_pos.merge(bill_status_all, on=["Session", "Bill"], how="left")

    if not fiscal_impact.empty and {"Session", "Bill", "Version", "EstimatedTwoYearNetImpactGR"}.issubset(fiscal_impact.columns):
        fi = fiscal_impact[fiscal_impact["Session"].astype(str).str.strip() == str(session_val)]
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

    bills = ensure_cols(bills, {"Author": "", "Caption": "", "Status": "", "Fiscal Impact H": 0, "Fiscal Impact S": 0})
    return bills

def build_policy_mentions(bills: pd.DataFrame, bill_sub_all: pd.DataFrame, session_val: str) -> pd.DataFrame:
    if bills.empty or bill_sub_all.empty or "Bill" not in bills.columns:
        return pd.DataFrame(columns=["Subject", "Mentions", "Share"])
    if "Subject" not in bill_sub_all.columns:
        return pd.DataFrame(columns=["Subject", "Mentions", "Share"])

    bill_subjects = bill_sub_all
    if "Session" in bill_subjects.columns:
        bill_subjects = bill_subjects[bill_subjects["Session"].astype(str).str.strip() == str(session_val)]
    bill_subjects = bill_subjects.merge(
        bills[["Bill"]].drop_duplicates(), on=["Bill"], how="inner"
    )
    if bill_subjects.empty:
        return pd.DataFrame(columns=["Subject", "Mentions", "Share"])

    mentions = (
        bill_subjects.groupby("Subject")["Bill"]
        .nunique()
        .reset_index(name="Mentions")
        .sort_values("Mentions", ascending=False)
    )
    total_mentions = int(mentions["Mentions"].sum()) or 1
    mentions["Share"] = (mentions["Mentions"] / total_mentions).fillna(0)
    return mentions

def build_lobby_subject_counts(
    lobby_sub_all: pd.DataFrame,
    session_val: str,
    lobbyshort: str,
    lobbyshort_norm: str,
    selected_filer_ids: tuple[int, ...],
) -> tuple[pd.DataFrame, float]:
    if lobby_sub_all.empty:
        return pd.DataFrame(columns=["Topic", "Mentions"]), 0.0

    lobby_sub = lobby_sub_all
    if "Session" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)]
    elif "session" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["session"].astype(str).str.strip() == str(session_val)]

    if selected_filer_ids and "FilerID" in lobby_sub.columns:
        fid = pd.to_numeric(lobby_sub["FilerID"], errors="coerce").fillna(-1).astype(int)
        lobby_sub = lobby_sub[fid.isin(selected_filer_ids)]
    elif "LobbyShortNorm" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"] == lobbyshort_norm]
    elif "LobbyShort" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip() == lobbyshort]
    else:
        lobby_sub = lobby_sub.iloc[0:0]

    if lobby_sub.empty:
        return pd.DataFrame(columns=["Topic", "Mentions"]), 0.0

    lobby_sub = lobby_sub.assign(
        Subject=lobby_sub.get("Subject Matter", pd.Series([""] * len(lobby_sub), index=lobby_sub.index)).fillna("").astype(str).str.strip(),
        Other=lobby_sub.get("Other Subject Matter Description", pd.Series([""] * len(lobby_sub), index=lobby_sub.index)).fillna("").astype(str).str.strip(),
        PrimaryBusiness=lobby_sub.get("Primary Business", pd.Series([""] * len(lobby_sub), index=lobby_sub.index)).fillna("").astype(str).str.strip(),
    )
    for col in ["Subject", "Other"]:
        series = lobby_sub[col]
        lobby_sub[col] = series.where(~series.str.lower().isin(["nan", "none"]), "")

    subject_non_empty = lobby_sub["Subject"].ne("").mean() if len(lobby_sub) else 0

    unnamed0 = lobby_sub.get("Unnamed: 0", pd.Series([""] * len(lobby_sub), index=lobby_sub.index)).fillna("").astype(str).str.strip()
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
    return lobby_sub_counts, subject_non_empty

def build_lobbyist_trend(
    df: pd.DataFrame,
    lobbyshort: str,
    filer_ids: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    if df.empty or not lobbyshort:
        return pd.DataFrame(columns=["Session", "Funding", "Mid", "SessionBase", "SessionLabel"])
    d = df
    d = d[d.get("LobbyShort", pd.Series(dtype=object)).astype(str).str.strip() == str(lobbyshort)]
    if d.empty:
        return pd.DataFrame(columns=["Session", "Funding", "Mid", "SessionBase", "SessionLabel"])
    if filer_ids and "FilerID" in d.columns:
        fid = pd.to_numeric(d["FilerID"], errors="coerce").fillna(-1).astype(int)
        d = d[fid.isin(filer_ids)]
    d = ensure_cols(d, {"IsTFL": 0, "Low_num": 0.0, "High_num": 0.0, "Session": ""})
    d["Session"] = d["Session"].astype(str).str.strip()
    d["Low_num"] = pd.to_numeric(d["Low_num"], errors="coerce").fillna(0)
    d["High_num"] = pd.to_numeric(d["High_num"], errors="coerce").fillna(0)
    d["Mid"] = (d["Low_num"] + d["High_num"]) / 2
    g = (
        d.groupby(["Session", "IsTFL"], as_index=False)
        .agg(Mid=("Mid", "sum"))
    )
    g["Funding"] = g["IsTFL"].map({1: "Taxpayer Funded", 0: "Private"}).fillna("Private")
    g["SessionBase"] = _session_base_number_series(g["Session"])
    g = g[g["SessionBase"].notna()]
    g["SessionLabel"] = g["SessionBase"].map(_session_base_label)
    return g[["Session", "Funding", "Mid", "SessionBase", "SessionLabel"]]

def build_top_clients(lt: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    if lt.empty or "Client" not in lt.columns:
        return pd.DataFrame(columns=["Client", "Funding", "Low", "High", "Mid"])
    d = lt.copy()
    d["Client"] = d["Client"].fillna("").astype(str).str.strip()
    d = d[d["Client"] != ""]
    if d.empty:
        return pd.DataFrame(columns=["Client", "Funding", "Low", "High", "Mid"])
    d = ensure_cols(d, {"IsTFL": 0, "Low_num": 0.0, "High_num": 0.0})
    d["Low_num"] = pd.to_numeric(d["Low_num"], errors="coerce").fillna(0)
    d["High_num"] = pd.to_numeric(d["High_num"], errors="coerce").fillna(0)
    d["Mid"] = (d["Low_num"] + d["High_num"]) / 2
    g = (
        d.groupby(["Client", "IsTFL"], as_index=False)
        .agg(Low=("Low_num", "sum"), High=("High_num", "sum"), Mid=("Mid", "sum"))
    )
    g["Funding"] = g["IsTFL"].map({1: "Taxpayer Funded", 0: "Private"}).fillna("Private")
    g = g.sort_values("Mid", ascending=False).head(top_n)
    return g[["Client", "Funding", "Low", "High", "Mid"]]

def build_activities(df_food, df_ent, df_tran, df_gift, df_evnt, df_awrd,
                     lobbyshort: str, session: str | None, name_to_short: dict,
                     lobbyist_norms_tuple: tuple[str, ...], filerid_to_short: dict | None = None,
                     filer_ids: tuple[int, ...] | None = None) -> pd.DataFrame:

    lobbyist_norms = set(lobbyist_norms_tuple)
    filer_ids_set = set(filer_ids) if filer_ids else None

    def keep(df: pd.DataFrame) -> pd.DataFrame:
        return filter_filer_rows(
            df,
            session=session,
            lobbyshort=lobbyshort,
            name_to_short=name_to_short,
            lobbyist_norms=lobbyist_norms,
            filerid_to_short=filerid_to_short,
            filer_ids=filer_ids_set,
            loose=True,
        )

    out = []

    d = keep(df_food)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Food",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("restaurantName", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_ent)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Entertainment",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("entertainmentName", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_tran)
    if not d.empty:
        desc = d.get("travelPurpose", pd.Series([""] * len(d))).fillna("").astype(str)
        fallback = d.get("transportationTypeDescr", pd.Series([""] * len(d))).fillna("").astype(str)
        desc = desc.where(desc.str.len() > 0, fallback)
        route = (d.get("departureCity", "").fillna("").astype(str) + " -> " + d.get("arrivalCity", "").fillna("").astype(str)).str.strip()
        desc2 = (desc + " | " + route).str.replace(r"\s+\|\s+$", "", regex=True)
        date = d.get("departureDt", d.get("checkInDt", d.get("periodStartDt", ""))).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Travel",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": desc2,
            "Amount": "",
        }))

    d = keep(df_gift)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Gift",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_evnt)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Event",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": "",
        }))

    d = keep(df_awrd)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Award",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    if not out:
        return pd.DataFrame(columns=["Session", "Date", "Type", "Filer", "Member", "Description", "Amount"])

    result = pd.concat(out, ignore_index=True)
    for c in ["Session", "Date", "Filer", "Member", "Description", "Amount"]:
        result[c] = result[c].fillna("").astype(str)
    date_sort = pd.to_datetime(result["Date"], errors="coerce")
    result = result.assign(_date_sort=date_sort).sort_values(
        ["_date_sort", "Type", "Member"], ascending=[False, True, True]
    ).drop(columns=["_date_sort"])
    return result

def build_activities_multi(
    df_food,
    df_ent,
    df_tran,
    df_gift,
    df_evnt,
    df_awrd,
    lobbyshorts: list[str],
    session: str | None,
    name_to_short: dict,
    lobbyist_norms_tuple: tuple[str, ...],
    filerid_to_short: dict | None = None,
    lobbyshort_to_name: dict | None = None,
) -> pd.DataFrame:
    lobbyist_norms = set(lobbyist_norms_tuple)
    lobbyshort_to_name = lobbyshort_to_name or {}

    def keep(df: pd.DataFrame) -> pd.DataFrame:
        return filter_filer_rows_multi(
            df,
            session=session,
            lobbyshorts=lobbyshorts,
            name_to_short=name_to_short,
            lobbyist_norms=lobbyist_norms,
            filerid_to_short=filerid_to_short,
            loose=True,
        )

    def lobbyist_display(d: pd.DataFrame) -> pd.Series:
        short = d.get("MatchedLobbyShort", pd.Series([""] * len(d))).fillna("").astype(str)
        mapped = short.map(lobbyshort_to_name)
        mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), short)
        filer = d.get("filerName", pd.Series([""] * len(d))).fillna("").astype(str)
        return mapped.where(mapped.astype(str).str.strip().ne(""), filer)

    out = []

    d = keep(df_food)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Food",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("restaurantName", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_ent)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Entertainment",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("entertainmentName", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_tran)
    if not d.empty:
        desc = d.get("travelPurpose", pd.Series([""] * len(d))).fillna("").astype(str)
        fallback = d.get("transportationTypeDescr", pd.Series([""] * len(d))).fillna("").astype(str)
        desc = desc.where(desc.str.len() > 0, fallback)
        route = (d.get("departureCity", "").fillna("").astype(str) + " -> " + d.get("arrivalCity", "").fillna("").astype(str)).str.strip()
        desc2 = (desc + " | " + route).str.replace(r"\s+\|\s+$", "", regex=True)
        date = d.get("departureDt", d.get("checkInDt", d.get("periodStartDt", ""))).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Travel",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": desc2,
            "Amount": "",
        }))

    d = keep(df_gift)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Gift",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    d = keep(df_evnt)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Event",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": "",
        }))

    d = keep(df_awrd)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Award",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": _vectorized_person_display(d.get("recipientNameOrganization", pd.Series([""] * len(d))), d.get("recipientNameLast", pd.Series([""] * len(d))), d.get("recipientNameFirst", pd.Series([""] * len(d)))),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": _vectorized_amount_display(d.get("activityExactAmount", pd.Series([""] * len(d))), d.get("activityAmountRangeLow", pd.Series([""] * len(d))), d.get("activityAmountRangeHigh", pd.Series([""] * len(d))), d.get("activityAmountCd", pd.Series([""] * len(d)))),
        }))

    if not out:
        return pd.DataFrame(columns=["Session", "Date", "Type", "Lobbyist", "Filer", "Member", "Description", "Amount"])

    result = pd.concat(out, ignore_index=True)
    for c in ["Session", "Date", "Lobbyist", "Filer", "Member", "Description", "Amount"]:
        result[c] = result[c].fillna("").astype(str)
    date_sort = pd.to_datetime(result["Date"], errors="coerce")
    result = result.assign(_date_sort=date_sort).sort_values(
        ["_date_sort", "Type", "Lobbyist", "Member"], ascending=[False, True, True, True]
    ).drop(columns=["_date_sort"])
    return result

def build_disclosures(
    df_cvr: pd.DataFrame,
    df_dock: pd.DataFrame,
    df_i4e: pd.DataFrame,
    df_sub: pd.DataFrame,
    lobbyshort: str,
    session: str | None,
    name_to_short: dict,
    lobbyist_norms_tuple: tuple[str, ...],
    filerid_to_short: dict | None = None,
    filer_ids: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    lobbyist_norms = set(lobbyist_norms_tuple)
    filer_ids_set = set(filer_ids) if filer_ids else None
    out = []

    d = filter_filer_rows(df_cvr, session, lobbyshort, name_to_short, lobbyist_norms, filerid_to_short, filer_ids_set)
    if not d.empty:
        date = d.get("filedDt", d.get("periodStartDt", "")).fillna("").astype(str)
        desc = d.get("subjectMatterMemo", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        dockets = d.get("docketsMemo", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        source_codes = d.get("sourceCategoryCd", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        desc = desc.where(desc.str.strip() != "", dockets)
        desc = desc.where(desc.str.strip() != "", source_codes)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Coverage",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": desc,
            "Entity": d.get("filerNameOrganization", "").fillna("").astype(str),
        }))

    d = filter_filer_rows(df_dock, session, lobbyshort, name_to_short, lobbyist_norms, filerid_to_short, filer_ids_set)
    if not d.empty:
        date = d.get("receivedDt", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Docket",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": d.get("designationText", "").fillna("").astype(str),
            "Entity": d.get("agencyName", "").fillna("").astype(str),
        }))

    d = filter_filer_rows(df_i4e, session, lobbyshort, name_to_short, lobbyist_norms, filerid_to_short, filer_ids_set)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        entity = (
            d.get("onbehalfName", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
            + " -- "
            + d.get("onbehalfMailingCity", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        ).str.replace(r"\s+--\s+$", "", regex=True)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "On Behalf",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": d.get("onbehalfPrimaryPhoneNumber", "").fillna("").astype(str),
            "Entity": entity,
        }))

    d = filter_filer_rows(df_sub, session, lobbyshort, name_to_short, lobbyist_norms, filerid_to_short, filer_ids_set)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        desc = d.get("subjectMatterCodeValue", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        desc = desc.where(
            desc.str.strip() != "",
            d.get("subjectMatterDescr", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str),
        )
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Subject Matter",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": desc,
            "Entity": d.get("subjectMatterDescr", "").fillna("").astype(str),
        }))

    if not out:
        return pd.DataFrame(columns=["Session", "Date", "Type", "Filer", "Description", "Entity"])

    result = pd.concat(out, ignore_index=True)
    for c in ["Session", "Date", "Type", "Filer", "Description", "Entity"]:
        result[c] = result[c].fillna("").astype(str)
    date_sort = pd.to_datetime(result["Date"], errors="coerce")
    result = result.assign(_date_sort=date_sort).sort_values(
        ["_date_sort", "Type", "Description"], ascending=[False, True, True]
    ).drop(columns=["_date_sort"])
    return result

def build_disclosures_multi(
    df_cvr: pd.DataFrame,
    df_dock: pd.DataFrame,
    df_i4e: pd.DataFrame,
    df_sub: pd.DataFrame,
    lobbyshorts: list[str],
    session: str | None,
    name_to_short: dict,
    lobbyist_norms_tuple: tuple[str, ...],
    filerid_to_short: dict | None = None,
    lobbyshort_to_name: dict | None = None,
) -> pd.DataFrame:
    lobbyist_norms = set(lobbyist_norms_tuple)
    lobbyshort_to_name = lobbyshort_to_name or {}

    def keep(df: pd.DataFrame) -> pd.DataFrame:
        return filter_filer_rows_multi(
            df,
            session=session,
            lobbyshorts=lobbyshorts,
            name_to_short=name_to_short,
            lobbyist_norms=lobbyist_norms,
            filerid_to_short=filerid_to_short,
            loose=False,
        )

    def lobbyist_display(d: pd.DataFrame) -> pd.Series:
        short = d.get("MatchedLobbyShort", pd.Series([""] * len(d))).fillna("").astype(str)
        mapped = short.map(lobbyshort_to_name)
        mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), short)
        filer = d.get("filerName", pd.Series([""] * len(d))).fillna("").astype(str)
        return mapped.where(mapped.astype(str).str.strip().ne(""), filer)

    out = []

    d = keep(df_cvr)
    if not d.empty:
        date = d.get("filedDt", d.get("periodStartDt", "")).fillna("").astype(str)
        desc = d.get("subjectMatterMemo", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        dockets = d.get("docketsMemo", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        source_codes = d.get("sourceCategoryCd", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        desc = desc.where(desc.str.strip() != "", dockets)
        desc = desc.where(desc.str.strip() != "", source_codes)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Coverage",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": desc,
            "Entity": d.get("filerNameOrganization", "").fillna("").astype(str),
        }))

    d = keep(df_dock)
    if not d.empty:
        date = d.get("receivedDt", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Docket",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": d.get("designationText", "").fillna("").astype(str),
            "Entity": d.get("agencyName", "").fillna("").astype(str),
        }))

    d = keep(df_i4e)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        entity = (
            d.get("onbehalfName", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
            + " - "
            + d.get("onbehalfMailingCity", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        ).str.replace(r"\s+-\s+$", "", regex=True)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "On Behalf",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": d.get("onbehalfPrimaryPhoneNumber", "").fillna("").astype(str),
            "Entity": entity,
        }))

    d = keep(df_sub)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        desc = d.get("subjectMatterCodeValue", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str)
        desc = desc.where(
            desc.str.strip() != "",
            d.get("subjectMatterDescr", pd.Series([""] * len(d), index=d.index)).fillna("").astype(str),
        )
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Subject Matter",
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": desc,
            "Entity": d.get("subjectMatterDescr", "").fillna("").astype(str),
        }))

    if not out:
        return pd.DataFrame(columns=["Session", "Date", "Type", "Lobbyist", "Filer", "Description", "Entity"])

    result = pd.concat(out, ignore_index=True)
    for c in ["Session", "Date", "Type", "Lobbyist", "Filer", "Description", "Entity"]:
        result[c] = result[c].fillna("").astype(str)
    date_sort = pd.to_datetime(result["Date"], errors="coerce")
    result = result.assign(_date_sort=date_sort).sort_values(
        ["_date_sort", "Type", "Description"], ascending=[False, True, True]
    ).drop(columns=["_date_sort"])
    return result

def _build_tfl_trend_data(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-compute TFL trend data for 85th-89th sessions (cached)."""
    d = df.copy()
    d["Session"] = _session_series(d)
    d = ensure_cols(d, {"IsTFL": 0, "Low_num": 0.0, "High_num": 0.0})
    d = d[d["IsTFL"] == 1]
    d["SessionBase"] = _session_base_number_series(d["Session"])
    d = d[d["SessionBase"].between(85, 89)]
    if d.empty:
        return pd.DataFrame(columns=["SessionBase", "Low", "High", "SessionLabel"])
    d["Low_num"] = pd.to_numeric(d["Low_num"], errors="coerce").fillna(0)
    d["High_num"] = pd.to_numeric(d["High_num"], errors="coerce").fillna(0)
    trend_group = (
        d.groupby("SessionBase", as_index=False)
        .agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
    )
    trend_group["SessionLabel"] = trend_group["SessionBase"].map(_session_base_label)
    return trend_group

def _build_top5_tfl_clients(df: pd.DataFrame, session_val: str | None, scope_val: str) -> pd.DataFrame:
    """Pre-compute top-5 taxpayer-funded clients (cached)."""
    clients = df.copy()
    clients["Session"] = _session_series(clients)
    if scope_val == "This Session" and session_val is not None:
        clients = clients[clients["Session"] == str(session_val)]
    clients = ensure_cols(clients, {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0})
    clients = clients[clients["IsTFL"] == 1]
    if clients.empty:
        return pd.DataFrame(columns=["Client", "Taxpayer Funded Total"])
    top_clients = (
        clients.groupby("Client", as_index=False)
        .agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
        .sort_values(["High", "Low"], ascending=[False, False])
        .head(5)
    )
    top_clients["Taxpayer Funded Total"] = top_clients["Low"].map(fmt_usd) + " - " + top_clients["High"].map(fmt_usd)
    return top_clients[["Client", "Taxpayer Funded Total"]]

def _build_lobby_display_names(df: pd.DataFrame) -> pd.DataFrame:
    """Build LobbyShort â†’ display name mapping (cached)."""
    lobby_display = (
        df[["LobbyShort", "Lobby Name"]]
        .dropna()
        .drop_duplicates()
        .assign(
            LobbyShort=lambda d: d["LobbyShort"].astype(str).str.strip(),
            LobbyNameClean=lambda d: d["Lobby Name"]
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True),
        )
    )
    _lnc = lobby_display["LobbyNameClean"]
    _has_comma = _lnc.str.contains(",", na=False)
    _sp = _lnc.str.split(",", n=1, expand=True)
    _first = _sp[1].str.strip().fillna("") if 1 in _sp.columns else pd.Series("", index=_lnc.index)
    _last = _sp[0].str.strip()
    _display = (_first + " " + _last).str.strip()
    lobby_display = lobby_display.assign(
        LobbyNameDisplay=_display.where(_has_comma, _lnc)
    )
    return lobby_display[["LobbyShort", "LobbyNameDisplay"]].drop_duplicates()

def build_all_lobbyists_overview_fast(df: pd.DataFrame, session_val: str | None, scope_val: str) -> tuple[pd.DataFrame, dict]:
    if df.empty:
        return pd.DataFrame(), {}

    d = df.copy()
    d["Session"] = _session_series(d)

    if scope_val == "This Session" and session_val is not None:
        d = d[d["Session"] == str(session_val)]

    d = ensure_cols(d, {"IsTFL": 0, "LobbyShort": "", "Client": "", "Low_num": 0.0, "High_num": 0.0})

    g = (
        d.groupby(["LobbyShort", "IsTFL"], as_index=False)
         .agg(
             Low=("Low_num", "sum"),
             High=("High_num", "sum"),
             Clients=("Client", lambda s: s.dropna().astype(str).nunique()),
         )
    )

    pivot = g.pivot(index="LobbyShort", columns="IsTFL", values=["Low", "High", "Clients"]).fillna(0)
    pivot.columns = [f"{a}_{'TFL' if b==1 else 'Private'}" for a, b in pivot.columns]
    pivot = pivot.reset_index()

    for col in ["Low_TFL","High_TFL","Clients_TFL","Low_Private","High_Private","Clients_Private"]:
        if col not in pivot.columns:
            pivot[col] = 0

    pivot["Has_TFL"] = pivot["Clients_TFL"] > 0
    pivot["Has_Private"] = pivot["Clients_Private"] > 0
    pivot["Only_TFL"] = pivot["Has_TFL"] & (~pivot["Has_Private"])
    pivot["Only_Private"] = pivot["Has_Private"] & (~pivot["Has_TFL"])
    pivot["Mixed"] = pivot["Has_TFL"] & pivot["Has_Private"]

    stats = {
        "total_lobbyists": int(pivot["LobbyShort"].nunique()),
        "has_tfl": int(pivot["Has_TFL"].sum()),
        "only_private": int(pivot["Only_Private"].sum()),
        "only_tfl": int(pivot["Only_TFL"].sum()),
        "mixed": int(pivot["Mixed"].sum()),
        "tfl_low_total": float(pivot["Low_TFL"].sum()),
        "tfl_high_total": float(pivot["High_TFL"].sum()),
        "pri_low_total": float(pivot["Low_Private"].sum()),
        "pri_high_total": float(pivot["High_Private"].sum()),
    }

    pivot["Total_Low"] = pivot["Low_TFL"] + pivot["Low_Private"]
    pivot["Total_High"] = pivot["High_TFL"] + pivot["High_Private"]
    pivot["TFL_Mid"] = (pivot["Low_TFL"] + pivot["High_TFL"]) / 2
    pivot["Private_Mid"] = (pivot["Low_Private"] + pivot["High_Private"]) / 2
    pivot["Total_Mid"] = pivot["TFL_Mid"] + pivot["Private_Mid"]
    pivot["TFL_Share"] = pivot["TFL_Mid"] / pivot["Total_Mid"].where(pivot["Total_Mid"] != 0, 1)
    pivot["TFL_Share"] = pivot["TFL_Share"].fillna(0)

    return pivot, stats



@dataclass(frozen=True)
class ClientScopeBundle:
    overview: pd.DataFrame
    stats: dict[str, Any]
    category_chart_data: pd.DataFrame


@dataclass(frozen=True)
class LobbyScopeBundle:
    all_pivot: pd.DataFrame
    all_stats: dict[str, Any]
    trend_group: pd.DataFrame
    top_clients: pd.DataFrame
    lobby_display: pd.DataFrame


@dataclass(frozen=True)
class MemberSessionBundle:
    all_legislators: pd.DataFrame
    stats: dict[str, Any]


def build_client_scope_bundle(
    df: pd.DataFrame,
    session_val: str | None,
    scope_val: str,
    *,
    match_entity_type: Callable[[str], tuple[str, str]],
    build_category_chart_data: Callable[[pd.DataFrame], pd.DataFrame],
) -> ClientScopeBundle:
    if df.empty:
        return ClientScopeBundle(pd.DataFrame(), {}, build_category_chart_data(df))

    d = df.copy()
    d["Session"] = _session_series(d)
    if scope_val == "This Session" and session_val is not None:
        d = d[d["Session"] == str(session_val)]

    d = ensure_cols(d, {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0, "LobbyShort": ""})
    d = d[d["Client"].fillna("").astype(str).str.strip() != ""]
    if d.empty:
        return ClientScopeBundle(pd.DataFrame(), {}, build_category_chart_data(df))

    g = (
        d.groupby("Client", as_index=False)
        .agg(
            Low=("Low_num", "sum"),
            High=("High_num", "sum"),
            Lobbyists=("LobbyShort", lambda s: s.dropna().astype(str).nunique()),
            IsTFL=("IsTFL", "max"),
        )
    )
    if not g.empty:
        entity_info = [match_entity_type(name) for name in g["Client"].fillna("").astype(str)]
        g["Entity Type"] = [info[0] for info in entity_info]
        g["Category"] = [info[1] for info in entity_info]

    stats = {
        "total_clients": int(g["Client"].nunique()),
        "tfl_clients": int((g["IsTFL"] == 1).sum()),
        "private_clients": int((g["IsTFL"] == 0).sum()),
        "tfl_low_total": float(g.loc[g["IsTFL"] == 1, "Low"].sum()),
        "tfl_high_total": float(g.loc[g["IsTFL"] == 1, "High"].sum()),
        "pri_low_total": float(g.loc[g["IsTFL"] == 0, "Low"].sum()),
        "pri_high_total": float(g.loc[g["IsTFL"] == 0, "High"].sum()),
    }
    return ClientScopeBundle(g.reset_index(drop=True), stats, build_category_chart_data(df))


def build_lobby_scope_bundle(df: pd.DataFrame, session_val: str | None, scope_val: str) -> LobbyScopeBundle:
    all_pivot, all_stats = build_all_lobbyists_overview_fast(df, session_val, scope_val)
    trend_group = _build_tfl_trend_data(df)
    top_clients = _build_top5_tfl_clients(df, session_val, scope_val)
    lobby_display = _build_lobby_display_names(df)
    return LobbyScopeBundle(all_pivot, all_stats, trend_group, top_clients, lobby_display)


def build_member_session_bundle(author_bills: pd.DataFrame, wit_all: pd.DataFrame, session_val: str) -> MemberSessionBundle:
    if author_bills.empty:
        return MemberSessionBundle(pd.DataFrame(), {})

    session = str(session_val).strip()
    if not session:
        return MemberSessionBundle(pd.DataFrame(), {})

    d = author_bills.copy()
    d["Session"] = _session_series(d)
    d = d[d["Session"] == session]
    d = ensure_cols(d, {"Author": "", "Status": "", "Bill": ""})
    d = d[d["Author"].astype(str).str.strip() != ""]
    if d.empty:
        return MemberSessionBundle(pd.DataFrame(), {})

    d = d[d["Bill"].notna()]
    d["Bill"] = d["Bill"].astype(str)
    d = d[d["Bill"].str.strip() != ""]
    d["StatusClean"] = d["Status"].fillna("").astype(str).str.strip()

    bills = d[["Author", "Bill", "StatusClean"]].drop_duplicates()
    bill_status = bills[["Bill", "StatusClean"]].drop_duplicates()

    total_bills = int(bill_status["Bill"].nunique())
    passed_total = int((bill_status["StatusClean"] == "Passed").sum())
    failed_total = int((bill_status["StatusClean"] == "Failed").sum())

    g = bills.groupby("Author", as_index=False).agg(
        Bills=("Bill", "nunique"),
        Passed=("StatusClean", lambda s: (s == "Passed").sum()),
        Failed=("StatusClean", lambda s: (s == "Failed").sum()),
    )
    g = g.rename(columns={"Author": "Legislator"})

    wit = pd.DataFrame(columns=["Bill", "LobbyShort"])
    if isinstance(wit_all, pd.DataFrame) and not wit_all.empty:
        wit = wit_all.copy()
        wit = ensure_cols(wit, {"Session": "", "Bill": "", "LobbyShort": ""})
        wit["Session"] = _session_series(wit)
        wit = wit[wit["Session"] == session]
        wit = wit[wit["Bill"].notna()]
        wit["Bill"] = wit["Bill"].astype(str)
        wit = wit[wit["Bill"].str.strip() != ""]
        bill_set = set(bills["Bill"].dropna().astype(str).unique().tolist())
        if bill_set:
            wit = wit[wit["Bill"].astype(str).isin(bill_set)]
        wit["LobbyShort"] = wit["LobbyShort"].fillna("").astype(str).str.strip()
        wit = wit[wit["LobbyShort"] != ""]

    witness_rows = int(len(wit)) if not wit.empty else 0
    witness_lobbyists = int(wit["LobbyShort"].nunique()) if not wit.empty else 0
    witness_bills = int(wit["Bill"].nunique()) if not wit.empty else 0

    if not wit.empty:
        bill_authors = bills[["Bill", "Author"]].drop_duplicates()
        bill_authors["Bill"] = bill_authors["Bill"].astype(str)
        wit_join = bill_authors.merge(wit[["Bill", "LobbyShort"]], on="Bill", how="left")
        wit_join = wit_join[wit_join["LobbyShort"].astype(str).str.strip() != ""]
        if not wit_join.empty:
            wit_counts = (
                wit_join.groupby("Author", as_index=False)
                .agg(
                    WitnessRows=("LobbyShort", "size"),
                    WitnessLobbyists=("LobbyShort", "nunique"),
                    WitnessBills=("Bill", "nunique"),
                )
            )
        else:
            wit_counts = pd.DataFrame(columns=["Author", "WitnessRows", "WitnessLobbyists", "WitnessBills"])
    else:
        wit_counts = pd.DataFrame(columns=["Author", "WitnessRows", "WitnessLobbyists", "WitnessBills"])

    g = g.merge(wit_counts, left_on="Legislator", right_on="Author", how="left")
    if "Author" in g.columns:
        g = g.drop(columns=["Author"])

    for col in ["WitnessRows", "WitnessLobbyists", "WitnessBills"]:
        if col not in g.columns:
            g[col] = 0
        g[col] = g[col].fillna(0).astype(int)

    stats = {
        "total_legislators": int(g["Legislator"].nunique()),
        "total_bills": total_bills,
        "passed": passed_total,
        "failed": failed_total,
        "witness_rows": witness_rows,
        "witness_lobbyists": witness_lobbyists,
        "witness_bills": witness_bills,
    }
    return MemberSessionBundle(g.reset_index(drop=True), stats)

