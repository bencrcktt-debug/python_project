from __future__ import annotations

import re
from typing import Any

import pandas as pd


_SESSION_BASE_YEAR = 2023
_SESSION_BASE_NUM = 88


def ordinal(value: int) -> str:
    if 10 <= (value % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def session_label(session_val: str | None) -> str:
    text = str(session_val or "").strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return ""
    if text.isdigit():
        if len(text) >= 3:
            base = text[:-1]
            special = text[-1]
            if base.isdigit() and special.isdigit():
                return f"{base}R / {ordinal(int(special))} Special"
        return ordinal(int(text))
    return text


def session_long_label(session_val: str | None) -> str:
    text = str(session_val or "").strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return ""
    if text.isdigit() and len(text) >= 3:
        base = text[:-1]
        special = text[-1]
        if base.isdigit() and special.isdigit():
            return f"{ordinal(int(base))} {ordinal(int(special))} Special Session"
    match = re.match(r"^(\d+)\s*R$", text, flags=re.IGNORECASE)
    if match:
        return f"{ordinal(int(match.group(1)))} Regular Session"
    if text.isdigit():
        return f"{ordinal(int(text))} Regular Session"
    match = re.search(r"(\d+).*(\d+)(?:st|nd|rd|th)?\s*Special", text, flags=re.IGNORECASE)
    if match:
        return f"{ordinal(int(match.group(1)))} {ordinal(int(match.group(2)))} Special Session"
    return text


def session_sort_key(session_val: str | None) -> tuple[int, int, int]:
    text = str(session_val or "").strip()
    if not text:
        return (0, 2, 0)
    if text.isdigit():
        base = int(text[:-1]) if len(text) >= 2 else int(text)
        special = int(text[-1]) if len(text) >= 2 else 0
        return (base, 1, special)
    match = re.match(r"^(\d+)\s*R$", text, flags=re.IGNORECASE)
    if match:
        return (int(match.group(1)), 0, 0)
    return (0, 2, 0)


def default_session_from_list(sessions: list[str]) -> str:
    if not sessions:
        return ""
    if "89R" in sessions:
        return "89R"
    regular = [
        session
        for session in sessions
        if str(session).strip().upper().endswith("R") and str(session).strip()[:-1].isdigit()
    ]
    if regular:
        return sorted(regular, key=session_sort_key)[-1]
    return sorted(sessions, key=session_sort_key)[-1]


def session_base_number_series(series: pd.Series) -> pd.Series:
    base = series.fillna("").astype(str).str.strip().str.extract(r"^(\d+)", expand=False)
    base = base.where(base.str.len() <= 2, base.str[:-1])
    return pd.to_numeric(base, errors="coerce")


def session_base_label(base_val: float | int) -> str:
    if pd.isna(base_val):
        return ""
    return ordinal(int(base_val))


def session_range_label(series: pd.Series) -> str:
    if series is None or series.empty:
        return "All Sessions"
    base_nums = session_base_number_series(series).dropna().astype(int)
    if base_nums.empty:
        return "All Sessions"
    min_base = int(base_nums.min())
    max_base = int(base_nums.max())
    if min_base == max_base:
        return f"{ordinal(min_base)} Regular Session"
    return f"{ordinal(min_base)} to {ordinal(max_base)} Sessions"


def session_from_year(year_val: Any) -> str:
    try:
        year = int(year_val)
    except Exception:
        return ""
    session = _SESSION_BASE_NUM + ((year - _SESSION_BASE_YEAR) // 2)
    return f"{session}R"


def add_session_from_year(df: pd.DataFrame) -> pd.DataFrame:
    if "Session" in df.columns:
        return df
    out = df.copy()
    year_col = None
    for candidate in ("applicableYear", "applicable_year", "ApplicableYear", "year", "Year"):
        if candidate in out.columns:
            year_col = candidate
            break
    if year_col:
        out["Session"] = pd.to_numeric(out[year_col], errors="coerce").map(session_from_year)
    else:
        out["Session"] = ""
    return out


def session_series(df: pd.DataFrame) -> pd.Series:
    if not isinstance(df, pd.DataFrame):
        return pd.Series(dtype="string")
    if "SessionKey" in df.columns:
        return df["SessionKey"].fillna("").astype(str)
    if "Session" in df.columns:
        return df["Session"].fillna("").astype(str).str.strip()
    if "session" in df.columns:
        return df["session"].fillna("").astype(str).str.strip()
    return pd.Series("", index=df.index, dtype="string")


def clean_options(options: list[str]) -> list[str]:
    clean: list[str] = []
    for option in options:
        text = str(option).strip()
        if not text or text.lower() in {"none", "nan", "null"}:
            continue
        clean.append(text)
    return clean


def slugify(value: str, default: str = "report") -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "")).strip("-").lower()
    return text or default


def tfl_session_for_filter(session_val: str | None, tfl_sessions: set[str]) -> str | None:
    if session_val is None:
        return None
    session = str(session_val).strip()
    if not session:
        return ""
    if session.isdigit() and len(session) >= 3:
        regular = f"{session[:-1]}R"
        if regular in tfl_sessions:
            return regular
    return session
