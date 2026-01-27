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
PATH = r"C:\Users\ben\OneDrive\Documents\TFL Webstite books - combined.parquet"
_base_path = Path(PATH)
if not _base_path.exists():
    _fallback = Path(__file__).resolve().parent.parent / "TFL Webstite books - combined.parquet"
    if _fallback.exists():
        _base_path = _fallback
PATH = str(_base_path)

st.set_page_config(page_title="TPPF Lobby Look-Up", layout="wide")

# =========================================================
# STYLE (unchanged)
# =========================================================
st.markdown(
    """
<style>
:root{
  --bg: #071627;
  --panel: rgba(255,255,255,0.06);
  --panel2: rgba(255,255,255,0.04);
  --border: rgba(255,255,255,0.10);
  --text: rgba(255,255,255,0.92);
  --muted: rgba(255,255,255,0.70);
  --accent: #1e90ff;
}

html, body, [data-testid="stAppViewContainer"]{
  background: radial-gradient(1200px 600px at 20% 15%, rgba(30,144,255,0.16), transparent 60%),
              radial-gradient(900px 500px at 75% 30%, rgba(0,255,180,0.08), transparent 55%),
              var(--bg) !important;
  color: var(--text) !important;
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

[data-testid="stSidebar"]{
  background: rgba(255,255,255,0.02) !important;
  border-right: 1px solid rgba(255,255,255,0.07);
}

[data-testid="stDataFrame"]{
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.10);
}

button[kind="primary"]{
  border-radius: 14px !important;
}

/* Dark text for select inputs and dropdown items */
[data-testid="stSelectbox"] [data-baseweb="select"] *{
  color: #0b1a2b !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] ::placeholder{
  color: #405264 !important;
}
[data-testid="stSelectbox"] div[role="combobox"] *{
  color: #0b1a2b !important;
}
[data-baseweb="popover"] ul[role="listbox"] *,
[data-baseweb="popover"] div[role="option"],
[data-baseweb="popover"] div[role="option"] *{
  color: #0b1a2b !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# HELPERS
# =========================================================
_RE_NONWORD = re.compile(r"[^\w]+", flags=re.UNICODE)

def norm_name(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x).replace("\u00A0", " ").strip().upper()
    return _RE_NONWORD.sub("", s)

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

def render_bill_search_results(bill_query: str, session_val: str | None,
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
    d = d[d["LobbyShort"].notna() & (d["LobbyShort"].astype(str).str.strip() != "")].copy()

    tfl = lobby_tfl_client_all.copy()
    tfl["Session"] = tfl["Session"].astype(str).str.strip()
    if session_val is not None:
        tfl = tfl[tfl["Session"] == str(session_val)].copy()
    tfl = ensure_cols(tfl, {"LobbyShort": ""})
    lobbyshort_set = set(tfl["LobbyShort"].dropna().astype(str).str.strip().unique().tolist())
    if lobbyshort_set:
        d = d[d["LobbyShort"].astype(str).str.strip().isin(lobbyshort_set)].copy()
    if d.empty:
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
    if session_val is not None:
        tfl = tfl[tfl["Session"] == str(session_val)].copy()
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

def load_workbook(path: str) -> dict:
    cfg = {
        "Wit_All": ["Session", "Bill", "LobbyShort", "IsFor", "IsAgainst", "IsOn"],
        "Bill_Status_All": ["Session", "Bill", "Author", "Caption", "Status"],
        "Fiscal_Impact": ["Session", "Bill", "Version", "EstimatedTwoYearNetImpactGR"],
        "Bill_Sub_All": ["Session", "Bill", "Subject"],
        "Lobby_TFL_Client_All": ["Session", "Client", "Lobby Name", "LobbyShort", "IsTFL", "Low", "High", "Amount", "Mid"],
        "Staff_All": ["Session", "Legislator", "Title", "Staffer", "lobby name"],
        "LaFood": ["Session", "filerName", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "restaurantName", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaEnt": ["Session", "filerName", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                  "entertainmentName", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaTran": ["Session", "filerName", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "travelPurpose", "transportationTypeDescr", "departureCity", "arrivalCity", "checkInDt", "checkOutDt"],
        "LaGift": ["Session", "filerName", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaEvnt": ["Session", "filerName", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription"],
        "LaAwrd": ["Session", "filerName", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
    }

    base = Path(path)
    if not base.exists():
        return {k: _empty_df(v) for k, v in cfg.items()}
    if base.is_dir():
        parquet_map = {
            "Wit_All": "Witness_Lists.parquet",
            "Bill_Status_All": "Bill_Status.parquet",
            "Fiscal_Impact": "Fiscal_Notes.parquet",
            "Bill_Sub_All": "Bill_Sub_All.parquet",
            "Lobby_TFL_Client_All": "Lobby_TFL_Client_All.parquet",
            "Staff_All": None,
            "LaFood": "LaFood.parquet",
            "LaEnt": "LaEnt.parquet",
            "LaTran": "LaTran.parquet",
            "LaGift": "LaGift.parquet",
            "LaEvnt": "LaEvnt.parquet",
            "LaAwrd": "LaAwrd.parquet",
        }
        data = {}
        for key, cols in cfg.items():
            fname = parquet_map.get(key)
            if not fname:
                data[key] = _empty_df(cols)
                continue
            fpath = base / fname
            if not fpath.exists():
                data[key] = _empty_df(cols)
                continue
            try:
                data[key] = pd.read_parquet(fpath)
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

    for key in ["LaFood", "LaEnt", "LaTran", "LaGift", "LaEvnt", "LaAwrd"]:
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
            if "org" in wit.columns:
                org_series = wit.get("org", pd.Series([""] * len(wit))).fillna("").astype(str)
                org_norm = org_series.map(norm_name)
                mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), org_norm.map(name_to_short))
            blank = wit["LobbyShort"].isna() | (wit["LobbyShort"].astype(str).str.strip() == "")
            wit.loc[blank, "LobbyShort"] = mapped[blank].fillna("")
        data["Wit_All"] = wit

    data["name_to_short"] = name_to_short
    data["short_to_names"] = short_to_names
    data["lobby_index"] = lobby_index
    data["known_shorts"] = known_shorts
    return data

# =========================================================
# ACTIVITIES (unchanged logic, still cached)
# =========================================================
@st.cache_data(show_spinner=False)
def build_activities(df_food, df_ent, df_tran, df_gift, df_evnt, df_awrd,
                     lobbyshort: str, session: str, name_to_short: dict, lobbyist_norms_tuple: tuple[str, ...]) -> pd.DataFrame:

    lobbyist_norms = set(lobbyist_norms_tuple)

    def keep(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        d = df[df["Session"].astype(str).str.strip() == str(session)].copy()
        d["FilerShortMapped"] = d["filerName"].map(lambda x: name_to_short.get(norm_name(x), None))
        d["FilerNorm"] = d["filerName"].map(norm_name)
        d["FilerIsShort"] = d["filerName"].astype(str).str.strip().eq(str(lobbyshort))

        ok = (
            (d["FilerShortMapped"].astype(str) == str(lobbyshort)) |
            (d["FilerNorm"].isin(lobbyist_norms) if lobbyist_norms else False) |
            (d["FilerIsShort"])
        )
        return d[ok].copy()

    out = []

    d = keep(df_food)
    if not d.empty:
        out.append(pd.DataFrame({
            "Type": "Food",
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("restaurantName", "").fillna("").astype(str),
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
        }))

    d = keep(df_ent)
    if not d.empty:
        out.append(pd.DataFrame({
            "Type": "Entertainment",
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
        out.append(pd.DataFrame({
            "Type": "Travel",
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": desc2,
            "Amount": "",
        }))

    d = keep(df_gift)
    if not d.empty:
        out.append(pd.DataFrame({
            "Type": "Gift",
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
        }))

    d = keep(df_evnt)
    if not d.empty:
        out.append(pd.DataFrame({
            "Type": "Event",
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": "",
        }))

    d = keep(df_awrd)
    if not d.empty:
        out.append(pd.DataFrame({
            "Type": "Award",
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
        }))

    if not out:
        return pd.DataFrame(columns=["Type", "Member", "Description", "Amount"])

    result = pd.concat(out, ignore_index=True)
    for c in ["Member", "Description", "Amount"]:
        result[c] = result[c].fillna("").astype(str)
    return result

# =========================================================
# APP HEADER
# =========================================================
st.markdown('<div class="big-title">TPPF Lobby Look-Up</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Search any lobbyist and see clients, witness activity, fiscal impacts, and expenditures.</div>', unsafe_allow_html=True)

# Validate workbook path
if not os.path.exists(PATH):
    st.error("Data path not found. Update PATH at the top of main.py.")
    st.stop()

# Load workbook once (cached)
with st.spinner("Loading workbook..."):
    data = load_workbook(PATH)

Wit_All = data["Wit_All"]
Bill_Status_All = data["Bill_Status_All"]
Fiscal_Impact = data["Fiscal_Impact"]
Bill_Sub_All = data["Bill_Sub_All"]
Lobby_TFL_Client_All = data["Lobby_TFL_Client_All"]
Staff_All = data["Staff_All"]
name_to_short = data["name_to_short"]
short_to_names = data["short_to_names"]
lobby_index = data["lobby_index"]
known_shorts = data["known_shorts"]

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
if not sessions:
    st.error("No sessions found in the workbook.")
    st.stop()

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
    label_to_session = {"All": None}
    session_labels = ["All"]
    for s in sessions:
        try:
            lab = _ordinal(int(s))
        except Exception:
            lab = s
        session_labels.append(lab)
        label_to_session[lab] = s

    default_session = sessions[-1]
    default_label = _ordinal(int(default_session)) if default_session.isdigit() else default_session

    # initialize once
    if st.session_state.session is None:
        st.session_state.session = default_session

    current_label = "All" if st.session_state.session is None else (
        _ordinal(int(st.session_state.session)) if str(st.session_state.session).isdigit() else str(st.session_state.session)
    )
    if current_label not in session_labels:
        current_label = default_label if default_label in session_labels else session_labels[0]

    chosen_label = st.selectbox("Session", session_labels, index=session_labels.index(current_label))
    st.session_state.session = label_to_session.get(chosen_label, None)

with top3:
    st.markdown('<div class="small-muted">Known name variants</div>', unsafe_allow_html=True)
    names_hint = short_to_names.get(st.session_state.lobbyshort, [])
    st.write(", ".join(names_hint) if names_hint else "—")

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

if suggestions:
    label_to_short = {s: s.split(" - ")[0] for s in suggestions}
    pick = st.selectbox("Suggestions", ["Select a lobbyist..."] + suggestions, index=0)
    if pick in label_to_short:
        resolved_short = label_to_short[pick]

st.session_state.lobbyshort = resolved_short or ""

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
    st.session_state.session,
    st.session_state.scope,
)

if bill_mode:
    st.subheader("Bill Search Results")
    render_bill_search_results(
        st.session_state.search_query,
        st.session_state.session,
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
tab_all, tab_overview, tab_bills, tab_policy, tab_staff, tab_activities = st.tabs(
    ["All Lobbyists", "Overview", "Bills", "Policy Areas", "Staff History", "Activities"]
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
    st.subheader(f"All Lobbyists Overview — {st.session_state.scope}")

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
            st.subheader("Top 5 Taxpayer Funded Lobbyists")
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
            st.subheader("Top 5 Taxpayer Funding Governments/Entities")
            clients = Lobby_TFL_Client_All.copy()
            clients["Session"] = clients["Session"].astype(str).str.strip()
            if st.session_state.scope == "This Session" and st.session_state.session is not None:
                clients = clients[clients["Session"] == str(st.session_state.session)].copy()
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
        view = all_pivot.copy()
        if flt.strip():
            view = view[view["LobbyShort"].astype(str).str.contains(flt.strip(), case=False, na=False)].copy()

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
    else:
        session = str(st.session_state.session)
        lobbyshort = str(st.session_state.lobbyshort).strip()
        typed_norms_tuple = tuple(sorted(typed_norms))

        # Wit_All filtered
        wit = Wit_All[
            (Wit_All["Session"].astype(str).str.strip() == session) &
            (Wit_All["LobbyShort"].astype(str).str.strip() == lobbyshort)
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

        # Lobbyist clients + totals (use precomputed Low_num/High_num)
        lt = Lobby_TFL_Client_All[
            (Lobby_TFL_Client_All["Session"].astype(str).str.strip() == session) &
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
        if typed_norms:
            staff_pick = Staff_All[
                (Staff_All["Session"].astype(str).str.strip() == session) &
                (Staff_All["lobby name"].map(norm_name).isin(typed_norms))
            ].copy()
        else:
            staff_pick = Staff_All[
                (Staff_All["Session"].astype(str).str.strip() == session) &
                (Staff_All["lobby name"].astype(str).str.contains(lobbyshort, case=False, na=False))
            ].copy()

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

        staff_stats = staff_metrics(staff_pick, bills, session, Bill_Status_All)

        activities = build_activities(
            data["LaFood"], data["LaEnt"], data["LaTran"], data["LaGift"], data["LaEvnt"], data["LaAwrd"],
            lobbyshort=lobbyshort,
            session=session,
            name_to_short=name_to_short,
            lobbyist_norms_tuple=typed_norms_tuple,
        )

        # ---- Overview tab
        with tab_overview:
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
            st.subheader("Bills with Witness-List Activity")
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

                for col in ["Fiscal Impact H", "Fiscal Impact S"]:
                    if col in filtered.columns:
                        filtered[col] = pd.to_numeric(filtered[col], errors="coerce").fillna(0)

                show_cols = ["Bill", "Author", "Caption", "Position", "Fiscal Impact H", "Fiscal Impact S", "Status"]
                show_cols = [c for c in show_cols if c in filtered.columns]

                st.dataframe(filtered[show_cols].sort_values(["Bill"]), use_container_width=True, height=520, hide_index=True)
                export_dataframe(filtered[show_cols], "bills.csv")

        # ---- Policy tab
        with tab_policy:
            st.subheader("Policy Areas")
            if mentions.empty:
                st.info("No subjects found (Bill_Sub_All join returned 0 rows).")
            else:
                m2 = mentions.copy()
                m2["Share"] = (m2["Share"] * 100).round(0).astype("Int64").astype(str) + "%"
                m2 = m2.rename(columns={"Subject": "Policy Area"})
                st.dataframe(m2[["Policy Area", "Mentions", "Share"]], use_container_width=True, height=520, hide_index=True)
                export_dataframe(m2, "policy_areas.csv")

        # ---- Staff tab
        with tab_staff:
            st.subheader("Legislative Staffer History")
            if staff_pick.empty:
                st.info("No staff-history rows matched for this lobbyist/session in Staff_All.")
            else:
                staff_view = staff_pick[["Legislator", "Title", "Staffer"]].drop_duplicates().sort_values(["Legislator", "Title"])
                st.dataframe(staff_view, use_container_width=True, height=380, hide_index=True)
                export_dataframe(staff_view, "staff_history.csv")

            if not staff_stats.empty:
                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                st.caption("Computed from authored bills intersected with this lobbyist’s witness activity.")
                s2 = staff_stats.copy()
                for col in ["% Against that Failed", "% For that Passed"]:
                    s2[col] = (s2[col] * 100).round(0)
                st.dataframe(s2, use_container_width=True, height=320, hide_index=True)
                export_dataframe(s2, "staff_stats.csv")

        # ---- Activities tab
        with tab_activities:
            st.subheader("Lobbying Expenditures / Activity")
            if activities.empty:
                st.info("No activity rows found for this lobbyist/session in activity sheets (after improved matching).")
                st.caption("If Excel still shows rows, your workbook may key activities on a different ID (e.g., filerID).")
            else:
                st.dataframe(activities, use_container_width=True, height=560, hide_index=True)
                export_dataframe(activities, "activities.csv")

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
