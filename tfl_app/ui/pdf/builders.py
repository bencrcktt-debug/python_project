from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from tfl_app.data.loaders import _MONEY_RANGE
from tfl_app.ui.pdf.charts import _calc_share_range, _chart_lines
from tfl_app.ui.pdf.export_utils import fmt_usd
from tfl_app.ui.pdf.runtime_helpers import (
    _last_first_initial_key,
    bill_position_from_flags,
    build_activities,
    build_activities_multi,
    build_author_bill_index,
    build_disclosures,
    build_disclosures_multi,
    build_member_activities,
    ensure_cols,
    last_name_norm_from_text,
    last_name_norm_series,
    match_entity_type,
    norm_name,
    norm_name_series,
    norm_person_variants,
    normalize_bill,
    parse_member_name,
)
from tfl_app.ui.pdf.session_state import (
    _session_label,
    _session_long_label,
    _session_range_label,
)


def _slugify(value: str, default: str = "report") -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "")).strip("-").lower()
    return s or default

def _clean_options(options: list[str]) -> list[str]:
    clean = []
    for opt in options:
        s = str(opt).strip()
        if not s or s.lower() in {"none", "nan", "null"}:
            continue
        clean.append(s)
    return clean

def _hydrate_report_inputs(
    focus_context: dict | None,
    report_tables: dict[str, pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, dict]:
    fc = dict(focus_context or {})

    tables = fc.get("tables", {})
    tables = dict(tables) if isinstance(tables, dict) else {}
    loaded = report_tables if isinstance(report_tables, dict) else {}
    for key, value in loaded.items():
        if isinstance(value, pd.DataFrame):
            tables[str(key)] = value
    fc["tables"] = tables
    bill_sub_all = tables["Bill_Sub_All"] if isinstance(tables.get("Bill_Sub_All"), pd.DataFrame) else pd.DataFrame()
    return bill_sub_all, fc

def _build_report_payload(
    *,
    session_val: str | None,
    scope_label: str,
    focus_label: str,
    Lobby_TFL_Client_All: pd.DataFrame,
    Wit_All: pd.DataFrame,
    Bill_Status_All: pd.DataFrame,
    Bill_Sub_All: pd.DataFrame,
    tfl_session_val: str | None,
    focus_context: dict | None = None,
) -> dict:
    session_label = _session_label(session_val) if session_val else "Selected Session"
    generated_dt = datetime.now()
    generated_date = generated_dt.strftime("%B %d, %Y")
    generated_ts = generated_dt.strftime("%Y-%m-%d %H:%M")
    scope_label = scope_label or "Selected Session"
    focus_label = focus_label or "All"

    scope_all = scope_label.strip().lower().startswith("all")
    tfl_session = str(tfl_session_val) if tfl_session_val is not None else str(session_val or "")

    base = ensure_cols(
        Lobby_TFL_Client_All,
        {"IsTFL": 0, "Low_num": 0.0, "High_num": 0.0, "Client": "", "LobbyShort": ""},
    ).copy()
    if "Session" in base.columns:
        base["Session"] = base["Session"].astype(str).str.strip()
        if not scope_all and tfl_session:
            base = base[base["Session"] == tfl_session]

    base["IsTFL"] = pd.to_numeric(base.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)
    base["Low_num"] = pd.to_numeric(base.get("Low_num", 0), errors="coerce").fillna(0.0)
    base["High_num"] = pd.to_numeric(base.get("High_num", 0), errors="coerce").fillna(0.0)

    scope_session_label = ""
    if scope_all:
        if "Session" in base.columns:
            scope_session_label = _session_range_label(base["Session"])
        else:
            scope_session_label = "All Sessions"
    else:
        scope_session_label = _session_long_label(session_val)
    if not scope_session_label:
        scope_session_label = scope_label or "Selected Session"

    report_id = f"LL-{generated_dt.strftime('%Y%m%d-%H%M')}-{_slugify(focus_label, default='scope')[:10]}"
    filter_summary_parts = [f"Scope: {scope_session_label}"]
    if focus_label:
        filter_summary_parts.append(f"Focus: {focus_label}")
    if focus_context and isinstance(focus_context, dict):
        if focus_context.get("type") == "bill":
            bill_id = focus_context.get("bill") or focus_context.get("query", "")
            if bill_id:
                filter_summary_parts.append(f"Bill: {bill_id}")
        if focus_context.get("type") == "lobbyist":
            lobby_name = focus_context.get("display_name", "")
            if lobby_name:
                filter_summary_parts.append(f"Lobbyist: {lobby_name}")
    filter_summary = "; ".join(filter_summary_parts)
    selected_lobbyist = ""
    if focus_context and isinstance(focus_context, dict) and focus_context.get("type") == "lobbyist":
        selected_lobbyist = focus_context.get("display_name") or ""

    total_low = float(base["Low_num"].sum()) if not base.empty else 0.0
    total_high = float(base["High_num"].sum()) if not base.empty else 0.0
    tfl_low = float(base.loc[base["IsTFL"] == 1, "Low_num"].sum()) if not base.empty else 0.0
    tfl_high = float(base.loc[base["IsTFL"] == 1, "High_num"].sum()) if not base.empty else 0.0
    private_low = float(base.loc[base["IsTFL"] == 0, "Low_num"].sum()) if not base.empty else 0.0
    private_high = float(base.loc[base["IsTFL"] == 0, "High_num"].sum()) if not base.empty else 0.0

    tfl_share_low_pct, tfl_share_high_pct = _calc_share_range(tfl_low, tfl_high, total_low, total_high)
    private_share_low_pct, private_share_high_pct = _calc_share_range(
        private_low, private_high, total_low, total_high
    )

    funding_mix = {
        "Taxpayer Funded": (tfl_low + tfl_high) / 2,
        "Private": (private_low + private_high) / 2,
    }

    def _top_clients(df: pd.DataFrame, is_tfl: int, limit: int = 5) -> list[dict]:
        if df.empty or "Client" not in df.columns:
            return []
        subset = df[df["IsTFL"] == is_tfl]
        subset["Client"] = subset["Client"].fillna("").astype(str).str.strip()
        subset = subset[subset["Client"] != ""]
        if subset.empty:
            return []
        grouped = (
            subset.groupby("Client", as_index=False)
            .agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
            .sort_values(["High", "Low"], ascending=False)
            .head(limit)
        )
        return [
            {"Client": row.Client, "Low": float(row.Low), "High": float(row.High)}
            for row in grouped.itertuples(index=False)
        ]

    top_clients_tfl = _top_clients(base, 1, limit=5)
    top_clients_private = _top_clients(base, 0, limit=5)

    def _series_from(df: pd.DataFrame, col: str) -> pd.Series:
        s = df.get(col, pd.Series(dtype=object))
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        return s

    def _unique_count(s: pd.Series) -> int:
        if s is None or s.empty:
            return 0
        v = s.dropna().astype(str).str.strip()
        v = v[(v != "") & (~v.str.lower().isin(["nan", "none", "null"]))]
        return int(v.nunique())

    unique_lobbyists_total = _unique_count(_series_from(base, "LobbyShort"))
    unique_lobbyists_tfl = _unique_count(_series_from(base.loc[base["IsTFL"] == 1], "LobbyShort"))
    unique_clients_total = _unique_count(_series_from(base, "Client"))
    unique_clients_tfl = _unique_count(_series_from(base.loc[base["IsTFL"] == 1], "Client"))

    chart_compensation_bar = _chart_lines(
        [
            ("Taxpayer Funded", f"{fmt_usd(tfl_low)} - {fmt_usd(tfl_high)}"),
            ("Private", f"{fmt_usd(private_low)} - {fmt_usd(private_high)}"),
            ("Total", f"{fmt_usd(total_low)} - {fmt_usd(total_high)}"),
        ]
    )
    chart_share = _chart_lines(
        [
            ("Taxpayer Funded share", f"{tfl_share_low_pct:.1f}% - {tfl_share_high_pct:.1f}%"),
            ("Private share", f"{private_share_low_pct:.1f}% - {private_share_high_pct:.1f}%"),
        ]
    )

    chart_entity_types = "No taxpayer-funded clients found."
    entity_type_counts = []
    tfl_clients = base[base["IsTFL"] == 1]
    if not tfl_clients.empty:
        clients = _series_from(tfl_clients, "Client").dropna().astype(str).str.strip()
        clients = clients[(clients != "") & (~clients.str.lower().isin(["nan", "none", "null"]))].drop_duplicates()
        if not clients.empty:
            type_counts = clients.map(lambda x: match_entity_type(x)[0]).value_counts().head(5)
            chart_entity_types = "\n".join(
                [f"{name}: {count} clients" for name, count in type_counts.items()]
            )
            entity_type_counts = [
                {"type": name, "count": int(count)} for name, count in type_counts.items()
            ]

    tfl_flag = pd.DataFrame(columns=["LobbyShort", "IsTFL"])
    if not base.empty and "LobbyShort" in base.columns:
        tfl_flag = (
            base.groupby("LobbyShort", as_index=False)["IsTFL"]
            .max()
            .rename(columns={"IsTFL": "IsTFL"})
        )

    witness_summary = "No witness-list data available for this scope/session."
    chart_witness_positions = "No witness-list data available."
    witness_counts = {
        "tfl": {"Against": 0, "For": 0, "On": 0},
        "private": {"Against": 0, "For": 0, "On": 0},
    }
    against = pd.DataFrame()

    wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
    if not wit.empty and "LobbyShort" in wit.columns:
        if session_val is not None and "Session" in wit.columns:
            wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
        if not wit.empty:
            pos = bill_position_from_flags(wit)
            if not pos.empty:
                pos = pos.merge(tfl_flag, on="LobbyShort", how="left")
                pos["IsTFL"] = pd.to_numeric(pos.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

                def _pos_counts(df: pd.DataFrame) -> dict:
                    return {
                        "Against": int(df["Position"].astype(str).str.contains("Against", case=False, na=False).sum()),
                        "For": int(df["Position"].astype(str).str.contains(r"\bFor\b", case=False, na=False).sum()),
                        "On": int(df["Position"].astype(str).str.contains(r"\bOn\b", case=False, na=False).sum()),
                    }

                tfl_counts = _pos_counts(pos[pos["IsTFL"] == 1])
                pri_counts = _pos_counts(pos[pos["IsTFL"] != 1])
                witness_counts = {"tfl": tfl_counts, "private": pri_counts}

                witness_summary = (
                    "Taxpayer-funded lobbyists recorded "
                    f"{tfl_counts['Against']:,} against, {tfl_counts['For']:,} for, "
                    f"and {tfl_counts['On']:,} on positions; private lobbyists recorded "
                    f"{pri_counts['Against']:,} against, {pri_counts['For']:,} for, "
                    f"and {pri_counts['On']:,} on positions."
                )
                chart_witness_positions = _chart_lines(
                    [
                        (
                            "Taxpayer Funded",
                            f"Against {tfl_counts['Against']:,}, For {tfl_counts['For']:,}, On {tfl_counts['On']:,}",
                        ),
                        (
                            "Private",
                            f"Against {pri_counts['Against']:,}, For {pri_counts['For']:,}, On {pri_counts['On']:,}",
                        ),
                    ]
                )
                against = pos[pos["Position"].astype(str).str.contains("Against", case=False, na=False)]

    top_bills = []
    if not against.empty:
        counts = (
            against.groupby(["Bill", "IsTFL"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        counts["tfl"] = counts.get(1, 0)
        counts["private"] = counts.get(0, 0)
        counts = counts.sort_values(["tfl", "private", "Bill"], ascending=[False, False, True]).head(5)

        bill_info = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
        if not bill_info.empty and "Session" in bill_info.columns and session_val is not None:
            bill_info = bill_info[bill_info["Session"].astype(str).str.strip() == str(session_val)]
        keep_cols = [c for c in ["Bill", "Caption", "Status"] if c in bill_info.columns]
        if keep_cols:
            bill_info = bill_info[keep_cols].drop_duplicates(subset=["Bill"])
        counts = counts.merge(bill_info, on="Bill", how="left") if keep_cols else counts

        for row in counts.itertuples(index=False):
            bill_id = str(getattr(row, "Bill", "")).strip() or "-"
            caption = str(getattr(row, "Caption", "")).strip() or "-"
            status = str(getattr(row, "Status", "")).strip()
            summary = f"Status: {status}" if status else "Status: Unknown"
            top_bills.append(
                {
                    "id": bill_id,
                    "caption": caption,
                    "tfl": int(getattr(row, "tfl", 0) or 0),
                    "private": int(getattr(row, "private", 0) or 0),
                    "summary": summary,
                }
            )

    chart_top_bills = (
        "\n".join(
            [
                f"{i + 1}. {b['id']} - TFL {b['tfl']:,}, Private {b['private']:,}"
                for i, b in enumerate(top_bills)
            ]
        )
        if top_bills
        else "No bill-level opposition data available."
    )

    top_subjects = []
    bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
    if not against.empty and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
        if "Session" in bill_sub.columns and session_val is not None:
            bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
        merged = against[["Bill"]].merge(bill_sub[["Bill", "Subject"]], on="Bill", how="left")
        merged["Subject"] = merged["Subject"].fillna("").astype(str).str.strip()
        merged = merged[merged["Subject"] != ""]
        if not merged.empty:
            subject_counts = (
                merged.groupby("Subject")
                .size()
                .reset_index(name="Oppositions")
                .sort_values("Oppositions", ascending=False)
                .head(5)
            )
            top_subjects = subject_counts.to_dict("records")

    chart_top_subjects = (
        "\n".join(
            [
                f"{i + 1}. {s['Subject']} - {int(s['Oppositions']):,} oppositions"
                for i, s in enumerate(top_subjects)
            ]
        )
        if top_subjects
        else "No subject-level opposition data available."
    )

    scope_note = ""
    if scope_all:
        scope_note = (
            f"Totals reflect all available sessions. Bill-level sections reflect {session_label}."
        )

    existing_law_gap_summary = (
        "Texas law restricts state agencies from hiring lobbyists with public funds, "
        "but political subdivisions are not uniformly covered, creating a parity gap."
    )
    recommended_fix_statute = (
        "Amend Texas Government Code Section 556.005 to include political subdivisions and "
        "prohibit direct or indirect use of public funds for lobbying."
    )
    implementation_notes = (
        "Define political subdivision and public funds clearly, cover dues and assessments, "
        "and provide enforceable remedies for violations."
    )
    data_sources_bullets = "\n".join(
        [
            "- Texas Ethics Commission: lobby registrations, compensation ranges, and activity reports.",
            "- Texas Legislature Online: bill status, witness lists, and subject classifications.",
            "- Lobby Look-Up compiled dataset.",
        ]
    )
    disclaimer_note = (
        "Disclaimer: Figures are based on reported ranges and should be read as conservative estimates."
    )

    focus_section = None
    fc = focus_context or {}
    focus_type = str(fc.get("type", "")).strip().lower()
    tables = fc.get("tables", {}) if isinstance(fc, dict) else {}
    lookups = fc.get("lookups", {}) if isinstance(fc, dict) else {}
    if not isinstance(tables, dict):
        tables = {}
    if not isinstance(lookups, dict):
        lookups = {}

    staff_all = tables.get("Staff_All", pd.DataFrame())
    lobby_sub_all = tables.get("Lobby_Sub_All", pd.DataFrame())
    la_food = tables.get("LaFood", pd.DataFrame())
    la_ent = tables.get("LaEnt", pd.DataFrame())
    la_tran = tables.get("LaTran", pd.DataFrame())
    la_gift = tables.get("LaGift", pd.DataFrame())
    la_evnt = tables.get("LaEvnt", pd.DataFrame())
    la_awrd = tables.get("LaAwrd", pd.DataFrame())
    la_cvr = tables.get("LaCvr", pd.DataFrame())
    la_dock = tables.get("LaDock", pd.DataFrame())
    la_i4e = tables.get("LaI4E", pd.DataFrame())
    la_sub = tables.get("LaSub", pd.DataFrame())

    name_to_short = lookups.get("name_to_short", {})
    short_to_names = lookups.get("short_to_names", {})
    filerid_to_short = lookups.get("filerid_to_short", {})
    if not isinstance(name_to_short, dict):
        name_to_short = {}
    if not isinstance(short_to_names, dict):
        short_to_names = {}
    if not isinstance(filerid_to_short, dict):
        filerid_to_short = {}

    report_title = str(fc.get("report_title", "")).strip()
    if not report_title:
        if focus_type == "client":
            report_title = "Client Report"
        elif focus_type == "legislator":
            report_title = "Legislator Report"
        elif focus_type == "lobbyist":
            report_title = "Lobbyist Report"
        elif focus_type == "bill":
            report_title = "Bill Report"
        else:
            report_title = "Lobby Look-Up Report"

    def _truncate_text(text: str, max_len: int = 80) -> str:
        s = str(text or "").strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 3].rstrip() + "..."

    def _join_top(items: list[str], fallback: str = "Not available") -> str:
        clean = [s for s in items if str(s).strip()]
        return ", ".join(clean) if clean else fallback

    def _amount_mid_sum(series: pd.Series) -> float:
        if series is None or series.empty:
            return 0.0
        s = series.fillna("").astype(str).str.strip()
        s_clean = s.str.replace("$", "", regex=False).str.replace(",", "", regex=False)
        rng = s_clean.str.extract(_MONEY_RANGE)
        rng_lo = pd.to_numeric(rng[0], errors="coerce")
        rng_hi = pd.to_numeric(rng[1], errors="coerce")
        mid = (rng_lo + rng_hi) / 2
        single = pd.to_numeric(s_clean.str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce")
        val = mid.where(mid.notna(), single).fillna(0.0)
        return float(val.sum())

    def _top_counts(series: pd.Series, limit: int = 5) -> list[tuple[str, int]]:
        if series is None or series.empty:
            return []
        clean = series.dropna().astype(str).str.strip()
        clean = clean[clean != ""]
        if clean.empty:
            return []
        counts = clean.value_counts().head(limit)
        return [(idx, int(val)) for idx, val in counts.items()]

    lobbyshort_to_name = {}
    if isinstance(short_to_names, dict) and short_to_names:
        lobbyshort_to_name = {k: (v[0] if v else k) for k, v in short_to_names.items()}
    if not lobbyshort_to_name and isinstance(Lobby_TFL_Client_All, pd.DataFrame) and not Lobby_TFL_Client_All.empty:
        tmp = Lobby_TFL_Client_All[["LobbyShort", "Lobby Name"]].dropna()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
        lobbyshort_to_name = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .first()
            .to_dict()
        )

    def _pos_counts_from_positions(df: pd.DataFrame) -> dict:
        if df.empty:
            return {"Against": 0, "For": 0, "On": 0}
        return {
            "Against": int(df["Position"].astype(str).str.contains("Against", case=False, na=False).sum()),
            "For": int(df["Position"].astype(str).str.contains(r"\bFor\b", case=False, na=False).sum()),
            "On": int(df["Position"].astype(str).str.contains(r"\bOn\b", case=False, na=False).sum()),
        }

    if focus_type == "client":
        client_name = str(fc.get("name", "")).strip()
        if client_name:
            client_rows = ensure_cols(
                base,
                {"Client": "", "LobbyShort": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0, "Lobby Name": ""},
            ).copy()
            _cr_norms = norm_name_series(client_rows["Client"])
            client_rows = client_rows[_cr_norms == norm_name(client_name)]

            focus_section = {"title": f"Client - {client_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            if client_rows.empty:
                focus_section["summary"] = "No client rows were found for the selected scope."
            else:
                client_rows["Mid"] = (client_rows["Low_num"] + client_rows["High_num"]) / 2
                c_total_low = float(client_rows["Low_num"].sum())
                c_total_high = float(client_rows["High_num"].sum())
                c_tfl_low = float(client_rows.loc[client_rows["IsTFL"] == 1, "Low_num"].sum())
                c_tfl_high = float(client_rows.loc[client_rows["IsTFL"] == 1, "High_num"].sum())
                c_pri_low = float(client_rows.loc[client_rows["IsTFL"] == 0, "Low_num"].sum())
                c_pri_high = float(client_rows.loc[client_rows["IsTFL"] == 0, "High_num"].sum())
                lobbyist_count = _unique_count(_series_from(client_rows, "LobbyShort"))
                session_count = _unique_count(_series_from(client_rows, "Session")) if "Session" in client_rows.columns else 0
                is_tfl_client = "Yes" if (client_rows["IsTFL"] == 1).any() else "No"

                focus_section["summary"] = (
                    f"{client_name} is associated with {lobbyist_count:,} lobbyists in this scope "
                    f"and reported compensation ranging from {fmt_usd(c_total_low)} to {fmt_usd(c_total_high)}."
                )
                focus_section["metrics"] = [
                    ("Client", client_name),
                    ("Taxpayer funded", is_tfl_client),
                    ("Lobbyists", f"{lobbyist_count:,}"),
                    ("Total range", f"{fmt_usd(c_total_low)} - {fmt_usd(c_total_high)}"),
                    ("Taxpayer-funded range", f"{fmt_usd(c_tfl_low)} - {fmt_usd(c_tfl_high)}"),
                    ("Private range", f"{fmt_usd(c_pri_low)} - {fmt_usd(c_pri_high)}"),
                ]
                if scope_all and session_count:
                    focus_section["bullets"].append(f"Sessions observed: {session_count:,}")

                lobbyshorts = (
                    client_rows["LobbyShort"].dropna().astype(str).str.strip().unique().tolist()
                )
                lobbyshort_norms = {norm_name(s) for s in lobbyshorts if s}
                lobbyist_names = [
                    lobbyshort_to_name.get(s, s) for s in lobbyshorts
                ]
                lobbyist_norms = set()
                for name in lobbyist_names + lobbyshorts:
                    lobbyist_norms |= norm_person_variants(name)
                    init_key = _last_first_initial_key(name)
                    if init_key:
                        lobbyist_norms.add(init_key)
                lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                bill_count = 0
                policy_count = 0
                top_bill_lines = []
                top_subject_lines = []
                status_counts = []
                bill_list_all = []
                sub_counts = pd.DataFrame()
                if lobbyshorts and not wit.empty and "LobbyShort" in wit.columns:
                    wit = wit[wit["LobbyShort"].astype(str).str.strip().isin(lobbyshorts)]
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    if not wit.empty:
                        pos = bill_position_from_flags(wit)
                        bill_count = int(pos["Bill"].nunique()) if not pos.empty else 0
                        bill_list_all = pos["Bill"].dropna().astype(str).unique().tolist() if not pos.empty else []
                        pos_counts = _pos_counts_from_positions(pos)
                        focus_section["bullets"].append(
                            f"Bills with witness activity (selected session): {bill_count:,}"
                        )
                        focus_section["bullets"].append(
                            f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                        )

                        bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
                        if not bs.empty and "Session" in bs.columns and session_val is not None:
                            bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                        if bill_list_all and not bs.empty and "Bill" in bs.columns:
                            status_counts = _top_counts(
                                bs[bs["Bill"].astype(str).isin(bill_list_all)].get(
                                    "Status", pd.Series(dtype=object)
                                ),
                                4,
                            )

                        if "Bill" in wit.columns:
                            bill_counts = (
                                wit.groupby("Bill").size().reset_index(name="Witness Rows")
                                .sort_values("Witness Rows", ascending=False)
                                .head(5)
                            )
                            if not bill_counts.empty:
                                if not bs.empty and "Bill" in bs.columns:
                                    bs_short = bs.drop_duplicates(subset=["Bill"])
                                    bill_counts = bill_counts.merge(
                                        bs_short[["Bill", "Caption", "Status"]],
                                        on="Bill",
                                        how="left",
                                    )
                                for row in bill_counts.to_dict("records"):
                                    bill = str(row.get("Bill", "")).strip()
                                    count = int(row.get("Witness Rows", 0) or 0)
                                    caption = _truncate_text(row.get("Caption", ""), 70)
                                    status = str(row.get("Status", "")).strip()
                                    line = f"{bill} ({count:,} witness rows)"
                                    if status:
                                        line += f", {status}"
                                    if caption:
                                        line += f" - {caption}"
                                    top_bill_lines.append(line)

                        bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                        if bill_list_all and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                            if session_val is not None and "Session" in bill_sub.columns:
                                bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                            sub_counts = (
                                bill_sub[bill_sub["Bill"].astype(str).isin(bill_list_all)]
                                .groupby("Subject")
                                .size()
                                .reset_index(name="Mentions")
                                .sort_values("Mentions", ascending=False)
                                .head(5)
                            )
                            policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                            for row in sub_counts.to_dict("records"):
                                subject = _truncate_text(row.get("Subject", ""), 60)
                                mentions = int(row.get("Mentions", 0) or 0)
                                if subject:
                                    top_subject_lines.append(f"{subject} ({mentions:,})")

                if bill_count:
                    focus_section["metrics"].append(("Bills w/ witness activity", f"{bill_count:,}"))
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))
                if top_bill_lines:
                    focus_section["bullets"].append(
                        f"Top bills by witness activity: {_join_top(top_bill_lines)}"
                    )
                if top_subject_lines:
                    focus_section["bullets"].append(
                        f"Top policy areas: {_join_top(top_subject_lines)}"
                    )
                if not sub_counts.empty:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Policy Areas (Witness Bills)",
                            "caption": "Focus Chart. Policy areas tied to client-linked witness activity",
                            "data": [
                                {"label": str(r.Subject), "value": int(r.Mentions)}
                                for r in sub_counts.itertuples()
                            ],
                        }
                    )
                if status_counts:
                    status_summary = ", ".join([f"{k} ({v:,})" for k, v in status_counts])
                    focus_section["bullets"].append(f"Bill outcomes (selected session): {status_summary}")

                if not lobby_sub_all.empty:
                    lobby_sub = lobby_sub_all
                    if "Session" in lobby_sub.columns and session_val is not None:
                        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)]
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
                        unnamed0 = lobby_sub.get("Unnamed: 0", lobby_sub.get("Column1", "")).fillna("").astype(str).str.strip()
                        unnamed0 = unnamed0.where(~unnamed0.str.lower().isin(["nan", "none"]), "")
                        topic = lobby_sub["Subject"]
                        topic = topic.where(topic != "", lobby_sub["Other"])
                        topic = topic.where(topic != "", unnamed0)
                        topic = topic.where(topic != "", "Unspecified")
                        lobby_sub["Topic"] = topic
                        topic_counts = _top_counts(lobby_sub["Topic"], 5)
                        if topic_counts:
                            topics = ", ".join([f"{t} ({c:,})" for t, c in topic_counts])
                            focus_section["bullets"].append(f"Reported subject matters: {topics}")

                if not staff_all.empty and lobbyist_norms:
                    staff_df = staff_all
                    staff_session_mask = (
                        staff_df["Session"].astype(str).str.strip() == str(session_val)
                        if "Session" in staff_df.columns and session_val is not None
                        else pd.Series(False, index=staff_df.index)
                    )
                    last_names = {last_name_norm_from_text(n) for n in lobbyist_names if last_name_norm_from_text(n)}
                    init_map = {k: v for k, v in ((_last_first_initial_key(n), n) for n in lobbyist_names) if k}
                    full_map = {norm_name(n): n for n in lobbyist_names if n}
                    last_map = {k: v for k, v in ((last_name_norm_from_text(n), n) for n in lobbyist_names) if k}

                    match_mask = pd.Series(False, index=staff_df.index)
                    match_mask = match_mask | staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    if last_names:
                        match_mask = match_mask | staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)).isin(last_names)
                    if lobbyshort_norms:
                        match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyshort_norms)

                    staff_pick = staff_df[match_mask]
                    staff_pick_session = staff_df[staff_session_mask & match_mask]
                    if not staff_pick.empty:
                        staff_rows = int(len(staff_pick))
                        staff_legs = int(staff_pick.get("Legislator", pd.Series(dtype=object)).nunique()) if "Legislator" in staff_pick.columns else 0
                        focus_section["metrics"].append(("Staff history rows", f"{staff_rows:,}"))
                        if staff_legs:
                            focus_section["metrics"].append(("Legislators w/ staff ties", f"{staff_legs:,}"))
                if lobbyshorts:
                    activities = build_activities_multi(
                        la_food,
                        la_ent,
                        la_tran,
                        la_gift,
                        la_evnt,
                        la_awrd,
                        lobbyshorts=lobbyshorts,
                        session=str(session_val) if session_val is not None else None,
                        name_to_short=name_to_short,
                        lobbyist_norms_tuple=lobbyist_norms_tuple,
                        filerid_to_short=filerid_to_short,
                        lobbyshort_to_name=lobbyshort_to_name,
                    )
                    if not activities.empty:
                        focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                        type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                        if type_counts:
                            types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                            focus_section["bullets"].append(f"Top activity types: {types}")
                        amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                        if amount_total > 0:
                            focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                        focus_section["charts"].append(
                            {
                                "kind": "bar",
                                "orientation": "h",
                                "title": "Activity Types (Rows)",
                                "caption": "Focus Chart. Activity types for client-linked lobbyists",
                                "data": [{"label": t, "value": c} for t, c in type_counts],
                            }
                        )

                    disclosures = build_disclosures_multi(
                        la_cvr,
                        la_dock,
                        la_i4e,
                        la_sub,
                        lobbyshorts=lobbyshorts,
                        session=str(session_val) if session_val is not None else None,
                        name_to_short=name_to_short,
                        lobbyist_norms_tuple=lobbyist_norms_tuple,
                        filerid_to_short=filerid_to_short,
                        lobbyshort_to_name=lobbyshort_to_name,
                    )
                    if not disclosures.empty:
                        focus_section["metrics"].append(("Disclosure rows", f"{len(disclosures):,}"))
                        d_counts = _top_counts(disclosures.get("Type", pd.Series(dtype=object)), 4)
                        if d_counts:
                            types = ", ".join([f"{t} ({c:,})" for t, c in d_counts])
                            focus_section["bullets"].append(f"Top disclosure types: {types}")
                        focus_section["charts"].append(
                            {
                                "kind": "bar",
                                "orientation": "h",
                                "title": "Disclosure Types (Rows)",
                                "caption": "Focus Chart. Disclosure types for client-linked lobbyists",
                                "data": [{"label": t, "value": c} for t, c in d_counts],
                            }
                        )
                lobby_group = (
                    client_rows.groupby("LobbyShort", as_index=False)
                    .agg(Mid=("Mid", "sum"), LobbyName=("Lobby Name", lambda s: s.dropna().astype(str).iloc[0] if len(s) else ""))
                )
                lobby_group["Lobbyist"] = lobby_group["LobbyName"].where(
                    lobby_group["LobbyName"].astype(str).str.strip().ne(""),
                    lobby_group["LobbyShort"],
                )
                top_lobby = lobby_group.sort_values("Mid", ascending=False).head(5)
                chart_data = [
                    {"label": str(r.Lobbyist), "value": float(r.Mid)}
                    for r in top_lobby.itertuples()
                    if float(r.Mid) > 0
                ]
                if chart_data:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Lobbyists by Midpoint Compensation",
                            "caption": "Focus Chart. Top lobbyists by midpoint compensation",
                            "data": chart_data,
                        }
                    )

    if focus_type == "lobbyist":
        lobbyshort = str(fc.get("lobbyshort", "")).strip()
        display_name = str(fc.get("display_name", "")).strip() or lobbyshort
        if lobbyshort:
            lobbyist_norms = set()
            for name in [display_name, lobbyshort]:
                if not name:
                    continue
                lobbyist_norms |= norm_person_variants(name)
                init_key = _last_first_initial_key(name)
                if init_key:
                    lobbyist_norms.add(init_key)
            if isinstance(short_to_names, dict) and lobbyshort in short_to_names:
                for name in short_to_names.get(lobbyshort, []):
                    lobbyist_norms |= norm_person_variants(name)
                    init_key = _last_first_initial_key(name)
                    if init_key:
                        lobbyist_norms.add(init_key)
            lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))
            lobbyshort_norm = norm_name(lobbyshort)

            lobby_rows = ensure_cols(
                base,
                {"Client": "", "LobbyShort": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0},
            )
            lobby_rows = lobby_rows[lobby_rows["LobbyShort"].astype(str).str.strip() == lobbyshort]

            focus_section = {"title": f"Lobbyist - {display_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            if lobby_rows.empty:
                focus_section["summary"] = "No lobbyist rows were found for the selected scope."
            else:
                lobby_rows["Mid"] = (lobby_rows["Low_num"] + lobby_rows["High_num"]) / 2
                l_tfl_low = float(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "Low_num"].sum())
                l_tfl_high = float(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "High_num"].sum())
                l_pri_low = float(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "Low_num"].sum())
                l_pri_high = float(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "High_num"].sum())
                tfl_clients_count = int(lobby_rows.loc[lobby_rows["IsTFL"] == 1, "Client"].nunique())
                pri_clients_count = int(lobby_rows.loc[lobby_rows["IsTFL"] == 0, "Client"].nunique())

                focus_section["summary"] = (
                    f"{display_name} is tied to {tfl_clients_count + pri_clients_count:,} clients in this scope "
                    f"and reported compensation ranging from {fmt_usd(l_tfl_low + l_pri_low)} to {fmt_usd(l_tfl_high + l_pri_high)}."
                )
                focus_section["metrics"] = [
                    ("Lobbyist", display_name),
                    ("Total clients", f"{tfl_clients_count + pri_clients_count:,}"),
                    ("Taxpayer-funded clients", f"{tfl_clients_count:,}"),
                    ("Private clients", f"{pri_clients_count:,}"),
                    ("Taxpayer-funded range", f"{fmt_usd(l_tfl_low)} - {fmt_usd(l_tfl_high)}"),
                    ("Private range", f"{fmt_usd(l_pri_low)} - {fmt_usd(l_pri_high)}"),
                ]

                bill_count = 0
                policy_count = 0
                top_bill_lines = []
                top_subject_lines = []
                status_counts = []
                bill_list_all = []
                sub_counts = pd.DataFrame()

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                if not wit.empty and "LobbyShort" in wit.columns:
                    wit = wit[wit["LobbyShort"].astype(str).str.strip() == lobbyshort]
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    if not wit.empty:
                        pos = bill_position_from_flags(wit)
                        bill_count = int(pos["Bill"].nunique()) if not pos.empty else 0
                        bill_list_all = pos["Bill"].dropna().astype(str).unique().tolist() if not pos.empty else []
                        pos_counts = _pos_counts_from_positions(pos)
                        focus_section["bullets"].append(
                            f"Bills with witness activity (selected session): {bill_count:,}"
                        )
                        focus_section["bullets"].append(
                            f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                        )

                        bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
                        if not bs.empty and "Session" in bs.columns and session_val is not None:
                            bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                        if bill_list_all and not bs.empty and "Bill" in bs.columns:
                            status_counts = _top_counts(
                                bs[bs["Bill"].astype(str).isin(bill_list_all)].get(
                                    "Status", pd.Series(dtype=object)
                                ),
                                4,
                            )

                        if "Bill" in wit.columns:
                            bill_counts = (
                                wit.groupby("Bill").size().reset_index(name="Witness Rows")
                                .sort_values("Witness Rows", ascending=False)
                                .head(5)
                            )
                            if not bill_counts.empty:
                                if not bs.empty and "Bill" in bs.columns:
                                    bs_short = bs.drop_duplicates(subset=["Bill"])
                                    bill_counts = bill_counts.merge(
                                        bs_short[["Bill", "Caption", "Status"]],
                                        on="Bill",
                                        how="left",
                                    )
                                for row in bill_counts.to_dict("records"):
                                    bill = str(row.get("Bill", "")).strip()
                                    count = int(row.get("Witness Rows", 0) or 0)
                                    caption = _truncate_text(row.get("Caption", ""), 70)
                                    status = str(row.get("Status", "")).strip()
                                    line = f"{bill} ({count:,} witness rows)"
                                    if status:
                                        line += f", {status}"
                                    if caption:
                                        line += f" - {caption}"
                                    top_bill_lines.append(line)

                        bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                        if bill_list_all and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                            if session_val is not None and "Session" in bill_sub.columns:
                                bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                            sub_counts = (
                                bill_sub[bill_sub["Bill"].astype(str).isin(bill_list_all)]
                                .groupby("Subject")
                                .size()
                                .reset_index(name="Mentions")
                                .sort_values("Mentions", ascending=False)
                                .head(5)
                            )
                            policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                            for row in sub_counts.to_dict("records"):
                                subject = _truncate_text(row.get("Subject", ""), 60)
                                mentions = int(row.get("Mentions", 0) or 0)
                                if subject:
                                    top_subject_lines.append(f"{subject} ({mentions:,})")

                if bill_count:
                    focus_section["metrics"].append(("Bills w/ witness activity", f"{bill_count:,}"))
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))

                client_mid = (
                    lobby_rows.groupby(["Client", "IsTFL"], as_index=False)
                    .agg(Mid=("Mid", "sum"))
                    .sort_values("Mid", ascending=False)
                )
                tfl_top = client_mid[client_mid["IsTFL"] == 1].head(5)
                pri_top = client_mid[client_mid["IsTFL"] == 0].head(5)
                if not tfl_top.empty:
                    top_tfl = [
                        f"{_truncate_text(r.Client, 50)} ({fmt_usd(r.Mid)})"
                        for r in tfl_top.itertuples()
                    ]
                    focus_section["bullets"].append(f"Top taxpayer-funded clients: {_join_top(top_tfl)}")
                if not pri_top.empty:
                    top_pri = [
                        f"{_truncate_text(r.Client, 50)} ({fmt_usd(r.Mid)})"
                        for r in pri_top.itertuples()
                    ]
                    focus_section["bullets"].append(f"Top private clients: {_join_top(top_pri)}")
                if top_bill_lines:
                    focus_section["bullets"].append(
                        f"Top bills by witness activity: {_join_top(top_bill_lines)}"
                    )
                if top_subject_lines:
                    focus_section["bullets"].append(
                        f"Top policy areas: {_join_top(top_subject_lines)}"
                    )
                if not sub_counts.empty:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Policy Areas (Witness Bills)",
                            "caption": "Focus Chart. Policy areas tied to lobbyist witness activity",
                            "data": [
                                {"label": str(r.Subject), "value": int(r.Mentions)}
                                for r in sub_counts.itertuples()
                            ],
                        }
                    )
                if status_counts:
                    status_summary = ", ".join([f"{k} ({v:,})" for k, v in status_counts])
                    focus_section["bullets"].append(f"Bill outcomes (selected session): {status_summary}")

                if not lobby_sub_all.empty:
                    lobby_sub = lobby_sub_all
                    if "Session" in lobby_sub.columns and session_val is not None:
                        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)]
                    if "LobbyShortNorm" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"] == lobbyshort_norm]
                    elif "LobbyShort" in lobby_sub.columns:
                        lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip() == lobbyshort]
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
                        unnamed0 = lobby_sub.get("Unnamed: 0", lobby_sub.get("Column1", "")).fillna("").astype(str).str.strip()
                        unnamed0 = unnamed0.where(~unnamed0.str.lower().isin(["nan", "none"]), "")
                        topic = lobby_sub["Subject"]
                        topic = topic.where(topic != "", lobby_sub["Other"])
                        topic = topic.where(topic != "", unnamed0)
                        topic = topic.where(topic != "", "Unspecified")
                        lobby_sub["Topic"] = topic
                        topic_counts = _top_counts(lobby_sub["Topic"], 5)
                        if topic_counts:
                            topics = ", ".join([f"{t} ({c:,})" for t, c in topic_counts])
                            focus_section["bullets"].append(f"Reported subject matters: {topics}")

                if not staff_all.empty and lobbyist_norms:
                    staff_df = staff_all
                    staff_session_mask = (
                        staff_df["Session"].astype(str).str.strip() == str(session_val)
                        if "Session" in staff_df.columns and session_val is not None
                        else pd.Series(False, index=staff_df.index)
                    )
                    last_names = {last_name_norm_from_text(n) for n in [display_name, lobbyshort] if last_name_norm_from_text(n)}

                    match_mask = pd.Series(False, index=staff_df.index)
                    match_mask = match_mask | staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    match_mask = match_mask | staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(lobbyist_norms)
                    if last_names:
                        match_mask = match_mask | staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)).isin(last_names)
                    if lobbyshort_norm:
                        match_mask = match_mask | (
                            staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm
                        )

                    staff_pick = staff_df[match_mask]
                    staff_pick_session = staff_df[staff_session_mask & match_mask]
                    if not staff_pick.empty:
                        staff_rows = int(len(staff_pick))
                        staff_legs = int(staff_pick.get("Legislator", pd.Series(dtype=object)).nunique()) if "Legislator" in staff_pick.columns else 0
                        focus_section["metrics"].append(("Staff history rows", f"{staff_rows:,}"))
                        if staff_legs:
                            focus_section["metrics"].append(("Legislators w/ staff ties", f"{staff_legs:,}"))
                activities = build_activities(
                    la_food,
                    la_ent,
                    la_tran,
                    la_gift,
                    la_evnt,
                    la_awrd,
                    lobbyshort=lobbyshort,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    lobbyist_norms_tuple=lobbyist_norms_tuple,
                    filerid_to_short=filerid_to_short,
                )
                if not activities.empty:
                    focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                    type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                    if type_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                        focus_section["bullets"].append(f"Top activity types: {types}")
                    amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                    if amount_total > 0:
                        focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Activity Types (Rows)",
                            "caption": "Focus Chart. Activity types for the selected lobbyist",
                            "data": [{"label": t, "value": c} for t, c in type_counts],
                        }
                    )

                disclosures = build_disclosures(
                    la_cvr,
                    la_dock,
                    la_i4e,
                    la_sub,
                    lobbyshort=lobbyshort,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    lobbyist_norms_tuple=lobbyist_norms_tuple,
                    filerid_to_short=filerid_to_short,
                )
                if not disclosures.empty:
                    focus_section["metrics"].append(("Disclosure rows", f"{len(disclosures):,}"))
                    d_counts = _top_counts(disclosures.get("Type", pd.Series(dtype=object)), 4)
                    if d_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in d_counts])
                        focus_section["bullets"].append(f"Top disclosure types: {types}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Disclosure Types (Rows)",
                            "caption": "Focus Chart. Disclosure types for the selected lobbyist",
                            "data": [{"label": t, "value": c} for t, c in d_counts],
                        }
                    )

                client_group = (
                    lobby_rows.groupby("Client", as_index=False)
                    .agg(Mid=("Mid", "sum"))
                    .sort_values("Mid", ascending=False)
                    .head(5)
                )
                chart_data = [
                    {"label": str(r.Client), "value": float(r.Mid)}
                    for r in client_group.itertuples()
                    if float(r.Mid) > 0
                ]
                if chart_data:
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Top Clients by Midpoint Compensation",
                            "caption": "Focus Chart. Top clients by midpoint compensation",
                            "data": chart_data,
                        }
                    )

    if focus_type == "legislator":
        member_name = str(fc.get("name", "")).strip()
        if member_name:
            focus_section = {"title": f"Legislator - {member_name}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            member_info = parse_member_name(member_name)
            authored_all = build_author_bill_index(Bill_Status_All) if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
            if authored_all.empty:
                focus_section["summary"] = "No authored bill data was available for the selected session."
            else:
                authored = authored_all
                authored = authored[authored["AuthorNorm"] == norm_name(member_name)]
                if session_val is not None and "Session" in authored.columns:
                    authored = authored[authored["Session"].astype(str).str.strip() == str(session_val)]

                bill_count = int(authored["Bill"].nunique()) if not authored.empty else 0
                passed = int((authored.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not authored.empty else 0
                failed = int((authored.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not authored.empty else 0
                bill_list = authored["Bill"].dropna().astype(str).unique().tolist() if not authored.empty else []

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                witness = pd.DataFrame()
                if bill_list and not wit.empty:
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                    wit = wit[wit["Bill"].astype(str).isin(bill_list)] if "Bill" in wit.columns else wit.iloc[0:0]
                    witness = bill_position_from_flags(wit) if not wit.empty else pd.DataFrame()
                    if not witness.empty:
                        witness = witness.merge(tfl_flag, on="LobbyShort", how="left")
                        witness["IsTFL"] = pd.to_numeric(witness.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

                any_witness = int(witness["Bill"].nunique()) if not witness.empty else 0
                tfl_opposed = 0
                lobbyist_count = int(witness["LobbyShort"].nunique()) if not witness.empty and "LobbyShort" in witness.columns else 0
                tfl_lobbyist_count = int(witness.loc[witness["IsTFL"] == 1, "LobbyShort"].nunique()) if not witness.empty and "LobbyShort" in witness.columns else 0
                if not witness.empty:
                    against_mask = witness["Position"].astype(str).str.contains("Against", case=False, na=False)
                    tfl_mask = witness["IsTFL"] == 1
                    tfl_opposed = int(witness.loc[against_mask & tfl_mask, "Bill"].nunique())

                focus_section["summary"] = (
                    f"{member_name} authored {bill_count:,} bills in the selected session, with "
                    f"{passed:,} passed and {failed:,} failed."
                )
                focus_section["metrics"] = [
                    ("Bills authored", f"{bill_count:,}"),
                    ("Passed / Failed", f"{passed:,} / {failed:,}"),
                    ("Bills with witness activity", f"{any_witness:,}"),
                    ("Bills opposed by TFL lobbyists", f"{tfl_opposed:,}"),
                    ("Unique lobbyists", f"{lobbyist_count:,}"),
                    ("Lobbyists w/ TFL clients", f"{tfl_lobbyist_count:,}"),
                ]

                top_bills_lines = []
                if not authored.empty:
                    authored_unique = authored.drop_duplicates(subset=["Bill"])
                    status_rank = authored_unique.get("Status", pd.Series(dtype=object)).map(
                        {"Passed": 0, "Failed": 1}
                    ).fillna(2)
                    authored_unique = authored_unique.assign(_rank=status_rank)
                    top_authored = authored_unique.sort_values(["_rank", "Bill"]).head(5)
                    for row in top_authored.to_dict("records"):
                        bill = str(row.get("Bill", "")).strip()
                        status = str(row.get("Status", "")).strip()
                        caption = _truncate_text(row.get("Caption", ""), 70)
                        line = bill
                        if status:
                            line += f" ({status})"
                        if caption:
                            line += f" - {caption}"
                        if line.strip():
                            top_bills_lines.append(line)

                policy_count = 0
                top_subject_lines = []
                bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
                if bill_list and not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                    if session_val is not None and "Session" in bill_sub.columns:
                        bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                    sub_counts = (
                        bill_sub[bill_sub["Bill"].astype(str).isin(bill_list)]
                        .groupby("Subject")
                        .size()
                        .reset_index(name="Mentions")
                        .sort_values("Mentions", ascending=False)
                        .head(5)
                    )
                    policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                    for row in sub_counts.to_dict("records"):
                        subject = _truncate_text(row.get("Subject", ""), 60)
                        mentions = int(row.get("Mentions", 0) or 0)
                        if subject:
                            top_subject_lines.append(f"{subject} ({mentions:,})")

                if top_bills_lines:
                    focus_section["bullets"].append(f"Top authored bills: {_join_top(top_bills_lines)}")
                if top_subject_lines:
                    focus_section["bullets"].append(f"Top policy areas: {_join_top(top_subject_lines)}")
                if policy_count:
                    focus_section["metrics"].append(("Policy areas", f"{policy_count:,}"))

                if not witness.empty:
                    pos_counts = _pos_counts_from_positions(witness)
                    focus_section["bullets"].append(
                        f"Witness positions - Against {pos_counts['Against']:,}, For {pos_counts['For']:,}, On {pos_counts['On']:,}."
                    )
                    if "LobbyShort" in witness.columns:
                        top_lobby = (
                            witness.groupby("LobbyShort")
                            .size()
                            .reset_index(name="Rows")
                            .sort_values("Rows", ascending=False)
                            .head(5)
                        )
                        top_lobby_lines = []
                        top_lobby_chart = []
                        for row in top_lobby.to_dict("records"):
                            short = str(row.get("LobbyShort", "")).strip()
                            rows = int(row.get("Rows", 0) or 0)
                            label = lobbyshort_to_name.get(short, short)
                            if label:
                                top_lobby_lines.append(f"{label} ({rows:,} rows)")
                                top_lobby_chart.append({"label": label, "value": rows})
                        if top_lobby_lines:
                            focus_section["bullets"].append(
                                f"Top lobbyists on witness lists: {_join_top(top_lobby_lines)}"
                            )
                        if top_lobby_chart:
                            focus_section["charts"].append(
                                {
                                    "kind": "bar",
                                    "orientation": "h",
                                    "title": "Top Lobbyists on Witness Lists",
                                    "caption": "Focus Chart. Lobbyists with the most witness-list rows",
                                    "data": top_lobby_chart,
                                }
                            )

                    if "IsTFL" in witness.columns:
                        counts = []
                        for funding_label, mask in [
                            ("Taxpayer Funded", witness["IsTFL"] == 1),
                            ("Private", witness["IsTFL"] != 1),
                        ]:
                            subset = witness[mask]
                            pos_counts = _pos_counts_from_positions(subset)
                            for position in ["Against", "For", "On"]:
                                counts.append(
                                    {
                                        "Position": position,
                                        "Funding": funding_label,
                                        "Count": int(pos_counts.get(position, 0)),
                                    }
                                )
                        if counts:
                            focus_section["charts"].append(
                                {
                                    "kind": "grouped_bar",
                                    "title": "Witness Positions by Funding Type",
                                    "caption": "Focus Chart. Witness positions by funding type",
                                    "data": counts,
                                }
                            )

                activities = build_member_activities(
                    la_food,
                    la_ent,
                    la_tran,
                    la_gift,
                    la_evnt,
                    la_awrd,
                    member_name=member_name,
                    session=str(session_val) if session_val is not None else None,
                    name_to_short=name_to_short,
                    filerid_to_short=filerid_to_short,
                    lobbyshort_to_name=lobbyshort_to_name,
                )
                if not activities.empty:
                    focus_section["metrics"].append(("Activity rows", f"{len(activities):,}"))
                    type_counts = _top_counts(activities.get("Type", pd.Series(dtype=object)), 4)
                    if type_counts:
                        types = ", ".join([f"{t} ({c:,})" for t, c in type_counts])
                        focus_section["bullets"].append(f"Top activity types: {types}")
                    amount_total = _amount_mid_sum(activities.get("Amount", pd.Series(dtype=object)))
                    if amount_total > 0:
                        focus_section["bullets"].append(f"Reported activity amount (midpoint): {fmt_usd(amount_total)}")
                    focus_section["charts"].append(
                        {
                            "kind": "bar",
                            "orientation": "h",
                            "title": "Activity Types (Rows)",
                            "caption": "Focus Chart. Activity types linked to the legislator",
                            "data": [{"label": t, "value": c} for t, c in type_counts],
                        }
                    )

                staff_matches = pd.DataFrame()
                if not staff_all.empty and "Legislator" in staff_all.columns:
                    staff_df = staff_all
                    leg_norm = norm_name_series(staff_df["Legislator"])
                    leg_last_norm = last_name_norm_series(staff_df["Legislator"])
                    leg_init_key = staff_df["Legislator"].fillna("").astype(str).map(_last_first_initial_key)

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

                if not staff_matches.empty:
                    focus_section["metrics"].append(("Staff history rows", f"{len(staff_matches):,}"))
                    staffer_count = int(staff_matches.get("Staffer", pd.Series(dtype=object)).nunique()) if "Staffer" in staff_matches.columns else 0
                    if staffer_count:
                        focus_section["metrics"].append(("Staffers", f"{staffer_count:,}"))
                    top_staffers = _top_counts(staff_matches.get("Staffer", pd.Series(dtype=object)), 5)
                    if top_staffers:
                        staffer_list = ", ".join([f"{s} ({c:,})" for s, c in top_staffers])
                        focus_section["bullets"].append(f"Top staffers in history: {staffer_list}")

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
                    if not staff_lobbyists.empty:
                        focus_section["metrics"].append(
                            ("Staffers who became lobbyists", f"{staff_lobbyists['Staffer'].nunique():,}")
                        )
                        staff_lobbyists["Lobbyist"] = staff_lobbyists["LobbyShort"].map(lobbyshort_to_name).fillna(staff_lobbyists["LobbyShort"])
                        top_lobbyists = _top_counts(staff_lobbyists.get("Lobbyist", pd.Series(dtype=object)), 5)
                        if top_lobbyists:
                            lobbyist_list = ", ".join([f"{l} ({c:,})" for l, c in top_lobbyists])
                            focus_section["bullets"].append(f"Staff-to-lobbyist matches: {lobbyist_list}")

                chart_data = [
                    {"label": "Bills authored", "value": bill_count},
                    {"label": "Bills with witness activity", "value": any_witness},
                    {"label": "Bills opposed by TFL lobbyists", "value": tfl_opposed},
                ]
                focus_section["charts"].append(
                    {
                        "kind": "bar",
                        "orientation": "v",
                        "title": "Legislator Focus Metrics",
                        "caption": "Focus Chart. Legislator summary metrics",
                        "data": chart_data,
                    }
                )

    if focus_type == "bill":
        bill_id = str(fc.get("bill", "")).strip()
        if bill_id:
            bill_norm = bill_id
            try:
                bill_norm = normalize_bill(bill_id) or bill_id
            except Exception:
                bill_norm = bill_id
            bill_id = bill_norm
            focus_section = {"title": f"Bill - {bill_id}", "summary": "", "metrics": [], "bullets": [], "charts": []}
            bs = Bill_Status_All if isinstance(Bill_Status_All, pd.DataFrame) else pd.DataFrame()
            caption = ""
            status = ""
            author = ""
            if not bs.empty and "Bill" in bs.columns:
                bs = bs.copy()
                if session_val is not None and "Session" in bs.columns:
                    bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)]
                try:
                    bs["BillNorm"] = bs["Bill"].astype(str).map(normalize_bill)
                except Exception:
                    bs["BillNorm"] = bs["Bill"].astype(str).str.strip()
                bs_match = bs[bs["BillNorm"] == bill_id]
                if not bs_match.empty:
                    caption = str(bs_match.get("Caption", pd.Series([""])).iloc[0]).strip()
                    status = str(bs_match.get("Status", pd.Series([""])).iloc[0]).strip()
                    for col in ["Author", "Authors"]:
                        if col in bs_match.columns:
                            author = str(bs_match.get(col, pd.Series([""])).iloc[0]).strip()
                            if author:
                                break

            wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
            pos = pd.DataFrame()
            if not wit.empty and "Bill" in wit.columns:
                wit = wit.copy()
                if session_val is not None and "Session" in wit.columns:
                    wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)]
                try:
                    wit["Bill"] = wit["Bill"].astype(str).map(normalize_bill)
                except Exception:
                    wit["Bill"] = wit["Bill"].astype(str).str.strip()
                wit = wit[wit["Bill"] == bill_id]
                if not wit.empty:
                    pos = bill_position_from_flags(wit)
                    if not pos.empty:
                        pos = pos.merge(tfl_flag, on="LobbyShort", how="left")
                        pos["IsTFL"] = pd.to_numeric(pos.get("IsTFL", 0), errors="coerce").fillna(0).astype(int)

            unique_lobbyists = int(pos["LobbyShort"].nunique()) if not pos.empty else 0
            org_series = wit.get("org", pd.Series(dtype=object)) if isinstance(wit, pd.DataFrame) else pd.Series(dtype=object)
            org_counts = _top_counts(org_series, 5)
            unique_orgs = int(org_series.dropna().astype(str).str.strip().nunique()) if not org_series.empty else 0

            witness_rows = int(len(wit)) if isinstance(wit, pd.DataFrame) else 0
            tfl_opposed = 0
            top_lobbyist_lines = []
            subject_lines = []
            tfl_witness_rows = 0
            private_witness_rows = 0
            if not pos.empty:
                against_mask = pos["Position"].astype(str).str.contains("Against", case=False, na=False)
                tfl_mask = pos["IsTFL"] == 1
                tfl_opposed = int(pos.loc[against_mask & tfl_mask, "LobbyShort"].nunique())
                tfl_witness_rows = int(pos.loc[tfl_mask, "LobbyShort"].nunique())
                private_witness_rows = int(pos.loc[~tfl_mask, "LobbyShort"].nunique())

                if "LobbyShort" in pos.columns:
                    name_map = {}
                    lt = Lobby_TFL_Client_All if isinstance(Lobby_TFL_Client_All, pd.DataFrame) else pd.DataFrame()
                    if not lt.empty and {"LobbyShort", "Lobby Name"}.issubset(lt.columns):
                        tmp = lt[["LobbyShort", "Lobby Name"]].dropna()
                        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
                        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
                        name_map = (
                            tmp.groupby("LobbyShort")["Lobby Name"]
                            .first()
                            .to_dict()
                        )

                    counts = (
                        pos.groupby("LobbyShort")
                        .size()
                        .reset_index(name="Rows")
                        .sort_values("Rows", ascending=False)
                        .head(5)
                    )
                    for row in counts.to_dict("records"):
                        short = str(row.get("LobbyShort", "")).strip()
                        rows = int(row.get("Rows", 0) or 0)
                        name = name_map.get(short, "")
                        label = f"{short}"
                        if name:
                            label = f"{name} ({short})"
                        top_lobbyist_lines.append(f"{label} ({rows:,} rows)")

            focus_section["summary"] = (
                f"{bill_id} has {witness_rows:,} witness-list rows in the selected session."
            )
            focus_section["metrics"] = [
                ("Bill", bill_id),
                ("Status", status or "Unknown"),
                ("Witness rows", f"{witness_rows:,}"),
                ("Unique lobbyists", f"{unique_lobbyists:,}"),
                ("TFL lobbyists opposed", f"{tfl_opposed:,}"),
                ("TFL lobbyists (any position)", f"{tfl_witness_rows:,}"),
                ("Private lobbyists (any position)", f"{private_witness_rows:,}"),
            ]
            if unique_orgs:
                focus_section["metrics"].append(("Organizations", f"{unique_orgs:,}"))
            if caption:
                focus_section["bullets"].append(f"Caption: {caption}")
            if author:
                focus_section["bullets"].append(f"Author: {author}")

            if top_lobbyist_lines:
                focus_section["bullets"].append(
                    f"Top lobbyists by witness rows: {_join_top(top_lobbyist_lines)}"
                )
            if org_counts:
                org_lines = [f"{_truncate_text(n, 60)} ({c:,})" for n, c in org_counts]
                focus_section["bullets"].append(
                    f"Top organizations on witness lists: {_join_top(org_lines)}"
                )
                focus_section["charts"].append(
                    {
                        "kind": "bar",
                        "orientation": "h",
                        "title": "Top Witness Organizations",
                        "caption": "Focus Chart. Organizations with the most witness-list rows",
                        "data": [{"label": n, "value": c} for n, c in org_counts],
                    }
                )

            bill_sub = Bill_Sub_All if isinstance(Bill_Sub_All, pd.DataFrame) else pd.DataFrame()
            if not bill_sub.empty and {"Bill", "Subject"}.issubset(bill_sub.columns):
                if session_val is not None and "Session" in bill_sub.columns:
                    bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)]
                bill_sub = bill_sub.copy()
                bill_sub["BillNorm"] = bill_sub["Bill"].astype(str).map(normalize_bill)
                sub_rows = bill_sub[bill_sub["BillNorm"] == bill_id]
                if not sub_rows.empty:
                    subjects = sub_rows["Subject"].dropna().astype(str).str.strip().unique().tolist()
                    for subject in subjects[:6]:
                        subject_lines.append(_truncate_text(subject, 70))
            if subject_lines:
                focus_section["bullets"].append(f"Subjects: {_join_top(subject_lines)}")

            if not pos.empty:
                counts = []
                for funding_label, mask in [
                    ("Taxpayer Funded", pos["IsTFL"] == 1),
                    ("Private", pos["IsTFL"] != 1),
                ]:
                    subset = pos[mask]
                    pos_counts = _pos_counts_from_positions(subset)
                    for position in ["Against", "For", "On"]:
                        counts.append(
                            {
                                "Position": position,
                                "Funding": funding_label,
                                "Count": int(pos_counts.get(position, 0)),
                            }
                        )
                focus_section["charts"].append(
                    {
                        "kind": "grouped_bar",
                        "title": "Witness Positions by Funding Type",
                        "caption": "Focus Chart. Witness positions by funding type",
                        "data": counts,
                    }
                )

    tfl_mid = (tfl_low + tfl_high) / 2
    private_mid = (private_low + private_high) / 2
    total_mid = tfl_mid + private_mid
    tfl_mid_share_pct = (tfl_mid / total_mid * 100) if total_mid > 0 else 0.0

    if total_mid <= 0:
        conditional_share_sentence = (
            "No reportable lobbying compensation was identified for the selected scope."
        )
        conditional_balance_sentence = ""
    else:
        if tfl_mid_share_pct >= 50:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a majority share "
                "of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share_pct >= 35:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a substantial "
                "share of reported lobbying compensation in this scope."
            )
        elif tfl_mid_share_pct >= 15:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a material, "
                "non-trivial share of reported lobbying compensation in this scope."
            )
        else:
            conditional_share_sentence = (
                "Midpoint estimates indicate taxpayer-funded entities represent a smaller share "
                "of reported lobbying compensation in this scope."
            )

        mix_delta = tfl_mid - private_mid
        if abs(mix_delta) <= (0.10 * total_mid):
            conditional_balance_sentence = (
                "The midpoint funding mix is near parity between taxpayer-funded and private activity."
            )
        elif mix_delta > 0:
            conditional_balance_sentence = (
                "The midpoint funding mix shows taxpayer-funded activity outweighing private activity."
            )
        else:
            conditional_balance_sentence = (
                "The midpoint funding mix shows private activity outweighing taxpayer-funded activity."
            )

    tfl_w = witness_counts.get("tfl", {}) if isinstance(witness_counts, dict) else {}
    pri_w = witness_counts.get("private", {}) if isinstance(witness_counts, dict) else {}
    tfl_against = int(tfl_w.get("Against", 0) or 0)
    tfl_for = int(tfl_w.get("For", 0) or 0)
    tfl_on = int(tfl_w.get("On", 0) or 0)
    pri_against = int(pri_w.get("Against", 0) or 0)
    pri_for = int(pri_w.get("For", 0) or 0)
    pri_on = int(pri_w.get("On", 0) or 0)
    witness_total = tfl_against + tfl_for + tfl_on + pri_against + pri_for + pri_on
    if witness_total <= 0:
        conditional_witness_sentence = (
            "No witness-position activity was available in the selected scope/session."
        )
    else:
        if tfl_against >= max(tfl_for, tfl_on):
            stance_text = "taxpayer-funded testimony skews toward opposition"
        elif tfl_for >= max(tfl_against, tfl_on):
            stance_text = "taxpayer-funded testimony skews toward support"
        else:
            stance_text = "taxpayer-funded testimony is mixed across positions"
        conditional_witness_sentence = (
            f"In witness data, {stance_text} "
            f"({tfl_against:,} Against, {tfl_for:,} For, {tfl_on:,} On)."
        )

    if focus_type == "client":
        conditional_focus_sentence = (
            "Focus findings are client-centered and update as the selected client changes."
        )
        focus_highlights_intro = (
            "Key client-specific findings generated from the current scope and linked lobbyist activity."
        )
    elif focus_type == "lobbyist":
        conditional_focus_sentence = (
            "Focus findings are lobbyist-centered and update as the selected lobbyist changes."
        )
        focus_highlights_intro = (
            "Key lobbyist-specific findings generated from the current scope and linked client activity."
        )
    elif focus_type == "legislator":
        conditional_focus_sentence = (
            "Focus findings are legislator-centered and update as the selected legislator changes."
        )
        focus_highlights_intro = (
            "Key legislator-specific findings generated from authored-bill, witness, and activity data."
        )
    elif focus_type == "bill":
        conditional_focus_sentence = (
            "Focus findings are bill-centered and update as the selected bill changes."
        )
        focus_highlights_intro = (
            "Key bill-specific findings generated from witness, status, and subject-matter records."
        )
    else:
        conditional_focus_sentence = (
            "Focus findings are generated from the current filters and update as inputs change."
        )
        focus_highlights_intro = "Most relevant findings for the selected focus."

    conditional_exec_sentences = [
        s
        for s in [
            conditional_share_sentence,
            conditional_balance_sentence,
            conditional_witness_sentence,
        ]
        if str(s).strip()
    ]

    payload = {
        "session_label": session_label,
        "generated_date": generated_date,
        "generated_ts": generated_ts,
        "report_id": report_id,
        "scope_label": scope_label,
        "focus_label": focus_label,
        "filter_summary": filter_summary,
        "selected_lobbyist": selected_lobbyist,
        "total_low_value": total_low,
        "total_high_value": total_high,
        "tfl_low_value": tfl_low,
        "tfl_high_value": tfl_high,
        "private_low_value": private_low,
        "private_high_value": private_high,
        "total_low": fmt_usd(total_low),
        "total_high": fmt_usd(total_high),
        "tfl_low": fmt_usd(tfl_low),
        "tfl_high": fmt_usd(tfl_high),
        "private_low": fmt_usd(private_low),
        "private_high": fmt_usd(private_high),
        "tfl_share_low_pct": f"{tfl_share_low_pct:.1f}",
        "tfl_share_high_pct": f"{tfl_share_high_pct:.1f}",
        "tfl_share_low_pct_value": tfl_share_low_pct,
        "tfl_share_high_pct_value": tfl_share_high_pct,
        "private_share_low_pct_value": private_share_low_pct,
        "private_share_high_pct_value": private_share_high_pct,
        "funding_mix": funding_mix,
        "unique_lobbyists_total": f"{unique_lobbyists_total:,}",
        "unique_lobbyists_tfl": f"{unique_lobbyists_tfl:,}",
        "unique_clients_total": f"{unique_clients_total:,}",
        "unique_clients_tfl": f"{unique_clients_tfl:,}",
        "top_clients_tfl": top_clients_tfl,
        "top_clients_private": top_clients_private,
        "chart_compensation_bar": chart_compensation_bar,
        "chart_share": chart_share,
        "chart_entity_types": chart_entity_types,
        "chart_entity_types_data": entity_type_counts,
        "witness_activity_summary": witness_summary,
        "chart_witness_positions": chart_witness_positions,
        "witness_counts": witness_counts,
        "chart_top_bills": chart_top_bills,
        "chart_top_subjects": chart_top_subjects,
        "existing_law_gap_summary": existing_law_gap_summary,
        "recommended_fix_statute": recommended_fix_statute,
        "implementation_notes": implementation_notes,
        "data_sources_bullets": data_sources_bullets,
        "disclaimer_note": disclaimer_note,
        "report_title": report_title,
        "scope_session_label": scope_session_label,
        "scope_note": scope_note,
        "has_top_bills": bool(top_bills),
        "has_top_subjects": bool(top_subjects),
        "top_bills": top_bills,
        "top_subjects": top_subjects,
        "focus_section": focus_section,
        "conditional_exec_sentences": conditional_exec_sentences,
        "conditional_focus_sentence": conditional_focus_sentence,
        "focus_highlights_intro": focus_highlights_intro,
        "tfl_mid_share_pct_value": tfl_mid_share_pct,
    }

    for i in range(5):
        if i < len(top_bills):
            b = top_bills[i]
            payload[f"bill_{i + 1}_id"] = b["id"]
            payload[f"bill_{i + 1}_caption"] = b["caption"]
            payload[f"bill_{i + 1}_opp_count"] = f"{b['tfl']:,}"
            payload[f"bill_{i + 1}_private_opp"] = f"{b['private']:,}"
            payload[f"bill_{i + 1}_summary"] = b["summary"]
        else:
            payload[f"bill_{i + 1}_id"] = "-"
            payload[f"bill_{i + 1}_caption"] = "-"
            payload[f"bill_{i + 1}_opp_count"] = "0"
            payload[f"bill_{i + 1}_private_opp"] = "0"
            payload[f"bill_{i + 1}_summary"] = "No summary available."

    for i in range(5):
        if i < len(top_subjects):
            s = top_subjects[i]
            payload[f"subject_{i + 1}"] = s["Subject"]
            payload[f"subject_{i + 1}_opp_count"] = f"{int(s['Oppositions']):,}"
        else:
            payload[f"subject_{i + 1}"] = "-"
            payload[f"subject_{i + 1}_opp_count"] = "0"

    return payload

__all__ = [
    '_build_report_payload',
    '_clean_options',
    '_hydrate_report_inputs',
    '_slugify',
]
