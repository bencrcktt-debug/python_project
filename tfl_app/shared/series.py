from __future__ import annotations

import pandas as pd


def first_nonempty(series: pd.Series) -> str:
    if series is None or len(series) == 0:
        return ""
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    return values.iloc[0] if not values.empty else ""


def vectorized_person_display(org: pd.Series, last: pd.Series, first: pd.Series) -> pd.Series:
    """Build display labels without row-wise apply calls."""
    org_s = org.fillna("").astype(str).str.strip()
    last_s = last.fillna("").astype(str).str.strip()
    first_s = first.fillna("").astype(str).str.strip()

    result = org_s.where(org_s != "", last_s + ", " + first_s)
    both = (last_s != "") & (first_s != "")
    only_last = (last_s != "") & (first_s == "")
    only_first = (last_s == "") & (first_s != "")
    neither = (last_s == "") & (first_s == "")
    no_org = org_s == ""

    result = result.where(~no_org, pd.Series("", index=org.index))
    result[no_org & both] = last_s[no_org & both] + ", " + first_s[no_org & both]
    result[no_org & only_last] = last_s[no_org & only_last]
    result[no_org & only_first] = first_s[no_org & only_first]
    result[no_org & neither] = ""
    result[~no_org] = org_s[~no_org]
    return result.str.strip()


def vectorized_amount_display(
    exact: pd.Series,
    low: pd.Series,
    high: pd.Series,
    code: pd.Series | None = None,
) -> pd.Series:
    """Build displayable amount labels without row-wise apply calls."""
    exact_s = exact.fillna("").astype(str).str.strip()
    low_s = low.fillna("").astype(str).str.strip()
    high_s = high.fillna("").astype(str).str.strip()
    code_s = code.fillna("").astype(str).str.strip() if code is not None else pd.Series("", index=exact.index)

    result = pd.Series("", index=exact.index)
    has_exact = exact_s != ""
    has_low = low_s != ""
    has_high = high_s != ""
    has_code = code_s != ""

    result = result.where(~has_exact, exact_s)
    need_range = ~has_exact & has_low & has_high
    result[need_range] = low_s[need_range] + "--" + high_s[need_range]
    need_low_only = ~has_exact & has_low & ~has_high
    result[need_low_only] = low_s[need_low_only]
    need_code = ~has_exact & ~has_low & has_code
    result[need_code] = code_s[need_code]
    return result
