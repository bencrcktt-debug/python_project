from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

import tfl_app.bundles.page_bundles as page_bundles
import tfl_app.shared.names as search_state
from tfl_app.shared.sessions import session_series as _session_series
from tfl_app.shared.series import first_nonempty as _first_nonempty
from tfl_app.shared.workspace import staff_metrics as _staff_metrics


def _empty_df(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _client_norm_series(df: pd.DataFrame) -> pd.Series:
    if "ClientNorm" in df.columns:
        return df["ClientNorm"].fillna("").astype(str)
    return search_state.norm_name_series(df.get("Client", pd.Series("", index=df.index)))


@dataclass(frozen=True)
class ClientWorkspaceDetailBundle:
    context: dict[str, Any]
    has_rows: bool


@dataclass(frozen=True)
class MemberWorkspaceDetailBundle:
    context: dict[str, Any]
    has_rows: bool


@dataclass(frozen=True)
class LobbyWorkspaceDetailBundle:
    context: dict[str, Any]


def build_client_workspace_detail_bundle(
    data: dict[str, Any],
    *,
    name_to_short: dict[str, str],
    session: str,
    tfl_session_val: str | None,
    client_name: str,
) -> ClientWorkspaceDetailBundle:
    empty_context = {
        "client_has_rows": False,
        "client_rows_all": _empty_df([]),
        "client_lt": _empty_df(["Session", "Client", "LobbyShort", "Lobby Name", "IsTFL", "Low_num", "High_num"]),
        "lobbyist_totals": _empty_df(["LobbyShort", "Low", "High", "Lobby Name", "Lobbyist"]),
        "top_lobbyist_label": "",
        "top_lobbyist_short": "",
        "lobbyshorts": [],
        "lobbyshort_norms": set(),
        "lobbyshort_to_name": {},
        "lobbyist_names": [],
        "lobbyist_norms": set(),
        "lobbyist_norms_tuple": tuple(),
        "client_is_tfl": False,
        "total_low": 0.0,
        "total_high": 0.0,
        "wit": _empty_df([]),
        "bills": _empty_df(["Session", "Bill", "LobbyShort", "Position", "Author", "Caption", "Status", "Organization", "Fiscal Impact H", "Fiscal Impact S", "Lobbyist"]),
        "bill_subjects": _empty_df(["Session", "Bill", "Subject"]),
        "mentions": _empty_df(["Subject", "Mentions", "Share"]),
        "lobby_sub_counts": _empty_df(["Topic", "Mentions"]),
        "activities": _empty_df(["Session", "Date", "Type", "LobbyShort", "Lobbyist", "Filer", "Member", "Description", "Amount"]),
        "disclosures": _empty_df(["Session", "Date", "Type", "LobbyShort", "Lobbyist", "Filer", "Entity", "Description"]),
        "staff_pick": _empty_df([]),
        "staff_pick_session": _empty_df([]),
        "staff_stats": _empty_df(["Legislator", "% Against that Failed", "% For that Passed"]),
    }
    client_name = str(client_name or "").strip()
    if not client_name:
        return ClientWorkspaceDetailBundle(context=empty_context, has_rows=False)

    lobby_tfl_client_all = data["Lobby_TFL_Client_All"]
    fiscal_impact = data["Fiscal_Impact"]
    bill_status_all = data["Bill_Status_All"]
    bill_sub_all = data["Bill_Sub_All"]
    lobby_sub_all = data["Lobby_Sub_All"]
    wit_all = data["Wit_All"]
    staff_all = data["Staff_All"]

    session = str(session or "").strip()
    client_norm = search_state.norm_name(client_name)
    client_rows_all = lobby_tfl_client_all[_client_norm_series(lobby_tfl_client_all) == client_norm]
    tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
    client_lt = client_rows_all[_session_series(client_rows_all) == tfl_session]
    client_lt = page_bundles.ensure_cols(
        client_lt,
        {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0, "LobbyShort": "", "Lobby Name": ""},
    )
    if client_lt.empty:
        empty_context.update({"client_rows_all": client_rows_all, "client_lt": client_lt})
        return ClientWorkspaceDetailBundle(context=empty_context, has_rows=False)

    lobbyist_totals = (
        client_lt.groupby("LobbyShort", as_index=False)
        .agg(
            Low=("Low_num", "sum"),
            High=("High_num", "sum"),
            LobbyName=("Lobby Name", _first_nonempty),
        )
        .rename(columns={"LobbyName": "Lobby Name"})
    )
    lobbyist_totals["Lobbyist"] = lobbyist_totals["Lobby Name"].fillna("").astype(str).str.strip()
    lobbyist_totals["Lobbyist"] = lobbyist_totals["Lobbyist"].where(
        lobbyist_totals["Lobbyist"] != "",
        lobbyist_totals["LobbyShort"],
    )
    lobbyist_totals = lobbyist_totals.sort_values(["High", "Low"], ascending=[False, False])
    top_lobbyist_label = ""
    top_lobbyist_short = ""
    if not lobbyist_totals.empty:
        top_lobby_row = lobbyist_totals.iloc[0]
        top_lobbyist_label = str(top_lobby_row.get("Lobbyist", "")).strip()
        top_lobbyist_short = str(top_lobby_row.get("LobbyShort", "")).strip()

    lobbyshorts = lobbyist_totals["LobbyShort"].dropna().astype(str).unique().tolist()
    lobbyshort_norms = {search_state.norm_name(value) for value in lobbyshorts if value}
    lobbyshort_to_name = dict(zip(lobbyist_totals["LobbyShort"], lobbyist_totals["Lobbyist"]))

    lobbyist_names = lobbyist_totals["Lobbyist"].dropna().astype(str).tolist()
    lobbyist_norms: set[str] = set()
    for name in lobbyist_names + lobbyshorts:
        lobbyist_norms |= search_state.norm_person_variants(name)
        init_key = search_state._last_first_initial_key(name)
        if init_key:
            lobbyist_norms.add(init_key)
    lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))

    client_is_tfl = bool((client_lt["IsTFL"] == 1).any())
    total_low = float(client_lt["Low_num"].sum()) if not client_lt.empty else 0.0
    total_high = float(client_lt["High_num"].sum()) if not client_lt.empty else 0.0

    wit_source = wit_all
    if "LobbyShortNorm" not in wit_source.columns:
        wit_source = wit_source.copy()
        wit_source["LobbyShortNorm"] = search_state.norm_name_series(wit_source["LobbyShort"])
    wit = wit_source[
        (_session_series(wit_source) == session) & (wit_source["LobbyShortNorm"].isin(lobbyshort_norms))
    ].copy()
    if not wit.empty:
        norm_to_short = {search_state.norm_name(value): value for value in lobbyshorts if value}
        wit["LobbyShort"] = wit["LobbyShortNorm"].map(norm_to_short).fillna(wit["LobbyShort"])

    bill_pos = page_bundles.bill_position_from_flags(wit)
    if bill_pos.empty:
        bills = empty_context["bills"].copy()
    else:
        bills = bill_pos.merge(bill_status_all, on=["Session", "Bill"], how="left")

    if not wit.empty and "org" in wit.columns:
        orgs = wit.copy()
        orgs["Organization"] = orgs.get("org", "").fillna("").astype(str).str.strip()
        orgs = (
            orgs.groupby(["Session", "Bill", "LobbyShort"])["Organization"]
            .apply(lambda values: ", ".join(sorted({item for item in values if item})))
            .reset_index()
        )
        bills = bills.merge(orgs, on=["Session", "Bill", "LobbyShort"], how="left")

    if not bills.empty:
        fi = fiscal_impact[_session_series(fiscal_impact) == session].copy()
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

    bills = page_bundles.ensure_cols(
        bills,
        {"LobbyShort": "", "Organization": "", "Fiscal Impact H": 0, "Fiscal Impact S": 0},
    )
    bills["Lobbyist"] = bills.get("LobbyShort", "").map(lobbyshort_to_name).fillna(bills.get("LobbyShort", ""))

    bill_subjects = bill_sub_all[_session_series(bill_sub_all) == session].merge(
        bills[["Session", "Bill"]].drop_duplicates(),
        on=["Session", "Bill"],
        how="inner",
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
        mentions = empty_context["mentions"].copy()

    lobby_sub = lobby_sub_all
    if "Session" in lobby_sub.columns or "session" in lobby_sub.columns or "SessionKey" in lobby_sub.columns:
        lobby_sub = lobby_sub[_session_series(lobby_sub) == session]
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
        lobby_sub_counts = empty_context["lobby_sub_counts"].copy()

    activities = page_bundles.build_activities_multi(
        data["LaFood"],
        data["LaEnt"],
        data["LaTran"],
        data["LaGift"],
        data["LaEvnt"],
        data["LaAwrd"],
        lobbyshorts=lobbyshorts,
        session=session,
        name_to_short=name_to_short,
        lobbyist_norms_tuple=lobbyist_norms_tuple,
        filerid_to_short=data.get("filerid_to_short", {}),
        lobbyshort_to_name=lobbyshort_to_name,
    )
    disclosures = page_bundles.build_disclosures_multi(
        data["LaCvr"],
        data["LaDock"],
        data["LaI4E"],
        data["LaSub"],
        lobbyshorts=lobbyshorts,
        session=session,
        name_to_short=name_to_short,
        lobbyist_norms_tuple=lobbyist_norms_tuple,
        filerid_to_short=data.get("filerid_to_short", {}),
        lobbyshort_to_name=lobbyshort_to_name,
    )

    staff_df = staff_all
    staff_session = _session_series(staff_df) == session
    last_names = {
        page_bundles.last_name_norm_from_text(name)
        for name in lobbyist_names
        if page_bundles.last_name_norm_from_text(name)
    }
    init_map = {
        key: value
        for key, value in ((search_state._last_first_initial_key(name), name) for name in lobbyist_names)
        if key
    }
    full_map = {search_state.norm_name(name): name for name in lobbyist_names if name}
    last_map = {
        key: value
        for key, value in ((page_bundles.last_name_norm_from_text(name), name) for name in lobbyist_names)
        if key
    }

    match_mask = pd.Series(False, index=staff_df.index)
    if lobbyist_norms:
        match_mask = match_mask | staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
        match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
    if last_names:
        match_mask = match_mask | staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)).isin(last_names)
    if lobbyshort_norms:
        match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyshort_norms)

    staff_pick = staff_df[match_mask].copy()
    staff_pick_session = staff_df[staff_session & match_mask].copy()
    if not staff_pick.empty:
        staff_pick["Matched Lobbyist"] = (
            staff_pick.get("StaffNameNorm", pd.Series([""] * len(staff_pick))).map(full_map)
            .fillna(staff_pick.get("StaffLastInitialNorm", pd.Series([""] * len(staff_pick))).map(init_map))
            .fillna(staff_pick.get("StaffLastNorm", pd.Series([""] * len(staff_pick))).map(last_map))
        )
    staff_stats = _staff_metrics(staff_pick_session, bills, session, bill_status_all) if not staff_pick_session.empty else empty_context["staff_stats"].copy()

    context = {
        "client_has_rows": True,
        "client_rows_all": client_rows_all,
        "client_lt": client_lt,
        "lobbyist_totals": lobbyist_totals,
        "top_lobbyist_label": top_lobbyist_label,
        "top_lobbyist_short": top_lobbyist_short,
        "lobbyshorts": lobbyshorts,
        "lobbyshort_norms": lobbyshort_norms,
        "lobbyshort_to_name": lobbyshort_to_name,
        "lobbyist_names": lobbyist_names,
        "lobbyist_norms": lobbyist_norms,
        "lobbyist_norms_tuple": lobbyist_norms_tuple,
        "client_is_tfl": client_is_tfl,
        "total_low": total_low,
        "total_high": total_high,
        "wit": wit,
        "bills": bills,
        "bill_subjects": bill_subjects,
        "mentions": mentions,
        "lobby_sub_counts": lobby_sub_counts,
        "activities": activities,
        "disclosures": disclosures,
        "staff_pick": staff_pick,
        "staff_pick_session": staff_pick_session,
        "staff_stats": staff_stats,
    }
    return ClientWorkspaceDetailBundle(context=context, has_rows=True)


def build_member_workspace_detail_bundle(
    data: dict[str, Any],
    *,
    author_bills_all: pd.DataFrame,
    name_to_short: dict[str, str],
    short_to_names: dict[str, list[str]],
    initial_to_short: dict[str, str] | None = None,
    session: str,
    tfl_session_val: str | None,
    member_name: str,
) -> MemberWorkspaceDetailBundle:
    empty_context = {
        "member_has_rows": False,
        "authored": _empty_df([]),
        "lt": _empty_df([]),
        "tfl_flag": _empty_df(["LobbyShort", "Has TFL Client"]),
        "lobbyshort_to_name": {},
        "bill_list": [],
        "wit": _empty_df([]),
        "witness": _empty_df(["Session", "Bill", "LobbyShort", "Organization", "Witness Name", "Position", "Has TFL Client", "Lobbyist"]),
        "activities": _empty_df(["Session", "Date", "Type", "LobbyShort", "Lobbyist", "Filer", "Member", "Description", "Amount", "Has TFL Client"]),
        "staff_matches": _empty_df([]),
        "staff_lobbyists": _empty_df([]),
        "member_info": {},
    }
    member_name = str(member_name or "").strip()
    if not member_name:
        return MemberWorkspaceDetailBundle(context=empty_context, has_rows=False)

    session = str(session or "").strip()
    initial_to_short = dict(initial_to_short or {})
    member_norm = search_state.norm_name(member_name)
    member_info = search_state.parse_member_name(member_name)
    authored = author_bills_all[
        (author_bills_all["AuthorNorm"] == member_norm)
        & (_session_series(author_bills_all) == session)
    ].drop_duplicates(subset=["Session", "Bill", "Author"])
    if authored.empty:
        empty_context.update({"authored": authored, "member_info": member_info})
        return MemberWorkspaceDetailBundle(context=empty_context, has_rows=False)

    tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
    lt = data["Lobby_TFL_Client_All"]
    if "Session" in lt.columns or "session" in lt.columns or "SessionKey" in lt.columns:
        lt = lt[_session_series(lt) == tfl_session]
    lt = page_bundles.ensure_cols(lt, {"LobbyShort": "", "IsTFL": 0})
    tfl_flag = (
        lt.groupby("LobbyShort", as_index=False)["IsTFL"]
        .max()
        .rename(columns={"IsTFL": "Has TFL Client"})
    )

    lobbyshort_to_name: dict[str, str] = {}
    if short_to_names:
        lobbyshort_to_name = {key: (values[0] if values else key) for key, values in short_to_names.items()}
    if not lobbyshort_to_name and not data["Lobby_TFL_Client_All"].empty:
        tmp = data["Lobby_TFL_Client_All"][["LobbyShort", "Lobby Name"]].dropna().copy()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
        lobbyshort_to_name = tmp.groupby("LobbyShort")["Lobby Name"].first().to_dict()

    bill_list = authored["Bill"].dropna().astype(str).unique().tolist()
    wit_all = data["Wit_All"]
    if "LobbyShortNorm" not in wit_all.columns and "LobbyShort" in wit_all.columns:
        wit_all = wit_all.copy()
        wit_all["LobbyShortNorm"] = search_state.norm_name_series(wit_all["LobbyShort"])

    if bill_list:
        wit = wit_all[
            (_session_series(wit_all) == session)
            & (wit_all["Bill"].astype(str).isin(bill_list))
        ]
    else:
        wit = wit_all.iloc[0:0]
    if "LobbyShort" in wit.columns:
        wit = wit[wit["LobbyShort"].notna() & (wit["LobbyShort"].astype(str).str.strip() != "")]

    witness = empty_context["witness"].copy()
    if not wit.empty:
        positions = page_bundles.bill_position_from_flags(wit)

        orgs = pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Organization"])
        if "org" in wit.columns:
            orgs = (
                wit.assign(Organization=wit.get("org", "").fillna("").astype(str).str.strip())
                .groupby(["Session", "Bill", "LobbyShort"])["Organization"]
                .apply(lambda values: ", ".join(sorted({item for item in values if item})))
                .reset_index()
            )

        names = pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Witness Name"])
        if "name" in wit.columns:
            names = (
                wit.assign(WitnessName=wit.get("name", "").fillna("").astype(str).str.strip())
                .groupby(["Session", "Bill", "LobbyShort"])["WitnessName"]
                .apply(lambda values: ", ".join(sorted({item for item in values if item})))
                .reset_index()
                .rename(columns={"WitnessName": "Witness Name"})
            )

        witness = positions.merge(orgs, on=["Session", "Bill", "LobbyShort"], how="left")
        witness = witness.merge(names, on=["Session", "Bill", "LobbyShort"], how="left")
        witness = witness.merge(tfl_flag, on="LobbyShort", how="left")
        witness["Has TFL Client"] = witness["Has TFL Client"].map({1: "Yes", 0: "No"}).fillna("Unknown")
        witness["Lobbyist"] = witness["LobbyShort"].map(lobbyshort_to_name).fillna(witness["LobbyShort"])

        authored_base_cols = [col for col in ["Session", "Bill", "Status", "Caption", "Link"] if col in authored.columns]
        authored_base = authored[authored_base_cols].drop_duplicates()
        witness = witness.merge(authored_base, on=["Session", "Bill"], how="left")

    activities = page_bundles.build_member_activities(
        data["LaFood"],
        data["LaEnt"],
        data["LaTran"],
        data["LaGift"],
        data["LaEvnt"],
        data["LaAwrd"],
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
        activities = empty_context["activities"].copy()

    staff_df = data["Staff_All"]
    staff_matches = pd.DataFrame()
    if not staff_df.empty and "Legislator" in staff_df.columns:
        leg_norm = staff_df.get("LegislatorNorm", search_state.norm_name_series(staff_df["Legislator"]))
        leg_last_norm = staff_df.get("LegislatorLastNorm", search_state.last_name_norm_series(staff_df["Legislator"]))
        leg_init_key = staff_df.get(
            "LegislatorInitKey",
            staff_df["Legislator"].fillna("").astype(str).map(search_state._last_first_initial_key),
        )

        match = pd.Series(False, index=staff_df.index)
        last_norm = member_info.get("last_norm", "")
        if last_norm:
            match = leg_last_norm == last_norm
            if member_info.get("initial_key"):
                match = match & (leg_init_key == member_info["initial_key"])

        full_norm = member_info.get("full_norm", "")
        if full_norm:
            match = match | leg_norm.str.contains(full_norm, na=False)

        staff_matches = staff_df[match].copy()

    staff_lobbyists = pd.DataFrame()
    if not staff_matches.empty and "Staffer" in staff_matches.columns:
        def map_staffer(name: str) -> str:
            if not name:
                return ""
            for value in search_state.norm_person_variants(name):
                if value in name_to_short:
                    return str(name_to_short[value])
            init_key = search_state._last_first_initial_key(name)
            if init_key and init_key in initial_to_short:
                return str(initial_to_short[init_key])
            return ""

        staff_lobbyists = staff_matches.copy()
        staff_lobbyists["LobbyShort"] = staff_lobbyists["Staffer"].fillna("").astype(str).map(map_staffer)
        staff_lobbyists = staff_lobbyists[staff_lobbyists["LobbyShort"].astype(str).str.strip() != ""]
        staff_lobbyists["Lobbyist"] = staff_lobbyists["LobbyShort"].map(lobbyshort_to_name).fillna(staff_lobbyists["LobbyShort"])

    context = {
        "member_has_rows": True,
        "authored": authored,
        "lt": lt,
        "tfl_flag": tfl_flag,
        "lobbyshort_to_name": lobbyshort_to_name,
        "bill_list": bill_list,
        "wit": wit,
        "witness": witness,
        "activities": activities,
        "staff_matches": staff_matches,
        "staff_lobbyists": staff_lobbyists,
        "member_info": member_info,
    }
    return MemberWorkspaceDetailBundle(context=context, has_rows=True)


def build_lobby_workspace_detail_bundle(
    data: dict[str, Any],
    *,
    name_to_short: dict[str, str],
    short_to_names: dict[str, list[str]],
    session: str,
    tfl_session_val: str | None,
    lobbyshort: str,
    typed_norms_tuple: tuple[str, ...],
    selected_names: tuple[str, ...],
    selected_filer_ids: tuple[int, ...],
) -> LobbyWorkspaceDetailBundle:
    empty_context = {
        "session": str(session or "").strip(),
        "lobbyshort": str(lobbyshort or "").strip(),
        "typed_norms": set(typed_norms_tuple or ()),
        "typed_norms_tuple": tuple(typed_norms_tuple or ()),
        "selected_filer_ids": tuple(selected_filer_ids or ()),
        "lobbyist_label": str(lobbyshort or "").strip(),
        "selected_names": list(selected_names or ()),
        "wit": _empty_df([]),
        "witness_match_note": "",
        "bills": _empty_df(["Session", "Bill", "Position", "Organization", "Author", "Caption", "Status", "Fiscal Impact H", "Fiscal Impact S"]),
        "mentions": _empty_df(["Subject", "Mentions", "Share"]),
        "bill_subjects": _empty_df(["Session", "Bill", "Subject"]),
        "lobby_sub_counts": _empty_df(["Topic", "Mentions"]),
        "subject_non_empty": 0.0,
        "lt": _empty_df([]),
        "has_tfl": False,
        "has_private": False,
        "tfl_clients": [],
        "private_clients": [],
        "tfl_low": 0.0,
        "tfl_high": 0.0,
        "pri_low": 0.0,
        "pri_high": 0.0,
        "staff_pick": _empty_df([]),
        "staff_pick_session": _empty_df([]),
        "staff_stats": _empty_df(["Legislator", "% Against that Failed", "% For that Passed"]),
        "activities": _empty_df(["Session", "Date", "Type", "Filer", "Member", "Description", "Amount"]),
        "disclosures": _empty_df(["Session", "Date", "Type", "Filer", "Entity", "Description"]),
    }
    session = str(session or "").strip()
    lobbyshort = str(lobbyshort or "").strip()
    typed_norms = set(typed_norms_tuple or ())
    selected_name_list = [str(value).strip() for value in (selected_names or ()) if str(value).strip()]
    selected_filer_ids_set = {int(value) for value in (selected_filer_ids or ())}
    if not lobbyshort:
        return LobbyWorkspaceDetailBundle(context=empty_context)

    lobbyist_label = lobbyshort
    if selected_name_list:
        lobbyist_label = selected_name_list[0]
    elif short_to_names.get(lobbyshort):
        lobbyist_label = short_to_names[lobbyshort][0]

    wit_all = page_bundles.ensure_cols(
        data["Wit_All"],
        {"Session": "", "Bill": "", "LobbyShort": "", "IsFor": 0, "IsAgainst": 0, "IsOn": 0},
    )
    if "LobbyShortNorm" not in wit_all.columns:
        wit_all = wit_all.copy()
        wit_all["LobbyShortNorm"] = search_state.norm_name_series(wit_all["LobbyShort"])
    base_wit = wit_all[_session_series(wit_all) == session]

    lobbyshort_norm = search_state.norm_name(lobbyshort)
    witness_match_note = ""
    if selected_name_list:
        name_variants = set()
        name_pairs: list[tuple[str, str, str]] = []
        for name in selected_name_list:
            name_variants |= search_state.norm_person_variants_with_nicknames(name)
            info = search_state.parse_person_name(name)
            first_norm = info.get("first_norm", "")
            last_norm = info.get("last_norm", "")
            first_initial = info.get("first_initial", "")
            if first_norm and last_norm:
                name_pairs.append((first_norm, last_norm, first_initial))

        name_mask = pd.Series(False, index=base_wit.index)
        if name_variants:
            name_norm = base_wit.get("NameNorm")
            if not isinstance(name_norm, pd.Series):
                name_norm = base_wit.get("name", pd.Series([""] * len(base_wit))).fillna("").astype(str).map(search_state.norm_name)
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
            wit = base_wit[name_mask].copy()
            wit["LobbyShort"] = lobbyshort
            wit["LobbyShortNorm"] = lobbyshort_norm
            witness_match_note = "Witness list filtered to the selected name."
        else:
            wit = base_wit.iloc[0:0]
            witness_match_note = "No witness-list rows matched the selected name. Clear the specific match to see all rows for that last name + first initial."
    else:
        if "LobbyShortNorm" in base_wit.columns:
            wit = base_wit[base_wit["LobbyShortNorm"] == lobbyshort_norm].copy()
            if not wit.empty:
                wit["LobbyShort"] = lobbyshort
        else:
            wit = base_wit[base_wit["LobbyShort"].astype(str).str.strip() == lobbyshort].copy()

    bills = page_bundles.build_bills_with_status(wit, data["Bill_Status_All"], data["Fiscal_Impact"], session)
    mentions = page_bundles.build_policy_mentions(bills, data["Bill_Sub_All"], session)

    bill_subjects = _empty_df(["Session", "Bill", "Subject"])
    bill_sub_all = data["Bill_Sub_All"]
    if (
        isinstance(bill_sub_all, pd.DataFrame)
        and {"Session", "Bill", "Subject"}.issubset(bill_sub_all.columns)
        and isinstance(bills, pd.DataFrame)
        and {"Session", "Bill"}.issubset(bills.columns)
        and not bills.empty
    ):
        bill_subjects = bill_sub_all[_session_series(bill_sub_all) == session].merge(
            bills[["Session", "Bill"]].drop_duplicates(),
            on=["Session", "Bill"],
            how="inner",
        )
        bill_subjects = bill_subjects[bill_subjects["Subject"].fillna("").astype(str).str.strip() != ""]

    lobby_sub_counts, subject_non_empty = page_bundles.build_lobby_subject_counts(
        data["Lobby_Sub_All"],
        session,
        lobbyshort,
        lobbyshort_norm,
        tuple(sorted(selected_filer_ids_set)) if selected_filer_ids_set else tuple(),
    )

    tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
    lt = data["Lobby_TFL_Client_All"][
        (_session_series(data["Lobby_TFL_Client_All"]) == tfl_session)
        & (data["Lobby_TFL_Client_All"]["LobbyShort"].astype(str).str.strip() == lobbyshort)
    ]
    if selected_filer_ids_set and "FilerID" in lt.columns:
        fid = pd.to_numeric(lt["FilerID"], errors="coerce").fillna(-1).astype(int)
        lt = lt[fid.isin(selected_filer_ids_set)]
    lt = page_bundles.ensure_cols(lt, {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0})

    has_tfl = bool((lt["IsTFL"] == 1).any()) if not lt.empty else False
    has_private = bool((lt["IsTFL"] == 0).any()) if not lt.empty else False
    tfl_clients = sorted(lt.loc[lt["IsTFL"] == 1, "Client"].dropna().astype(str).unique().tolist())
    private_clients = sorted(lt.loc[lt["IsTFL"] == 0, "Client"].dropna().astype(str).unique().tolist())
    tfl_low = float(lt.loc[lt["IsTFL"] == 1, "Low_num"].sum()) if not lt.empty else 0.0
    tfl_high = float(lt.loc[lt["IsTFL"] == 1, "High_num"].sum()) if not lt.empty else 0.0
    pri_low = float(lt.loc[lt["IsTFL"] == 0, "Low_num"].sum()) if not lt.empty else 0.0
    pri_high = float(lt.loc[lt["IsTFL"] == 0, "High_num"].sum()) if not lt.empty else 0.0

    staff_df = data["Staff_All"]
    staff_session = _session_series(staff_df) == str(session)
    if typed_norms:
        typed_last_norm = page_bundles.last_name_norm_from_text(search_state.clean_person_name(lobbyist_label))
        match_mask = (
            staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(typed_norms)
            | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(typed_norms)
        )
        if typed_last_norm:
            match_mask = match_mask | (
                staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)) == typed_last_norm
            )
        if lobbyshort_norm:
            match_mask = match_mask | (
                staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm
            )
    else:
        lobby_last_norm = page_bundles.last_name_norm_from_text(lobbyshort)
        match_mask = pd.Series(False, index=staff_df.index)
        if lobbyshort_norm:
            match_mask = match_mask | (
                staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm
            )
        if lobby_last_norm:
            match_mask = match_mask | (
                staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)) == lobby_last_norm
            )
    staff_pick = staff_df[match_mask].copy()
    staff_pick_session = staff_df[staff_session & match_mask].copy()
    staff_stats = _staff_metrics(staff_pick_session, bills, session, data["Bill_Status_All"]) if not staff_pick_session.empty else empty_context["staff_stats"].copy()

    activities = page_bundles.build_activities(
        data["LaFood"],
        data["LaEnt"],
        data["LaTran"],
        data["LaGift"],
        data["LaEvnt"],
        data["LaAwrd"],
        lobbyshort=lobbyshort,
        session=session,
        name_to_short=name_to_short,
        lobbyist_norms_tuple=typed_norms_tuple,
        filerid_to_short=data.get("filerid_to_short", {}),
        filer_ids=tuple(sorted(selected_filer_ids_set)) if selected_filer_ids_set else None,
    )
    disclosures = page_bundles.build_disclosures(
        data["LaCvr"],
        data["LaDock"],
        data["LaI4E"],
        data["LaSub"],
        lobbyshort=lobbyshort,
        session=session,
        name_to_short=name_to_short,
        lobbyist_norms_tuple=typed_norms_tuple,
        filerid_to_short=data.get("filerid_to_short", {}),
        filer_ids=tuple(sorted(selected_filer_ids_set)) if selected_filer_ids_set else None,
    )

    context = {
        "session": session,
        "lobbyshort": lobbyshort,
        "typed_norms": typed_norms,
        "typed_norms_tuple": tuple(sorted(typed_norms)),
        "selected_filer_ids": tuple(sorted(selected_filer_ids_set)),
        "lobbyist_label": lobbyist_label,
        "selected_names": selected_name_list,
        "wit": wit,
        "witness_match_note": witness_match_note,
        "bills": bills,
        "mentions": mentions,
        "bill_subjects": bill_subjects,
        "lobby_sub_counts": lobby_sub_counts,
        "subject_non_empty": subject_non_empty,
        "lt": lt,
        "has_tfl": has_tfl,
        "has_private": has_private,
        "tfl_clients": tfl_clients,
        "private_clients": private_clients,
        "tfl_low": tfl_low,
        "tfl_high": tfl_high,
        "pri_low": pri_low,
        "pri_high": pri_high,
        "staff_pick": staff_pick,
        "staff_pick_session": staff_pick_session,
        "staff_stats": staff_stats,
        "activities": activities,
        "disclosures": disclosures,
    }
    return LobbyWorkspaceDetailBundle(context=context)

