from __future__ import annotations

import pandas as pd

from tfl_app.shared.sessions import session_series


STAFF_METRIC_COLUMNS = ["Legislator", "% Against that Failed", "% For that Passed"]


def staff_metrics(
    staff_rows: pd.DataFrame,
    bills_df: pd.DataFrame,
    session_val: str,
    bill_status_all: pd.DataFrame,
) -> pd.DataFrame:
    if staff_rows.empty or bills_df.empty:
        return pd.DataFrame(columns=STAFF_METRIC_COLUMNS)

    legislators = sorted(staff_rows["Legislator"].dropna().astype(str).unique().tolist())
    rows: list[dict[str, object]] = []
    session_key = str(session_val or "").strip()
    authored_source = bill_status_all[session_series(bill_status_all) == session_key]

    for legislator in legislators:
        authored = authored_source[
            authored_source["Author"].fillna("").astype(str).str.contains(legislator, case=False, na=False)
        ][["Session", "Bill", "Status"]]
        if authored.empty:
            rows.append({"Legislator": legislator, "% Against that Failed": None, "% For that Passed": None})
            continue

        joined = authored.merge(
            bills_df[["Session", "Bill", "Position", "Status"]],
            on=["Session", "Bill"],
            how="inner",
            suffixes=("_authored", "_witness"),
        )
        if joined.empty:
            rows.append({"Legislator": legislator, "% Against that Failed": None, "% For that Passed": None})
            continue

        status_col = "Status"
        if status_col not in joined.columns:
            if "Status_authored" in joined.columns:
                status_col = "Status_authored"
            elif "Status_witness" in joined.columns:
                status_col = "Status_witness"

        against = joined[joined["Position"].astype(str).str.contains("Against", na=False)]
        denom_against = len(against)
        pct_against_failed = (against[status_col].eq("Failed").sum() / denom_against) if denom_against else None

        support = joined[joined["Position"].astype(str).str.contains(r"\bFor\b", regex=True, na=False)]
        denom_support = len(support)
        pct_support_passed = (support[status_col].eq("Passed").sum() / denom_support) if denom_support else None

        rows.append(
            {
                "Legislator": legislator,
                "% Against that Failed": pct_against_failed,
                "% For that Passed": pct_support_passed,
            }
        )

    return pd.DataFrame(rows)
