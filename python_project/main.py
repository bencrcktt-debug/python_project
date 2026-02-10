import os
import re
import difflib
import html
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
import altair as alt

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
        here.parent / "data" / DEFAULT_DATA_FILENAME,
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
    --nav-h: 72px;
    --nav-bg: rgba(6, 16, 30, 0.98);
    --nav-border: rgba(255,255,255,0.08);
    --nav-search-w: 320px;
    --nav-search-h: 38px;
}

html, body, [data-testid="stAppViewContainer"]{
    background: radial-gradient(1200px 600px at 20% 15%, rgba(30,144,255,0.16), transparent 60%),
                            radial-gradient(900px 500px at 75% 30%, rgba(0,255,180,0.08), transparent 55%),
                            var(--bg) !important;
    color: var(--text) !important;
    font-family: 'IBM Plex Sans', system-ui, -apple-system, Segoe UI, sans-serif !important;
}

[data-testid="stHeader"]{ display: none !important; }
[data-testid="stToolbar"]{ right: 1rem; }
.block-container{ padding-top: calc(var(--nav-h) + 0.8rem); }

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
div[data-testid="stPlotlyChart"]{
    background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.01));
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 10px 12px 6px 12px;
    box-shadow: 0 18px 30px rgba(0,0,0,0.22);
    box-sizing: border-box;
    margin-top: 0.35rem;
}
div[data-testid="stPlotlyChart"] > div{
    border-radius: 14px;
    overflow: hidden;
}
.about-wrap{
    display: flex;
    flex-direction: column;
    gap: 20px;
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
}
.about-hero{
    position: relative;
    overflow: hidden;
    padding: 24px 24px 20px 24px;
    border-radius: 22px;
    background: linear-gradient(135deg, rgba(0,224,184,0.22), rgba(30,144,255,0.14) 45%, rgba(7,22,39,0.82));
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: 0 20px 40px rgba(0,0,0,0.35);
    backdrop-filter: blur(6px);
}
.about-hero::before{
    content: "";
    position: absolute;
    inset: -40px -10px auto auto;
    width: 320px;
    height: 320px;
    background: radial-gradient(circle, rgba(30,144,255,0.35), transparent 70%);
    opacity: 0.6;
    pointer-events: none;
}
.about-hero::after{
    content: "";
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(transparent 24px, rgba(255,255,255,0.03) 25px),
        linear-gradient(90deg, transparent 24px, rgba(255,255,255,0.03) 25px);
    background-size: 32px 32px;
    opacity: 0.18;
    pointer-events: none;
}
.about-hero > *{
    position: relative;
    z-index: 1;
}
.about-hero p{
    max-width: 980px;
}
.about-kicker{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.68rem;
    color: var(--muted);
    margin-bottom: 8px;
}
.about-title{
    font-size: 2.2rem;
    font-weight: 700;
    margin: 0 0 0.4rem 0;
    text-shadow: 0 6px 16px rgba(0,0,0,0.35);
}
.about-lead{
    font-size: 1.05rem;
    line-height: 1.55;
    margin: 0.2rem 0 0.6rem 0;
}
.about-body{
    color: var(--muted);
    margin: 0 0 0.8rem 0;
}
.about-wrap p{
    line-height: 1.55;
}
.about-meta{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 0.6rem;
}
.about-meta .pill{
    background: rgba(7,22,39,0.35);
    border-color: rgba(255,255,255,0.18);
}
.about-shell{
    display: grid;
    grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
    gap: 20px;
    align-items: start;
}
.about-sidebar{
    display: flex;
    flex-direction: column;
    gap: 20px;
}
.about-panel{
    padding: 18px 18px 16px 18px;
    border-left: 3px solid rgba(0,224,184,0.55);
    background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02));
    border-color: rgba(255,255,255,0.12);
    box-shadow: 0 16px 26px rgba(0,0,0,0.26);
    backdrop-filter: blur(4px);
}
.about-panel-head{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 0.6rem;
}
.about-panel h3{
    margin: 0;
    font-size: 1.1rem;
}
.about-panel-tag{
    font-size: 0.65rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    border: 1px solid rgba(255,255,255,0.16);
    padding: 3px 8px;
    border-radius: 999px;
    background: rgba(7,22,39,0.35);
}
.about-actions{
    display: grid;
    gap: 8px;
    margin-bottom: 0.6rem;
}
.about-action{
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 8px 10px;
    border-radius: 12px;
    background: rgba(7,22,39,0.4);
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
}
.about-action::before{
    content: "";
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent2);
    margin-top: 0.35rem;
    box-shadow: 0 0 0 3px rgba(0,224,184,0.18);
    flex: 0 0 auto;
}
.about-list-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px 12px;
    margin-top: 0.35rem;
}
.about-note{
    color: var(--muted);
    font-size: 0.95rem;
}
.about-checklist{
    list-style: none;
    padding: 0;
    margin: 0;
}
.about-checklist li{
    position: relative;
    padding-left: 1.4rem;
    margin: 0.35rem 0;
    line-height: 1.45;
}
.about-checklist li::before{
    content: "";
    position: absolute;
    left: 0;
    top: 0.5rem;
    width: 9px;
    height: 9px;
    border-radius: 3px;
    background: rgba(30,144,255,0.85);
    box-shadow: inset 0 0 0 2px rgba(30,144,255,0.15);
}
.about-main{
    display: flex;
    flex-direction: column;
    gap: 20px;
}
.about-section{
    position: relative;
    padding: 18px 18px 16px 26px;
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02));
    border-color: rgba(255,255,255,0.12);
    box-shadow: 0 18px 30px rgba(0,0,0,0.28);
    backdrop-filter: blur(4px);
}
.about-section::before{
    content: "";
    position: absolute;
    left: 14px;
    top: 18px;
    bottom: 18px;
    width: 2px;
    background: linear-gradient(180deg, rgba(30,144,255,0.9), rgba(0,224,184,0.6));
    border-radius: 999px;
}
.about-section-head{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 0.6rem;
}
.about-section-head h3{
    margin: 0;
    font-size: 1.35rem;
    letter-spacing: -0.01em;
}
.about-section-num{
    font-size: 0.68rem;
    letter-spacing: 0.2em;
    font-weight: 700;
    color: var(--accent2);
    border: 1px solid rgba(0,224,184,0.35);
    border-radius: 999px;
    padding: 4px 8px;
    background: rgba(0,224,184,0.12);
}
.source-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    margin-top: 0.6rem;
}
.source-item{
    position: relative;
    overflow: hidden;
    background: rgba(7,22,39,0.4);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 14px 12px 12px 12px;
    box-shadow: 0 14px 24px rgba(0,0,0,0.24);
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.source-item::before{
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, rgba(0,224,184,0.8), rgba(30,144,255,0.8));
    opacity: 0.7;
}
.source-title{
    font-weight: 700;
    margin-bottom: 0.2rem;
}
.source-text{
    color: var(--muted);
    font-size: 0.93rem;
    margin-bottom: 0.25rem;
}
.source-note{
    color: var(--muted);
    font-size: 0.85rem;
    margin-top: 0.35rem;
}
.source-links{
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 0.35rem;
}
.video-grid{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
    margin-top: 0.4rem;
}
.video-card{
    background: rgba(7,22,39,0.4);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 16px;
    padding: 10px;
    box-shadow: 0 14px 24px rgba(0,0,0,0.24);
}
.video-card.is-active{
    border-color: rgba(30,144,255,0.55);
    box-shadow: 0 0 0 1px rgba(30,144,255,0.35), 0 14px 24px rgba(0,0,0,0.24);
}
.video-embed{
    position: relative;
    padding-top: 56.25%;
    border-radius: 12px;
    overflow: hidden;
    background: rgba(0,0,0,0.25);
}
.video-embed iframe{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
}
.tap-hero{
    position: relative;
    overflow: hidden;
    padding: 18px 20px 16px 20px;
    border-radius: 20px;
    background: linear-gradient(135deg, rgba(30,144,255,0.18), rgba(0,224,184,0.12), rgba(7,22,39,0.85));
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: 0 18px 34px rgba(0,0,0,0.32);
}
.tap-hero::after{
    content: "";
    position: absolute;
    inset: auto -40px -50px -40px;
    height: 120px;
    background: radial-gradient(circle, rgba(30,144,255,0.25), transparent 70%);
    opacity: 0.6;
    pointer-events: none;
}
.tap-hero > *{ position: relative; z-index: 1; }
.tap-hero-kicker{
    text-transform: uppercase;
    letter-spacing: 0.2em;
    font-size: 0.7rem;
    color: var(--muted);
    margin-bottom: 6px;
}
.tap-hero-title{
    font-size: 2rem;
    font-weight: 700;
    margin: 0 0 0.4rem 0;
}
.tap-hero-lead{
    color: var(--muted);
    margin: 0;
    max-width: 860px;
    line-height: 1.55;
}
.tap-feature{
    margin-top: 1rem;
}
.tap-feature-head{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 12px;
    flex-wrap: wrap;
}
.tap-feature-kicker{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-bottom: 6px;
}
.tap-feature-title{
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0;
}
.tap-feature-summary{
    color: var(--muted);
    margin-top: 6px;
    font-size: 0.95rem;
}
.tap-feature-link{
    color: var(--text);
    text-decoration: none;
    font-weight: 600;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 999px;
    padding: 6px 12px;
    background: rgba(7,22,39,0.35);
}
.tap-feature-link:hover{
    border-color: rgba(30,144,255,0.6);
}
.tap-gallery-title{
    margin-top: 1.4rem;
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.02em;
}
.tap-thumb{
    display: block;
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 10px;
    border: 1px solid rgba(255,255,255,0.08);
}
.tap-thumb img{
    width: 100%;
    display: block;
}
.tap-card-title{
    font-weight: 700;
    margin-bottom: 4px;
}
.tap-card-summary{
    color: var(--muted);
    font-size: 0.9rem;
    margin-bottom: 6px;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.tap-card-link{
    color: var(--accent);
    text-decoration: none;
    font-size: 0.85rem;
}
.tap-card-link:hover{
    text-decoration: underline;
}
.about-link{
    color: var(--accent);
    text-decoration: none;
}
.about-link:hover{
    text-decoration: underline;
}
@keyframes about-fade-up{
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
.about-hero,
.about-panel,
.about-section{
    animation: about-fade-up 420ms ease both;
}
.about-sidebar .about-panel:nth-child(1){ animation-delay: 60ms; }
.about-sidebar .about-panel:nth-child(2){ animation-delay: 120ms; }
.about-main .about-section:nth-child(1){ animation-delay: 80ms; }
.about-main .about-section:nth-child(2){ animation-delay: 140ms; }
.about-main .about-section:nth-child(3){ animation-delay: 200ms; }
@media (prefers-reduced-motion: reduce){
    .about-hero,
    .about-panel,
    .about-section{
        animation: none;
    }
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

/* Custom navigation header */
.custom-nav{
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000;
    height: var(--nav-h);
    padding: 0 16px;
    background: linear-gradient(180deg, var(--nav-bg) 0%, rgba(6, 16, 30, 0.94) 70%, rgba(6, 16, 30, 0.9) 100%);
    border-bottom: 1px solid var(--nav-border);
    box-shadow: 0 12px 24px rgba(0,0,0,0.25);
    backdrop-filter: blur(8px);
}
.custom-nav::after{
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 1px;
    background: linear-gradient(90deg, rgba(255,255,255,0.02), rgba(255,255,255,0.16), rgba(255,255,255,0.02));
}
.custom-nav .nav-inner{
    max-width: 1280px;
    margin: 0 auto;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 28px;
    padding-right: 0;
}
.custom-nav .brand{
    display: flex;
    flex-direction: column;
    gap: 2px;
    line-height: 1.05;
    color: var(--text);
    border-left: 3px solid var(--accent);
    padding-left: 12px;
}
.custom-nav .brand-top{
    font-size: 0.9rem;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    opacity: 0.8;
}
.custom-nav .brand-bottom{
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.01em;
}
.custom-nav .nav-links{
    display: flex;
    gap: 22px;
    align-items: center;
    flex: 1 1 auto;
    margin-left: 12px;
    padding-right: calc(var(--nav-search-w) + 20px);
    white-space: nowrap;
}
.custom-nav .nav-link{
    position: relative;
    color: var(--muted);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.98rem;
    letter-spacing: 0.01em;
    padding: 10px 2px;
    transition: color 120ms ease;
}
.custom-nav .nav-link::after{
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    bottom: 2px;
    height: 2px;
    background: transparent;
    transition: background 120ms ease;
}
.custom-nav .nav-link:hover{
    color: var(--text);
}
.custom-nav .nav-link.active{
    color: var(--text);
}
.custom-nav .nav-link.active::after{
    background: var(--accent);
}

div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]){
    position: fixed;
    top: 0;
    right: 18px;
    z-index: 1002;
    width: min(var(--nav-search-w), 38vw);
    height: var(--nav-h);
    display: flex;
    align-items: center;
}
div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) > div{
    width: 100%;
    margin: 0 !important;
}
div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) input{
    height: var(--nav-search-h) !important;
    border-radius: 999px !important;
    padding: 0 38px 0 14px !important;
    background: rgba(10, 18, 32, 0.75) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.03);
    color: var(--text) !important;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23b7c2d3' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='11' cy='11' r='7'/><line x1='21' y1='21' x2='16.65' y2='16.65'/></svg>");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 16px;
}
div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) input::placeholder{
    color: rgba(255,255,255,0.6);
}

/* Mobile responsive improvements */
@media (max-width: 768px) {
    :root{ --nav-h: 108px; --nav-search-w: 100%; }
    .block-container {
        padding-left: 0.5rem;
        padding-right: 0.5rem;
        padding-top: calc(var(--nav-h) + 3.6rem);
    }
    .section-title { font-size: 1.3rem; min-height: 2.5rem; }
    .big-title { font-size: 2rem; }
    .subtitle { font-size: 1rem; }
    [data-testid="stTextInput"] input { font-size: 16px !important; }
    [data-testid="stSelectbox"] div[role="combobox"] { font-size: 14px !important; }
    button { padding: 0.5rem 1rem !important; font-size: 14px !important; }
    .stTabs [data-baseweb="tab"] { padding: 8px 12px !important; font-size: 13px !important; }
    .stTabs [data-baseweb="tab-list"]{
        flex-wrap: nowrap;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        gap: 8px;
        padding-bottom: 6px;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar{ display: none; }
    .stTabs [data-baseweb="tab"]{ flex: 0 0 auto; }
    .card{ padding: 12px 12px 10px 12px; border-radius: 16px; }
    .kpi-title{ font-size: 0.78rem; }
    .kpi-value{ font-size: 1.4rem; }
    .kpi-sub{ font-size: 0.85rem; }
    .section-sub{ font-size: 0.9rem; }
    .chip{ font-size: 0.75rem; padding: 4px 8px; margin-right: 4px; }
    [data-testid="stHorizontalBlock"]{ flex-direction: column; }
    [data-testid="column"]{ width: 100% !important; flex: 1 1 100% !important; }
    [data-testid="stDataFrame"]{ overflow-x: auto; }
    button[kind="primary"]{ width: 100%; }
    .custom-nav{
        height: var(--nav-h);
        padding: 8px 12px;
    }
    .custom-nav .nav-inner{
        flex-direction: column;
        align-items: flex-start;
        gap: 6px;
        padding-right: 0;
    }
    .custom-nav .nav-links{
        flex-wrap: nowrap;
        gap: 14px;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        padding-right: 0;
        width: 100%;
    }
    .custom-nav .nav-links::-webkit-scrollbar{ display: none; }
    .custom-nav .nav-link{ font-size: 0.9rem; padding: 8px 2px; }
    .custom-nav .brand-top{ font-size: 0.8rem; }
    .custom-nav .brand-bottom{ font-size: 1.2rem; }
    .about-shell{ grid-template-columns: 1fr; }
    .about-hero{ padding: 18px 16px 16px 16px; }
    .about-title{ font-size: 1.6rem; }
    .about-panel-head{
        flex-direction: column;
        align-items: flex-start;
    }
    .about-list-grid{ grid-template-columns: 1fr; }
    .source-grid{ grid-template-columns: 1fr; }
    .about-section{ padding-left: 22px; }
    .about-section::before{ left: 12px; }
    .tap-hero{ padding: 16px 14px 14px 14px; }
    .tap-hero-title{ font-size: 1.5rem; }
    .tap-feature-head{ flex-direction: column; align-items: flex-start; }
    div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]){
        top: calc(var(--nav-h) + 6px);
        left: 12px;
        right: 12px;
        width: auto;
        height: auto;
    }
    div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) input{
        width: 100%;
        height: 42px !important;
    }
    div[data-testid="stPlotlyChart"]{ padding: 6px 8px 4px 8px; border-radius: 16px; }
}
</style>
""",
    unsafe_allow_html=True,
)

def _page_about():
    st.markdown('<div class="section-title">About</div>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="about-wrap">
  <div class="card about-hero">
    <div class="about-kicker">Overview</div>
    <div class="about-title">Lobby Look-Up</div>
    <p class="about-lead">Lobby Look-Up makes Texas lobbying activity easier to understand -- who is
    lobbying, for whom, on what issues, and how those efforts appear in the legislative process.</p>
    <p class="about-body">The dashboard brings together lobbyists, clients, compensation ranges, bill activity,
    witness-list positions, policy subjects, and outcomes in one place. The goal is simple:
    give taxpayers, reporters, and lawmakers the ability to verify what they see and follow
    the money using publicly available records.</p>
    <div class="about-meta">
      <span class="pill"><b>Sessions</b> 85th-89th</span>
      <span class="pill"><b>Signals</b> Witness lists + filings</span>
      <span class="pill"><b>Focus</b> Transparency</span>
    </div>
  </div>
  <div class="about-shell">
    <div class="about-sidebar">
      <div class="card about-panel">
        <div class="about-panel-head">
          <h3>What You Can Do Here</h3>
          <span class="about-panel-tag">Quick Guide</span>
        </div>
        <div class="about-actions">
          <div class="about-action">Browse lobbyists immediately -- no search required.</div>
          <div class="about-action">Filter results by legislative session (85th through 89th).</div>
        </div>
        <p class="about-note">For any individual lobbyist, you can review:</p>
        <div class="about-list-grid">
          <ul class="about-checklist">
            <li>Taxpayer-funded versus privately funded clients</li>
            <li>Compensation ranges (low and high bounds)</li>
            <li>Bills with witness-list activity (for, against, or on)</li>
          </ul>
          <ul class="about-checklist">
            <li>Policy areas and subject matter</li>
            <li>Bill outcomes and fiscal-note context, where available</li>
            <li>Reported lobbying activities and expenditures (including food, gifts, travel, events, and similar items when present in the source data)</li>
          </ul>
        </div>
        <p class="about-note">Each profile moves from a high-level overview to bill-level detail, allowing users to confirm results directly against original filings.</p>
      </div>
      <div class="card about-panel">
        <div class="about-panel-head">
          <h3>Feedback or Corrections</h3>
          <span class="about-panel-tag">Contact</span>
        </div>
        <p>If you spot an error, have a question, or would like to request a feature, please email
        <a class="about-link" href="mailto:communications@texaspolicy.com">communications@texaspolicy.com</a></p>
        <p class="about-note">To help us review efficiently, include:</p>
        <ul class="about-checklist">
          <li>The legislative session</li>
          <li>The lobbyist name (or LobbyShort identifier)</li>
          <li>A brief description of the issue or requested change</li>
        </ul>
      </div>
    </div>
    <div class="about-main">
      <div class="card about-section">
        <div class="about-section-head">
          <span class="about-section-num">01</span>
          <h3>Where the Data Comes From</h3>
        </div>
        <p class="about-note">All information displayed in Lobby Look-Up is drawn from publicly available
        government and nonprofit sources, including the following:</p>
        <div class="source-grid">
          <div class="source-item">
            <div class="source-title">Texas Ethics Commission</div>
            <div class="source-text">Lobby registration records, client relationships, compensation ranges, subject-matter disclosures, and lobbying activity reports.</div>
            <div class="source-links">
              <a class="about-link" href="https://www.ethics.state.tx.us/search/lobby/" target="_blank" rel="noopener">Lobbyist Search and Filings</a>
            </div>
            <div class="source-note">Source datasets include: Subject Matter List; Lobbyist by Client; Lobbyists Compensated by Political Funds; Lobby Activities List (Food, Awards, Events, Travel, Entertainment, Fundraisers, Media).</div>
          </div>
          <div class="source-item">
            <div class="source-title">Texas Legislature Online (TLO)</div>
            <div class="source-text">Official legislative records used to connect lobbying activity to specific bills and outcomes.</div>
            <div class="source-links">
              <a class="about-link" href="https://capitol.texas.gov/billlookup/filedownloads.aspx" target="_blank" rel="noopener">Bill Files and Downloads</a>
              <a class="about-link" href="https://capitol.texas.gov/reports/BillsBy.aspx" target="_blank" rel="noopener">Bills-by Reports</a>
            </div>
            <div class="source-note">Specific datasets drawn from TLO include: Witness Lists, Bill Status, General Subject Bill Information, Fiscal Notes.</div>
          </div>
          <div class="source-item">
            <div class="source-title">Transparency USA</div>
            <div class="source-text">Supplemental lobbying records used for cross-checking and classification.</div>
            <div class="source-links">
              <a class="about-link" href="https://www.transparencyusa.org/tx/lobbying/clients?cycle=2015-to-now" target="_blank" rel="noopener">Texas Lobbying Clients (2015-present)</a>
            </div>
            <div class="source-note">Used to support: Taxpayer-funded versus privately funded client classification; cross-validation of client and lobbyist records.</div>
          </div>
          <div class="source-item">
            <div class="source-title">House Research Organization (HRO)</div>
            <div class="source-text">Legislative staff reference data.</div>
            <div class="source-links">
              <a class="about-link" href="https://hro.house.texas.gov/staff.aspx" target="_blank" rel="noopener">House and Senate Staff Lists</a>
            </div>
          </div>
        </div>
      </div>
      <div class="card about-section">
        <div class="about-section-head">
          <span class="about-section-num">02</span>
          <h3>How We Handle the Data</h3>
        </div>
        <p>Source files are retrieved as published and preserved in a format that supports
        auditability and replication.</p>
        <p>When the Texas Ethics Commission reports compensation as ranges, we retain both
        the low and high bounds and calculate rollups from those bounds rather than inventing
        artificial precision.</p>
        <p class="about-note">Because the dashboard reflects official reporting conventions, minor
        differences can occur due to rounding, aggregation, or source-level updates.</p>
      </div>
      <div class="card about-section">
        <div class="about-section-head">
          <span class="about-section-num">03</span>
          <h3>Coverage and Caveats</h3>
        </div>
        <p>This dashboard reflects what public agencies publish. If a source contains gaps,
        inconsistent naming, or missing witness-list entries, those limitations may carry through
        to the dashboard.</p>
        <p class="about-note">Witness lists are the strongest publicly available bill-level signal of
        lobbying activity, but a lobbyist's appearance or position on a bill does not always map
        cleanly to a single client. This challenge is compounded by the use of nicknames,
        abbreviations, and minor misspellings in source data. While every effort is made to
        accurately classify clients as taxpayer-funded or privately funded, some misclassifications
        may occur.</p>
      </div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

def _page_turn_off_tap():
    st.markdown('<div class="section-title">Turn off the tap</div>', unsafe_allow_html=True)

    st.markdown(
        """
<div class="card tap-hero">
  <div class="tap-hero-kicker">Video Series</div>
  <div class="tap-hero-title">Turn off the tap</div>
  <p class="tap-hero-lead">Six short explainers on transparency, lobbying, and reform. Use the selector to play
  in-page or open YouTube for sharing.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    videos = [
        {
            "id": "VfNk92xJImg",
            "embed": "https://www.youtube.com/embed/VfNk92xJImg?si=f5Yn716z6UcdLKWW",
            "title": "Taking on Taxpayer Funded Lobbying with Rep. Hillary Hickland | Parent Empowerment with Mandy Drogin",
            "summary": "Rep. Hillary Hickland of Belton shares her experiences with the taxpayer-funded lobbyist complex that's leeching off our education system, pushing ideology on kids, and ensuring that property tax bills just go up and up.",
        },
        {
            "id": "5ozqYYpP1VI",
            "embed": "https://www.youtube.com/embed/5ozqYYpP1VI?si=Iy7APVxAq3cBgdUi",
            "title": "Taxpayer Empowerment | Episode 11: Property Taxes, Lobbyists & PFAs with Rep. Helen Kerwin",
            "summary": "On this episode of Taxpayer Empowerment, TPPF's Jose Melendez sits down with Texas State Representative Helen Kerwin to discuss major property tax reform and the potential elimination of property taxes in Texas. Rep. Kerwin also shares details about her PFAS legislation designed to keep harmful chemicals out of fertilizer and protect Texas farmers and families. Plus, they expose how taxpayer-funded lobbyists were paid to fight against this important reform. Watch now to learn more about how Texas lawmakers are working to protect taxpayers, promote transparency, and ensure safer agricultural practices across the Lone Star State.",
        },
        {
            "id": "p644amuejVE",
            "embed": "https://www.youtube.com/embed/p644amuejVE?si=U_DXk6ttlI_M4HhA",
            "title": "Taxpayer Empowerment | Episode 6: Property Taxes & Taxpayer-Funded Lobbying with Rep. Cody Vasut",
            "summary": "On this episode of Taxpayer Empowerment, TPPF's Jose Melendez sits down with Representative Cody Vasut to break down the latest efforts at the Texas Legislature to deliver real property tax relief and stop government entities from using your tax dollars to lobby against you.",
        },
        {
            "id": "RWLD-zC9Slg",
            "embed": "https://www.youtube.com/embed/RWLD-zC9Slg?si=CCapZXXDO4xOaQFw",
            "title": "Fund Students Not Lobbyists | Fast Facts",
            "summary": "Texas schools should focus on one thing: educating our kids. But too often districts are spending taxpayer money not on classrooms, but on lobbying the legislature.",
        },
        {
            "id": "RAClQAg_JpU",
            "embed": "https://www.youtube.com/embed/RAClQAg_JpU?si=D4RrYgtq4FIdUTrb",
            "title": "Lobbyists Paid By You | Fast Facts",
            "summary": "Your tax dollars fund everything from police to potholes. But one thing your money shouldn't be doing is lining the pockets on lobbyists. Unfortunately, local governments in Texas spend millions of your tax dollars on lobbyists that advocate against your interests.",
        },
        {
            "id": "LUxuCq0SeQA",
            "embed": "https://www.youtube.com/embed/LUxuCq0SeQA?si=dxLmQ4Vo621qmCBV",
            "title": "Parent Empowerment with Mandy Drogin | Local Government Reform with Senator Mayes Middleton",
            "summary": "Senator Mayes Middleton of Galveston breaks down how local governments are running massive deficits, taking on huge amounts of debt, and not just wasting taxpayer money, but weaponizing it against their own citizens.",
        },
    ]

    video_titles = [video["title"] for video in videos]
    if (
        "tap_selected_title" not in st.session_state
        or st.session_state.tap_selected_title not in video_titles
    ):
        st.session_state.tap_selected_title = video_titles[0]

    controls = st.columns([3, 1])
    with controls[0]:
        selected_title = st.selectbox(
            "Choose a video",
            video_titles,
            key="tap_selected_title",
            label_visibility="collapsed",
        )
    with controls[1]:
        show_all_players = st.checkbox("Show all players", value=False)

    selected = next(video for video in videos if video["title"] == selected_title)
    selected_watch_url = f"https://www.youtube.com/watch?v={selected['id']}"
    selected_summary = selected.get("summary", "").strip()
    selected_title_html = html.escape(selected.get("title", ""), quote=True)
    selected_summary_html = (
        f'<div class="tap-feature-summary">{html.escape(selected_summary, quote=True)}</div>'
        if selected_summary
        else ""
    )

    st.markdown(
        f"""
<div class="card tap-feature">
  <div class="tap-feature-head">
    <div>
      <div class="tap-feature-kicker">Now Playing</div>
      <div class="tap-feature-title">{selected_title_html}</div>{selected_summary_html}
    </div>
    <a class="tap-feature-link" href="{selected_watch_url}" target="_blank" rel="noopener">Open in YouTube</a>
  </div>
  <div class="video-embed tap-feature-embed">
    <iframe src="{selected['embed']}" title="YouTube video player" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="tap-gallery-title">Gallery</div>', unsafe_allow_html=True)
    gallery_cards = []
    for video in videos:
        watch_url = f"https://www.youtube.com/watch?v={video['id']}"
        thumb_url = f"https://img.youtube.com/vi/{video['id']}/hqdefault.jpg"
        summary = video.get("summary", "").strip()
        safe_title = html.escape(video.get("title", ""), quote=True)
        summary_html = (
            f'<div class="tap-card-summary">{html.escape(summary, quote=True)}</div>'
            if summary
            else ""
        )
        active_class = " is-active" if video["title"] == selected_title else ""
        gallery_cards.append(
            f"""
  <div class="video-card{active_class}">
    <a class="tap-thumb" href="{watch_url}" target="_blank" rel="noopener">
      <img src="{thumb_url}" alt="{safe_title} thumbnail"/>
    </a>
    <div class="tap-card-title">{safe_title}</div>{summary_html}
    <a class="tap-card-link" href="{watch_url}" target="_blank" rel="noopener">Open in YouTube</a>
  </div>
"""
        )
    st.markdown(f'<div class="video-grid">{"".join(gallery_cards)}</div>', unsafe_allow_html=True)
    st.caption("Tip: use the selector to play in-page. Thumbnails open YouTube in a new tab.")

    if show_all_players:
        st.markdown('<div class="tap-gallery-title">All Players</div>', unsafe_allow_html=True)
        all_cards = []
        for video in videos:
            all_cards.append(
                f"""
  <div class="video-card">
    <div class="video-embed">
      <iframe src="{video['embed']}" title="YouTube video player" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
    </div>
    <div class="tap-card-title">{video['title']}</div>
  </div>
"""
            )
        st.markdown(f'<div class="video-grid">{"".join(all_cards)}</div>', unsafe_allow_html=True)

def _page_solutions():
    st.markdown('<div class="section-title">Solutions</div>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="about-wrap">
  <div class="card about-hero">
    <div class="about-kicker">Policy Solution</div>
    <div class="about-title">Ending Taxpayer-Funded Lobbying by Local Governments</div>
    <p class="about-lead">Local governments across Texas spend tens of millions of taxpayer dollars each session to hire registered lobbyists -- either directly through contracts or indirectly through association dues. These lobbyists often work to oppose property tax relief, expand local taxing authority, and block reforms supported by taxpayers.</p>
    <p class="about-body">This practice creates a clear conflict of interest: Texans are forced to fund political advocacy against their own interests. While state agencies are subject to lobbying restrictions, no comparable limits exist for cities, counties, or school districts.</p>
    <div class="about-meta">
      <span class="pill"><b>Principle</b> Public funds should not lobby</span>
      <span class="pill"><b>Scope</b> All political subdivisions</span>
      <span class="pill"><b>Fix</b> Close the loophole</span>
    </div>
  </div>
  <div class="about-shell">
    <div class="about-sidebar">
      <div class="card about-panel">
        <div class="about-panel-head">
          <h3>The Problem</h3>
          <span class="about-panel-tag">Conflict</span>
        </div>
        <div class="about-actions">
          <div class="about-action">Oppose property tax relief and fiscal transparency.</div>
          <div class="about-action">Expand local taxing and regulatory authority.</div>
          <div class="about-action">Block reforms supported by taxpayers.</div>
        </div>
        <p class="about-note">Taxpayers should not be forced to finance lobbying that works against them.</p>
      </div>
      <div class="card about-panel">
        <div class="about-panel-head">
          <h3>Principle &amp; Policy Fix</h3>
          <span class="about-panel-tag">Solution</span>
        </div>
        <ul class="about-checklist">
          <li><b>Principle:</b> Public money should not be used to lobby the government -- at any level.</li>
          <li><b>Policy Fix:</b> Extend existing lobbying restrictions on state agencies to all political subdivisions.</li>
        </ul>
      </div>
    </div>
    <div class="about-main">
      <div class="card about-section">
        <div class="about-section-head">
          <span class="about-section-num">01</span>
          <h3>The Problem</h3>
        </div>
        <p>Local governments across Texas spend tens of millions of taxpayer dollars each session to hire registered lobbyists -- either directly through contracts or indirectly through association dues.</p>
        <p class="about-note">Those lobbyists often work to oppose property tax relief and fiscal transparency, expand local taxing authority, and block reforms supported by taxpayers.</p>
      </div>
      <div class="card about-section">
        <div class="about-section-head">
          <span class="about-section-num">02</span>
          <h3>The Solution: Enact a Comprehensive Ban</h3>
        </div>
        <p>Public money should not be used to lobby the government -- at any level.</p>
        <p class="about-note">Extend existing lobbying restrictions on state agencies to all political subdivisions.</p>
      </div>
      <div class="card about-section">
        <div class="about-section-head">
          <span class="about-section-num">03</span>
          <h3>Legislative Proposal</h3>
        </div>
        <p>Amend Texas Government Code Section 556.005 to prohibit:</p>
        <ul class="about-checklist">
          <li>Hiring of registered lobbyists (as employees or contractors) by political subdivisions.</li>
          <li>Payment of public funds for dues to organizations that lobby on behalf of local governments.</li>
        </ul>
        <p class="about-note">This closes the loophole and ensures taxpayer funds are used for public services -- not political influence.</p>
      </div>
      <div class="card about-section">
        <div class="about-section-head">
          <span class="about-section-num">04</span>
          <h3>Why It Matters</h3>
        </div>
        <ul class="about-checklist">
          <li>Restores democratic accountability -- local officials should advocate directly, not outsource with tax dollars.</li>
          <li>Protects taxpayers -- redirects millions in lobbying expenses toward core services.</li>
          <li>Ensures fairness -- levels the playing field for citizens and private stakeholders.</li>
        </ul>
        <p class="about-note">Texans deserve a government that listens -- not one that lobbies itself.</p>
      </div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

def _page_client_lookup():
    st.markdown('<div class="big-title">Client Look-Up</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">Search any client and explore lobbyists, witness activity, policy areas, and filings.</div>',
        unsafe_allow_html=True,
    )

    if not PATH:
        st.error("Data path not configured. Set the DATA_PATH environment variable.")
        st.stop()
    if not _is_url(PATH) and not os.path.exists(PATH):
        st.error("Data path not found. Set DATA_PATH or place the parquet file in ./data.")
        st.stop()

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
    tfl_sessions = set(
        Lobby_TFL_Client_All.get("Session", pd.Series(dtype=object))
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    if "client_scope" not in st.session_state:
        st.session_state.client_scope = "This Session"
    if "client_session" not in st.session_state:
        st.session_state.client_session = None
    if "client_query" not in st.session_state:
        st.session_state.client_query = ""
    if "client_name" not in st.session_state:
        st.session_state.client_name = ""
    if "client_bill_search" not in st.session_state:
        st.session_state.client_bill_search = ""
    if "client_activity_search" not in st.session_state:
        st.session_state.client_activity_search = ""
    if "client_disclosure_search" not in st.session_state:
        st.session_state.client_disclosure_search = ""
    if "client_filter" not in st.session_state:
        st.session_state.client_filter = ""

    st.sidebar.header("Filters")
    st.session_state.client_scope = st.sidebar.radio(
        "Overview scope", ["This Session", "All Sessions"], index=0, key="client_scope_radio"
    )

    sessions = sorted(
        pd.concat([
            Wit_All.get("Session", pd.Series(dtype=object)),
            Lobby_TFL_Client_All.get("Session", pd.Series(dtype=object)),
            Bill_Status_All.get("Session", pd.Series(dtype=object)),
        ], ignore_index=True).dropna().astype(str).str.strip().unique().tolist()
    )
    sessions = [s for s in sessions if s and s.lower() not in {"none", "nan", "null"}]
    sessions = sorted(sessions, key=_session_sort_key)
    if not sessions:
        st.error("No sessions found in the workbook.")
        st.stop()

    with st.sidebar.expander("Data health", expanded=False):
        st.caption(f"Data path: {PATH}")
        health = data_health_table(data)
        st.dataframe(health, use_container_width=True, height=260, hide_index=True)

    top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

    with top1:
        st.session_state.client_query = st.text_input(
            "Search client",
            value=st.session_state.client_query,
            placeholder="e.g., City of Austin",
        )

    with top2:
        label_to_session = {}
        session_labels = []
        for s in sessions:
            lab = _session_label(s)
            session_labels.append(lab)
            label_to_session[lab] = s

        default_session = _default_session_from_list(sessions)
        default_label = _session_label(default_session)

        if st.session_state.client_session is None or str(st.session_state.client_session).strip().lower() in {"none", "nan", "null", ""}:
            st.session_state.client_session = default_session

        current_label = _session_label(st.session_state.client_session)
        if current_label not in session_labels:
            current_label = default_label if default_label in session_labels else session_labels[0]

        chosen_label = st.selectbox(
            "Session",
            session_labels,
            index=session_labels.index(current_label),
            key="client_session_select",
        )
        st.session_state.client_session = label_to_session.get(chosen_label, default_session)

    client_index = build_client_index(Lobby_TFL_Client_All)
    resolved_client, client_suggestions = resolve_client_name(
        st.session_state.client_query,
        client_index,
    )

    if client_suggestions:
        pick = st.selectbox(
            "Suggestions",
            ["Select a client..."] + client_suggestions,
            index=0,
            key="client_suggestions_select",
        )
        if pick in client_suggestions:
            resolved_client = pick

    st.session_state.client_name = resolved_client or ""

    with top3:
        st.markdown('<div class="small-muted">Client</div>', unsafe_allow_html=True)
        if st.session_state.client_name:
            st.write(st.session_state.client_name)
        else:
            st.write("-")

    tfl_session_val = _tfl_session_for_filter(st.session_state.client_session, tfl_sessions)

    chips = [f"Session: {_session_label(st.session_state.client_session)}", f"Scope: {st.session_state.client_scope}"]
    if st.session_state.client_name:
        chips.append(f"Client: {st.session_state.client_name}")
    st.markdown("".join([f'<span class="chip">{c}</span>' for c in chips]), unsafe_allow_html=True)

    @st.cache_data(show_spinner=False)
    def build_all_clients_overview(df: pd.DataFrame, session_val: str | None, scope_val: str) -> tuple[pd.DataFrame, dict]:
        if df.empty:
            return pd.DataFrame(), {}

        d = df.copy()
        d["Session"] = d["Session"].astype(str).str.strip()
        if scope_val == "This Session" and session_val is not None:
            d = d[d["Session"] == str(session_val)].copy()

        d = ensure_cols(d, {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0, "LobbyShort": ""})
        d = d[d["Client"].fillna("").astype(str).str.strip() != ""].copy()
        if d.empty:
            return pd.DataFrame(), {}

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
        return g, stats

    all_clients, all_stats = build_all_clients_overview(
        Lobby_TFL_Client_All,
        tfl_session_val,
        st.session_state.client_scope,
    )

    tab_all, tab_overview, tab_lobbyists, tab_bills, tab_policy, tab_staff, tab_activities, tab_disclosures = st.tabs(
        ["All Clients", "Overview", "Lobbyists", "Bills", "Policy Areas", "Staff History", "Activities", "Disclosures"]
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

    with tab_all:
        st.markdown('<div class="section-title">All Clients Overview</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="section-sub">Scope: {st.session_state.client_scope}</div>', unsafe_allow_html=True)

        if all_clients.empty:
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
                kpi_card("Total Clients", f"{all_stats.get('total_clients', 0):,}")
                kpi_card("Taxpayer Funded Clients", f"{all_stats.get('tfl_clients', 0):,}")
            with a4:
                kpi_card("Private Clients", f"{all_stats.get('private_clients', 0):,}")

            mix_left, mix_right = st.columns([1, 2])
            with mix_left:
                st.markdown('<div class="section-sub">Funding Mix (Midpoint)</div>', unsafe_allow_html=True)
                tfl_mid = (all_stats.get("tfl_low_total", 0.0) + all_stats.get("tfl_high_total", 0.0)) / 2
                pri_mid = (all_stats.get("pri_low_total", 0.0) + all_stats.get("pri_high_total", 0.0)) / 2
                mix_df = pd.DataFrame(
                    {
                        "Funding": ["Taxpayer Funded", "Private"],
                        "Total": [tfl_mid, pri_mid],
                    }
                )
                if mix_df["Total"].sum() > 0:
                    fig_mix = px.pie(
                        mix_df,
                        names="Funding",
                        values="Total",
                        hole=0.55,
                        color="Funding",
                        color_discrete_map=FUNDING_COLOR_MAP,
                    )
                    fig_mix.update_traces(
                        textposition="inside",
                        textinfo="percent+label",
                        insidetextorientation="radial",
                        marker=dict(line=dict(color="rgba(7,22,39,0.9)", width=2)),
                        hovertemplate="%{label}: %{percent}<extra></extra>",
                    )
                    _apply_plotly_layout(fig_mix, showlegend=False, margin_top=12)
                    fig_mix.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
                    st.plotly_chart(fig_mix, use_container_width=True, config=PLOTLY_CONFIG)
                else:
                    st.info("No totals available for funding mix.")

            with mix_right:
                st.markdown('<div class="section-sub">Expenditure by Category (85th-89th, Taxpayer Funded)</div>', unsafe_allow_html=True)
                cat_base = Lobby_TFL_Client_All.copy()
                cat_base["Session"] = cat_base["Session"].astype(str).str.strip()
                cat_base = ensure_cols(cat_base, {"Client": "", "Low_num": 0.0, "High_num": 0.0, "IsTFL": 0})
                cat_base["IsTFL"] = pd.to_numeric(cat_base["IsTFL"], errors="coerce").fillna(0)
                cat_base = cat_base[cat_base["IsTFL"] == 1].copy()
                cat_base["SessionBase"] = _session_base_number_series(cat_base["Session"])
                cat_base = cat_base[cat_base["SessionBase"].between(85, 89)].copy()
                cat_base = cat_base[cat_base["Client"].fillna("").astype(str).str.strip() != ""].copy()
                if not cat_base.empty:
                    cat_base["Category"] = cat_base["Client"].map(lambda x: match_entity_type(x)[1])
                    cat_base["Low_num"] = pd.to_numeric(cat_base["Low_num"], errors="coerce").fillna(0)
                    cat_base["High_num"] = pd.to_numeric(cat_base["High_num"], errors="coerce").fillna(0)
                    cat_base["Mid"] = (cat_base["Low_num"] + cat_base["High_num"]) / 2
                    cat_group = (
                        cat_base.groupby(["SessionBase", "Category"], as_index=False)["Mid"]
                        .sum()
                        .rename(columns={"Mid": "Total"})
                    )
                    cat_group["SessionLabel"] = cat_group["SessionBase"].apply(_session_base_label)
                    session_order = sorted(cat_group["SessionBase"].dropna().unique().tolist())
                    session_labels = [_session_base_label(s) for s in session_order]
                    cat_order = (
                        cat_group.groupby("Category")["Total"]
                        .sum()
                        .sort_values(ascending=False)
                        .index.tolist()
                    )
                    fig_cat = px.bar(
                        cat_group,
                        x="SessionLabel",
                        y="Total",
                        color="Category",
                        barmode="stack",
                        category_orders={"SessionLabel": session_labels, "Category": cat_order},
                        color_discrete_sequence=CHART_COLORS,
                    )
                    fig_cat.update_traces(
                        hovertemplate="%{x}<br>%{fullData.name}: $%{y:,.0f}<extra></extra>"
                    )
                    _apply_plotly_layout(fig_cat, showlegend=True, legend_title="Category", margin_top=16)
                    fig_cat.update_layout(
                        bargap=0.22,
                        hovermode="x unified",
                        legend=dict(
                            orientation="h",
                            yanchor="top",
                            y=-0.22,
                            xanchor="left",
                            x=0,
                            font=dict(size=11, color="rgba(235,245,255,0.75)"),
                        ),
                    )
                    fig_cat.update_yaxes(
                        tickprefix="$",
                        tickformat="~s",
                        showgrid=True,
                        gridcolor="rgba(255,255,255,0.08)",
                    )
                    fig_cat.update_xaxes(title_text="", tickfont=dict(color="rgba(235,245,255,0.8)"))
                    st.plotly_chart(fig_cat, use_container_width=True, config=PLOTLY_CONFIG)
                else:
                    st.info("No taxpayer funded category totals available for 85th-89th sessions.")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

            t1, t2 = st.columns(2)
            with t1:
                st.markdown('<div class="section-title">Top 5 Taxpayer Funded Clients</div>', unsafe_allow_html=True)
                top_tfl = all_clients[all_clients["IsTFL"] == 1].copy()
                if not top_tfl.empty:
                    top_tfl = top_tfl.sort_values(["High", "Low"], ascending=[False, False]).head(5)
                    top_tfl["Taxpayer Funded Total"] = top_tfl.apply(
                        lambda r: f"{fmt_usd(r.get('Low', 0.0))} - {fmt_usd(r.get('High', 0.0))}", axis=1
                    )
                    st.dataframe(
                        top_tfl[["Client", "Taxpayer Funded Total"]],
                        use_container_width=True,
                        height=240,
                        hide_index=True,
                    )
                else:
                    st.info("No taxpayer funded clients found for the selected scope/session.")

            with t2:
                st.markdown('<div class="section-title">Top 5 Private Clients</div>', unsafe_allow_html=True)
                top_pri = all_clients[all_clients["IsTFL"] == 0].copy()
                if not top_pri.empty:
                    top_pri = top_pri.sort_values(["High", "Low"], ascending=[False, False]).head(5)
                    top_pri["Private Total"] = top_pri.apply(
                        lambda r: f"{fmt_usd(r.get('Low', 0.0))} - {fmt_usd(r.get('High', 0.0))}", axis=1
                    )
                    st.dataframe(
                        top_pri[["Client", "Private Total"]],
                        use_container_width=True,
                        height=240,
                        hide_index=True,
                    )
                else:
                    st.info("No private clients found for the selected scope/session.")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Taxpayer Funded Breakdown</div>', unsafe_allow_html=True)

            tfl_breakdown = all_clients[all_clients["IsTFL"] == 1].copy()
            if tfl_breakdown.empty:
                st.info("No taxpayer funded clients found for the selected scope/session.")
            else:
                tfl_breakdown = ensure_cols(tfl_breakdown, {"Category": "Other", "Entity Type": "Other"})
                tfl_breakdown["Category"] = tfl_breakdown["Category"].fillna("Other").astype(str)
                tfl_breakdown["Entity Type"] = tfl_breakdown["Entity Type"].fillna("Other").astype(str)

                by_category = (
                    tfl_breakdown.groupby("Category", as_index=False)
                    .agg(Clients=("Client", "nunique"), Low=("Low", "sum"), High=("High", "sum"))
                    .sort_values(["Clients", "High", "Low"], ascending=[False, False, False])
                )
                by_type = (
                    tfl_breakdown.groupby("Entity Type", as_index=False)
                    .agg(Clients=("Client", "nunique"), Low=("Low", "sum"), High=("High", "sum"))
                    .sort_values(["Clients", "High", "Low"], ascending=[False, False, False])
                )

                for df in (by_category, by_type):
                    df["Total Compensation"] = df.apply(
                        lambda r: f"{fmt_usd(r.get('Low', 0.0))} - {fmt_usd(r.get('High', 0.0))}",
                        axis=1,
                    )

                b1, b2 = st.columns(2)
                with b1:
                    st.markdown('<div class="section-sub">By Category</div>', unsafe_allow_html=True)
                    st.dataframe(
                        by_category[["Category", "Clients", "Total Compensation"]],
                        use_container_width=True,
                        height=360,
                        hide_index=True,
                    )
                with b2:
                    st.markdown('<div class="section-sub">By Entity Type</div>', unsafe_allow_html=True)
                    st.dataframe(
                        by_type[["Entity Type", "Clients", "Total Compensation"]],
                        use_container_width=True,
                        height=360,
                        hide_index=True,
                    )

            st.session_state.client_filter = st.text_input(
                "Filter client (contains)",
                value=st.session_state.client_filter,
                placeholder="e.g., Austin",
                key="client_filter_input",
            )

            view = all_clients.copy()
            if st.session_state.client_filter.strip():
                view = view[
                    view["Client"].astype(str).str.contains(st.session_state.client_filter.strip(), case=False, na=False)
                ].copy()

            view_disp = view.copy()
            view_disp["Taxpayer Funded"] = view_disp["IsTFL"].map({1: "Yes", 0: "No"})
            view_disp["Low"] = view_disp["Low"].astype(float).apply(fmt_usd)
            view_disp["High"] = view_disp["High"].astype(float).apply(fmt_usd)

            show_cols = ["Client", "Taxpayer Funded", "Lobbyists", "Low", "High"]
            st.dataframe(
                view_disp[show_cols].sort_values(["Taxpayer Funded", "Client"], ascending=[False, True]),
                use_container_width=True,
                height=560,
                hide_index=True,
            )
            export_dataframe(view_disp[show_cols], "all_clients_overview.csv", label="Download overview CSV")

    def _no_client_msg():
        st.info("Type a client name at the top to view details. The All Clients tab is available without a selection.")

    if not st.session_state.client_name:
        with tab_overview:
            _no_client_msg()
        with tab_lobbyists:
            _no_client_msg()
        with tab_bills:
            _no_client_msg()
        with tab_policy:
            _no_client_msg()
        with tab_staff:
            _no_client_msg()
        with tab_activities:
            _no_client_msg()
        with tab_disclosures:
            _no_client_msg()
        return

    session = str(st.session_state.client_session).strip()
    client_norm = norm_name(st.session_state.client_name)

    lt_base = Lobby_TFL_Client_All.copy()
    lt_base["ClientNorm"] = lt_base["Client"].map(norm_name)
    client_rows_all = lt_base[lt_base["ClientNorm"] == client_norm].copy()

    tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
    client_lt = client_rows_all[client_rows_all["Session"].astype(str).str.strip() == tfl_session].copy()
    client_lt = ensure_cols(
        client_lt,
        {"IsTFL": 0, "Client": "", "Low_num": 0.0, "High_num": 0.0, "LobbyShort": "", "Lobby Name": ""},
    )

    if client_lt.empty:
        with tab_overview:
            if not client_rows_all.empty:
                st.info("No rows found for this client in the selected session. Try another session.")
            else:
                st.info("No rows found for this client.")
        with tab_lobbyists:
            _no_client_msg()
        with tab_bills:
            _no_client_msg()
        with tab_policy:
            _no_client_msg()
        with tab_staff:
            _no_client_msg()
        with tab_activities:
            _no_client_msg()
        with tab_disclosures:
            _no_client_msg()
        return

    def _first_nonempty(series: pd.Series) -> str:
        if series is None or len(series) == 0:
            return ""
        s = series.dropna().astype(str).str.strip()
        s = s[s != ""]
        return s.iloc[0] if not s.empty else ""

    lobbyist_totals = (
        client_lt.groupby("LobbyShort", as_index=False)
        .agg(
            Low=("Low_num", "sum"),
            High=("High_num", "sum"),
            LobbyName=("Lobby Name", _first_nonempty),
        )
    )
    lobbyist_totals = lobbyist_totals.rename(columns={"LobbyName": "Lobby Name"})
    lobbyist_totals["Lobbyist"] = lobbyist_totals["Lobby Name"].fillna("").astype(str).str.strip()
    lobbyist_totals["Lobbyist"] = lobbyist_totals["Lobbyist"].where(
        lobbyist_totals["Lobbyist"] != "", lobbyist_totals["LobbyShort"]
    )
    lobbyist_totals = lobbyist_totals.sort_values(["High", "Low"], ascending=[False, False])

    lobbyshorts = lobbyist_totals["LobbyShort"].dropna().astype(str).unique().tolist()
    lobbyshort_norms = {norm_name(s) for s in lobbyshorts if s}
    lobbyshort_to_name = dict(zip(lobbyist_totals["LobbyShort"], lobbyist_totals["Lobbyist"]))

    lobbyist_names = lobbyist_totals["Lobbyist"].dropna().astype(str).tolist()
    lobbyist_norms = set()
    for name in lobbyist_names + lobbyshorts:
        lobbyist_norms |= norm_person_variants(name)
        init_key = _last_first_initial_key(name)
        if init_key:
            lobbyist_norms.add(init_key)
    lobbyist_norms_tuple = tuple(sorted(lobbyist_norms))

    client_is_tfl = bool((client_lt["IsTFL"] == 1).any())
    total_low = float(client_lt["Low_num"].sum()) if not client_lt.empty else 0.0
    total_high = float(client_lt["High_num"].sum()) if not client_lt.empty else 0.0

    wit_all = Wit_All
    if "LobbyShortNorm" not in wit_all.columns:
        wit_all = wit_all.copy()
        wit_all["LobbyShortNorm"] = norm_name_series(wit_all["LobbyShort"])
    session_col = wit_all["Session"].astype(str).str.strip()
    wit = wit_all[(session_col == session) & (wit_all["LobbyShortNorm"].isin(lobbyshort_norms))].copy()
    if not wit.empty:
        norm_to_short = {norm_name(s): s for s in lobbyshorts if s}
        wit["LobbyShort"] = wit["LobbyShortNorm"].map(norm_to_short).fillna(wit["LobbyShort"])

    bill_pos = bill_position_from_flags(wit)
    bills = (
        bill_pos.merge(Bill_Status_All, on=["Session", "Bill"], how="left")
        if not bill_pos.empty else
        pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Position", "Author", "Caption", "Status"])
    )

    if not wit.empty and "org" in wit.columns:
        orgs = wit.copy()
        orgs["Organization"] = orgs.get("org", "").fillna("").astype(str).str.strip()
        orgs = orgs.groupby(["Session", "Bill", "LobbyShort"])["Organization"].apply(
            lambda s: ", ".join(sorted({x for x in s if x}))
        ).reset_index()
        bills = bills.merge(orgs, on=["Session", "Bill", "LobbyShort"], how="left")

    if not bills.empty:
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

    bills = ensure_cols(bills, {"LobbyShort": "", "Organization": "", "Fiscal Impact H": 0, "Fiscal Impact S": 0})
    bills["Lobbyist"] = bills.get("LobbyShort", "").map(lobbyshort_to_name).fillna(bills.get("LobbyShort", ""))

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

    lobby_sub = Lobby_Sub_All.copy()
    if "Session" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == session].copy()
    elif "session" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["session"].astype(str).str.strip() == session].copy()
    if "LobbyShortNorm" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"].isin(lobbyshort_norms)].copy()
    elif "LobbyShort" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip().isin(lobbyshorts)].copy()
    else:
        lobby_sub = lobby_sub.iloc[0:0].copy()

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

        lobby_sub_counts = (
            lobby_sub.groupby("Topic")
            .size()
            .reset_index(name="Mentions")
            .sort_values("Mentions", ascending=False)
        )
    else:
        lobby_sub_counts = pd.DataFrame(columns=["Topic", "Mentions"])

    activities = build_activities_multi(
        data["LaFood"], data["LaEnt"], data["LaTran"], data["LaGift"], data["LaEvnt"], data["LaAwrd"],
        lobbyshorts=lobbyshorts,
        session=session,
        name_to_short=name_to_short,
        lobbyist_norms_tuple=lobbyist_norms_tuple,
        filerid_to_short=data.get("filerid_to_short", {}),
        lobbyshort_to_name=lobbyshort_to_name,
    )

    disclosures = build_disclosures_multi(
        LaCvr, LaDock, LaI4E, LaSub,
        lobbyshorts=lobbyshorts,
        session=session,
        name_to_short=name_to_short,
        lobbyist_norms_tuple=lobbyist_norms_tuple,
        filerid_to_short=data.get("filerid_to_short", {}),
        lobbyshort_to_name=lobbyshort_to_name,
    )

    staff_df = Staff_All
    staff_session = staff_df["Session"].astype(str).str.strip() == session if "Session" in staff_df.columns else pd.Series(False, index=staff_df.index)

    last_names = {last_name_norm_from_text(n) for n in lobbyist_names if last_name_norm_from_text(n)}
    init_map = {k: v for k, v in ((_last_first_initial_key(n), n) for n in lobbyist_names) if k}
    full_map = {norm_name(n): n for n in lobbyist_names if n}
    last_map = {k: v for k, v in ((last_name_norm_from_text(n), n) for n in lobbyist_names) if k}

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

    with tab_overview:
        st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)
        o1, o2, o3, o4 = st.columns(4)
        with o1:
            kpi_card("Session", session, f"Scope: {st.session_state.client_scope}")
        with o2:
            kpi_card("Client", st.session_state.client_name)
        with o3:
            kpi_card("Taxpayer Funded?", "Yes" if client_is_tfl else "No")
        with o4:
            kpi_card("Total Compensation", f"{fmt_usd(total_low)} - {fmt_usd(total_high)}")

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        s1, s2, s3, s4 = st.columns(4)
        with s1:
            kpi_card("Lobbyists", f"{len(lobbyshorts):,}")
        with s2:
            kpi_card("Total Bills (Witness Lists)", f"{len(bills):,}")
        with s3:
            passed = int((bills.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not bills.empty else 0
            failed = int((bills.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not bills.empty else 0
            kpi_card("Passed / Failed", f"{passed:,} / {failed:,}")
        with s4:
            kpi_card("Sessions with Client", f"{client_rows_all['Session'].astype(str).nunique():,}")

        st.markdown('<div class="section-sub">Funding Mix (Midpoint)</div>', unsafe_allow_html=True)
        client_tfl_low = float(client_lt.loc[client_lt["IsTFL"] == 1, "Low_num"].sum()) if not client_lt.empty else 0.0
        client_tfl_high = float(client_lt.loc[client_lt["IsTFL"] == 1, "High_num"].sum()) if not client_lt.empty else 0.0
        client_pri_low = float(client_lt.loc[client_lt["IsTFL"] == 0, "Low_num"].sum()) if not client_lt.empty else 0.0
        client_pri_high = float(client_lt.loc[client_lt["IsTFL"] == 0, "High_num"].sum()) if not client_lt.empty else 0.0
        client_mix = pd.DataFrame(
            {
                "Funding": ["Taxpayer Funded", "Private"],
                "Total": [
                    (client_tfl_low + client_tfl_high) / 2,
                    (client_pri_low + client_pri_high) / 2,
                ],
            }
        )
        if client_mix["Total"].sum() > 0:
            fig_client_mix = px.pie(
                client_mix,
                names="Funding",
                values="Total",
                hole=0.55,
                color="Funding",
                color_discrete_map=FUNDING_COLOR_MAP,
            )
            fig_client_mix.update_traces(
                textposition="inside",
                textinfo="percent+label",
                insidetextorientation="radial",
                marker=dict(line=dict(color="rgba(7,22,39,0.9)", width=2)),
                hovertemplate="%{label}: %{percent}<extra></extra>",
            )
            _apply_plotly_layout(fig_client_mix, showlegend=False, margin_top=12)
            fig_client_mix.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
            st.plotly_chart(fig_client_mix, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("No totals available for funding mix.")

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
        st.subheader("Lobbyists Under Contract")
        st.write(", ".join(lobbyist_totals["Lobbyist"].tolist()) if not lobbyist_totals.empty else "-")

    with tab_lobbyists:
        st.markdown('<div class="section-title">Lobbyists</div>', unsafe_allow_html=True)
        if lobbyist_totals.empty:
            st.info("No lobbyists found for this client in the selected session.")
        else:
            view = lobbyist_totals.copy()
            view["Low"] = view["Low"].astype(float).apply(fmt_usd)
            view["High"] = view["High"].astype(float).apply(fmt_usd)
            show_cols = ["Lobbyist", "LobbyShort", "Low", "High"]
            st.dataframe(view[show_cols], use_container_width=True, height=520, hide_index=True)
            export_dataframe(view[show_cols], "client_lobbyists.csv")

    with tab_bills:
        st.markdown('<div class="section-title">Bills with Witness-List Activity</div>', unsafe_allow_html=True)
        if bills.empty:
            st.info("No witness-list rows found for lobbyists tied to this client/session.")
        else:
            st.session_state.client_bill_search = st.text_input(
                "Search bills (Bill / Author / Caption / Organization)",
                value=st.session_state.client_bill_search,
                placeholder="e.g., HB 4 or housing",
                key="client_bill_search_input",
            )
            filtered = bills.copy()
            if st.session_state.client_bill_search.strip():
                q = st.session_state.client_bill_search.strip()
                filtered = filtered[
                    filtered["Bill"].astype(str).str.contains(q, case=False, na=False) |
                    filtered["Author"].astype(str).str.contains(q, case=False, na=False) |
                    filtered["Caption"].astype(str).str.contains(q, case=False, na=False) |
                    filtered["Organization"].astype(str).str.contains(q, case=False, na=False) |
                    filtered["Lobbyist"].astype(str).str.contains(q, case=False, na=False)
                ].copy()

            f1, f2, f3 = st.columns(3)
            with f1:
                status_opts = sorted(filtered.get("Status", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
                status_sel = st.multiselect("Filter by status", status_opts, default=status_opts, key="client_status_filter")
            with f2:
                pos_opts = sorted(filtered.get("Position", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
                pos_sel = st.multiselect("Filter by position", pos_opts, default=pos_opts, key="client_position_filter")
            with f3:
                lobby_opts = sorted(filtered.get("Lobbyist", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
                lobby_sel = st.multiselect("Filter by lobbyist", lobby_opts, default=lobby_opts, key="client_lobbyist_filter")

            if status_sel:
                filtered = filtered[filtered["Status"].astype(str).isin(status_sel)].copy()
            if pos_sel:
                filtered = filtered[filtered["Position"].astype(str).isin(pos_sel)].copy()
            if lobby_sel:
                filtered = filtered[filtered["Lobbyist"].astype(str).isin(lobby_sel)].copy()

            for col in ["Fiscal Impact H", "Fiscal Impact S"]:
                if col in filtered.columns:
                    filtered[col] = pd.to_numeric(filtered[col], errors="coerce").fillna(0)

            show_cols = ["Bill", "Lobbyist", "Organization", "Position", "Author", "Caption", "Fiscal Impact H", "Fiscal Impact S", "Status"]
            show_cols = [c for c in show_cols if c in filtered.columns]
            st.dataframe(filtered[show_cols].sort_values(["Bill", "Lobbyist"]), use_container_width=True, height=520, hide_index=True)
            export_dataframe(filtered[show_cols], "client_bills.csv")

    with tab_policy:
        st.markdown('<div class="section-title">Policy Areas</div>', unsafe_allow_html=True)
        if mentions.empty:
            st.info("No subjects found (Bill_Sub_All join returned 0 rows).")
        else:
            chart_mentions = mentions.copy()
            chart_mentions["SharePct"] = (chart_mentions["Share"] * 100).round(1)
            chart_mentions = chart_mentions.sort_values("Share", ascending=False)
            top_mentions = chart_mentions.head(20)
            c1, c2 = st.columns(2)
            with c1:
                fig_share = px.bar(
                    top_mentions,
                    x="SharePct",
                    y="Subject",
                    orientation="h",
                    text="SharePct",
                )
                fig_share.update_traces(
                    texttemplate="%{text:.1f}%",
                    textposition="outside",
                    marker_color="#1e90ff",
                    cliponaxis=False,
                    hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
                )
                _apply_plotly_layout(fig_share, showlegend=False, margin_top=12)
                fig_share.update_layout(margin=dict(l=8, r=36, t=12, b=8))
                fig_share.update_xaxes(
                    showgrid=True,
                    gridcolor="rgba(255,255,255,0.08)",
                    ticksuffix="%",
                    title_text="Share (%)",
                )
                fig_share.update_yaxes(title_text="", categoryorder="total descending")
                st.plotly_chart(fig_share, use_container_width=True, config=PLOTLY_CONFIG)
            with c2:
                fig_tree = px.treemap(
                    top_mentions,
                    path=["Subject"],
                    values="Mentions",
                    color="SharePct",
                    color_continuous_scale=["#0b1a2b", "#1e90ff", "#00e0b8"],
                )
                fig_tree.update_traces(
                    hovertemplate="%{label}<br>%{value} mentions (%{color:.1f}%)<extra></extra>"
                )
                _apply_plotly_layout(fig_tree, showlegend=False, margin_top=12)
                fig_tree.update_layout(coloraxis_showscale=False)
                st.plotly_chart(fig_tree, use_container_width=True, config=PLOTLY_CONFIG)

            m2 = mentions.copy()
            m2["Share"] = (m2["Share"] * 100).round(0).astype("Int64").astype(str) + "%"
            m2 = m2.rename(columns={"Subject": "Policy Area"})
            st.dataframe(m2[["Policy Area", "Mentions", "Share"]], use_container_width=True, height=520, hide_index=True)
            export_dataframe(m2, "client_policy_areas.csv")

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
        st.subheader("Reported Subject Matters (Lobby_Sub_All)")
        if lobby_sub_counts.empty:
            st.info("No Lobby_Sub_All rows found for lobbyists tied to this client/session.")
        else:
            top_topics = lobby_sub_counts.head(12).copy()
            max_mentions = int(top_topics["Mentions"].max()) if not top_topics.empty else 0
            topic_chunks = [top_topics.iloc[i:i + 4] for i in range(0, len(top_topics), 4)]
            if topic_chunks:
                cols = st.columns(len(topic_chunks))
                for col, chunk in zip(cols, topic_chunks):
                    fig_topic = px.bar(
                        chunk.sort_values("Mentions"),
                        x="Mentions",
                        y="Topic",
                        orientation="h",
                        text="Mentions",
                    )
                    fig_topic.update_traces(
                        textposition="outside",
                        marker_color="#8cc9ff",
                        cliponaxis=False,
                        hovertemplate="%{y}: %{x}<extra></extra>",
                    )
                    _apply_plotly_layout(fig_topic, showlegend=False, height=220, margin_top=8)
                    fig_topic.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                    fig_topic.update_xaxes(
                        showticklabels=False,
                        showgrid=False,
                        range=[0, max_mentions * 1.15] if max_mentions else None,
                        title_text="",
                    )
                    fig_topic.update_yaxes(
                        title_text="",
                        categoryorder="total ascending",
                        tickfont=dict(size=11, color="rgba(235,245,255,0.75)"),
                    )
                    col.plotly_chart(fig_topic, use_container_width=True, config=PLOTLY_CONFIG)

            st.dataframe(
                lobby_sub_counts.rename(columns={"Topic": "Subject Matter"}),
                use_container_width=True,
                height=420,
                hide_index=True,
            )
            export_dataframe(lobby_sub_counts, "client_reported_subject_matters.csv")

    with tab_staff:
        st.markdown('<div class="section-title">Legislative Staffer History</div>', unsafe_allow_html=True)
        if staff_pick.empty:
            st.info("No staff-history rows matched for lobbyists tied to this client.")
        else:
            st.caption("Showing staff history across all sessions.")
            cols = ["Session", "Legislator", "Title", "Staffer", "Matched Lobbyist"]
            cols = [c for c in cols if c in staff_pick.columns]
            staff_view = staff_pick[cols].drop_duplicates()
            sort_cols = [c for c in ["Session", "Legislator", "Title"] if c in staff_view.columns]
            if sort_cols:
                staff_view = staff_view.sort_values(sort_cols)
            st.dataframe(staff_view, use_container_width=True, height=380, hide_index=True)
            export_dataframe(staff_view, "client_staff_history.csv")

        if staff_pick_session.empty:
            st.caption("Session-specific staff metrics are not shown because there are no matches for the selected session.")
        elif not staff_stats.empty:
            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.caption("Computed from authored bills intersected with this client's lobbyist witness activity.")
            s2 = staff_stats.copy()
            for col in ["% Against that Failed", "% For that Passed"]:
                s2[col] = pd.to_numeric(s2[col], errors="coerce")
                s2[col] = (s2[col] * 100).round(0)
            st.dataframe(s2, use_container_width=True, height=320, hide_index=True)
            export_dataframe(s2, "client_staff_stats.csv")

    with tab_activities:
        st.markdown('<div class="section-title">Lobbying Expenditures / Activity</div>', unsafe_allow_html=True)
        if activities.empty:
            st.info("No activity rows found for lobbyists tied to this client/session.")
        else:
            filt = activities.copy()
            t_opts = sorted(filt["Type"].dropna().astype(str).unique().tolist())
            sel_types = st.multiselect("Filter by activity type", t_opts, default=t_opts, key="client_activity_types")
            if sel_types:
                filt = filt[filt["Type"].isin(sel_types)].copy()

            lobby_opts = sorted(filt["Lobbyist"].dropna().astype(str).unique().tolist())
            sel_lobby = st.multiselect("Filter by lobbyist", lobby_opts, default=lobby_opts, key="client_activity_lobbyist")
            if sel_lobby:
                filt = filt[filt["Lobbyist"].isin(sel_lobby)].copy()

            st.session_state.client_activity_search = st.text_input(
                "Search activities (lobbyist, filer, member, description)",
                value=st.session_state.client_activity_search,
                key="client_activity_search_input",
            )
            if st.session_state.client_activity_search.strip():
                q = st.session_state.client_activity_search.strip()
                filt = filt[
                    filt["Lobbyist"].astype(str).str.contains(q, case=False, na=False) |
                    filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                    filt["Member"].astype(str).str.contains(q, case=False, na=False) |
                    filt["Description"].astype(str).str.contains(q, case=False, na=False)
                ].copy()

            date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
            if date_parsed.notna().any():
                min_d = date_parsed.min().date()
                max_d = date_parsed.max().date()
                d_from, d_to = st.date_input("Date range", (min_d, max_d), key="client_activity_dates")
                if d_from and d_to:
                    mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                    filt = filt[mask].copy()

            st.caption(f"{len(filt):,} rows")
            st.dataframe(filt, use_container_width=True, height=560, hide_index=True)
            export_dataframe(filt, "client_activities.csv")

    with tab_disclosures:
        st.markdown('<div class="section-title">Disclosures & Subject Matter Filings</div>', unsafe_allow_html=True)
        if disclosures.empty:
            st.info("No disclosure rows found for lobbyists tied to this client/session.")
        else:
            filt = disclosures.copy()
            d_types = sorted(filt["Type"].dropna().astype(str).unique().tolist())
            sel_types = st.multiselect("Filter by disclosure type", d_types, default=d_types, key="client_disclosure_types")
            if sel_types:
                filt = filt[filt["Type"].isin(sel_types)].copy()

            lobby_opts = sorted(filt["Lobbyist"].dropna().astype(str).unique().tolist())
            sel_lobby = st.multiselect("Filter by lobbyist", lobby_opts, default=lobby_opts, key="client_disclosure_lobbyist")
            if sel_lobby:
                filt = filt[filt["Lobbyist"].isin(sel_lobby)].copy()

            st.session_state.client_disclosure_search = st.text_input(
                "Search disclosures (lobbyist, filer, description, entity)",
                value=st.session_state.client_disclosure_search,
                key="client_disclosure_search_input",
            )
            if st.session_state.client_disclosure_search.strip():
                q = st.session_state.client_disclosure_search.strip()
                filt = filt[
                    filt["Lobbyist"].astype(str).str.contains(q, case=False, na=False) |
                    filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                    filt["Description"].astype(str).str.contains(q, case=False, na=False) |
                    filt["Entity"].astype(str).str.contains(q, case=False, na=False)
                ].copy()

            date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
            if date_parsed.notna().any():
                min_d = date_parsed.min().date()
                max_d = date_parsed.max().date()
                d_from, d_to = st.date_input("Date range", (min_d, max_d), key="client_disclosure_dates")
                if d_from and d_to:
                    mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                    filt = filt[mask].copy()

            st.caption(f"{len(filt):,} rows")
            st.dataframe(filt, use_container_width=True, height=560, hide_index=True)
            export_dataframe(filt, "client_disclosures.csv")

    st.markdown(
        """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stToolbar"] {visibility: hidden;}
</style>
""",
        unsafe_allow_html=True,
    )

def _page_member_lookup():
    st.markdown('<div class="big-title">Legislators</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">Explore legislators through bills, witness lists, lobbying activity, and staff history.</div>',
        unsafe_allow_html=True,
    )

    if not PATH:
        st.error("Data path not configured. Set the DATA_PATH environment variable.")
        st.stop()
    if not _is_url(PATH) and not os.path.exists(PATH):
        st.error("Data path not found. Set DATA_PATH or place the parquet file in ./data.")
        st.stop()

    with st.spinner("Loading workbook..."):
        data = load_workbook(PATH)

    Wit_All = data["Wit_All"]
    Bill_Status_All = data["Bill_Status_All"]
    Lobby_TFL_Client_All = data["Lobby_TFL_Client_All"]
    Staff_All = data["Staff_All"]
    LaCvr = data["LaCvr"]
    LaDock = data["LaDock"]
    LaI4E = data["LaI4E"]
    LaSub = data["LaSub"]
    name_to_short = data["name_to_short"]
    short_to_names = data["short_to_names"]
    tfl_sessions = set(
        Lobby_TFL_Client_All.get("Session", pd.Series(dtype=object))
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    if "member_session" not in st.session_state:
        st.session_state.member_session = None
    if "member_query" not in st.session_state:
        st.session_state.member_query = ""
    if "member_name" not in st.session_state:
        st.session_state.member_name = ""
    if "member_bill_search" not in st.session_state:
        st.session_state.member_bill_search = ""
    if "member_witness_search" not in st.session_state:
        st.session_state.member_witness_search = ""
    if "member_activity_search" not in st.session_state:
        st.session_state.member_activity_search = ""

    st.sidebar.header("Filters")

    sessions = sorted(
        pd.concat([
            Bill_Status_All.get("Session", pd.Series(dtype=object)),
            Wit_All.get("Session", pd.Series(dtype=object)),
            Lobby_TFL_Client_All.get("Session", pd.Series(dtype=object)),
        ], ignore_index=True).dropna().astype(str).str.strip().unique().tolist()
    )
    sessions = [s for s in sessions if s and s.lower() not in {"none", "nan", "null"}]
    sessions = sorted(sessions, key=_session_sort_key)
    if not sessions:
        st.error("No sessions found in the workbook.")
        st.stop()

    with st.sidebar.expander("Data health", expanded=False):
        st.caption(f"Data path: {PATH}")
        health = data_health_table(data)
        st.dataframe(health, use_container_width=True, height=260, hide_index=True)

    top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

    with top1:
        st.session_state.member_query = st.text_input(
            "Search legislator",
            value=st.session_state.member_query,
            placeholder="e.g., Bell, Keith",
        )

    with top2:
        label_to_session = {}
        session_labels = []
        for s in sessions:
            lab = _session_label(s)
            session_labels.append(lab)
            label_to_session[lab] = s

        default_session = _default_session_from_list(sessions)
        default_label = _session_label(default_session)

        if st.session_state.member_session is None or str(st.session_state.member_session).strip().lower() in {"none", "nan", "null", ""}:
            st.session_state.member_session = default_session

        current_label = _session_label(st.session_state.member_session)
        if current_label not in session_labels:
            current_label = default_label if default_label in session_labels else session_labels[0]

        chosen_label = st.selectbox(
            "Session",
            session_labels,
            index=session_labels.index(current_label),
            key="member_session_select",
        )
        st.session_state.member_session = label_to_session.get(chosen_label, default_session)

    author_bills_all = build_author_bill_index(Bill_Status_All)
    member_index = build_member_index(author_bills_all)
    resolved_member, member_suggestions = resolve_member_name(
        st.session_state.member_query,
        member_index,
    )

    if member_suggestions:
        pick = st.selectbox(
            "Suggestions",
            ["Select a legislator..."] + member_suggestions,
            index=0,
            key="member_suggestions_select",
        )
        if pick in member_suggestions:
            resolved_member = pick

    st.session_state.member_name = resolved_member or ""

    with top3:
        st.markdown('<div class="small-muted">Member</div>', unsafe_allow_html=True)
        if st.session_state.member_name:
            st.write(st.session_state.member_name)
        else:
            st.write("-")

    tfl_session_val = _tfl_session_for_filter(st.session_state.member_session, tfl_sessions)

    chips = [f"Session: {_session_label(st.session_state.member_session)}"]
    if st.session_state.member_name:
        chips.append(f"Member: {st.session_state.member_name}")
    st.markdown("".join([f'<span class="chip">{c}</span>' for c in chips]), unsafe_allow_html=True)

    tab_overview, tab_bills, tab_witness, tab_activities, tab_staff = st.tabs(
        ["Overview", "Bills", "Witness Lists", "Activities", "Staff to Lobbyist"]
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

    def _no_member_msg():
        st.info("Type a legislator name at the top to view details.")

    if not st.session_state.member_name:
        with tab_overview:
            _no_member_msg()
        with tab_bills:
            _no_member_msg()
        with tab_witness:
            _no_member_msg()
        with tab_activities:
            _no_member_msg()
        with tab_staff:
            _no_member_msg()
        return

    session = str(st.session_state.member_session).strip()
    member_name = st.session_state.member_name
    member_norm = norm_name(member_name)
    member_info = parse_member_name(member_name)

    authored = author_bills_all.copy()
    authored = authored[authored["AuthorNorm"] == member_norm].copy()
    authored = authored[authored["Session"].astype(str).str.strip() == session].copy()
    authored = authored.drop_duplicates(subset=["Session", "Bill", "Author"])

    tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
    lt = Lobby_TFL_Client_All.copy()
    if "Session" in lt.columns:
        lt = lt[lt["Session"].astype(str).str.strip() == tfl_session].copy()
    lt = ensure_cols(lt, {"LobbyShort": "", "IsTFL": 0})
    tfl_flag = (
        lt.groupby("LobbyShort", as_index=False)["IsTFL"]
        .max()
        .rename(columns={"IsTFL": "Has TFL Client"})
    )

    lobbyshort_to_name = {}
    if short_to_names:
        lobbyshort_to_name = {k: (v[0] if v else k) for k, v in short_to_names.items()}
    if not lobbyshort_to_name and not Lobby_TFL_Client_All.empty:
        tmp = Lobby_TFL_Client_All[["LobbyShort", "Lobby Name"]].dropna().copy()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
        lobbyshort_to_name = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .agg(lambda s: s.dropna().astype(str).iloc[0] if len(s) else "")
            .to_dict()
        )

    bill_list = authored["Bill"].dropna().astype(str).unique().tolist()
    wit_all = Wit_All
    if "LobbyShortNorm" not in wit_all.columns and "LobbyShort" in wit_all.columns:
        wit_all = wit_all.copy()
        wit_all["LobbyShortNorm"] = norm_name_series(wit_all["LobbyShort"])

    if bill_list:
        wit = wit_all[
            (wit_all["Session"].astype(str).str.strip() == session) &
            (wit_all["Bill"].astype(str).isin(bill_list))
        ].copy()
    else:
        wit = wit_all.iloc[0:0].copy()

    if "LobbyShort" in wit.columns:
        wit = wit[wit["LobbyShort"].notna() & (wit["LobbyShort"].astype(str).str.strip() != "")].copy()

    witness = pd.DataFrame()
    if not wit.empty:
        positions = bill_position_from_flags(wit)

        orgs = pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Organization"])
        if "org" in wit.columns:
            orgs = (
                wit.assign(Organization=wit.get("org", "").fillna("").astype(str).str.strip())
                .groupby(["Session", "Bill", "LobbyShort"])["Organization"]
                .apply(lambda s: ", ".join(sorted({x for x in s if x})))
                .reset_index()
            )

        names = pd.DataFrame(columns=["Session", "Bill", "LobbyShort", "Witness Name"])
        if "name" in wit.columns:
            names = (
                wit.assign(WitnessName=wit.get("name", "").fillna("").astype(str).str.strip())
                .groupby(["Session", "Bill", "LobbyShort"])["WitnessName"]
                .apply(lambda s: ", ".join(sorted({x for x in s if x})))
                .reset_index()
                .rename(columns={"WitnessName": "Witness Name"})
            )

        witness = positions.merge(orgs, on=["Session", "Bill", "LobbyShort"], how="left")
        witness = witness.merge(names, on=["Session", "Bill", "LobbyShort"], how="left")
        witness = witness.merge(tfl_flag, on="LobbyShort", how="left")
        witness["Has TFL Client"] = witness["Has TFL Client"].map({1: "Yes", 0: "No"}).fillna("Unknown")
        witness["Lobbyist"] = witness["LobbyShort"].map(lobbyshort_to_name).fillna(witness["LobbyShort"])

        authored_base_cols = [c for c in ["Session", "Bill", "Status", "Caption", "Link"] if c in authored.columns]
        authored_base = authored[authored_base_cols].drop_duplicates()
        witness = witness.merge(authored_base, on=["Session", "Bill"], how="left")

    activities = build_member_activities(
        data["LaFood"], data["LaEnt"], data["LaTran"], data["LaGift"], data["LaEvnt"], data["LaAwrd"],
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
        activities = pd.DataFrame(columns=["Session", "Date", "Type", "LobbyShort", "Lobbyist", "Filer", "Member", "Description", "Amount", "Has TFL Client"])

    staff_df = Staff_All.copy()
    staff_matches = pd.DataFrame()
    if not staff_df.empty and "Legislator" in staff_df.columns:
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

        staff_matches = staff_df[match].copy()

    staff_lobbyists = pd.DataFrame()
    if not staff_matches.empty and "Staffer" in staff_matches.columns:
        tmp_short = Lobby_TFL_Client_All[["LobbyShort"]].dropna().copy()
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

        staff_lobbyists = staff_matches.copy()
        staff_lobbyists["LobbyShort"] = staff_lobbyists["Staffer"].fillna("").astype(str).map(map_staffer)
        staff_lobbyists = staff_lobbyists[staff_lobbyists["LobbyShort"].astype(str).str.strip() != ""].copy()
        staff_lobbyists["Lobbyist"] = staff_lobbyists["LobbyShort"].map(lobbyshort_to_name).fillna(staff_lobbyists["LobbyShort"])

    with tab_overview:
        st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)

        if authored.empty:
            st.info("No authored bills found for this legislator/session in Bill_Status_All.")
        else:
            bill_count = int(authored["Bill"].nunique())
            passed = int((authored.get("Status", pd.Series(dtype=object)) == "Passed").sum())
            failed = int((authored.get("Status", pd.Series(dtype=object)) == "Failed").sum())
            witness_rows = int(len(witness)) if isinstance(witness, pd.DataFrame) else 0
            lobbyist_count = int(witness.get("LobbyShort", pd.Series(dtype=object)).nunique()) if isinstance(witness, pd.DataFrame) and not witness.empty else 0
            tfl_count = int((witness.get("Has TFL Client", pd.Series(dtype=object)) == "Yes").sum()) if isinstance(witness, pd.DataFrame) and not witness.empty else 0

            o1, o2, o3, o4 = st.columns(4)
            with o1:
                kpi_card("Session", session)
            with o2:
                kpi_card("Member", member_name)
            with o3:
                kpi_card("Bills Authored", f"{bill_count:,}")
            with o4:
                kpi_card("Passed / Failed", f"{passed:,} / {failed:,}")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

            s1, s2, s3, s4 = st.columns(4)
            with s1:
                kpi_card("Witness Rows", f"{witness_rows:,}")
            with s2:
                kpi_card("Unique Lobbyists", f"{lobbyist_count:,}")
            with s3:
                kpi_card("Lobbyists w/ TFL Clients", f"{tfl_count:,}")
            with s4:
                kpi_card("Activities Rows", f"{len(activities):,}")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.markdown('<div class="section-sub">TFL Opposition Snapshot</div>', unsafe_allow_html=True)
            witness_df = witness if isinstance(witness, pd.DataFrame) else pd.DataFrame()
            total_bills = int(bill_count)
            tfl_opposed = 0
            tfl_any = 0
            any_witness = 0
            if not witness_df.empty:
                against_mask = witness_df.get("Position", pd.Series(dtype=object)).astype(str).str.contains("Against", case=False, na=False)
                tfl_mask = witness_df.get("Has TFL Client", pd.Series(dtype=object)).astype(str) == "Yes"
                tfl_opposed = int(witness_df.loc[against_mask & tfl_mask, "Bill"].dropna().astype(str).nunique())
                tfl_any = int(witness_df.loc[tfl_mask, "Bill"].dropna().astype(str).nunique())
                any_witness = int(witness_df.get("Bill", pd.Series(dtype=object)).dropna().astype(str).nunique())

            pie_df = pd.DataFrame(
                {
                    "Outcome": ["Opposed by TFL lobbyist", "Not opposed by TFL lobbyist"],
                    "Bills": [tfl_opposed, max(total_bills - tfl_opposed, 0)],
                }
            )
            if total_bills > 0:
                c1, c2 = st.columns([1.1, 1])
                with c1:
                    fig_tfl = px.pie(
                        pie_df,
                        names="Outcome",
                        values="Bills",
                        hole=0.55,
                        color="Outcome",
                        color_discrete_map=OPPOSITION_COLOR_MAP,
                    )
                    fig_tfl.update_traces(
                        textposition="inside",
                        textinfo="percent+label",
                        insidetextorientation="radial",
                        marker=dict(line=dict(color="rgba(7,22,39,0.9)", width=2)),
                        hovertemplate="%{label}: %{value} bills (%{percent})<extra></extra>",
                    )
                    _apply_plotly_layout(fig_tfl, showlegend=False, margin_top=12)
                    fig_tfl.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
                    st.plotly_chart(fig_tfl, use_container_width=True, config=PLOTLY_CONFIG)
                with c2:
                    summary_df = pd.DataFrame(
                        {
                            "Metric": [
                                "Bills authored",
                                "Bills with any witness",
                                "Bills with any TFL witness",
                                "Bills opposed by TFL lobbyist",
                            ],
                            "Count": [total_bills, any_witness, tfl_any, tfl_opposed],
                        }
                    )
                    st.dataframe(summary_df, use_container_width=True, height=200, hide_index=True)

        with tab_bills:
            st.markdown('<div class="section-title">Bills Authored</div>', unsafe_allow_html=True)
            if authored.empty:
                st.info("No authored bills found for this legislator/session.")
            else:
                st.session_state.member_bill_search = st.text_input(
                    "Search bills (Bill / Caption / Status)",
                    value=st.session_state.member_bill_search,
                    placeholder="e.g., HB 1 or education",
                    key="member_bill_search_input",
                )
                bill_view = authored.copy()
                if st.session_state.member_bill_search.strip():
                    q = st.session_state.member_bill_search.strip()
                    bill_view = bill_view[
                        bill_view["Bill"].astype(str).str.contains(q, case=False, na=False) |
                        bill_view.get("Caption", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False) |
                        bill_view.get("Status", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False)
                    ].copy()

                show_cols = [c for c in ["Bill", "Status", "Caption", "Chamber", "Link"] if c in bill_view.columns]
                bill_view = bill_view.drop_duplicates(subset=["Bill"])
                st.dataframe(
                    bill_view[show_cols].sort_values(["Bill"]),
                    use_container_width=True,
                    height=520,
                    hide_index=True,
                )
                export_dataframe(bill_view[show_cols], "member_bills.csv")

    with tab_witness:
        st.markdown('<div class="section-title">Witness Lists: Lobbyists and Organizations</div>', unsafe_allow_html=True)
        if witness.empty:
            st.info("No witness-list rows found for bills authored by this legislator in the selected session.")
        else:
            st.session_state.member_witness_search = st.text_input(
                "Search witness list (Bill / Lobbyist / Organization)",
                value=st.session_state.member_witness_search,
                key="member_witness_search_input",
            )
            witness_view = witness.copy()
            if st.session_state.member_witness_search.strip():
                q = st.session_state.member_witness_search.strip()
                witness_view = witness_view[
                    witness_view["Bill"].astype(str).str.contains(q, case=False, na=False) |
                    witness_view.get("Lobbyist", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False) |
                    witness_view.get("Organization", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False) |
                    witness_view.get("Witness Name", pd.Series(dtype=object)).astype(str).str.contains(q, case=False, na=False)
                ].copy()

            f1, f2, f3 = st.columns(3)
            with f1:
                pos_opts = sorted(witness_view.get("Position", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
                pos_sel = st.multiselect("Filter by position", pos_opts, default=pos_opts, key="member_pos_filter")
            with f2:
                tfl_opts = sorted(witness_view.get("Has TFL Client", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
                tfl_sel = st.multiselect("Filter by TFL", tfl_opts, default=tfl_opts, key="member_tfl_filter")
            with f3:
                lob_opts = sorted(witness_view.get("Lobbyist", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())
                lob_sel = st.multiselect("Filter by lobbyist", lob_opts, default=lob_opts, key="member_lobbyist_filter")

            if pos_sel:
                witness_view = witness_view[witness_view["Position"].astype(str).isin(pos_sel)].copy()
            if tfl_sel:
                witness_view = witness_view[witness_view["Has TFL Client"].astype(str).isin(tfl_sel)].copy()
            if lob_sel:
                witness_view = witness_view[witness_view["Lobbyist"].astype(str).isin(lob_sel)].copy()

            show_cols = [
                "Bill",
                "Lobbyist",
                "Organization",
                "Witness Name",
                "Position",
                "Has TFL Client",
                "Status",
                "Caption",
            ]
            show_cols = [c for c in show_cols if c in witness_view.columns]
            st.dataframe(
                witness_view[show_cols].sort_values(["Bill", "Lobbyist"]),
                use_container_width=True,
                height=560,
                hide_index=True,
            )
            export_dataframe(witness_view[show_cols], "member_witness_lists.csv")

    with tab_activities:
        st.markdown('<div class="section-title">Lobbyist Activity Benefiting the Member</div>', unsafe_allow_html=True)
        if activities.empty:
            st.info("No activity rows found where this legislator is the recipient.")
        else:
            filt = activities.copy()
            t_opts = sorted(filt["Type"].dropna().astype(str).unique().tolist())
            sel_types = st.multiselect("Filter by activity type", t_opts, default=t_opts, key="member_activity_types")
            if sel_types:
                filt = filt[filt["Type"].isin(sel_types)].copy()

            lobby_opts = sorted(filt["Lobbyist"].dropna().astype(str).unique().tolist())
            sel_lobby = st.multiselect("Filter by lobbyist", lobby_opts, default=lobby_opts, key="member_activity_lobbyist")
            if sel_lobby:
                filt = filt[filt["Lobbyist"].isin(sel_lobby)].copy()

            st.session_state.member_activity_search = st.text_input(
                "Search activities (lobbyist, description, filer)",
                value=st.session_state.member_activity_search,
                key="member_activity_search_input",
            )
            if st.session_state.member_activity_search.strip():
                q = st.session_state.member_activity_search.strip()
                filt = filt[
                    filt["Lobbyist"].astype(str).str.contains(q, case=False, na=False) |
                    filt["Description"].astype(str).str.contains(q, case=False, na=False) |
                    filt["Filer"].astype(str).str.contains(q, case=False, na=False)
                ].copy()

            date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
            if date_parsed.notna().any():
                min_d = date_parsed.min().date()
                max_d = date_parsed.max().date()
                d_from, d_to = st.date_input("Date range", (min_d, max_d), key="member_activity_dates")
                if d_from and d_to:
                    mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                    filt = filt[mask].copy()

            show_cols = ["Date", "Type", "Lobbyist", "Has TFL Client", "Description", "Amount"]
            show_cols = [c for c in show_cols if c in filt.columns]
            st.caption(f"{len(filt):,} rows")
            st.dataframe(filt[show_cols], use_container_width=True, height=560, hide_index=True)
            export_dataframe(filt[show_cols], "member_activities.csv")

    with tab_staff:
        st.markdown('<div class="section-title">Staff Who Became Lobbyists</div>', unsafe_allow_html=True)
        if staff_lobbyists.empty:
            st.info("No staff matches found who appear in lobbyist records.")
        else:
            cols = ["Session", "Legislator", "Title", "Staffer", "Lobbyist", "LobbyShort", "source"]
            cols = [c for c in cols if c in staff_lobbyists.columns]
            staff_view = staff_lobbyists[cols].drop_duplicates()
            sort_cols = [c for c in ["Session", "Legislator", "Staffer"] if c in staff_view.columns]
            if sort_cols:
                staff_view = staff_view.sort_values(sort_cols)
            st.dataframe(staff_view, use_container_width=True, height=420, hide_index=True)
            export_dataframe(staff_view, "member_staff_to_lobbyists.csv")

    st.markdown(
        """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
[data-testid="stToolbar"] {visibility: hidden;}
</style>
""",
        unsafe_allow_html=True,
    )

def _page_lobby_lookup():
    pass

_lobby_page = st.Page(_page_lobby_lookup, title="Lobby Look-Up", url_path="lobbyists", default=True)
_client_page = st.Page(_page_client_lookup, title="Client Look-Up", url_path="clients")
_member_page = st.Page(_page_member_lookup, title="Legislators", url_path="legislators")
_about_page = st.Page(_page_about, title="About", url_path="about")
_tap_page = st.Page(_page_turn_off_tap, title="Turn off the tap", url_path="turn-off-the-tap")
_solutions_page = st.Page(_page_solutions, title="Solutions", url_path="solutions")
_pages = [
    _lobby_page,
    _client_page,
    _member_page,
    _about_page,
    _tap_page,
    _solutions_page,
]
_active_page = st.navigation(_pages, position="hidden")

def _nav_href(page) -> str:
    url_path = page.url_path
    return "./" if url_path == "" else f"./{url_path}"

_nav_items = [
    (_lobby_page, "Lobbyists"),
    (_client_page, "Clients"),
    (_member_page, "Legislators"),
    (_about_page, "About"),
    (_tap_page, "Turn off the tap"),
    (_solutions_page, "Solutions"),
]
_nav_links = []
for page, label in _nav_items:
    active = " active" if page == _active_page else ""
    _nav_links.append(
        f'<a class="nav-link{active}" href="{_nav_href(page)}" target="_self">{label}</a>'
    )

st.markdown(
    f"""
<div class="custom-nav">
  <div class="nav-inner">
    <div class="brand">
      <div class="brand-top">TPPF</div>
      <div class="brand-bottom">Lobby Look-Up</div>
    </div>
    <div class="nav-links">
      {''.join(_nav_links)}
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

if "nav_search_query" not in st.session_state:
    st.session_state.nav_search_query = ""
if "nav_search_last" not in st.session_state:
    st.session_state.nav_search_last = ""

nav_query_raw = st.text_input(
    "Nav search",
    key="nav_search_query",
    placeholder="Search bills, clients, members, lobbyists",
    label_visibility="collapsed",
)
nav_query = nav_query_raw.strip()
nav_search_submitted = False
if nav_query and nav_query != st.session_state.nav_search_last:
    nav_search_submitted = True
    st.session_state.nav_search_last = nav_query

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

PRIMARY_PATTERNS = [
    (r"\bmetropolitan transit authority\b", "Transit Authority"),
    (r"\bregional mobility authority\b", "Regional Mobility Authority"),
    (r"\bwater control ?&? improvement district\b", "Water Control & Improvement District"),
    (r"\bmunicipal utility district\b", "Municipal Utility District"),
    (r"\bmud\b", "Municipal Utility District"),
    (r"\bgroundwater conservation district\b", "Groundwater Conservation District"),
    (r"\bhospital district\b", "Hospital District"),
    (r"\bemergency services district\b", "Emergency Services District"),
    (r"\bappraisal district\b", "Appraisal District"),
    (r"\bhousing authority\b", "Housing Authority"),
    (r"\btransit authority\b", "Transit Authority"),
    (r"\bthe league\b|\bleague\b", "League"),
    (r"\briver authority\b", "River Authority"),
    (r"\bnavigation district\b", "Navigation District"),
    (r"\bport authority\b", "Port Authority"),
    (r"\bdrainage district\b", "Drainage District"),
    (r"\b(independent )?school district\b", "Independent School District"),
    (r"\bschool district\b", "Independent School District"),
    (r"(^|\s)isd($|\s|[^a-z])", "Independent School District"),
    (r"\bwcid\b", "Water Control & Improvement District"),
    (r"\bpublic improvement district\b", "Public Improvement District"),
    (r"(^|\s)pid($|\s|[^a-z])", "Public Improvement District"),
    (r"\bmunicipal corporation\b|\blocal government corporation\b|\bcorporation\b", "Local Government Corporation"),
    (r"\bcoalition\b", "Coalition"),
    (r"\bassociation\b", "Association"),
    (r"\bcommittee\b", "Committee"),
    (r"\bfoundation\b", "Foundation"),
    (r"\bcollege\b", "College"),
    (r"\bboard\b", "Board"),
    (r"\bauthority\b", "Authority"),
    (r"\bdistrict\b", "District"),
    (r"\bcity\b", "City"),
    (r"\bcounty\b", "County"),
]

COARSE_CATEGORY = {
    "Independent School District": "Public School Districts",
    "Transit Authority": "Special Districts and Other Authorities",
    "Regional Mobility Authority": "Special Districts and Other Authorities",
    "Water Control & Improvement District": "Special Districts and Other Authorities",
    "Municipal Utility District": "Special Districts and Other Authorities",
    "Groundwater Conservation District": "Special Districts and Other Authorities",
    "Hospital District": "Special Districts and Other Authorities",
    "Emergency Services District": "Special Districts and Other Authorities",
    "Appraisal District": "Special Districts and Other Authorities",
    "Housing Authority": "Special Districts and Other Authorities",
    "River Authority": "Special Districts and Other Authorities",
    "Navigation District": "Special Districts and Other Authorities",
    "Port Authority": "Special Districts and Other Authorities",
    "Drainage District": "Special Districts and Other Authorities",
    "Public Improvement District": "Special Districts and Other Authorities",
    "Local Government Corporation": "Special Districts and Other Authorities",
    "Authority": "Special Districts and Other Authorities",
    "District": "Special Districts and Other Authorities",
    "City": "Cities, Towns, Villages",
    "County": "County",
    "College": "Community and Junior Colleges",
    "Coalition": "Associations",
    "Association": "Associations",
    "Foundation": "Associations",
    "Committee": "Associations",
    "Board": "Associations",
    "League": "Associations",
}

def normalize_entity_name(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def match_entity_type(name: str) -> tuple[str, str]:
    s = normalize_entity_name(name)
    for pattern, canonical in PRIMARY_PATTERNS:
        if re.search(pattern, s, flags=re.IGNORECASE):
            coarse = COARSE_CATEGORY.get(canonical, None)
            if canonical == "Independent School District":
                coarse = "Public School Districts"
            if canonical in ("City",):
                coarse = "Cities, Towns, Villages"
            if canonical in ("County",):
                coarse = "County"
            if not coarse:
                coarse = COARSE_CATEGORY.get(canonical, "Special Districts and Other Authorities")
            return canonical, coarse

    if re.search(r"\bschool\b", s):
        return "Independent School District", "Public School Districts"

    if re.search(r"\bcommunity college\b|\bjunior college\b", s):
        return "College", "Community and Junior Colleges"

    if re.search(r"\bcity\b|\btown\b|\bvillage\b", s):
        return "City", "Cities, Towns, Villages"
    if re.search(r"\bcounty\b", s):
        return "County", "County"
    if re.search(r"\bassociation\b|\bcoalition\b|\bfoundation\b|\bcommittee\b|\bboard\b", s):
        return "Association", "Associations"

    return "Other", "Other"

def filter_filer_rows(
    df: pd.DataFrame,
    session: str | None,
    lobbyshort: str,
    name_to_short: dict,
    lobbyist_norms: set[str],
    filerid_to_short: dict | None,
    loose: bool = False,
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
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]
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

    return d[ok].copy()

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
        return df.iloc[0:0].copy()

    lobbyshorts_set = {str(s).strip() for s in lobbyshorts if str(s).strip()}
    if not lobbyshorts_set:
        return df.iloc[0:0].copy()

    d = df.copy()
    if session is not None:
        d = d[d["Session"].astype(str).str.strip() == str(session)].copy()
    if d.empty:
        return d

    lobbyshort_norms = {norm_name(s) for s in lobbyshorts_set if s}
    norm_to_short = {norm_name(s): s for s in lobbyshorts_set if s}
    filerid_map = filerid_to_short or {}

    if "filerIdent" in d.columns and filerid_map:
        d["FilerID"] = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
        d["FilerShortFromId"] = d["FilerID"].map(filerid_map)
    else:
        d["FilerShortFromId"] = ""

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]
    filer_clean = clean_filer_name_series(filer_name)

    d["FilerNormRaw"] = norm_name_series(filer_name)
    d["FilerNormClean"] = norm_name_series(filer_clean)
    d["FilerSortNorm"] = norm_name_series(filer_sort)

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

    d = d[ok].copy()
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

_SESSION_BASE_YEAR = 2023
_SESSION_BASE_NUM = 88

def _session_from_year(year_val) -> str:
    try:
        y = int(year_val)
    except Exception:
        return ""
    # Texas regular sessions map odd/even years to the same session.
    # Examples: 2023/2024 -> 88R, 2025/2026 -> 89R.
    session = _SESSION_BASE_NUM + ((y - _SESSION_BASE_YEAR) // 2)
    return f"{session}R"

def _add_session_from_year(df: pd.DataFrame) -> pd.DataFrame:
    if "Session" in df.columns:
        return df
    out = df.copy()
    year_col = None
    for cand in ["applicableYear", "applicable_year", "ApplicableYear", "year", "Year"]:
        if cand in out.columns:
            year_col = cand
            break
    if year_col:
        years = pd.to_numeric(out[year_col], errors="coerce")
        sessions = years.map(_session_from_year)
        out["Session"] = sessions
    else:
        out["Session"] = ""
    return out

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

def _default_session_from_list(sessions: list[str]) -> str:
    if not sessions:
        return ""
    if "89R" in sessions:
        return "89R"
    regular = [s for s in sessions if str(s).strip().upper().endswith("R") and str(s).strip()[:-1].isdigit()]
    if regular:
        return sorted(regular, key=_session_sort_key)[-1]
    return sorted(sessions, key=_session_sort_key)[-1]

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True, "displaylogo": False}
CHART_COLORS = [
    "#1e90ff",
    "#00e0b8",
    "#ff9f43",
    "#7d5fff",
    "#f368e0",
    "#54a0ff",
    "#10ac84",
    "#ee5253",
    "#c8d6e5",
    "#576574",
]
FUNDING_COLOR_MAP = {"Taxpayer Funded": "#00e0b8", "Private": "#1e90ff"}
OPPOSITION_COLOR_MAP = {"Opposed by TFL lobbyist": "#ff6b6b", "Not opposed by TFL lobbyist": "#6c7cff"}
TREND_COLOR_MAP = {"Low estimate": "#00e0b8", "High estimate": "#1e90ff"}

def _session_base_number_series(s: pd.Series) -> pd.Series:
    base = s.fillna("").astype(str).str.strip().str.extract(r"^(\d+)", expand=False)
    base = base.where(base.str.len() <= 2, base.str[:-1])
    return pd.to_numeric(base, errors="coerce")

def _session_base_label(base_val: float | int) -> str:
    if pd.isna(base_val):
        return ""
    return _ordinal(int(base_val))

def _apply_plotly_layout(
    fig,
    *,
    height: int | None = None,
    showlegend: bool = False,
    legend_title: str | None = None,
    margin_top: int = 30,
):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans", color="rgba(235,245,255,0.9)", size=12),
        margin=dict(l=8, r=8, t=margin_top, b=8),
        showlegend=showlegend,
        legend_title_text=legend_title,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11, color="rgba(235,245,255,0.75)"),
        ),
        hoverlabel=dict(
            bgcolor="rgba(7,22,39,0.95)",
            bordercolor="rgba(255,255,255,0.08)",
            font=dict(color="rgba(235,245,255,0.95)", size=12),
        ),
    )
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickfont=dict(color="rgba(235,245,255,0.75)"),
    )
    fig.update_yaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickfont=dict(color="rgba(235,245,255,0.75)"),
    )
    return fig

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

@st.cache_data(show_spinner=False)
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
    q = (user_text or "").strip()
    if not q or client_index.empty:
        return "", []
    q_norm = norm_name(q)
    if not q_norm:
        return "", []

    d = client_index
    exact = d[d["ClientNorm"] == q_norm]["Client"].dropna().astype(str).unique().tolist()
    if len(exact) == 1:
        return exact[0], []

    prefix = d[d["ClientNorm"].str.startswith(q_norm, na=False)]
    contains = d[d["ClientNorm"].str.contains(q_norm, na=False)]
    candidates = pd.concat([prefix, contains], ignore_index=True).drop_duplicates("Client")
    suggestions = candidates["Client"].dropna().astype(str).tolist()[:10]
    if len(suggestions) == 1 and len(q_norm) >= 4:
        return suggestions[0], []

    if not suggestions:
        norms = d["ClientNorm"].dropna().unique().tolist()
        close = difflib.get_close_matches(q_norm, norms, n=10, cutoff=0.78)
        if close:
            suggestions = (
                d[d["ClientNorm"].isin(close)]["Client"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()[:10]
            )
    return "", suggestions

def _split_authors(text: str) -> list[str]:
    if text is None:
        return []
    s = str(text).strip()
    if not s or s.lower() in {"nan", "none"}:
        return []
    parts = [p.strip() for p in s.split("|")]
    return [p for p in parts if p and p.lower() not in {"nan", "none"}]

@st.cache_data(show_spinner=False)
def build_author_bill_index(bs: pd.DataFrame) -> pd.DataFrame:
    if bs.empty:
        return pd.DataFrame(columns=["Session", "Bill", "Author", "AuthorNorm", "Status", "Caption", "Link", "Chamber"])

    author_col = "Author" if "Author" in bs.columns else "Authors"
    if author_col not in bs.columns:
        return pd.DataFrame(columns=["Session", "Bill", "Author", "AuthorNorm", "Status", "Caption", "Link", "Chamber"])

    d = bs.copy()
    d["AuthorRaw"] = d[author_col].fillna("").astype(str)
    d["AuthorList"] = d["AuthorRaw"].map(_split_authors)
    d = d.explode("AuthorList")
    d["Author"] = d["AuthorList"].fillna("").astype(str).str.strip()
    d = d[d["Author"].astype(str).str.strip() != ""].copy()
    d["AuthorNorm"] = d["Author"].map(norm_name)

    cols = [c for c in ["Session", "Bill", "Author", "AuthorNorm", "Status", "Caption", "Link", "Chamber"] if c in d.columns]
    return d[cols].drop_duplicates()

@st.cache_data(show_spinner=False)
def build_member_index(author_bills: pd.DataFrame) -> pd.DataFrame:
    if author_bills.empty or "Author" not in author_bills.columns:
        return pd.DataFrame(columns=["Member", "MemberNorm"])
    base = author_bills[["Author", "AuthorNorm"]].dropna().copy()
    base = base.rename(columns={"Author": "Member", "AuthorNorm": "MemberNorm"})
    base = base[base["Member"].astype(str).str.strip() != ""].drop_duplicates()
    return base

def resolve_member_name(user_text: str, member_index: pd.DataFrame) -> tuple[str, list[str]]:
    q = (user_text or "").strip()
    if not q or member_index.empty:
        return "", []
    q_norms = {n for n in norm_person_variants(q) if n}
    last_norm = parse_member_name(q).get("last_norm", "")
    if last_norm:
        q_norms.add(last_norm)
    q_norm = norm_name(q)
    if q_norm:
        q_norms.add(q_norm)
    if not q_norms:
        return "", []

    d = member_index
    exact = d[d["MemberNorm"].isin(q_norms)]["Member"].dropna().astype(str).unique().tolist()
    if len(exact) == 1:
        return exact[0], []

    prefix_mask = pd.Series(False, index=d.index)
    contains_mask = pd.Series(False, index=d.index)
    for qn in q_norms:
        if not qn:
            continue
        prefix_mask = prefix_mask | d["MemberNorm"].str.startswith(qn, na=False)
        contains_mask = contains_mask | d["MemberNorm"].str.contains(qn, na=False)

    prefix = d[prefix_mask]
    contains = d[contains_mask]
    candidates = pd.concat([prefix, contains], ignore_index=True).drop_duplicates("Member")
    suggestions = candidates["Member"].dropna().astype(str).tolist()[:10]
    if len(suggestions) == 1 and len(q_norm) >= 3:
        return suggestions[0], []

    if not suggestions:
        norms = d["MemberNorm"].dropna().unique().tolist()
        close = difflib.get_close_matches(q_norm, norms, n=10, cutoff=0.78) if q_norm else []
        if close:
            suggestions = (
                d[d["MemberNorm"].isin(close)]["Member"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()[:10]
            )
    return "", suggestions

def parse_member_name(member_name: str) -> dict:
    t = (member_name or "").strip()
    if not t:
        return {"full_norm": "", "last_norm": "", "first_norm": "", "first_initial": "", "initial_key": ""}

    if "," in t:
        last, rest = [p.strip() for p in t.split(",", 1)]
        first = rest.split()[0].strip() if rest else ""
    else:
        parts = t.split()
        if len(parts) == 1:
            first, last = "", parts[0]
        else:
            first, last = parts[0], parts[-1]

    first_norm = norm_name(first)
    last_norm = norm_name(last)
    first_initial = norm_name(first[0]) if first else ""
    initial_key = _last_first_initial_key(t)
    return {
        "full_norm": norm_name(t),
        "last_norm": last_norm,
        "first_norm": first_norm,
        "first_initial": first_initial,
        "initial_key": initial_key,
    }

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
    short = pd.Series([""] * len(d), index=d.index)

    if "filerIdent" in d.columns and filerid_map:
        fid = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
        short = fid.map(filerid_map).fillna("")

    filer_name = d.get("filerName", pd.Series([""] * len(d)))
    filer_sort = d.get("filerSort", pd.Series([""] * len(d)))
    if isinstance(filer_name, pd.DataFrame):
        filer_name = filer_name.iloc[:, 0]
    if isinstance(filer_sort, pd.DataFrame):
        filer_sort = filer_sort.iloc[:, 0]

    filer_clean = clean_filer_name_series(filer_name)
    norm_raw = norm_name_series(filer_name)
    norm_clean = norm_name_series(filer_clean)
    norm_sort = norm_name_series(filer_sort)

    mapped = norm_raw.map(name_to_short)
    mapped = mapped.where(mapped.notna(), norm_clean.map(name_to_short))
    mapped = mapped.where(mapped.notna(), norm_sort.map(name_to_short))

    short = short.where(short.astype(str).str.strip() != "", mapped)
    d["LobbyShort"] = short.fillna("")
    return d

@st.cache_data(show_spinner=False)
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
        d = df.copy()
        if session is not None and "Session" in d.columns:
            d = d[d["Session"].astype(str).str.strip() == str(session)].copy()
        if d.empty:
            return d
        mask = member_match_mask(d, member_info)
        if not mask.any():
            return d.iloc[0:0].copy()
        d = d[mask].copy()
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
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
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
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
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
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
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
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
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
        "Lobby_Sub_All": [
            "Session",
            "legislative_session",
            "Subject Matter",
            "Other Subject Matter Description",
            "Primary Business",
            "FilerID",
            "LobbyShort",
            "lobbyshort",
            "Lobby Name",
            "Unnamed: 0",
        ],
        "Lobbyist_Pol_Funds": [],
        "Lobby_TFL_Client_All": ["Session", "Client", "Lobby Name", "LobbyShort", "IsTFL", "Low", "High", "Amount", "Mid", "FilerID"],
        "Staff_All": ["Session", "session", "Legislator", "member_or_committee", "legislator_name", "Title", "role",
                      "Staffer", "name", "staff_name_last_initial", "lobby name", "source"],
        "LaFood": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "restaurantName", "activityDate", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaEnt": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                  "entertainmentName", "activityDate", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaTran": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "travelPurpose", "transportationTypeDescr", "departureCity", "arrivalCity", "checkInDt", "checkOutDt", "departureDt", "periodStartDt"],
        "LaGift": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "periodStartDt", "activityExactAmount", "activityAmountRangeLow", "activityAmountRangeHigh", "activityAmountCd"],
        "LaEvnt": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
                   "activityDescription", "activityDate", "periodStartDt"],
        "LaAwrd": ["Session", "applicableYear", "filerIdent", "filerName", "filerSort", "recipientNameOrganization", "recipientNameLast", "recipientNameFirst",
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
        "Wit_All": ["Witness_Lists.parquet", "Witness List.parquet", "Witness_List.parquet", "witnesslist.parquet"],
            "Bill_Status_All": "Bill_Status.parquet",
            "Fiscal_Impact": "Fiscal_Notes.parquet",
            "Bill_Sub_All": "Bill_Sub_All.parquet",
            "Lobby_Sub_All": "Lobby.Sub.parquet",
            "Lobbyist_Pol_Funds": "Lobbyist.Pol.Funds.parquet",
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
                if key == "Wit_All":
                    frames = []
                    for cand in fname:
                        cand_path = base / cand
                        if cand_path.exists():
                            try:
                                frames.append(read_parquet_cols(cand_path, cols))
                            except Exception:
                                continue
                    if frames:
                        data[key] = pd.concat(frames, ignore_index=True).drop_duplicates()
                    else:
                        data[key] = _empty_df(cols)
                    continue
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

    ls = data.get("Lobby_Sub_All")
    if isinstance(ls, pd.DataFrame):
        ls = ls.copy()
        if "Session" not in ls.columns:
            if "legislative_session" in ls.columns:
                ls = ls.rename(columns={"legislative_session": "Session"})
            elif "session" in ls.columns:
                ls = ls.rename(columns={"session": "Session"})
        if "LobbyShort" not in ls.columns:
            if "lobbyshort" in ls.columns:
                ls = ls.rename(columns={"lobbyshort": "LobbyShort"})
            elif "lobby_short" in ls.columns:
                ls = ls.rename(columns={"lobby_short": "LobbyShort"})
        data["Lobby_Sub_All"] = ls

    pf = data.get("Lobbyist_Pol_Funds")
    if isinstance(pf, pd.DataFrame):
        pf = pf.copy()
        if "Session" not in pf.columns and "legislative_session" in pf.columns:
            pf = pf.rename(columns={"legislative_session": "Session"})
        if "LobbyShort" not in pf.columns:
            if "lobbyshort" in pf.columns:
                pf = pf.rename(columns={"lobbyshort": "LobbyShort"})
            elif "lobby_short" in pf.columns:
                pf = pf.rename(columns={"lobby_short": "LobbyShort"})
        data["Lobbyist_Pol_Funds"] = pf

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
        filerid_to_short = _build_filerid_map([
            (lt, "FilerID", "LobbyShort"),
            (data.get("Lobby_Sub_All"), "FilerID", "LobbyShort"),
            (data.get("Lobbyist_Pol_Funds"), "FilerID", "LobbyShort"),
        ])

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
            "Lobbyist": lobbyist_display(d),
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
        route = (d.get("departureCity", "").fillna("").astype(str) + " -> " + d.get("arrivalCity", "").fillna("").astype(str)).str.strip()
        desc2 = (desc + " | " + route).str.replace(r"\s+\|\s+$", "", regex=True)
        date = d.get("departureDt", d.get("checkInDt", d.get("periodStartDt", ""))).fillna("").astype(str)
        out.append(pd.DataFrame({
            "Session": d.get("Session", ""),
            "Date": date,
            "Type": "Travel",
            "Lobbyist": lobbyist_display(d),
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
            "Lobbyist": lobbyist_display(d),
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
            "Lobbyist": lobbyist_display(d),
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
            "Lobbyist": lobbyist_display(d),
            "Filer": d.get("filerName", "").fillna("").astype(str),
            "Member": d.apply(lambda r: person_display(r.get("recipientNameOrganization"), r.get("recipientNameLast"), r.get("recipientNameFirst")), axis=1),
            "Description": d.get("activityDescription", "").fillna("").astype(str),
            "Amount": d.apply(lambda r: amount_display(r.get("activityExactAmount"), r.get("activityAmountRangeLow"), r.get("activityAmountRangeHigh"), r.get("activityAmountCd")), axis=1),
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

@st.cache_data(show_spinner=False)
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
        desc = d.get("subjectMatterMemo", "").fillna("").astype(str)
        desc = desc.where(desc.str.strip() != "", d.get("docketsMemo", "").fillna("").astype(str))
        desc = desc.where(desc.str.strip() != "", d.get("sourceCategoryCd", "").fillna("").astype(str))
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
            d.get("onbehalfName", "").fillna("").astype(str)
            + " - "
            + d.get("onbehalfMailingCity", "").fillna("").astype(str)
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
        desc = d.get("subjectMatterCodeValue", "").fillna("").astype(str)
        desc = desc.where(desc.str.strip() != "", d.get("subjectMatterDescr", "").fillna("").astype(str))
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

if nav_search_submitted:
    if nav_query:
        bill_norm = normalize_bill(nav_query)
        if bill_norm:
            st.session_state.search_query = bill_norm
            st.session_state.lobbyshort = ""
            if _active_page != _lobby_page:
                st.switch_page(_lobby_page)
                st.stop()
        else:
            if not PATH:
                st.error("Data path not configured. Set the DATA_PATH environment variable.")
                st.stop()
            if not _is_url(PATH) and not os.path.exists(PATH):
                st.error("Data path not found. Set DATA_PATH or place the parquet file in ./data.")
                st.stop()
            with st.spinner("Loading search data..."):
                data = load_workbook(PATH)

            client_index = build_client_index(data.get("Lobby_TFL_Client_All", pd.DataFrame()))
            author_bills_all = build_author_bill_index(data.get("Bill_Status_All", pd.DataFrame()))
            member_index = build_member_index(author_bills_all)

            resolved_client, client_suggestions = resolve_client_name(nav_query, client_index)
            resolved_member, member_suggestions = resolve_member_name(nav_query, member_index)
            resolved_lobby, lobby_suggestions = resolve_lobbyshort(
                nav_query,
                data.get("lobby_index", pd.DataFrame()),
                data.get("name_to_short", {}),
                data.get("known_shorts", set()),
                data.get("short_to_names", {}),
            )

            target_page = _lobby_page
            if resolved_client:
                target_page = _client_page
                st.session_state.client_query = resolved_client
            elif resolved_member:
                target_page = _member_page
                st.session_state.member_query = resolved_member
            elif resolved_lobby:
                target_page = _lobby_page
                st.session_state.search_query = nav_query
            else:
                if "," in nav_query and member_suggestions:
                    target_page = _member_page
                elif client_suggestions and not member_suggestions:
                    target_page = _client_page
                elif member_suggestions and not client_suggestions:
                    target_page = _member_page
                elif client_suggestions:
                    target_page = _client_page
                elif member_suggestions:
                    target_page = _member_page
                elif lobby_suggestions:
                    target_page = _lobby_page

                if target_page == _client_page:
                    st.session_state.client_query = nav_query
                elif target_page == _member_page:
                    st.session_state.member_query = nav_query
                else:
                    st.session_state.search_query = nav_query

            if target_page != _active_page:
                st.switch_page(target_page)
                st.stop()

# Render non-lobby pages before running the lobby lookup body.
if _active_page != _lobby_page:
    _active_page.run()
    st.stop()

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
if "bill_search" not in st.session_state:
    st.session_state.bill_search = ""
if "activity_search" not in st.session_state:
    st.session_state.activity_search = ""
if "disclosure_search" not in st.session_state:
    st.session_state.disclosure_search = ""
if "filter_lobbyshort" not in st.session_state:
    st.session_state.filter_lobbyshort = ""

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

    default_session = _default_session_from_list(sessions)
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
typed_init_key = _last_first_initial_key(st.session_state.search_query) if not bill_mode else ""
if typed_init_key:
    typed_norms.add(typed_init_key)
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

        st.markdown('<div class="section-sub">Taxpayer Funded Compensation Trend (85th-89th)</div>', unsafe_allow_html=True)
        trend_base = Lobby_TFL_Client_All.copy()
        trend_base["Session"] = trend_base["Session"].astype(str).str.strip()
        trend_base = ensure_cols(trend_base, {"IsTFL": 0, "Low_num": 0.0, "High_num": 0.0})
        trend_base = trend_base[trend_base["IsTFL"] == 1].copy()
        trend_base["SessionBase"] = _session_base_number_series(trend_base["Session"])
        trend_base = trend_base[trend_base["SessionBase"].between(85, 89)].copy()
        if not trend_base.empty:
            trend_base["Low_num"] = pd.to_numeric(trend_base["Low_num"], errors="coerce").fillna(0)
            trend_base["High_num"] = pd.to_numeric(trend_base["High_num"], errors="coerce").fillna(0)
            trend_group = (
                trend_base.groupby("SessionBase", as_index=False)
                .agg(Low=("Low_num", "sum"), High=("High_num", "sum"))
            )
            trend_group["SessionLabel"] = trend_group["SessionBase"].apply(_session_base_label)
            trend_long = trend_group.melt(
                id_vars=["SessionBase", "SessionLabel"],
                value_vars=["Low", "High"],
                var_name="Estimate",
                value_name="Total",
            )
            trend_long["Estimate"] = trend_long["Estimate"].map({"Low": "Low estimate", "High": "High estimate"})
            session_order = sorted(trend_group["SessionBase"].dropna().unique().tolist())
            session_labels = [_session_base_label(s) for s in session_order]
            fig_trend = px.line(
                trend_long,
                x="SessionLabel",
                y="Total",
                color="Estimate",
                markers=True,
                category_orders={"SessionLabel": session_labels},
                color_discrete_map=TREND_COLOR_MAP,
            )
            fig_trend.update_traces(mode="lines+markers", line=dict(width=3), marker=dict(size=6))
            _apply_plotly_layout(fig_trend, showlegend=True, legend_title="", margin_top=16)
            fig_trend.update_layout(hovermode="x unified")
            fig_trend.update_yaxes(
                tickprefix="$",
                tickformat="~s",
                showgrid=True,
                gridcolor="rgba(255,255,255,0.08)",
            )
            st.plotly_chart(fig_trend, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("No taxpayer funded totals available for 85th-89th sessions.")

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

        st.session_state.filter_lobbyshort = st.text_input(
            "Filter LobbyShort (contains)",
            value=st.session_state.filter_lobbyshort,
            placeholder="e.g., Abbott",
        )
        flt = st.session_state.filter_lobbyshort
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
        if "Session" in lobby_sub.columns:
            lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == session].copy()
        elif "session" in lobby_sub.columns:
            lobby_sub = lobby_sub[lobby_sub["session"].astype(str).str.strip() == session].copy()
        if "LobbyShortNorm" in lobby_sub.columns:
            lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"] == lobbyshort_norm].copy()
        elif "LobbyShort" in lobby_sub.columns:
            lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip() == lobbyshort].copy()
        else:
            lobby_sub = lobby_sub.iloc[0:0].copy()
        if not lobby_sub.empty:
            lobby_sub = lobby_sub.assign(
                Subject=lobby_sub.get("Subject Matter", "").fillna("").astype(str).str.strip(),
                Other=lobby_sub.get("Other Subject Matter Description", "").fillna("").astype(str).str.strip(),
                PrimaryBusiness=lobby_sub.get("Primary Business", "").fillna("").astype(str).str.strip(),
            )
            for col in ["Subject", "Other"]:
                series = lobby_sub[col]
                lobby_sub[col] = series.where(~series.str.lower().isin(["nan", "none"]), "")
            subject_non_empty = lobby_sub["Subject"].ne("").mean() if len(lobby_sub) else 0

            unnamed0 = lobby_sub.get("Unnamed: 0", "").fillna("").astype(str).str.strip()
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

            st.markdown('<div class="section-sub">Funding Mix (Midpoint)</div>', unsafe_allow_html=True)
            lobby_mix = pd.DataFrame(
                {
                    "Funding": ["Taxpayer Funded", "Private"],
                    "Total": [
                        (tfl_low + tfl_high) / 2,
                        (pri_low + pri_high) / 2,
                    ],
                }
            )
            if lobby_mix["Total"].sum() > 0:
                fig_lobby_mix = px.pie(
                    lobby_mix,
                    names="Funding",
                    values="Total",
                    hole=0.55,
                    color="Funding",
                    color_discrete_map=FUNDING_COLOR_MAP,
                )
                fig_lobby_mix.update_traces(
                    textposition="inside",
                    textinfo="percent+label",
                    insidetextorientation="radial",
                    marker=dict(line=dict(color="rgba(7,22,39,0.9)", width=2)),
                    hovertemplate="%{label}: %{percent}<extra></extra>",
                )
                _apply_plotly_layout(fig_lobby_mix, showlegend=False, margin_top=12)
                fig_lobby_mix.update_layout(uniformtext_minsize=10, uniformtext_mode="hide")
                st.plotly_chart(fig_lobby_mix, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.info("No totals available for funding mix.")

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
                st.session_state.bill_search = st.text_input(
                    "Search bills (Bill / Author / Caption)",
                    value=st.session_state.bill_search,
                    placeholder="e.g., HB 4 or Bettencourt or housing",
                )
                filtered = bills.copy()
                if st.session_state.bill_search.strip():
                    q = st.session_state.bill_search.strip()
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
                chart_mentions = mentions.copy()
                chart_mentions["SharePct"] = (chart_mentions["Share"] * 100).round(1)
                chart_mentions = chart_mentions.sort_values("Share", ascending=False)
                top_mentions = chart_mentions.head(20)
                c1, c2 = st.columns(2)
                with c1:
                    fig_share = px.bar(
                        top_mentions,
                        x="SharePct",
                        y="Subject",
                        orientation="h",
                        text="SharePct",
                    )
                    fig_share.update_traces(
                        texttemplate="%{text:.1f}%",
                        textposition="outside",
                        marker_color="#1e90ff",
                        cliponaxis=False,
                        hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
                    )
                    _apply_plotly_layout(fig_share, showlegend=False, margin_top=12)
                    fig_share.update_layout(margin=dict(l=8, r=36, t=12, b=8))
                    fig_share.update_xaxes(
                        showgrid=True,
                        gridcolor="rgba(255,255,255,0.08)",
                        ticksuffix="%",
                        title_text="Share (%)",
                    )
                    fig_share.update_yaxes(title_text="", categoryorder="total descending")
                    st.plotly_chart(fig_share, use_container_width=True, config=PLOTLY_CONFIG)
                with c2:
                    fig_tree = px.treemap(
                        top_mentions,
                        path=["Subject"],
                        values="Mentions",
                        color="SharePct",
                        color_continuous_scale=["#0b1a2b", "#1e90ff", "#00e0b8"],
                    )
                    fig_tree.update_traces(
                        hovertemplate="%{label}<br>%{value} mentions (%{color:.1f}%)<extra></extra>"
                    )
                    _apply_plotly_layout(fig_tree, showlegend=False, margin_top=12)
                    fig_tree.update_layout(coloraxis_showscale=False)
                    st.plotly_chart(fig_tree, use_container_width=True, config=PLOTLY_CONFIG)

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
                    st.caption("Note: Subject Matter is largely blank for this session in the source data. Showing Other Subject Matter Description or Unnamed: 0 when available.")
                top_topics = lobby_sub_counts.head(12).copy()
                max_mentions = int(top_topics["Mentions"].max()) if not top_topics.empty else 0
                topic_chunks = [top_topics.iloc[i:i + 4] for i in range(0, len(top_topics), 4)]
                if topic_chunks:
                    cols = st.columns(len(topic_chunks))
                    for col, chunk in zip(cols, topic_chunks):
                        fig_topic = px.bar(
                            chunk.sort_values("Mentions"),
                            x="Mentions",
                            y="Topic",
                            orientation="h",
                            text="Mentions",
                        )
                        fig_topic.update_traces(
                            textposition="outside",
                            marker_color="#8cc9ff",
                            cliponaxis=False,
                            hovertemplate="%{y}: %{x}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_topic, showlegend=False, height=220, margin_top=8)
                        fig_topic.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                        fig_topic.update_xaxes(
                            showticklabels=False,
                            showgrid=False,
                            range=[0, max_mentions * 1.15] if max_mentions else None,
                            title_text="",
                        )
                        fig_topic.update_yaxes(
                            title_text="",
                            categoryorder="total ascending",
                            tickfont=dict(size=11, color="rgba(235,245,255,0.75)"),
                        )
                        col.plotly_chart(fig_topic, use_container_width=True, config=PLOTLY_CONFIG)

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

                st.session_state.activity_search = st.text_input(
                    "Search activities (filer, member, description)",
                    value=st.session_state.activity_search,
                )
                if st.session_state.activity_search.strip():
                    q = st.session_state.activity_search.strip()
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

                st.session_state.disclosure_search = st.text_input(
                    "Search disclosures (filer, description, entity)",
                    value=st.session_state.disclosure_search,
                )
                if st.session_state.disclosure_search.strip():
                    q = st.session_state.disclosure_search.strip()
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
[data-testid="stToolbar"] {visibility: hidden;}
</style>
""",
    unsafe_allow_html=True,
)

