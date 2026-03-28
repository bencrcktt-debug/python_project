from __future__ import annotations

import re
from typing import Any

import pandas as pd

from tfl_app.charts.runtime import _session_base_label, _session_base_number_series
from tfl_app.search.models import AppState, LobbyLookupState
from tfl_app.shared.names import (
    clean_filer_name_series,
    first_name_norm_series,
    last_first_initial_key as _last_first_initial_key,
    last_name_norm_series,
    norm_name,
    norm_name_series,
    parse_person_name,
)
from tfl_app.shared.series import first_nonempty as _first_nonempty


_APP_STATE_BOOTSTRAP_COLUMNS = {
    "Wit_All": ("Session", "session"),
    "Bill_Status_All": ("Session", "Bill", "Authors", "Author", "Caption", "Status", "Link", "Chamber"),
    "Lobby_TFL_Client_All": ("Session", "Client", "Lobby Name", "LobbyShort", "IsTFL", "FilerID"),
    "Lobby_Sub_All": ("Session", "session", "legislative_session", "Lobby Name", "LobbyShort", "lobbyshort", "FilerID"),
    "Lobbyist_Pol_Funds": ("Session", "legislative_session", "Lobbyist", "LobbyShort", "lobbyshort", "FilerID"),
}


def _project_app_state_bootstrap_frame(table_key: str, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    keep = [column for column in _APP_STATE_BOOTSTRAP_COLUMNS.get(table_key, ()) if column in df.columns]
    if not keep:
        return df.copy()
    return df.loc[:, keep].copy()


def build_client_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Client" not in df.columns:
        return pd.DataFrame(columns=["Client", "ClientNorm"])
    base = df[["Client"]].dropna().copy()
    base["Client"] = base["Client"].astype(str).str.strip()
    base = base[base["Client"] != ""].drop_duplicates()
    base["ClientNorm"] = base["Client"].map(norm_name)
    base = base[base["ClientNorm"] != ""].drop_duplicates()
    return base


def _split_authors(text: str) -> list[str]:
    if text is None:
        return []
    value = str(text).strip()
    if not value or value.lower() in {"nan", "none"}:
        return []
    parts = [part.strip() for part in value.split("|")]
    return [part for part in parts if part and part.lower() not in {"nan", "none"}]


def build_author_bill_index(bs: pd.DataFrame) -> pd.DataFrame:
    columns = ["Session", "Bill", "Author", "AuthorNorm", "Status", "Caption", "Link", "Chamber"]
    if bs.empty:
        return pd.DataFrame(columns=columns)

    author_col = "Author" if "Author" in bs.columns else "Authors"
    if author_col not in bs.columns:
        return pd.DataFrame(columns=columns)

    data = bs.copy()
    data["AuthorRaw"] = data[author_col].fillna("").astype(str)
    data["AuthorList"] = data["AuthorRaw"].map(_split_authors)
    data = data.explode("AuthorList")
    data["Author"] = data["AuthorList"].fillna("").astype(str).str.strip()
    data = data[data["Author"].astype(str).str.strip() != ""]
    data["AuthorNorm"] = data["Author"].map(norm_name)

    available = [column for column in columns if column in data.columns]
    return data[available].drop_duplicates()


def build_member_index(author_bills: pd.DataFrame) -> pd.DataFrame:
    if author_bills.empty or "Author" not in author_bills.columns:
        return pd.DataFrame(columns=["Member", "MemberNorm"])
    base = author_bills[["Author", "AuthorNorm"]].dropna().copy()
    base = base.rename(columns={"Author": "Member", "AuthorNorm": "MemberNorm"})
    base = base[base["Member"].astype(str).str.strip() != ""].drop_duplicates()
    return base


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


def _dataframe_or_empty(value: object) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    return pd.DataFrame()


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
    filled_index = data.index[blank_mask]
    if blank_mask.any() and name_to_short:
        mapped = pd.Series("", index=filled_index, dtype="object")

        if "name" in data.columns:
            name_norm = norm_name_series(data.loc[filled_index, "name"].fillna("").astype(str))
            mapped = name_norm.map(name_to_short).fillna("")

        if "org" in data.columns:
            needs_org = mapped.astype(str).str.strip().eq("")
            if needs_org.any():
                org_index = mapped.index[needs_org]
                org_norm = norm_name_series(data.loc[org_index, "org"].fillna("").astype(str))
                mapped.loc[org_index] = org_norm.map(name_to_short).fillna("")

        data.loc[filled_index, "LobbyShort"] = mapped.fillna("")

    if "LobbyShortNorm" in data.columns:
        data.loc[filled_index, "LobbyShortNorm"] = norm_name_series(data.loc[filled_index, "LobbyShort"])
    else:
        data["LobbyShortNorm"] = norm_name_series(data["LobbyShort"])
    return data


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


def _build_lobbyshort_to_name(
    short_to_names: dict[str, list[str]],
    lobby_tfl_client_all: pd.DataFrame,
) -> dict[str, str]:
    if short_to_names:
        return {
            str(short).strip(): str(names[0]).strip()
            for short, names in short_to_names.items()
            if str(short).strip() and names and str(names[0]).strip()
        }
    if lobby_tfl_client_all.empty or not {"LobbyShort", "Lobby Name"}.issubset(lobby_tfl_client_all.columns):
        return {}
    tmp = lobby_tfl_client_all[["LobbyShort", "Lobby Name"]].copy()
    tmp["LobbyShort"] = tmp["LobbyShort"].fillna("").astype(str).str.strip()
    tmp["Lobby Name"] = tmp["Lobby Name"].fillna("").astype(str).str.strip()
    tmp = tmp[(tmp["LobbyShort"] != "") & (tmp["Lobby Name"] != "")]
    if tmp.empty:
        return {}
    grouped = tmp.groupby("LobbyShort", as_index=False).agg(LobbyName=("Lobby Name", _first_nonempty))
    return dict(zip(grouped["LobbyShort"], grouped["LobbyName"]))


def _build_initial_to_short(
    lobbyist_index: pd.DataFrame,
    short_to_names: dict[str, list[str]],
) -> dict[str, str]:
    rows: list[pd.DataFrame] = []
    if not lobbyist_index.empty and {"LastFirstInitialNorm", "LobbyShort"}.issubset(lobbyist_index.columns):
        tmp = lobbyist_index[["LastFirstInitialNorm", "LobbyShort"]].copy()
        tmp = tmp.rename(columns={"LastFirstInitialNorm": "InitialKey"})
        tmp["InitialKey"] = tmp["InitialKey"].fillna("").astype(str).str.strip()
        tmp["LobbyShort"] = tmp["LobbyShort"].fillna("").astype(str).str.strip()
        tmp = tmp[(tmp["InitialKey"] != "") & (tmp["LobbyShort"] != "")]
        if not tmp.empty:
            rows.append(tmp)
    if short_to_names:
        extra_rows = []
        for short, names in short_to_names.items():
            short_value = str(short).strip()
            if not short_value:
                continue
            for name in names:
                initial_key = _last_first_initial_key(str(name or "").strip())
                if initial_key:
                    extra_rows.append({"InitialKey": initial_key, "LobbyShort": short_value})
        if extra_rows:
            rows.append(pd.DataFrame(extra_rows))
    if not rows:
        return {}
    all_rows = pd.concat(rows, ignore_index=True)
    counts = (
        all_rows.groupby(["InitialKey", "LobbyShort"])
        .size()
        .reset_index(name="n")
        .sort_values(["InitialKey", "n", "LobbyShort"], ascending=[True, False, True])
        .drop_duplicates("InitialKey")
    )
    return dict(zip(counts["InitialKey"], counts["LobbyShort"]))


def _build_client_scope_overview(
    lobby_tfl_client_all: pd.DataFrame,
    *,
    by_session: bool,
) -> pd.DataFrame:
    columns = (["SessionKey"] if by_session else []) + ["Client", "Low", "High", "Lobbyists", "IsTFL", "Entity Type", "Category"]
    if lobby_tfl_client_all.empty:
        return pd.DataFrame(columns=columns)

    from tfl_app.charts.runtime import match_entity_type

    data = lobby_tfl_client_all.copy()
    if "SessionKey" not in data.columns:
        data = _ensure_session_key_column(data)
    data["Client"] = data.get("Client", pd.Series("", index=data.index)).fillna("").astype(str).str.strip()
    data = data[data["Client"] != ""]
    if data.empty:
        return pd.DataFrame(columns=columns)
    data["LobbyShort"] = data.get("LobbyShort", pd.Series("", index=data.index)).fillna("").astype(str)
    data["Low_num"] = pd.to_numeric(data.get("Low_num", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
    data["High_num"] = pd.to_numeric(data.get("High_num", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
    data["IsTFL"] = pd.to_numeric(data.get("IsTFL", pd.Series(0, index=data.index)), errors="coerce").fillna(0).astype(int)
    group_cols = ["SessionKey", "Client"] if by_session else ["Client"]
    grouped = (
        data.groupby(group_cols, as_index=False)
        .agg(
            Low=("Low_num", "sum"),
            High=("High_num", "sum"),
            Lobbyists=("LobbyShort", lambda series: series.dropna().astype(str).nunique()),
            IsTFL=("IsTFL", "max"),
        )
    )
    if grouped.empty:
        return pd.DataFrame(columns=columns)
    entity_info = [match_entity_type(name) for name in grouped["Client"].fillna("").astype(str)]
    grouped["Entity Type"] = [info[0] for info in entity_info]
    grouped["Category"] = [info[1] for info in entity_info]
    return grouped[columns]


def _build_lobby_scope_pivot(
    lobby_tfl_client_all: pd.DataFrame,
    *,
    by_session: bool,
) -> pd.DataFrame:
    columns = (["SessionKey"] if by_session else []) + [
        "LobbyShort",
        "Low_TFL",
        "High_TFL",
        "Clients_TFL",
        "Low_Private",
        "High_Private",
        "Clients_Private",
        "Has_TFL",
        "Has_Private",
        "Only_TFL",
        "Only_Private",
        "Mixed",
        "Total_Low",
        "Total_High",
        "TFL_Mid",
        "Private_Mid",
        "Total_Mid",
        "TFL_Share",
    ]
    if lobby_tfl_client_all.empty:
        return pd.DataFrame(columns=columns)

    data = lobby_tfl_client_all.copy()
    if "SessionKey" not in data.columns:
        data = _ensure_session_key_column(data)
    data["LobbyShort"] = data.get("LobbyShort", pd.Series("", index=data.index)).fillna("").astype(str).str.strip()
    data["Client"] = data.get("Client", pd.Series("", index=data.index)).fillna("").astype(str)
    data["Low_num"] = pd.to_numeric(data.get("Low_num", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
    data["High_num"] = pd.to_numeric(data.get("High_num", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
    data["IsTFL"] = pd.to_numeric(data.get("IsTFL", pd.Series(0, index=data.index)), errors="coerce").fillna(0).astype(int)
    group_cols = (["SessionKey"] if by_session else []) + ["LobbyShort", "IsTFL"]
    grouped = (
        data.groupby(group_cols, as_index=False)
        .agg(
            Low=("Low_num", "sum"),
            High=("High_num", "sum"),
            Clients=("Client", lambda series: series.dropna().astype(str).nunique()),
        )
    )
    if grouped.empty:
        return pd.DataFrame(columns=columns)
    index_cols = (["SessionKey"] if by_session else []) + ["LobbyShort"]
    pivot = grouped.pivot(index=index_cols, columns="IsTFL", values=["Low", "High", "Clients"]).fillna(0)
    pivot.columns = [f"{metric}_{'TFL' if funding == 1 else 'Private'}" for metric, funding in pivot.columns]
    pivot = pivot.reset_index()
    for column in ["Low_TFL", "High_TFL", "Clients_TFL", "Low_Private", "High_Private", "Clients_Private"]:
        if column not in pivot.columns:
            pivot[column] = 0
    pivot["Has_TFL"] = pivot["Clients_TFL"] > 0
    pivot["Has_Private"] = pivot["Clients_Private"] > 0
    pivot["Only_TFL"] = pivot["Has_TFL"] & (~pivot["Has_Private"])
    pivot["Only_Private"] = pivot["Has_Private"] & (~pivot["Has_TFL"])
    pivot["Mixed"] = pivot["Has_TFL"] & pivot["Has_Private"]
    pivot["Total_Low"] = pivot["Low_TFL"] + pivot["Low_Private"]
    pivot["Total_High"] = pivot["High_TFL"] + pivot["High_Private"]
    pivot["TFL_Mid"] = (pivot["Low_TFL"] + pivot["High_TFL"]) / 2
    pivot["Private_Mid"] = (pivot["Low_Private"] + pivot["High_Private"]) / 2
    pivot["Total_Mid"] = pivot["TFL_Mid"] + pivot["Private_Mid"]
    pivot["TFL_Share"] = pivot["TFL_Mid"] / pivot["Total_Mid"].where(pivot["Total_Mid"] != 0, 1)
    pivot["TFL_Share"] = pivot["TFL_Share"].fillna(0)
    return pivot[columns]


def _build_lobby_scope_trend_group(lobby_tfl_client_all: pd.DataFrame) -> pd.DataFrame:
    columns = ["SessionBase", "Low", "High", "SessionLabel"]
    if lobby_tfl_client_all.empty:
        return pd.DataFrame(columns=columns)
    data = lobby_tfl_client_all.copy()
    data["Session"] = data.get("SessionKey", data.get("Session", pd.Series("", index=data.index))).fillna("").astype(str).str.strip()
    data["IsTFL"] = pd.to_numeric(data.get("IsTFL", pd.Series(0, index=data.index)), errors="coerce").fillna(0).astype(int)
    data = data[data["IsTFL"] == 1]
    data["SessionBase"] = _session_base_number_series(data["Session"])
    data = data[data["SessionBase"].between(85, 89)]
    if data.empty:
        return pd.DataFrame(columns=columns)
    data["Low_num"] = pd.to_numeric(data.get("Low_num", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
    data["High_num"] = pd.to_numeric(data.get("High_num", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
    grouped = data.groupby("SessionBase", as_index=False).agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
    grouped["SessionLabel"] = grouped["SessionBase"].map(_session_base_label)
    return grouped[columns]


def _fmt_usd_simple(value: float) -> str:
    try:
        return f"${float(value):,.0f}"
    except Exception:
        return "$0"


def _build_lobby_scope_top_clients(
    lobby_tfl_client_all: pd.DataFrame,
    *,
    by_session: bool,
) -> pd.DataFrame:
    columns = (["SessionKey"] if by_session else []) + ["Client", "Taxpayer Funded Total"]
    if lobby_tfl_client_all.empty:
        return pd.DataFrame(columns=columns)
    data = lobby_tfl_client_all.copy()
    if "SessionKey" not in data.columns:
        data = _ensure_session_key_column(data)
    data["Client"] = data.get("Client", pd.Series("", index=data.index)).fillna("").astype(str).str.strip()
    data["IsTFL"] = pd.to_numeric(data.get("IsTFL", pd.Series(0, index=data.index)), errors="coerce").fillna(0).astype(int)
    data["Low_num"] = pd.to_numeric(data.get("Low_num", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
    data["High_num"] = pd.to_numeric(data.get("High_num", pd.Series(0.0, index=data.index)), errors="coerce").fillna(0.0)
    data = data[(data["IsTFL"] == 1) & (data["Client"] != "")]
    if data.empty:
        return pd.DataFrame(columns=columns)
    group_cols = ["SessionKey", "Client"] if by_session else ["Client"]
    grouped = data.groupby(group_cols, as_index=False).agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
    grouped["_rank"] = (
        grouped.groupby("SessionKey")["High"].rank(method="first", ascending=False)
        if by_session
        else grouped["High"].rank(method="first", ascending=False)
    )
    if by_session:
        grouped = grouped.sort_values(["SessionKey", "High", "Low", "Client"], ascending=[True, False, False, True])
        grouped = grouped.groupby("SessionKey", group_keys=False).head(5)
    else:
        grouped = grouped.sort_values(["High", "Low", "Client"], ascending=[False, False, True]).head(5)
    grouped["Taxpayer Funded Total"] = grouped["Low"].map(_fmt_usd_simple) + " - " + grouped["High"].map(_fmt_usd_simple)
    return grouped[columns]


def _build_lobby_display(lobbyshort_to_name: dict[str, str]) -> pd.DataFrame:
    if not lobbyshort_to_name:
        return pd.DataFrame(columns=["LobbyShort", "LobbyNameDisplay"])
    display_rows = []
    for short, name in lobbyshort_to_name.items():
        clean_name = str(name).strip()
        display = clean_name
        if "," in clean_name:
            last, first = [part.strip() for part in clean_name.split(",", 1)]
            display = f"{first} {last}".strip()
        display_rows.append({"LobbyShort": str(short).strip(), "LobbyNameDisplay": display})
    return pd.DataFrame(display_rows).drop_duplicates()


def _derive_lobby_lookup_state(data: dict[str, object]) -> LobbyLookupState:
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
    if not lobbyist_index.empty:
        known_shorts = frozenset(lobbyist_index["LobbyShort"].dropna().astype(str).str.strip().unique().tolist())

        tmp = lobbyist_index[["LobbyShort", "Lobby Name"]].dropna().copy()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str)
        short_to_names = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .agg(lambda values: sorted(set(map(str, values)))[:6])
            .to_dict()
        )

        key_frames = []
        for column in ["LobbyNameNorm", "LobbyNameCleanNorm", "LastFirstNorm", "FirstLastNorm", "LastFirstInitialNorm"]:
            if column in lobbyist_index.columns:
                key_frames.append(lobbyist_index[[column, "LobbyShort"]].rename(columns={column: "Key"}))
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

    filerid_to_short = _build_filerid_map(
        [
            (_dataframe_or_empty(data.get("Lobby_TFL_Client_All")), "FilerID", "LobbyShort"),
            (_dataframe_or_empty(data.get("Lobby_Sub_All")), "FilerID", "LobbyShort"),
            (_dataframe_or_empty(data.get("Lobbyist_Pol_Funds")), "FilerID", "LobbyShort"),
        ]
    )

    return LobbyLookupState(
        lobby_index=lobby_index,
        lobbyist_index=lobbyist_index,
        name_to_short=name_to_short,
        short_to_names=short_to_names,
        known_shorts=known_shorts,
        filerid_to_short=filerid_to_short,
    )


def _load_lobby_lookup_state(source: dict[str, object], data: dict[str, object]) -> LobbyLookupState:
    lookup_keys = ("lobby_index", "lobbyist_index", "name_to_short", "short_to_names", "known_shorts", "filerid_to_short")
    if not all(key in source for key in lookup_keys):
        return _derive_lobby_lookup_state(data)

    lobby_index = _dataframe_or_empty(source.get("lobby_index")).copy()
    lobbyist_index = _dataframe_or_empty(source.get("lobbyist_index")).copy()
    name_to_short = {
        str(key).strip(): str(value).strip()
        for key, value in dict(source.get("name_to_short") or {}).items()
        if str(key).strip() and str(value).strip()
    }
    short_to_names = {
        str(short).strip(): [str(name).strip() for name in (names or []) if str(name).strip()]
        for short, names in dict(source.get("short_to_names") or {}).items()
        if str(short).strip()
    }
    known_shorts = frozenset(str(short).strip() for short in (source.get("known_shorts") or []) if str(short).strip())
    filerid_to_short: dict[int, str] = {}
    for key, value in dict(source.get("filerid_to_short") or {}).items():
        try:
            filer_id = int(key)
        except (TypeError, ValueError):
            continue
        short_code = str(value).strip()
        if short_code:
            filerid_to_short[filer_id] = short_code

    return LobbyLookupState(
        lobby_index=lobby_index,
        lobbyist_index=lobbyist_index,
        name_to_short=name_to_short,
        short_to_names=short_to_names,
        known_shorts=known_shorts,
        filerid_to_short=filerid_to_short,
    )


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


def build_app_state(path: str, workbook: dict[str, object], *, data_version: str = "") -> AppState:
    source = dict(workbook or {})
    raw_manifest = source.pop("table_manifest", source.pop("__table_manifest__", {}))
    table_manifest = {
        str(key): dict(value)
        for key, value in dict(raw_manifest or {}).items()
        if isinstance(value, dict)
    }

    data: dict[str, object] = {
        "Wit_All": _ensure_session_key_column(_project_app_state_bootstrap_frame("Wit_All", _dataframe_or_empty(source.get("Wit_All")))),
        "Bill_Status_All": _ensure_session_key_column(_project_app_state_bootstrap_frame("Bill_Status_All", _dataframe_or_empty(source.get("Bill_Status_All")))),
        "Lobby_TFL_Client_All": _ensure_lobby_client_lookup_columns(_project_app_state_bootstrap_frame("Lobby_TFL_Client_All", _dataframe_or_empty(source.get("Lobby_TFL_Client_All")))),
        "Lobby_Sub_All": _ensure_session_key_column(_project_app_state_bootstrap_frame("Lobby_Sub_All", _dataframe_or_empty(source.get("Lobby_Sub_All")))),
        "Lobbyist_Pol_Funds": _ensure_session_key_column(_project_app_state_bootstrap_frame("Lobbyist_Pol_Funds", _dataframe_or_empty(source.get("Lobbyist_Pol_Funds")))),
    }

    lobby_lookup = _load_lobby_lookup_state(source, data)
    client_index = build_client_index(data["Lobby_TFL_Client_All"])
    author_bills_all = build_author_bill_index(data["Bill_Status_All"])
    member_index = build_member_index(author_bills_all)
    lobbyshort_to_name = _build_lobbyshort_to_name(lobby_lookup.short_to_names, data["Lobby_TFL_Client_All"])
    initial_to_short = _build_initial_to_short(lobby_lookup.lobbyist_index, lobby_lookup.short_to_names)
    client_scope_overview_all = _build_client_scope_overview(data["Lobby_TFL_Client_All"], by_session=False)
    client_scope_overview_by_session = _build_client_scope_overview(data["Lobby_TFL_Client_All"], by_session=True)

    from tfl_app.charts.runtime import build_category_chart_data

    client_category_chart_data = build_category_chart_data(data["Lobby_TFL_Client_All"])
    lobby_scope_pivot_all = _build_lobby_scope_pivot(data["Lobby_TFL_Client_All"], by_session=False)
    lobby_scope_pivot_by_session = _build_lobby_scope_pivot(data["Lobby_TFL_Client_All"], by_session=True)
    lobby_scope_trend_group = _build_lobby_scope_trend_group(data["Lobby_TFL_Client_All"])
    lobby_scope_top_clients_all = _build_lobby_scope_top_clients(data["Lobby_TFL_Client_All"], by_session=False)
    lobby_scope_top_clients_by_session = _build_lobby_scope_top_clients(data["Lobby_TFL_Client_All"], by_session=True)
    lobby_display = _build_lobby_display(lobbyshort_to_name)

    shared_sessions = _clean_sessions(
        data["Wit_All"].get("Session", pd.Series(dtype=object)),
        data["Lobby_TFL_Client_All"].get("Session", pd.Series(dtype=object)),
        data["Bill_Status_All"].get("Session", pd.Series(dtype=object)),
    )
    map_sessions = _clean_sessions(data["Lobby_TFL_Client_All"].get("Session", pd.Series(dtype=object)))
    default_shared_session = _default_session_from_list(list(shared_sessions)) if shared_sessions else None
    default_map_session = _default_session_from_list(list(map_sessions)) if map_sessions else None
    tfl_sessions = frozenset(
        data["Lobby_TFL_Client_All"].get("Session", pd.Series(dtype=object)).dropna().astype(str).str.strip().tolist()
    )

    data["client_index"] = client_index
    data["author_bills_all"] = author_bills_all
    data["member_index"] = member_index
    data["name_to_short"] = lobby_lookup.name_to_short
    data["short_to_names"] = lobby_lookup.short_to_names
    data["lobby_index"] = lobby_lookup.lobby_index
    data["lobbyist_index"] = lobby_lookup.lobbyist_index
    data["known_shorts"] = lobby_lookup.known_shorts
    data["filerid_to_short"] = lobby_lookup.filerid_to_short
    tables = {key: value for key, value in data.items() if isinstance(value, pd.DataFrame)}

    return AppState(
        path=path,
        data_version=str(data_version or "").strip(),
        data=data,
        tables=tables,
        table_manifest=table_manifest,
        client_index=client_index,
        author_bills_all=author_bills_all,
        member_index=member_index,
        lobby_index=lobby_lookup.lobby_index,
        lobbyist_index=lobby_lookup.lobbyist_index,
        name_to_short=lobby_lookup.name_to_short,
        short_to_names=lobby_lookup.short_to_names,
        known_shorts=lobby_lookup.known_shorts,
        filerid_to_short=lobby_lookup.filerid_to_short,
        initial_to_short=initial_to_short,
        lobbyshort_to_name=lobbyshort_to_name,
        client_scope_overview_all=client_scope_overview_all,
        client_scope_overview_by_session=client_scope_overview_by_session,
        client_category_chart_data=client_category_chart_data,
        lobby_scope_pivot_all=lobby_scope_pivot_all,
        lobby_scope_pivot_by_session=lobby_scope_pivot_by_session,
        lobby_scope_trend_group=lobby_scope_trend_group,
        lobby_scope_top_clients_all=lobby_scope_top_clients_all,
        lobby_scope_top_clients_by_session=lobby_scope_top_clients_by_session,
        lobby_display=lobby_display,
        shared_sessions=shared_sessions,
        default_shared_session=default_shared_session,
        map_sessions=map_sessions,
        default_map_session=default_map_session,
        tfl_sessions=tfl_sessions,
    )


__all__ = [
    "AppState",
    "LobbyLookupState",
    "_dataframe_or_empty",
    "_default_session_from_list",
    "_ensure_lobby_client_lookup_columns",
    "_ensure_session_key_column",
    "_ensure_staff_search_columns",
    "_ensure_witness_search_columns",
    "_fill_missing_witness_lobbyshorts",
    "_project_app_state_bootstrap_frame",
    "build_app_state",
    "build_author_bill_index",
    "build_client_index",
    "build_lobbyist_index",
    "build_member_index",
]
