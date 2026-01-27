import os
import re
import difflib
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

# =========================================================
# CONFIG
# =========================================================
DEFAULT_DATA_FILENAME = "TFL Webstite books - combined.parquet"


def _is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def _resolve_data_path() -> str:
    # Prefer environment variable, then local fallbacks.
    env_path = os.getenv("DATA_PATH", "").strip()
    if env_path:
        return env_path

    here = Path(__file__).resolve().parent
    candidates = [
        here / DEFAULT_DATA_FILENAME,
        here / "data" / DEFAULT_DATA_FILENAME,
        here.parent / DEFAULT_DATA_FILENAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


PATH = _resolve_data_path()

st.set_page_config(page_title="TPPF Lobby Look-Up", layout="wide")

# =========================================================
# STYLE (unchanged)
# =========================================================
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;600;700&display=swap');
:root{
    --bg: #071627;
    --panel: rgba(255,255,255,0.06);
    --panel2: rgba(255,255,255,0.04);
    --border: rgba(255,255,255,0.10);
    --text: rgba(255,255,255,0.92);
    --muted: rgba(255,255,255,0.70);
    --accent: #1e90ff;
    --accent2: #00e0b8;
}

html, body, [data-testid="stAppViewContainer"]{
    background: radial-gradient(1200px 600px at 20% 15%, rgba(30,144,255,0.16), transparent 60%),
                            radial-gradient(900px 500px at 75% 30%, rgba(0,255,180,0.08), transparent 55%),
                            var(--bg) !important;
    color: var(--text) !important;
    font-family: 'IBM Plex Sans', system-ui, -apple-system, Segoe UI, sans-serif !important;
}

[data-testid="stHeader"]{ background: transparent !important; }
[data-testid="stToolbar"]{ right: 1rem; }
.block-container{ padding-top: 2.2rem; }

h1,h2,h3{ color: var(--text) !important; }
p,li,span,div{ color: var(--text); }

.small-muted{ color: var(--muted); font-size: 0.95rem; }
.hr{ height:1px; background: var(--border); margin: 1rem 0 1.2rem 0; }

.card{
    background: linear-gradient(180deg, var(--panel), var(--panel2));
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 16px 16px 14px 16px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.20);
}
.section-title{
    margin-top: 0.8rem;
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    min-height: 3.6rem;
    display: flex;
    align-items: flex-end;
}
.section-sub{
    color: var(--muted);
    margin-top: -0.3rem;
    margin-bottom: 0.6rem;
}
.pill{
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.04);
    font-size: 0.8rem;
}
.pill b{ font-weight: 700; }

.kpi-title{ color: var(--muted); font-size: 0.85rem; margin-bottom: 8px; }
.kpi-value{ font-size: 2.0rem; font-weight: 700; line-height: 1.15; color: var(--text); }
.kpi-sub{ color: var(--muted); font-size: 0.9rem; margin-top: 6px; }

.big-title{
    font-size: 3.0rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin: 0.1rem 0 0.2rem 0;
}

.subtitle{
    font-size: 1.2rem;
    color: var(--muted);
    margin-bottom: 1rem;
}

.stTabs [data-baseweb="tab-list"]{
    gap: 8px;
}
.stTabs [data-baseweb="tab"]{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 10px 14px;
}
.stTabs [aria-selected="true"]{
    border-color: rgba(30,144,255,0.55) !important;
    background: rgba(30,144,255,0.12) !important;
}

[data-testid="stTextInput"] input,
[data-testid="stTextInput"] textarea{
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    color: var(--text) !important;
}

[data-testid="stSelectbox"] div[role="combobox"]{
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
}

.chip{
    display:inline-block;
    padding: 6px 10px;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.04);
    font-size: 0.85rem;
    margin-right: 6px;
}

[data-testid="stSidebar"]{
    background: rgba(255,255,255,0.02) !important;
    border-right: 1px solid rgba(255,255,255,0.07);
}

[data-testid="stDataFrame"]{
    border-radius: 16px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.10);
}
div[data-testid="stDataFrame"]{
    background: rgba(7, 22, 39, 0.65);
}

button[kind="primary"]{
    border-radius: 14px !important;
}

/* Force dark text for all selectbox and dropdown items */
[data-testid="stSelectbox"] [data-baseweb="select"] *,
[data-testid="stSelectbox"] [data-baseweb="select"] span,
[data-testid="stSelectbox"] [data-baseweb="select"] div,
[data-testid="stSelectbox"] [data-baseweb="select"] input,
[data-testid="stSelectbox"] [data-baseweb="select"] [role="option"],
[data-testid="stSelectbox"] [data-baseweb="select"] [role="listbox"] *,
[data-baseweb="popover"] ul[role="listbox"] *,
[data-baseweb="popover"] div[role="option"],
[data-baseweb="popover"] div[role="option"] * {
    color: #0b1a2b !important;
    background: white !important;
}

[data-testid="stSelectbox"] [data-baseweb="select"] ::placeholder{
    color: #405264 !important;
}
[data-testid="stSelectbox"] div[role="combobox"] *{
    color: #0b1a2b !important;
}

/* Improve selectbox readability */
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] [data-baseweb="select"] span{
    color: #0b1a2b !important;
    font-weight: 700 !important;
    opacity: 1 !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] ::placeholder{
    color: #2b3c4d !important;
    opacity: 1 !important;
}
[data-baseweb="popover"] div[role="option"]{
    font-weight: 600;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# HELPERS
# =========================================================
_RE_NONWORD = re.compile(r"[^\w]+", flags=re.UNICODE)
_TITLE_WORDS = {"MR", "MRS", "MS", "MISS", "DR", "HON", "JR", "SR", "II", "III", "IV"}

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
    s = s.fillna("").astype(str)
    s = s.str.replace(r"\([^)]*\)", "", regex=True)
    s = s.str.replace(r"\b(" + "|".join(_TITLE_WORDS) + r")\b\.?", "", regex=True, flags=re.IGNORECASE)
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()
    return s

def filter_filer_rows(
    df: pd.DataFrame,
    session: str | None,
    lobbyshort: str,
    name_to_short: dict,
    lobbyist_norms: set[str],
    filerid_to_short: dict | None,
) -> pd.DataFrame:
    if df.empty:
        return df

    d = df.copy()
    if session is not None:
        d = d[d["Session"].astype(str).str.strip() == str(session)].copy()
    if d.empty:
        return d

    filerid_map = filerid_to_short or {}
    if "filerIdent" in d.columns and filerid_map:
        d["FilerID"] = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
        d["FilerShortFromId"] = d["FilerID"].map(filerid_map)
    else:
        d["FilerShortFromId"] = ""

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    filer_clean = clean_filer_name_series(filer_name)
    d["FilerNormRaw"] = norm_name_series(filer_name)
    d["FilerNormClean"] = norm_name_series(filer_clean)
    d["FilerSortNorm"] = norm_name_series(filer_sort)

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
    return d[ok].copy()

def last_name_norm_from_text(text: str) -> str:
    if not text:
        return ""
    s = str(text).replace("\u00A0", " ").strip()
    if not s:
        return ""
    if "," in s:
        last = s.split(",", 1)[0].strip()
    else:
        parts = s.split()
        last = parts[-1] if parts else ""
    return norm_name(last)

def last_name_norm_series(s: pd.Series) -> pd.Series:
    s = (
        s.fillna("")
         .astype(str)
         .str.replace("\u00A0", " ", regex=False)
         .str.strip()
    )
    comma_mask = s.str.contains(",", na=False)
    last_from_comma = s.where(comma_mask, "").str.split(",", n=1).str[0].str.strip()
    last_from_space = s.where(~comma_mask, "").str.split().str[-1].str.strip()
    last = last_from_comma.where(comma_mask, last_from_space).fillna("")
    return norm_name_series(last)

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
        toks = s.split()
        if len(toks) < 2:
            return ""
        first, last = toks[0], toks[-1]
    initial = ""
    for ch in first:
        if ch.isalnum():
            initial = ch
            break
    if not last or not initial:
        return ""
    return norm_name(f"{last} {initial}")

def norm_person_variants(user_text: str) -> set[str]:
    if not user_text:
        return set()
    t = str(user_text).replace("\u00A0", " ").strip()
    if not t:
        return set()

    if "," in t:
        parts = [p.strip() for p in t.split(",", 1)]
        last = parts[0]
        first = parts[1] if len(parts) > 1 else ""
    else:
        toks = t.split()
        if len(toks) == 1:
            first, last = toks[0], ""
        else:
            first, last = toks[0], toks[-1]

    variants = {norm_name(t)}
    if first and last:
        variants |= {
            norm_name(f"{first} {last}"),
            norm_name(f"{last}, {first}"),
            norm_name(f"{last} {first}"),
            norm_name(f"{first}{last}"),
            norm_name(f"{last}{first}"),
        }
    return {v for v in variants if v}

def person_display(org, last, first) -> str:
    org = "" if pd.isna(org) else str(org).strip()
    last = "" if pd.isna(last) else str(last).strip()
    first = "" if pd.isna(first) else str(first).strip()
    if org:
        return org
    if last and first:
        return f"{last}, {first}"
    return (last or first or "").strip()

def amount_display(exact, low, high, code=None) -> str:
    if pd.notna(exact) and str(exact).strip():
        return str(exact)
    if pd.notna(low) and str(low).strip():
        if pd.notna(high) and str(high).strip():
            return f"{low}–{high}"
        return str(low)
    if pd.notna(code) and str(code).strip():
        return str(code)
    return ""

def ensure_cols(df: pd.DataFrame, cols_with_defaults: dict) -> pd.DataFrame:
    out = df.copy()
    for c, default in cols_with_defaults.items():
        if c not in out.columns:
            out[c] = default
    return out

def _session_from_year(year_val) -> str:
    try:
        y = int(year_val)
    except Exception:
        return ""
    # Texas regular sessions: 2011 -> 82R, 2013 -> 83R, etc.
    session = 82 + ((y - 2011) // 2)
    return f"{session}R"

def _add_session_from_year(df: pd.DataFrame) -> pd.DataFrame:
    if "Session" in df.columns:
        return df
    out = df.copy()
    if "applicableYear" in out.columns:
        years = pd.to_numeric(out["applicableYear"], errors="coerce")
        sessions = years.map(_session_from_year)
        out["Session"] = sessions
    else:
        out["Session"] = ""
    return out

def _tfl_session_for_filter(session_val: str | None, tfl_sessions: set[str]) -> str | None:
    if session_val is None:
        return None
    s = str(session_val).strip()
    if not s:
        return ""
    # Lobby_TFL_Client_All rolls special sessions into the regular session (e.g., 891 -> 89R).
    if s.isdigit() and len(s) >= 3:
        reg = f"{s[:-1]}R"
        if reg in tfl_sessions:
            return reg
    return s

def fmt_usd(x: float, decimals: int = 0) -> str:
    try:
        return f"${x:,.{decimals}f}"
    except Exception:
        return "$0"

def export_dataframe(df: pd.DataFrame, filename: str, label: str = "Download CSV"):
    st.download_button(label=label, data=df.to_csv(index=False), file_name=filename, mime="text/csv")

def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"

def _session_label(session_val: str) -> str:
    s = str(session_val).strip()
    if not s:
        return s
    # Special sessions encoded like 891 -> "89R / 1st Special".
    if s.isdigit():
        if len(s) >= 3:
            base = s[:-1]
            special = s[-1]
            if base.isdigit() and special.isdigit():
                return f"{base}R / {_ordinal(int(special))} Special"
        return _ordinal(int(s))
    return s

def _session_sort_key(session_val: str) -> tuple[int, int, int]:
    s = str(session_val).strip()
    if not s:
        return (0, 2, 0)
    if s.isdigit():
        base = int(s[:-1]) if len(s) >= 2 else int(s)
        special = int(s[-1]) if len(s) >= 2 else 0
        return (base, 1, special)
    m = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if m:
        return (int(m.group(1)), 0, 0)
    return (0, 2, 0)

def bill_position_from_flags(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Position"])
    agg = (
        df.groupby(["Session", "Bill", "LobbyShort"], as_index=False)
          .agg(IsFor=("IsFor", "max"), IsAgainst=("IsAgainst", "max"), IsOn=("IsOn", "max"))
    )
    def pos_row(r):
        p = []
        if int(r.get("IsFor", 0) or 0) == 1:
            p.append("For")
        if int(r.get("IsAgainst", 0) or 0) == 1:
            p.append("Against")
        if int(r.get("IsOn", 0) or 0) == 1:
            p.append("On")
        return ", ".join(p)
    agg["Position"] = agg.apply(pos_row, axis=1)
    return agg[["Session", "Bill", "LobbyShort", "Position"]]

def _candidate_label(short_code: str, short_to_names: dict) -> str:
    names = short_to_names.get(short_code, [])
    if names:
        return f"{short_code} - {names[0]}"
    return short_code

def resolve_lobbyshort(user_text: str, lobby_index: pd.DataFrame, name_to_short: dict,
                       known_shorts: set[str], short_to_names: dict) -> tuple[str, list[str]]:
    q = (user_text or "").strip()
    if not q:
        return "", []

    if q in known_shorts:
        return q, []

    norm_variants = norm_person_variants(q)
    for n in norm_variants:
        if n in name_to_short:
            return str(name_to_short[n]), []

    q_norm = norm_name(q)
    if not q_norm or lobby_index.empty:
        return "", []

    scores = {}
    d = lobby_index

    # Prefix matches on LobbyShort and Lobby Name
    prefix_mask = d["LobbyShortNorm"].str.startswith(q_norm) | d["LobbyNameNorm"].str.startswith(q_norm)
    for short in d.loc[prefix_mask, "LobbyShort"].dropna().unique().tolist():
        scores[short] = max(scores.get(short, 0), 90)

    # Contains matches on LobbyShort and Lobby Name
    contains_mask = d["LobbyShortNorm"].str.contains(q_norm, na=False) | d["LobbyNameNorm"].str.contains(q_norm, na=False)
    for short in d.loc[contains_mask, "LobbyShort"].dropna().unique().tolist():
        scores[short] = max(scores.get(short, 0), 70)

    # Fuzzy matches against normalized names for minor typos
    if len(q_norm) >= 3:
        name_norms = d["LobbyNameNorm"].dropna().unique().tolist()
        close = difflib.get_close_matches(q_norm, name_norms, n=5, cutoff=0.78)
        if close:
            close_set = set(close)
            for short in d.loc[d["LobbyNameNorm"].isin(close_set), "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 60)

    if not scores:
        return "", []

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    top_score = ranked[0][1]
    top = [s for s, sc in ranked if sc == top_score]

    if len(top) == 1 and top_score >= 90:
        return top[0], []

    suggestions = [_candidate_label(s, short_to_names) for s, _ in ranked][:10]
    return "", suggestions

def resolve_lobbyshort_from_wit(user_text: str, wit_all: pd.DataFrame, session_val: str | None) -> tuple[str, list[str]]:
    q = (user_text or "").strip()
    if not q or wit_all.empty or "LobbyShort" not in wit_all.columns:
        return "", []

    d = wit_all
    if session_val is not None and "Session" in d.columns:
        d = d[d["Session"].astype(str).str.strip() == str(session_val)].copy()
    if d.empty:
        return "", []

    d = d[d["LobbyShort"].notna() & (d["LobbyShort"].astype(str).str.strip() != "")].copy()
    if d.empty:
        return "", []

    d["LobbyShortNorm"] = norm_name_series(d["LobbyShort"])
    q_norm = norm_name(q)
    if not q_norm:
        return "", []

    scores = {}
    prefix_mask = d["LobbyShortNorm"].str.startswith(q_norm)
    for short in d.loc[prefix_mask, "LobbyShort"].dropna().unique().tolist():
        scores[short] = max(scores.get(short, 0), 90)

    contains_mask = d["LobbyShortNorm"].str.contains(q_norm, na=False)
    for short in d.loc[contains_mask, "LobbyShort"].dropna().unique().tolist():
        scores[short] = max(scores.get(short, 0), 70)

    if not scores:
        return "", []

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    top_score = ranked[0][1]
    top = [s for s, sc in ranked if sc == top_score]

    if len(top) == 1 and top_score >= 90:
        return top[0], []

    suggestions = [s for s, _ in ranked][:10]
    return "", suggestions

def normalize_bill(q: str) -> str:
    s = (q or "").strip().upper()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    m = re.search(r"\b(HB|SB|HR|SR|HCR|SCR)\s*(\d+)\b", s)
    if not m:
        return ""
    return f"{m.group(1)} {m.group(2)}"

def is_bill_query(q: str) -> bool:
    return bool(normalize_bill(q))

def render_bill_search_results(bill_query: str, session_val: str | None, tfl_session_val: str | None,
                               wit_all: pd.DataFrame, bill_status_all: pd.DataFrame,
                               lobby_tfl_client_all: pd.DataFrame, short_to_names: dict):
    q = normalize_bill(bill_query)
    if not q:
        return False

    d = wit_all.copy()
    d["Session"] = d["Session"].astype(str).str.strip()
    if session_val is not None:
        d = d[d["Session"] == str(session_val)].copy()

    d_bill_norm = d["Bill"].astype(str).str.upper().str.replace(r"\s+", " ", regex=True)
    d = d[d_bill_norm == q].copy()
    total_rows = len(d)
    d = d[d["LobbyShort"].notna() & (d["LobbyShort"].astype(str).str.strip() != "")].copy()
    if "LobbyShortNorm" not in d.columns:
        d["LobbyShortNorm"] = norm_name_series(d["LobbyShort"])

    tfl = lobby_tfl_client_all.copy()
    tfl["Session"] = tfl["Session"].astype(str).str.strip()
    if tfl_session_val is not None:
        tfl = tfl[tfl["Session"] == str(tfl_session_val)].copy()
    tfl = ensure_cols(tfl, {"LobbyShort": ""})
    if "LobbyShortNorm" not in tfl.columns:
        tfl["LobbyShortNorm"] = norm_name_series(tfl["LobbyShort"])
    lobbyshort_set = set(tfl["LobbyShortNorm"].dropna().unique().tolist())
    if lobbyshort_set:
        d = d[d["LobbyShortNorm"].isin(lobbyshort_set)].copy()
        if not tfl.empty:
            norm_to_short = (
                tfl[["LobbyShortNorm", "LobbyShort"]]
                .dropna()
                .drop_duplicates()
                .groupby("LobbyShortNorm")["LobbyShort"]
                .first()
                .to_dict()
            )
            d["LobbyShort"] = d["LobbyShortNorm"].map(norm_to_short).fillna(d["LobbyShort"])
    if d.empty:
        if total_rows > 0:
            st.info(
                f"Found {total_rows} witness-list rows for {q}, but none matched a lobbyist in Lobby_TFL_Client_All "
                "for the selected session."
            )
        else:
            st.info("No witness-list rows matched that bill search.")
        return True

    pos = bill_position_from_flags(d)
    bs = bill_status_all.copy()
    bs["Session"] = bs["Session"].astype(str).str.strip()
    if session_val is not None:
        bs = bs[bs["Session"] == str(session_val)].copy()

    merged = pos.merge(bs, on=["Session", "Bill"], how="left")
    merged["Lobbyist"] = merged["LobbyShort"].map(lambda s: _candidate_label(str(s), short_to_names))
    tfl = lobby_tfl_client_all.copy()
    tfl["Session"] = tfl["Session"].astype(str).str.strip()
    if tfl_session_val is not None:
        tfl = tfl[tfl["Session"] == str(tfl_session_val)].copy()
    tfl = ensure_cols(tfl, {"LobbyShort": "", "IsTFL": 0})
    tfl_flag = (
        tfl.groupby("LobbyShort", as_index=False)["IsTFL"]
        .max()
        .rename(columns={"IsTFL": "Has TFL Client"})
    )
    merged = merged.merge(tfl_flag, on="LobbyShort", how="left")
    merged["Has TFL Client"] = merged["Has TFL Client"].fillna(0).astype(int).map({1: "Yes", 0: "No"})

    show_cols = ["Session", "Bill", "Lobbyist", "Has TFL Client", "Position", "Author", "Caption", "Status"]
    show_cols = [c for c in show_cols if c in merged.columns]
    merged["_tfl_sort"] = merged["Has TFL Client"].map({"Yes": 1, "No": 0}).fillna(0)
    view = merged[show_cols + ["_tfl_sort"]].sort_values(
        ["_tfl_sort", "Session", "Bill", "Lobbyist"],
        ascending=[False, True, True, True],
    )
    view = view.drop(columns=["_tfl_sort"])
    st.dataframe(view, use_container_width=True, height=520, hide_index=True)
    export_dataframe(view, "bill_lobbyists.csv")
    return True

# =========================================================
# FAST MONEY PARSING (vectorized) for Lobby_TFL_Client_All
# =========================================================
_MONEY_RANGE = re.compile(r"(-?\d[\d,]*\.?\d*)\s*(?:–|-|to)\s*(-?\d[\d,]*\.?\d*)", re.IGNORECASE)

def _to_num_series(s: pd.Series) -> pd.Series:
    """Vectorized $/comma/paren cleanup -> float; blanks->0"""
    s = s.fillna("").astype(str).str.strip()
    neg = s.str.startswith("(") & s.str.endswith(")")
    s = s.str.replace(r"^\(|\)$", "", regex=True)
    s = s.str.replace("$", "", regex=False).str.replace(",", "", regex=False)
    out = pd.to_numeric(s, errors="coerce").fillna(0.0)
    out = out.where(~neg, -out)
    return out

def add_low_high_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Produces Low_num/High_num with minimal Python-level loops.
    Priority:
      1) Low/High columns if present and nonzero
      2) Parse Amount range "1000-5000"
      3) Parse Amount single value
      4) Mirror one side if only one exists
    """
    d = ensure_cols(df, {"Low": 0, "High": 0, "Amount": ""}).copy()

    low = _to_num_series(d["Low"])
    high = _to_num_series(d["High"])

    amt = d["Amount"].fillna("").astype(str).str.strip()
    amt_clean = amt.str.replace("$", "", regex=False).str.replace(",", "", regex=False)

    # range capture
    rng = amt_clean.str.extract(_MONEY_RANGE)
    rng_lo = pd.to_numeric(rng[0], errors="coerce").fillna(0.0)
    rng_hi = pd.to_numeric(rng[1], errors="coerce").fillna(0.0)

    # single numeric fallback
    single = pd.to_numeric(amt_clean.str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce").fillna(0.0)

    # If both low/high are zero, use range; else keep existing
    both_zero = (low == 0) & (high == 0)
    low = low.where(~both_zero, rng_lo.where(rng_lo != 0, single))
    high = high.where(~both_zero, rng_hi.where(rng_hi != 0, single))

    # Mirror
    high = high.where(high != 0, low)
    low = low.where(low != 0, high)

    d["Low_num"] = low
    d["High_num"] = high
    return d

# =========================================================
# LOAD WORKBOOK (open once -> much faster)
# =========================================================
def safe_read_excel_xf(xf: pd.ExcelFile, sheet_name: str, cols: list[str]) -> pd.DataFrame:
    try:
        return xf.parse(sheet_name=sheet_name, usecols=cols)
    except Exception:
        try:
            df = xf.parse(sheet_name=sheet_name)
            keep = [c for c in cols if c in df.columns]
            return df[keep].copy()
        except Exception:
            return pd.DataFrame(columns=cols)

@st.cache_data(show_spinner=False)
def _empty_df(cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cols)

def read_parquet_cols(path: Path, cols: list[str]) -> pd.DataFrame:
    try:
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(path)
        available = set(pf.schema.names)
        use_cols = [c for c in cols if c in available]
        if use_cols:
            return pd.read_parquet(path, columns=use_cols)
        return pd.read_parquet(path)
    except Exception:
        try:
            df = pd.read_parquet(path)
            keep = [c for c in cols if c in df.columns]
            return df[keep].copy() if keep else df
        except Exception:
            return pd.DataFrame(columns=cols)

@st.cache_data(show_spinner=False)
def load_workbook(path: str) -> dict:
    cfg = {
        "Wit_All": ["session", "bill", "position", "LobbyShort", "name", "org"],
        "Bill_Status_All": ["Session", "Bill", "Authors", "Author", "Caption", "Status"],
        "Fiscal_Impact": ["Session", "Bill", "Version", "EstimatedTwoYearNetImpactGR"],
        "Bill_Sub_All": ["Session", "Bill", "Subject"],
        "Lobby_Sub_All": ["Session", "Subject Matter", "Other Subject Matter Description", "Primary Business", "FilerID", "LobbyShort", "Lobby Name"],
        "Lobby_TFL_Client_All": ["Session", "Client", "Lobby Name", "LobbyShort", "IsTFL", "Low", "High", "Amount", "Mid", "FilerID"],
        "Staff_All": ["Session", "session", "Legislator", "member_or_committee", "legislator_name", "Title", "role",
                      "Staffer", "name", "staff_name_last_initial", "lobby name", "source"],
        "LaFood": ["Session", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "restaurantName", "activityDate", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaEnt": ["Session", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                  "entertainmentName", "activityDate", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaTran": ["Session", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "travelPurpose", "transportationTypeDescr", "departureCity", "arrivalCity", "checkInDt", "checkOutDt", "departureDt", "periodStartDt"],
        "LaGift": ["Session", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaEvnt": ["Session", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "activityDate", "periodStartDt"],
        "LaAwrd": ["Session", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaCvr": ["Session", "filerIdent", "filerName", "filerSort", "filedDt", "periodStartDt", "sourceCategoryCd",
                  "subjectMatterMemo", "docketsMemo", "filerNameOrganization"],
        "LaDock": ["Session", "filerIdent", "filerName", "filerSort", "receivedDt", "periodStartDt", "designationText", "agencyName"],
        "LaI4E": ["Session", "filerIdent", "filerName", "filerSort", "periodStartDt", "onbehalfName",
                  "onbehalfMailingCity", "onbehalfPrimaryPhoneNumber"],
        "LaSub": ["Session", "filerIdent", "filerName", "filerSort", "periodStartDt", "subjectMatterCodeValue", "subjectMatterDescr"],
    }

    base = Path(path)
    if not base.exists():
        return {k: _empty_df(v) for k, v in cfg.items()}
    if base.is_dir():
        parquet_map = {
            "Wit_All": ["Witness_Lists.parquet", "Witness List.parquet", "Witness_List.parquet"],
            "Bill_Status_All": "Bill_Status.parquet",
            "Fiscal_Impact": "Fiscal_Notes.parquet",
            "Bill_Sub_All": "Bill_Sub_All.parquet",
            "Lobby_Sub_All": "Lobby_Sub_All.parquet",
            "Lobby_TFL_Client_All": "Lobby_TFL_Client_All.parquet",
            "Staff_All": ["Staff.parquet", "staff.parquet"],
            "LaFood": "LaFood.parquet",
            "LaEnt": "LaEnt.parquet",
            "LaTran": "LaTran.parquet",
            "LaGift": "LaGift.parquet",
            "LaEvnt": "LaEvnt.parquet",
            "LaAwrd": "LaAwrd.parquet",
            "LaCvr": "LaCvr.parquet",
            "LaDock": "LaDock.parquet",
            "LaI4E": "LaI4E.parquet",
            "LaSub": "LaSub.parquet",
        }
        data = {}
        for key, cols in cfg.items():
            fname = parquet_map.get(key)
            if not fname:
                data[key] = _empty_df(cols)
                continue
            fpath = None
            if isinstance(fname, (list, tuple)):
                for cand in fname:
                    cand_path = base / cand
                    if cand_path.exists():
                        fpath = cand_path
                        break
            else:
                cand_path = base / fname
                if cand_path.exists():
                    fpath = cand_path
            if not fpath or not fpath.exists():
                data[key] = _empty_df(cols)
                continue
            try:
                data[key] = read_parquet_cols(fpath, cols)
            except Exception:
                data[key] = _empty_df(cols)
    else:
        xf = pd.ExcelFile(path, engine="openpyxl")  # OPEN ONCE
        data = {k: safe_read_excel_xf(xf, k, v) for k, v in cfg.items()}

    # Normalize parquet schema differences
    wit = data.get("Wit_All")
    if isinstance(wit, pd.DataFrame):
        wit = wit.copy()
        if "session" in wit.columns and "Session" not in wit.columns:
            wit = wit.rename(columns={"session": "Session"})
        if "bill" in wit.columns and "Bill" not in wit.columns:
            wit = wit.rename(columns={"bill": "Bill"})
        if "position" in wit.columns:
            pos = wit["position"].fillna("").astype(str).str.upper()
            if "IsFor" not in wit.columns:
                wit["IsFor"] = pos.str.contains(r"\bFOR\b").astype(int)
            if "IsAgainst" not in wit.columns:
                wit["IsAgainst"] = pos.str.contains(r"\bAGAINST\b").astype(int)
            if "IsOn" not in wit.columns:
                wit["IsOn"] = pos.str.contains(r"\bON\b").astype(int)
        if "LobbyShort" not in wit.columns:
            wit["LobbyShort"] = ""
        unnamed = [c for c in wit.columns if str(c).startswith("Unnamed:")]
        if unnamed:
            wit = wit.drop(columns=unnamed)
        data["Wit_All"] = wit

    bs = data.get("Bill_Status_All")
    if isinstance(bs, pd.DataFrame):
        bs = bs.copy()
        if "Authors" in bs.columns and "Author" not in bs.columns:
            bs["Author"] = bs["Authors"]
        data["Bill_Status_All"] = bs

    fi = data.get("Fiscal_Impact")
    if isinstance(fi, pd.DataFrame):
        fi = fi.copy()
        data["Fiscal_Impact"] = fi

    lt = data.get("Lobby_TFL_Client_All")
    if isinstance(lt, pd.DataFrame):
        lt = lt.copy()
        if "IsTFL" not in lt.columns and "TFL?" in lt.columns:
            lt["IsTFL"] = lt["TFL?"].astype(str).str.upper().isin(["Y", "YES", "TRUE", "1"]).astype(int)
        if "IsTFL" in lt.columns:
            lt["IsTFL"] = pd.to_numeric(lt["IsTFL"], errors="coerce").fillna(0).astype(int)
        data["Lobby_TFL_Client_All"] = lt

    staff = data.get("Staff_All")
    if isinstance(staff, pd.DataFrame) and not staff.empty:
        staff = staff.copy()
        # Rename session column if needed
        if "session" in staff.columns and "Session" not in staff.columns:
            staff = staff.rename(columns={"session": "Session"})
        # Map staff parquet schema to expected columns
        if "Legislator" not in staff.columns:
            if "legislator_name" in staff.columns:
                leg = staff["legislator_name"].fillna("").astype(str).str.strip()
                if "member_or_committee" in staff.columns:
                    fallback = staff["member_or_committee"].fillna("").astype(str).str.strip()
                    staff["Legislator"] = leg.where(leg != "", fallback)
                else:
                    staff["Legislator"] = leg
            elif "member_or_committee" in staff.columns:
                staff["Legislator"] = staff["member_or_committee"]
            else:
                staff["Legislator"] = ""
        if "Title" not in staff.columns:
            staff["Title"] = staff.get("role", "")
        if "Staffer" not in staff.columns:
            staff["Staffer"] = staff.get("name", staff.get("staff_name_last_initial", ""))
        if "lobby name" not in staff.columns:
            staff["lobby name"] = staff.get("staff_name_last_initial", staff.get("name", ""))
        # Normalized staff name helpers for matching
        staff["StaffNameNorm"] = norm_name_series(staff.get("name", pd.Series(dtype=object)))
        staff["StaffLastInitialNorm"] = norm_name_series(
            staff.get("staff_name_last_initial", staff.get("name", pd.Series(dtype=object)))
        )
        staff["StaffLastNorm"] = last_name_norm_series(
            staff.get("name", staff.get("staff_name_last_initial", pd.Series(dtype=object)))
        )
        # Normalize Session to match app sessions (e.g., 89 -> 89R)
        if "Session" in staff.columns:
            sess = staff["Session"].astype(str).str.strip()
            staff["Session"] = sess.where(~sess.str.fullmatch(r"\d+"), sess + "R")
        data["Staff_All"] = staff

    for key in ["LaFood", "LaEnt", "LaTran", "LaGift", "LaEvnt", "LaAwrd", "LaCvr", "LaDock", "LaI4E", "LaSub"]:
        df = data.get(key)
        if isinstance(df, pd.DataFrame):
            data[key] = _add_session_from_year(df)

    # Normalize Session everywhere
    for df in data.values():
        if isinstance(df, pd.DataFrame) and "Session" in df.columns:
            df["Session"] = df["Session"].astype(str).str.strip()

    # Precompute Low_num/High_num once (speed for overview + per-lobbyist)
    if isinstance(data.get("Lobby_TFL_Client_All"), pd.DataFrame) and not data["Lobby_TFL_Client_All"].empty:
        data["Lobby_TFL_Client_All"] = add_low_high_numeric(data["Lobby_TFL_Client_All"])

    # Build mapping from Lobby Name -> LobbyShort (across all sessions)
    lt = data["Lobby_TFL_Client_All"].dropna(subset=["Lobby Name", "LobbyShort"]).copy()
    name_to_short = {}
    short_to_names = {}
    lobby_index = pd.DataFrame(columns=["LobbyShort", "Lobby Name", "LobbyShortNorm", "LobbyNameNorm"])
    known_shorts = set()
    initial_to_short = {}
    filerid_to_short = {}
    if not lt.empty:
        lt["LobbyNameNorm"] = lt["Lobby Name"].map(norm_name)

        counts = (
            lt.groupby(["LobbyNameNorm", "LobbyShort"])
              .size()
              .reset_index(name="n")
              .sort_values(["LobbyNameNorm", "n"], ascending=[True, False])
              .drop_duplicates("LobbyNameNorm")
        )
        name_to_short = dict(zip(counts["LobbyNameNorm"], counts["LobbyShort"]))

        tmp = lt[["LobbyShort", "Lobby Name"]].dropna().copy()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str)
        short_to_names = (
            tmp.groupby("LobbyShort")["Lobby Name"]
               .agg(lambda s: sorted(set(map(str, s)))[:6])
               .to_dict()
        )

        base = lt[["LobbyShort", "Lobby Name"]].dropna().copy()
        base["LobbyShort"] = base["LobbyShort"].astype(str).str.strip()
        base["Lobby Name"] = base["Lobby Name"].astype(str).str.strip()
        base = base.drop_duplicates()
        base["LobbyShortNorm"] = base["LobbyShort"].map(norm_name)
        base["LobbyNameNorm"] = base["Lobby Name"].map(norm_name)
        lobby_index = base
        known_shorts = set(base["LobbyShort"].dropna().astype(str).str.strip().unique().tolist())

        # Map FilerID -> LobbyShort (used for activity matching)
        if "FilerID" in lt.columns:
            fid = lt[["FilerID", "LobbyShort"]].dropna().copy()
            fid["FilerID"] = pd.to_numeric(fid["FilerID"], errors="coerce")
            fid = fid.dropna(subset=["FilerID"])
            fid["FilerID"] = fid["FilerID"].astype(int)
            fid["LobbyShort"] = fid["LobbyShort"].astype(str).str.strip()
            if not fid.empty:
                fid_counts = (
                    fid.groupby(["FilerID", "LobbyShort"])
                    .size()
                    .reset_index(name="n")
                    .sort_values(["FilerID", "n"], ascending=[True, False])
                    .drop_duplicates("FilerID")
                )
                filerid_to_short = dict(zip(fid_counts["FilerID"], fid_counts["LobbyShort"]))

        # Map last name + first initial to LobbyShort (helps when names don't match exactly)
        tmp_short = lt[["LobbyShort"]].dropna().copy()
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

    # Map witness list names/orgs to LobbyShort where possible
    wit = data.get("Wit_All")
    if isinstance(wit, pd.DataFrame) and not wit.empty:
        wit = wit.copy()
        if "LobbyShort" not in wit.columns:
            wit["LobbyShort"] = ""
        if name_to_short:
            name_series = wit.get("name", pd.Series([""] * len(wit))).fillna("").astype(str)
            name_norm = name_series.map(norm_name)
            mapped = name_norm.map(name_to_short)
            if initial_to_short:
                init_key = name_series.map(_last_first_initial_key)
                mapped_init = init_key.map(initial_to_short)
                mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), mapped_init)
            if "org" in wit.columns:
                org_series = wit.get("org", pd.Series([""] * len(wit))).fillna("").astype(str)
                org_norm = org_series.map(norm_name)
                mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), org_norm.map(name_to_short))
            blank = wit["LobbyShort"].isna() | (wit["LobbyShort"].astype(str).str.strip() == "")
            wit.loc[blank, "LobbyShort"] = mapped[blank].fillna("")
        data["Wit_All"] = wit

    # Normalize LobbyShort for robust matching (hyphens/case/spacing).
    for key in ["Wit_All", "Lobby_TFL_Client_All", "Lobby_Sub_All"]:
        df = data.get(key)
        if isinstance(df, pd.DataFrame) and "LobbyShort" in df.columns:
            df["LobbyShortNorm"] = norm_name_series(df["LobbyShort"])

    data["name_to_short"] = name_to_short
    data["short_to_names"] = short_to_names
    data["lobby_index"] = lobby_index
    data["known_shorts"] = known_shorts
    data["filerid_to_short"] = filerid_to_short

    # Fill Lobby_Sub_All LobbyShort from FilerID when missing
    ls = data.get("Lobby_Sub_All")
    if isinstance(ls, pd.DataFrame) and not ls.empty and filerid_to_short:
        if "FilerID" in ls.columns and "LobbyShort" in ls.columns:
            ls = ls.copy()
            fid = pd.to_numeric(ls["FilerID"], errors="coerce").fillna(-1).astype(int)
            missing = ls["LobbyShort"].isna() | ls["LobbyShort"].astype(str).str.strip().eq("")
            ls.loc[missing, "LobbyShort"] = fid.map(filerid_to_short)
            data["Lobby_Sub_All"] = ls
    return data

def data_health_table(data: dict) -> pd.DataFrame:
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
    rows = []
    for key in order:
        df = data.get(key)
        if isinstance(df, pd.DataFrame):
            sess_count = int(df["Session"].dropna().astype(str).nunique()) if "Session" in df.columns else 0
            lobby_count = int(df["LobbyShort"].dropna().astype(str).nunique()) if "LobbyShort" in df.columns else 0
            rows.append({
                "Table": key,
                "Rows": int(len(df)),
                "Cols": int(len(df.columns)),
                "Has Session": "Yes" if "Session" in df.columns else "No",
                "Empty": "Yes" if df.empty else "No",
                "Sessions": sess_count,
                "LobbyShorts": lobby_count,
            })
        else:
            rows.append({
                "Table": key,
                "Rows": 0,
                "Cols": 0,
                "Has Session": "No",
                "Empty": "Yes",
                "Sessions": 0,
                "LobbyShorts": 0,
            })
    return pd.DataFrame(rows)

# =========================================================
# ACTIVITIES (unchanged logic, still cached)
# =========================================================
@st.cache_data(show_spinner=False)
def build_activities(df_food, df_ent, df_tran, df_gift, df_evnt, df_awrd,
                     lobbyshort: str, session: str | None, name_to_short: dict,
                     lobbyist_norms_tuple: tuple[str, ...], filerid_to_short: dict | None = None) -> pd.DataFrame:

    lobbyist_norms = set(lobbyist_norms_tuple)

    def keep(df: pd.DataFrame) -> pd.DataFrame:
        return filter_filer_rows(
            df,
            session=session,
            lobbyshort=lobbyshort,
            name_to_short=name_to_short,
            lobbyist_norms=lobbyist_norms,
            filerid_to_short=filerid_to_short,
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
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("restaurantName", "").fillna("").astype(str),
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
        }))

    d = keep(df_ent)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Entertainment",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("entertainmentName", "").fillna("").astype(str),
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
        }))

    d = keep(df_tran)
    if not d.empty:
        desc = d.get("travelPurpose", pd.Series([""] * len(d))).fillna("").astype(str)
        fallback = d.get("transportationTypeDescr", pd.Series([""] * len(d))).fillna("").astype(str)
        desc = desc.where(desc.str.len() > 0, fallback)
        route = (d.get("departureCity", "").fillna("").astype(str) + " → " + d.get("arrivalCity", "").fillna("").astype(str)).str.strip()
        desc2 = (desc + " | " + route).str.replace(r"\s+\|\s+$", "", regex=True)
        date = d.get("departureDt", d.get("checkInDt", d.get("periodStartDt", ""))).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Travel",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
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
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
        }))

    d = keep(df_evnt)
    if not d.empty:
        date = d.get("activityDate", d.get("periodStartDt", "")).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Event",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
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
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
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

@st.cache_data(show_spinner=False)
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
) -> pd.DataFrame:
    lobbyist_norms = set(lobbyist_norms_tuple)
    out = []

    d = filter_filer_rows(df_cvr, session, lobbyshort, name_to_short, lobbyist_norms, filerid_to_short)
    if not d.empty:
        date = d.get("filedDt", d.get("periodStartDt", "")).fillna("").astype(str)
        desc = d.get("subjectMatterMemo", "").fillna("").astype(str)
        desc = desc.where(desc.str.strip() != "", d.get("docketsMemo", "").fillna("").astype(str))
        desc = desc.where(desc.str.strip() != "", d.get("sourceCategoryCd", "").fillna("").astype(str))
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Coverage",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": desc,
            "Entity": d.get("filerNameOrganization", "").fillna("").astype(str),
        }))

    d = filter_filer_rows(df_dock, session, lobbyshort, name_to_short, lobbyist_norms, filerid_to_short)
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

    d = filter_filer_rows(df_i4e, session, lobbyshort, name_to_short, lobbyist_norms, filerid_to_short)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        entity = (
            d.get("onbehalfName", "").fillna("").astype(str)
            + " — "
            + d.get("onbehalfMailingCity", "").fillna("").astype(str)
        ).str.replace(r"\s+—\s+$", "", regex=True)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "On Behalf",
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Description": d.get("onbehalfPrimaryPhoneNumber", "").fillna("").astype(str),
            "Entity": entity,
        }))

    d = filter_filer_rows(df_sub, session, lobbyshort, name_to_short, lobbyist_norms, filerid_to_short)
    if not d.empty:
        date = d.get("periodStartDt", "").fillna("").astype(str)
        desc = d.get("subjectMatterCodeValue", "").fillna("").astype(str)
        desc = desc.where(desc.str.strip() != "", d.get("subjectMatterDescr", "").fillna("").astype(str))
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

# =========================================================
# APP HEADER
# =========================================================
st.markdown('<div class="big-title">Lobby Look-Up</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Search any lobbyist and explore clients, witness activity, policy areas, and filings.</div>', unsafe_allow_html=True)

# Validate workbook path
if not PATH:
    st.error(
        "Data path not configured. Set the DATA_PATH environment variable."
    )
    st.stop()
if not _is_url(PATH) and not os.path.exists(PATH):
    st.error(
        "Data path not found. Set DATA_PATH or place the parquet file in ./data."
    )
    st.stop()

# Load workbook once (cached)
with st.spinner("Loading workbook..."):
    data = load_workbook(PATH)

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
name_to_short = data["name_to_short"]
short_to_names = data["short_to_names"]
lobby_index = data["lobby_index"]
known_shorts = data["known_shorts"]
tfl_sessions = set(
    Lobby_TFL_Client_All.get("Session", pd.Series(dtype=object))
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
    .tolist()
)

# =========================================================
# SIDEBAR (unchanged: no search inputs)
# =========================================================
if "scope" not in st.session_state:
    st.session_state.scope = "This Session"
if "session" not in st.session_state:
    st.session_state.session = None
if "lobbyshort" not in st.session_state:
    st.session_state.lobbyshort = ""
if "search_query" not in st.session_state:
    st.session_state.search_query = ""

st.sidebar.header("Filters")
st.session_state.scope = st.sidebar.radio("Overview scope", ["This Session", "All Sessions"], index=0)

sessions = sorted(
    pd.concat([
        Wit_All.get("Session", pd.Series(dtype=object)),
        Lobby_TFL_Client_All.get("Session", pd.Series(dtype=object)),
        Bill_Status_All.get("Session", pd.Series(dtype=object)),
    ], ignore_index=True).dropna().astype(str).str.strip().unique().tolist()
)
# Drop invalid session tokens that can appear in data
sessions = [s for s in sessions if s and s.lower() not in {"none", "nan", "null"}]
sessions = sorted(sessions, key=_session_sort_key)
if not sessions:
    st.error("No sessions found in the workbook.")
    st.stop()

with st.sidebar.expander("Data health", expanded=False):
    st.caption(f"Data path: {PATH}")
    health = data_health_table(data)
    st.dataframe(health, use_container_width=True, height=260, hide_index=True)

# =========================================================
# TOP CONTROLS
#   - lobbyist name box (optional)
#   - session selector (All + ordinals)
# =========================================================
top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

with top1:
    st.session_state.search_query = st.text_input(
        "Search lobbyist or bill",
        value=st.session_state.search_query,
        placeholder="e.g., Abbott or HB 4",
    )

with top2:
    label_to_session = {}
    session_labels = []
    for s in sessions:
        lab = _session_label(s)
        session_labels.append(lab)
        label_to_session[lab] = s

    default_session = sessions[-1]
    default_label = _session_label(default_session)

    # initialize once
    if st.session_state.session is None or str(st.session_state.session).strip().lower() in {"none", "nan", "null", ""}:
        st.session_state.session = default_session

    current_label = _session_label(st.session_state.session)
    if current_label not in session_labels:
        current_label = default_label if default_label in session_labels else session_labels[0]

    chosen_label = st.selectbox("Session", session_labels, index=session_labels.index(current_label))
    st.session_state.session = label_to_session.get(chosen_label, default_session)

with top3:
    st.markdown('<div class="small-muted">Known name variants</div>', unsafe_allow_html=True)
    names_hint = short_to_names.get(st.session_state.lobbyshort, [])
    if not names_hint and st.session_state.lobbyshort and "name" in Wit_All.columns:
        wit_names = (
            Wit_All[Wit_All["LobbyShort"].astype(str).str.strip() == str(st.session_state.lobbyshort)]
            .get("name", pd.Series(dtype=object))
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )
        names_hint = wit_names[:6]
    st.write(", ".join(names_hint) if names_hint else "—")

tfl_session_val = _tfl_session_for_filter(st.session_state.session, tfl_sessions)

st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

# Resolve lobbyshort from search (if provided) but do not stop app if missing
bill_mode = is_bill_query(st.session_state.search_query)
typed_norms = norm_person_variants(st.session_state.search_query) if not bill_mode else set()
resolved_short, suggestions = ("", []) if bill_mode else resolve_lobbyshort(
    st.session_state.search_query,
    lobby_index,
    name_to_short,
    known_shorts,
    short_to_names,
)
if not bill_mode and not resolved_short:
    resolved_from_wit, wit_suggestions = resolve_lobbyshort_from_wit(
        st.session_state.search_query,
        Wit_All,
        st.session_state.session,
    )
    if resolved_from_wit:
        resolved_short = resolved_from_wit
    elif not suggestions:
        suggestions = wit_suggestions

if suggestions:
    label_to_short = {s: s.split(" - ")[0] for s in suggestions}
    pick = st.selectbox("Suggestions", ["Select a lobbyist..."] + suggestions, index=0)
    if pick in label_to_short:
        resolved_short = label_to_short[pick]

st.session_state.lobbyshort = resolved_short or ""

# Quick context chips
chips = [f"Session: {_session_label(st.session_state.session)}", f"Scope: {st.session_state.scope}"]
if st.session_state.lobbyshort:
    chips.append(f"Lobbyist: {st.session_state.lobbyshort}")
st.markdown("".join([f'<span class="chip">{c}</span>' for c in chips]), unsafe_allow_html=True)

# =========================================================
# FAST ALL-LOBBYISTS OVERVIEW (cached and uses Low_num/High_num)
# =========================================================
@st.cache_data(show_spinner=False)
def build_all_lobbyists_overview_fast(df: pd.DataFrame, session_val: str | None, scope_val: str) -> tuple[pd.DataFrame, dict]:
    if df.empty:
        return pd.DataFrame(), {}

    d = df.copy()
    d["Session"] = d["Session"].astype(str).str.strip()

    if scope_val == "This Session" and session_val is not None:
        d = d[d["Session"] == str(session_val)].copy()

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
    return pivot, stats

all_pivot, all_stats = build_all_lobbyists_overview_fast(
    Lobby_TFL_Client_All,
    tfl_session_val,
    st.session_state.scope,
)

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

# =========================================================
# TABS
# =========================================================
tab_all, tab_overview, tab_bills, tab_policy, tab_staff, tab_activities, tab_disclosures = st.tabs(
    ["All Lobbyists", "Overview", "Bills", "Policy Areas", "Staff History", "Activities", "Disclosures"]
)

def kpi_card(title: str, value: str, sub: str = ""):
    st.markdown(
        f"""
<div class="card">
  <div class="kpi-title">{title}</div>
  <div class="kpi-value">{value}</div>
  <div class="kpi-sub">{sub}</div>
</div>
""",
        unsafe_allow_html=True,
    )

# -----------------------------
# TAB: ALL LOBBYISTS (ALWAYS POPULATES)
# -----------------------------
with tab_all:
    st.markdown('<div class="section-title">All Lobbyists Overview</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-sub">Scope: {st.session_state.scope}</div>', unsafe_allow_html=True)

    if all_pivot.empty:
        st.info("No Lobby_TFL_Client_All rows found for the selected scope/session.")
    else:
        a1, a2, a3, a4 = st.columns(4)
        with a1:
            kpi_card(
                "Total Taxpayer Funded",
                f"{fmt_usd(all_stats.get('tfl_low_total', 0.0))} - {fmt_usd(all_stats.get('tfl_high_total', 0.0))}",
            )
        with a2:
            kpi_card(
                "Total Private",
                f"{fmt_usd(all_stats.get('pri_low_total', 0.0))} - {fmt_usd(all_stats.get('pri_high_total', 0.0))}",
            )
        with a3:
            kpi_card("Total Lobbyists", f"{all_stats.get('total_lobbyists', 0):,}")
            kpi_card("Lobbyists w/ ≥1 Taxpayer Funded client", f"{all_stats.get('has_tfl', 0):,}")
        with a4:
            kpi_card("Only Private", f"{all_stats.get('only_private', 0):,}")
            kpi_card("Only Taxpayer Funded", f"{all_stats.get('only_tfl', 0):,}", f"Mixed: {all_stats.get('mixed', 0):,}")

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        t1, t2 = st.columns(2)
        with t1:
            st.markdown('<div class="section-title">Top 5 Taxpayer Funded<br>Lobbyists</div>', unsafe_allow_html=True)
            top_lobbyists = all_pivot.copy()
            if not top_lobbyists.empty:
                top_lobbyists = top_lobbyists[top_lobbyists.get("Clients_TFL", 0) > 0].copy()
                top_lobbyists = top_lobbyists.sort_values(["High_TFL", "Low_TFL"], ascending=[False, False]).head(5)
                lobby_display = (
                    Lobby_TFL_Client_All[["LobbyShort", "Lobby Name"]]
                    .dropna()
                    .drop_duplicates()
                    .assign(
                        LobbyShort=lambda df: df["LobbyShort"].astype(str).str.strip(),
                        LobbyNameClean=lambda df: df["Lobby Name"]
                        .astype(str)
                        .str.strip()
                        .str.replace(r"\s+", " ", regex=True),
                    )
                )
                lobby_display = lobby_display.assign(
                    LobbyNameDisplay=lobby_display["LobbyNameClean"].apply(
                        lambda x: " ".join(
                            ([x.split(",", 1)[1].strip(), x.split(",", 1)[0].strip()] if "," in x else [x])
                        )
                    )
                )
                lobby_display = lobby_display[["LobbyShort", "LobbyNameDisplay"]].drop_duplicates()
                top_lobbyists = top_lobbyists.merge(lobby_display, on="LobbyShort", how="left")
                top_lobbyists["Lobbyist"] = top_lobbyists["LobbyNameDisplay"].fillna(top_lobbyists["LobbyShort"])
                top_lobbyists["Taxpayer Funded Total"] = top_lobbyists.apply(
                    lambda r: f"{fmt_usd(r.get('Low_TFL', 0.0))} - {fmt_usd(r.get('High_TFL', 0.0))}", axis=1
                )
                st.dataframe(
                    top_lobbyists[["Lobbyist", "Taxpayer Funded Total"]],
                    use_container_width=True,
                    height=240,
                    hide_index=True,
                )
            else:
                st.info("No taxpayer funded lobbyists found for the selected scope/session.")

        with t2:
            st.markdown('<div class="section-title">Top 5 Taxpayer Funding<br>Governments/Entities</div>', unsafe_allow_html=True)
            clients = Lobby_TFL_Client_All.copy()
            clients["Session"] = clients["Session"].astype(str).str.strip()
            if st.session_state.scope == "This Session" and tfl_session_val is not None:
                clients = clients[clients["Session"] == str(tfl_session_val)].copy()
            clients = ensure_cols(clients, {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0})
            clients = clients[clients["IsTFL"] == 1].copy()
            if not clients.empty:
                top_clients = (
                    clients.groupby("Client", as_index=False)
                    .agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
                    .sort_values(["High", "Low"], ascending=[False, False])
                    .head(5)
                )
                top_clients["Taxpayer Funded Total"] = top_clients.apply(
                    lambda r: f"{fmt_usd(r.get('Low', 0.0))} - {fmt_usd(r.get('High', 0.0))}", axis=1
                )
                st.dataframe(
                    top_clients[["Client", "Taxpayer Funded Total"]],
                    use_container_width=True,
                    height=240,
                    hide_index=True,
                )
            else:
                st.info("No taxpayer funded clients found for the selected scope/session.")

        flt = st.text_input("Filter LobbyShort (contains)", value="", placeholder="e.g., Abbott")
        c1, c2, c3 = st.columns(3)
        with c1:
            only_tfl = st.checkbox("Only taxpayer funded", value=False)
        with c2:
            only_private = st.checkbox("Only private", value=False)
        with c3:
            mixed_only = st.checkbox("Mixed only", value=False)

        view = all_pivot.copy()
        if flt.strip():
            view = view[view["LobbyShort"].astype(str).str.contains(flt.strip(), case=False, na=False)].copy()
        if only_tfl:
            view = view[view.get("Only_TFL", False)].copy()
        if only_private:
            view = view[view.get("Only_Private", False)].copy()
        if mixed_only:
            view = view[view.get("Mixed", False)].copy()

        view_disp = view.copy()
        for c in ["Low_TFL", "High_TFL", "Low_Private", "High_Private"]:
            if c in view_disp.columns:
                view_disp[c] = view_disp[c].astype(float).apply(lambda x: fmt_usd(x))

        rename_cols = {
            "Has_TFL": "Has Taxpayer Funded",
            "Only_TFL": "Only Taxpayer Funded",
            "Clients_TFL": "Taxpayer Funded Clients",
            "Low_TFL": "Taxpayer Funded Low",
            "High_TFL": "Taxpayer Funded High",
        }
        view_disp = view_disp.rename(columns=rename_cols)

        cols = [
            "LobbyShort",
            "Has_TFL", "Has_Private", "Only_TFL", "Only_Private", "Mixed",
            "Clients_TFL", "Low_TFL", "High_TFL",
            "Clients_Private", "Low_Private", "High_Private",
        ]
        cols = [rename_cols.get(c, c) for c in cols]
        cols = [c for c in cols if c in view_disp.columns]

        st.dataframe(
            view_disp[cols].sort_values(["Has Taxpayer Funded", "Mixed", "LobbyShort"], ascending=[False, False, True]),
            use_container_width=True,
            height=560,
            hide_index=True,
        )
        export_dataframe(view_disp[cols], "all_lobbyists_overview.csv", label="Download overview CSV")

# -----------------------------
# Per-lobbyist tabs: only compute when lobbyist is selected AND session != All
# -----------------------------
def _no_lobbyist_msg():
    st.info("Type a lobbyist name at the top to view details. The All Lobbyists tab is available without a selection.")

def _need_specific_session_msg():
    st.info("Select a specific session (e.g., 89th) to view lobbyist details. 'All' is for overview only.")

if st.session_state.session is None:
    with tab_overview:
        _need_specific_session_msg()
    with tab_bills:
        _need_specific_session_msg()
    with tab_policy:
        _need_specific_session_msg()
    with tab_staff:
        _need_specific_session_msg()
    with tab_activities:
        _need_specific_session_msg()
    with tab_disclosures:
        _need_specific_session_msg()
else:
    if not st.session_state.lobbyshort:
        with tab_overview:
            _no_lobbyist_msg()
        with tab_bills:
            _no_lobbyist_msg()
        with tab_policy:
            _no_lobbyist_msg()
        with tab_staff:
            _no_lobbyist_msg()
        with tab_activities:
            _no_lobbyist_msg()
        with tab_disclosures:
            _no_lobbyist_msg()
    else:
        session = str(st.session_state.session).strip()
        lobbyshort = str(st.session_state.lobbyshort).strip()
        typed_norms_tuple = tuple(sorted(typed_norms))

        # Wit_All filtered
        lobbyshort_norm = norm_name(lobbyshort)
        wit_all = Wit_All
        if "LobbyShortNorm" not in wit_all.columns:
            wit_all = wit_all.copy()
            wit_all["LobbyShortNorm"] = norm_name_series(wit_all["LobbyShort"])
        session_col = wit_all["Session"].astype(str).str.strip()
        if "LobbyShortNorm" in wit_all.columns:
            wit = wit_all[
                (session_col == session) &
                (wit_all["LobbyShortNorm"] == lobbyshort_norm)
            ].copy()
            if not wit.empty:
                wit["LobbyShort"] = lobbyshort
        else:
            wit = wit_all[
                (session_col == session) &
                (wit_all["LobbyShort"].astype(str).str.strip() == lobbyshort)
            ].copy()

        bill_pos = bill_position_from_flags(wit)
        bills = (
            bill_pos.merge(Bill_Status_All, on=["Session", "Bill"], how="left")
            if not bill_pos.empty else
            pd.DataFrame(columns=["Session", "Bill", "Position", "Author", "Caption", "Status"])
        )

        # Fiscal impacts (Version = H/S)
        fi = Fiscal_Impact[Fiscal_Impact["Session"].astype(str).str.strip() == session].copy()
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
        bills = ensure_cols(bills, {"Fiscal Impact H": 0, "Fiscal Impact S": 0})

        # Policy mentions/share
        bill_subjects = Bill_Sub_All[Bill_Sub_All["Session"].astype(str).str.strip() == session].merge(
            bills[["Session", "Bill"]].drop_duplicates(), on=["Session", "Bill"], how="inner"
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
            mentions = pd.DataFrame(columns=["Subject", "Mentions", "Share"])

        # Lobbyist-reported subject matters (Lobby_Sub_All)
        lobby_sub = Lobby_Sub_All.copy()
        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == session].copy()
        if "LobbyShortNorm" in lobby_sub.columns:
            lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"] == lobbyshort_norm].copy()
        else:
            lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip() == lobbyshort].copy()
        if not lobby_sub.empty:
            lobby_sub = lobby_sub.assign(
                Subject=lobby_sub.get("Subject Matter", "").fillna("").astype(str).str.strip(),
                Other=lobby_sub.get("Other Subject Matter Description", "").fillna("").astype(str).str.strip(),
                PrimaryBusiness=lobby_sub.get("Primary Business", "").fillna("").astype(str).str.strip(),
            )
            subject_non_empty = lobby_sub["Subject"].ne("").mean() if len(lobby_sub) else 0

            topic = lobby_sub["Subject"]
            topic = topic.where(topic != "", "Other: " + lobby_sub["Other"].where(lobby_sub["Other"] != "", ""))
            topic = topic.where(topic != "", "Primary Business: " + lobby_sub["PrimaryBusiness"].where(lobby_sub["PrimaryBusiness"] != "", ""))
            topic = topic.where(topic != "", "Unspecified")
            lobby_sub["Topic"] = topic

            lobby_sub_counts = (
                lobby_sub.groupby("Topic")
                .size()
                .reset_index(name="Mentions")
                .sort_values("Mentions", ascending=False)
            )
        else:
            lobby_sub_counts = pd.DataFrame(columns=["Topic", "Mentions"])
            subject_non_empty = 0

        # Lobbyist clients + totals (use precomputed Low_num/High_num)
        tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
        lt = Lobby_TFL_Client_All[
            (Lobby_TFL_Client_All["Session"].astype(str).str.strip() == tfl_session) &
            (Lobby_TFL_Client_All["LobbyShort"].astype(str).str.strip() == lobbyshort)
        ].copy()
        lt = ensure_cols(lt, {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0})

        has_tfl = bool((lt["IsTFL"] == 1).any()) if not lt.empty else False
        has_private = bool((lt["IsTFL"] == 0).any()) if not lt.empty else False

        tfl_clients = sorted(lt.loc[lt["IsTFL"] == 1, "Client"].dropna().astype(str).unique().tolist())
        private_clients = sorted(lt.loc[lt["IsTFL"] == 0, "Client"].dropna().astype(str).unique().tolist())

        tfl_low  = float(lt.loc[lt["IsTFL"] == 1, "Low_num"].sum()) if not lt.empty else 0.0
        tfl_high = float(lt.loc[lt["IsTFL"] == 1, "High_num"].sum()) if not lt.empty else 0.0
        pri_low  = float(lt.loc[lt["IsTFL"] == 0, "Low_num"].sum()) if not lt.empty else 0.0
        pri_high = float(lt.loc[lt["IsTFL"] == 0, "High_num"].sum()) if not lt.empty else 0.0

        # Staff history
        staff_df = Staff_All
        staff_session = staff_df["Session"].astype(str).str.strip() == session
        if typed_norms:
            typed_last_norm = last_name_norm_from_text(st.session_state.search_query)
            lobbyshort_norm = norm_name(lobbyshort)
            match_mask = (
                staff_df.get("StaffNameNorm", pd.Series(False, index=staff_df.index)).isin(typed_norms) |
                staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)).isin(typed_norms)
            )
            if typed_last_norm:
                match_mask = match_mask | (staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)) == typed_last_norm)
            if lobbyshort_norm:
                match_mask = match_mask | (staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm)
        else:
            lobbyshort_norm = norm_name(lobbyshort)
            lobby_last_norm = last_name_norm_from_text(lobbyshort)
            match_mask = pd.Series(False, index=staff_df.index)
            if lobbyshort_norm:
                match_mask = match_mask | (staff_df.get("StaffLastInitialNorm", pd.Series(False, index=staff_df.index)) == lobbyshort_norm)
            if lobby_last_norm:
                match_mask = match_mask | (staff_df.get("StaffLastNorm", pd.Series(False, index=staff_df.index)) == lobby_last_norm)

        staff_pick = staff_df[match_mask].copy()
        staff_pick_session = staff_df[staff_session & match_mask].copy()

        @st.cache_data(show_spinner=False)
        def staff_metrics(staff_rows: pd.DataFrame, bills_df: pd.DataFrame, session_val: str, bs_all: pd.DataFrame) -> pd.DataFrame:
            if staff_rows.empty or bills_df.empty:
                return pd.DataFrame(columns=["Legislator", "% Against that Failed", "% For that Passed"])

            legs = sorted(staff_rows["Legislator"].dropna().astype(str).unique().tolist())
            out = []
            bs = bs_all[bs_all["Session"].astype(str).str.strip() == str(session_val)].copy()

            for leg in legs:
                authored = bs[bs["Author"].fillna("").astype(str).str.contains(leg, case=False, na=False)][["Session", "Bill", "Status"]]
                if authored.empty:
                    out.append({"Legislator": leg, "% Against that Failed": None, "% For that Passed": None})
                    continue

                joined = authored.merge(bills_df[["Session", "Bill", "Position", "Status"]], on=["Session", "Bill"], how="inner")
                if joined.empty:
                    out.append({"Legislator": leg, "% Against that Failed": None, "% For that Passed": None})
                    continue

                against = joined[joined["Position"].astype(str).str.contains("Against", na=False)]
                denom_a = len(against)
                pct_against_failed = (against["Status"].eq("Failed").sum() / denom_a) if denom_a else None

                for_ = joined[joined["Position"].astype(str).str.contains(r"\bFor\b", regex=True, na=False)]
                denom_f = len(for_)
                pct_for_passed = (for_["Status"].eq("Passed").sum() / denom_f) if denom_f else None

                out.append({"Legislator": leg, "% Against that Failed": pct_against_failed, "% For that Passed": pct_for_passed})

            return pd.DataFrame(out)

        staff_stats = staff_metrics(staff_pick_session, bills, session, Bill_Status_All) if not staff_pick_session.empty else pd.DataFrame()

        activities = build_activities(
            data["LaFood"], data["LaEnt"], data["LaTran"], data["LaGift"], data["LaEvnt"], data["LaAwrd"],
            lobbyshort=lobbyshort,
            session=session,
            name_to_short=name_to_short,
            lobbyist_norms_tuple=typed_norms_tuple,
            filerid_to_short=data.get("filerid_to_short", {}),
        )

        disclosures = build_disclosures(
            LaCvr, LaDock, LaI4E, LaSub,
            lobbyshort=lobbyshort,
            session=session,
            name_to_short=name_to_short,
            lobbyist_norms_tuple=typed_norms_tuple,
            filerid_to_short=data.get("filerid_to_short", {}),
        )

        # ---- Overview tab
        with tab_overview:
            st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)
            o1, o2, o3, o4 = st.columns(4)
            with o1:
                kpi_card("Session", session, f"Scope: {st.session_state.scope}")
            with o2:
                kpi_card("Lobbyist", lobbyshort, st.session_state.search_query.strip() or "—")
            with o3:
                kpi_card("Taxpayer Funded Totals", f"{fmt_usd(tfl_low)} - {fmt_usd(tfl_high)}")
            with o4:
                kpi_card("Private Totals", f"{fmt_usd(pri_low)} - {fmt_usd(pri_high)}")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

            s1, s2, s3, s4 = st.columns(4)
            with s1:
                kpi_card("Taxpayer Funded?", "Yes" if has_tfl else "No")
            with s2:
                kpi_card("Private Funded?", "Yes" if has_private else "No")
            with s3:
                kpi_card("Total Bills (Witness Lists)", f"{len(bills):,}")
            with s4:
                passed = int((bills.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not bills.empty else 0
                failed = int((bills.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not bills.empty else 0
                kpi_card("Passed / Failed", f"{passed:,} / {failed:,}")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            cA, cB = st.columns(2)
            with cA:
                st.subheader("Taxpayer Funded Clients")
                st.write(", ".join(tfl_clients) if tfl_clients else "—")
            with cB:
                st.subheader("Private Clients")
                st.write(", ".join(private_clients) if private_clients else "—")

        # ---- Bills tab
        with tab_bills:
            st.markdown('<div class="section-title">Bills with Witness-List Activity</div>', unsafe_allow_html=True)
            if bills.empty:
                st.info("No witness-list rows found for this lobbyist/session in Wit_All.")
            else:
                bill_search = st.text_input("Search bills (Bill / Author / Caption)", value="", placeholder="e.g., HB 4 or Bettencourt or housing")
                filtered = bills.copy()
                if bill_search.strip():
                    q = bill_search.strip()
                    filtered = filtered[
                        filtered["Bill"].astype(str).str.contains(q, case=False, na=False) |
                        filtered["Author"].astype(str).str.contains(q, case=False, na=False) |
                        filtered["Caption"].astype(str).str.contains(q, case=False, na=False)
                    ].copy()

                f1, f2 = st.columns(2)
                with f1:
                    status_opts = sorted(filtered.get("Status", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
                    status_sel = st.multiselect("Filter by status", status_opts, default=status_opts)
                with f2:
                    pos_opts = sorted(filtered.get("Position", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
                    pos_sel = st.multiselect("Filter by position", pos_opts, default=pos_opts)

                if status_sel:
                    filtered = filtered[filtered["Status"].astype(str).isin(status_sel)].copy()
                if pos_sel:
                    filtered = filtered[filtered["Position"].astype(str).isin(pos_sel)].copy()

                for col in ["Fiscal Impact H", "Fiscal Impact S"]:
                    if col in filtered.columns:
                        filtered[col] = pd.to_numeric(filtered[col], errors="coerce").fillna(0)

                show_cols = ["Bill", "Author", "Caption", "Position", "Fiscal Impact H", "Fiscal Impact S", "Status"]
                show_cols = [c for c in show_cols if c in filtered.columns]

                st.dataframe(filtered[show_cols].sort_values(["Bill"]), use_container_width=True, height=520, hide_index=True)
                export_dataframe(filtered[show_cols], "bills.csv")

        # ---- Policy tab
        with tab_policy:
            st.markdown('<div class="section-title">Policy Areas</div>', unsafe_allow_html=True)
            if mentions.empty:
                st.info("No subjects found (Bill_Sub_All join returned 0 rows).")
            else:
                m2 = mentions.copy()
                m2["Share"] = (m2["Share"] * 100).round(0).astype("Int64").astype(str) + "%"
                m2 = m2.rename(columns={"Subject": "Policy Area"})
                st.dataframe(m2[["Policy Area", "Mentions", "Share"]], use_container_width=True, height=520, hide_index=True)
                export_dataframe(m2, "policy_areas.csv")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.subheader("Reported Subject Matters (Lobby_Sub_All)")
            if lobby_sub_counts.empty:
                st.info("No Lobby_Sub_All rows found for this lobbyist/session.")
            else:
                if subject_non_empty < 0.05:
                    st.caption("Note: Subject Matter is largely blank for this session in the source data. Showing Other Subject Matter and Primary Business when available.")
                st.dataframe(
                    lobby_sub_counts.rename(columns={"Topic": "Subject Matter"}),
                    use_container_width=True,
                    height=420,
                    hide_index=True,
                )
                export_dataframe(lobby_sub_counts, "reported_subject_matters.csv")

        # ---- Staff tab
        with tab_staff:
            st.markdown('<div class="section-title">Legislative Staffer History</div>', unsafe_allow_html=True)
            if staff_pick.empty:
                st.info("No staff-history rows matched for this lobbyist in Staff_All.")
            else:
                st.caption("Showing staff history across all sessions.")
                cols = ["Session", "Legislator", "Title", "Staffer"]
                staff_view = staff_pick[cols].drop_duplicates().sort_values(["Session", "Legislator", "Title"])
                st.dataframe(staff_view, use_container_width=True, height=380, hide_index=True)
                export_dataframe(staff_view, "staff_history.csv")

            if staff_pick_session.empty:
                st.caption("Session-specific staff metrics are not shown because there are no matches for the selected session.")
            elif not staff_stats.empty:
                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                st.caption("Computed from authored bills intersected with this lobbyist’s witness activity.")
                s2 = staff_stats.copy()
                for col in ["% Against that Failed", "% For that Passed"]:
                    s2[col] = pd.to_numeric(s2[col], errors="coerce")
                    s2[col] = (s2[col] * 100).round(0)
                st.dataframe(s2, use_container_width=True, height=320, hide_index=True)
                export_dataframe(s2, "staff_stats.csv")

        # ---- Activities tab
        with tab_activities:
            st.markdown('<div class="section-title">Lobbying Expenditures / Activity</div>', unsafe_allow_html=True)
            if activities.empty:
                st.info("No activity rows found for this lobbyist/session in activity sheets (after improved matching).")
                st.caption("If Excel still shows rows, your workbook may key activities on a different ID (e.g., filerID).")
            else:
                filt = activities.copy()
                t_opts = sorted(filt["Type"].dropna().astype(str).unique().tolist())
                sel_types = st.multiselect("Filter by activity type", t_opts, default=t_opts)
                if sel_types:
                    filt = filt[filt["Type"].isin(sel_types)].copy()

                search_text = st.text_input("Search activities (filer, member, description)", value="")
                if search_text.strip():
                    q = search_text.strip()
                    filt = filt[
                        filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Member"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Description"].astype(str).str.contains(q, case=False, na=False)
                    ].copy()

                date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                if date_parsed.notna().any():
                    min_d = date_parsed.min().date()
                    max_d = date_parsed.max().date()
                    d_from, d_to = st.date_input("Date range", (min_d, max_d))
                    if d_from and d_to:
                        mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                        filt = filt[mask].copy()

                st.caption(f"{len(filt):,} rows")
                st.dataframe(filt, use_container_width=True, height=560, hide_index=True)
                export_dataframe(filt, "activities.csv")

        # ---- Disclosures tab
        with tab_disclosures:
            st.markdown('<div class="section-title">Disclosures & Subject Matter Filings</div>', unsafe_allow_html=True)
            if disclosures.empty:
                st.info("No disclosure rows found for this lobbyist/session.")
            else:
                filt = disclosures.copy()
                d_types = sorted(filt["Type"].dropna().astype(str).unique().tolist())
                sel_types = st.multiselect("Filter by disclosure type", d_types, default=d_types)
                if sel_types:
                    filt = filt[filt["Type"].isin(sel_types)].copy()

                q = st.text_input("Search disclosures (filer, description, entity)", value="")
                if q.strip():
                    q = q.strip()
                    filt = filt[
                        filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Description"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Entity"].astype(str).str.contains(q, case=False, na=False)
                    ].copy()

                date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                if date_parsed.notna().any():
                    min_d = date_parsed.min().date()
                    max_d = date_parsed.max().date()
                    d_from, d_to = st.date_input("Date range", (min_d, max_d), key="disclosure_dates")
                    if d_from and d_to:
                        mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                        filt = filt[mask].copy()

                st.caption(f"{len(filt):,} rows")
                st.dataframe(filt, use_container_width=True, height=560, hide_index=True)
                export_dataframe(filt, "disclosures.csv")

# Hide Streamlit chrome
st.markdown(
    """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
""",
    unsafe_allow_html=True,
)
