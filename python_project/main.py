import os
import re
import difflib
import html
from datetime import datetime
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.io as pio
from fpdf import FPDF, XPos, YPos

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
    --space-1: 6px;
    --space-2: 10px;
    --space-3: 16px;
    --space-4: 22px;
    --radius-md: 14px;
    --radius-lg: 18px;
    --shadow-1: 0 10px 25px rgba(0,0,0,0.20);
    --shadow-2: 0 18px 32px rgba(0,0,0,0.28);
}

html, body, [data-testid="stAppViewContainer"]{
    background: radial-gradient(1200px 600px at 20% 15%, rgba(30,144,255,0.16), transparent 60%),
                            radial-gradient(900px 500px at 75% 30%, rgba(0,255,180,0.08), transparent 55%),
                            var(--bg) !important;
    color: var(--text) !important;
    font-family: 'IBM Plex Sans', system-ui, -apple-system, Segoe UI, sans-serif !important;
}

[data-testid="stAppViewContainer"]{
    position: relative;
}
[data-testid="stAppViewContainer"]::before{
    content: "";
    position: fixed;
    inset: 0;
    background-image:
        linear-gradient(transparent 26px, rgba(255,255,255,0.035) 27px),
        linear-gradient(90deg, transparent 26px, rgba(255,255,255,0.035) 27px);
    background-size: 32px 32px;
    opacity: 0.15;
    pointer-events: none;
    z-index: 0;
}
[data-testid="stAppViewContainer"] > div{
    position: relative;
    z-index: 1;
}

[data-testid="stHeader"]{ display: none !important; }
[data-testid="stToolbar"]{ right: 1rem; }
.block-container{
    padding-top: calc(var(--nav-h) + 0.8rem);
    padding-bottom: calc(1rem + env(safe-area-inset-bottom, 0px));
}

h1,h2,h3{ color: var(--text) !important; }
p,li,span,div{ color: var(--text); }

.small-muted{ color: var(--muted); font-size: 0.95rem; }
.hr{ height:1px; background: var(--border); margin: 1rem 0 1.2rem 0; }

.card{
    background: linear-gradient(180deg, var(--panel), var(--panel2));
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 16px 16px 14px 16px;
    box-shadow: var(--shadow-1);
}
div[data-testid="stPlotlyChart"]{
    background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.01));
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: var(--radius-lg);
    padding: 10px 12px 6px 12px;
    box-shadow: var(--shadow-2);
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
.fade-up{
    animation: about-fade-up 360ms ease both;
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
    .fade-up{
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
.section-caption{
    color: var(--muted);
    font-size: 0.92rem;
    margin-top: 0.2rem;
}
.callout{
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02));
    border-radius: var(--radius-md);
    padding: 12px 14px;
    box-shadow: 0 12px 22px rgba(0,0,0,0.22);
}
.callout-title{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-bottom: 4px;
}
.callout-body{
    color: var(--text);
    font-size: 0.96rem;
    line-height: 1.5;
}
.filter-summary{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: rgba(7,22,39,0.55);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
}
.filter-summary-label{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-right: 4px;
}
#filter-bar-marker + div[data-testid="stHorizontalBlock"],
#filter-summary-marker + div[data-testid="stHorizontalBlock"]{
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 12px 14px;
    background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
    box-shadow: 0 16px 28px rgba(0,0,0,0.24);
    animation: about-fade-up 360ms ease both;
}
#filter-summary-marker + div[data-testid="stHorizontalBlock"]{
    padding: 10px 12px;
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
.pill-list{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
}
.pill.pill-muted{
    color: var(--muted);
    border-color: rgba(255,255,255,0.08);
    background: rgba(255,255,255,0.02);
}
.meta-card{
    margin-top: 0.4rem;
    background: linear-gradient(135deg, rgba(30,144,255,0.12), rgba(0,224,184,0.08), rgba(7,22,39,0.85));
    border: 1px solid rgba(255,255,255,0.16);
    box-shadow: 0 14px 28px rgba(0,0,0,0.26);
}
.meta-title{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.7rem;
    color: var(--muted);
}
.meta-sub{
    color: var(--muted);
    font-size: 0.9rem;
    margin-top: 4px;
}
.insight-panel{
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
    gap: 16px;
    margin: 10px 0 4px 0;
}
.insight-card{
    background: linear-gradient(160deg, rgba(30,144,255,0.14), rgba(0,224,184,0.08), rgba(7,22,39,0.9));
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 18px;
    padding: 14px 16px;
    box-shadow: 0 16px 28px rgba(0,0,0,0.28);
}
.insight-kicker{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.65rem;
    color: var(--muted);
    margin-bottom: 6px;
}
.insight-title{
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0 0 0.4rem 0;
}
.insight-list{
    list-style: none;
    padding: 0;
    margin: 0;
}
.insight-list li{
    position: relative;
    padding-left: 1.1rem;
    margin: 0.35rem 0;
    line-height: 1.45;
}
.insight-list li::before{
    content: "";
    position: absolute;
    left: 0;
    top: 0.55rem;
    width: 7px;
    height: 7px;
    border-radius: 2px;
    background: rgba(0,224,184,0.9);
    box-shadow: 0 0 0 2px rgba(0,224,184,0.15);
}
.mini-kpi-grid{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}
.mini-kpi{
    background: rgba(7,22,39,0.5);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
    padding: 10px 12px;
}
.mini-kpi .label{
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.62rem;
    color: var(--muted);
    margin-bottom: 4px;
}
.mini-kpi .value{
    font-size: 1.15rem;
    font-weight: 700;
}
.mini-kpi .sub{
    color: var(--muted);
    font-size: 0.82rem;
    margin-top: 4px;
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
        padding-left: calc(0.5rem + env(safe-area-inset-left, 0px));
        padding-right: calc(0.5rem + env(safe-area-inset-right, 0px));
        padding-top: calc(var(--nav-h) + 3.6rem);
    }
    .section-title { font-size: 1.3rem; min-height: 2.5rem; }
    .big-title { font-size: 2rem; }
    .subtitle { font-size: 1rem; }
    [data-testid="stTextInput"] input { font-size: 16px !important; min-height: 44px !important; }
    [data-testid="stSelectbox"] div[role="combobox"] { font-size: 14px !important; min-height: 44px; }
    [data-testid="stMultiSelect"] div[role="combobox"] { min-height: 44px; }
    button { padding: 0.5rem 1rem !important; font-size: 14px !important; min-height: 44px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 12px !important; font-size: 13px !important; min-height: 40px; }
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
    [data-testid="stDataFrame"]{ overflow-x: auto; -webkit-overflow-scrolling: touch; }
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
    .custom-nav .nav-link{ font-size: 0.9rem; padding: 10px 6px; }
    .custom-nav .brand-top{ font-size: 0.8rem; }
    .custom-nav .brand-bottom{ font-size: 1.2rem; }
    .insight-panel{ grid-template-columns: 1fr; }
    .mini-kpi-grid{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
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
        left: calc(12px + env(safe-area-inset-left, 0px));
        right: calc(12px + env(safe-area-inset-right, 0px));
        width: auto;
        height: auto;
    }
    div[data-testid="stTextInput"]:has(input[aria-label="Nav search"]) input{
        width: 100%;
        height: 44px !important;
    }
    div[data-testid="stPlotlyChart"]{ padding: 6px 8px 4px 8px; border-radius: 16px; touch-action: pan-y; }
}
</style>
""",
    unsafe_allow_html=True,
)

def _page_about():
    st.markdown(
        """
<div class="about-wrap">
  <div class="card about-hero">
    <div class="about-kicker">Overview</div>
    <div class="about-title">Texas Lobby Data Center</div>
    <p class="about-lead">Texas Lobby Data Center makes Texas lobbying activity easier to understand -- who is
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
          <li>The lobbyist name (or last name + first initial)</li>
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
        <p class="about-note">All information displayed in Texas Lobby Data Center is drawn from publicly available
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
    st.markdown(
        """
<div class="card tap-hero">
  <div class="tap-hero-kicker">Video Series</div>
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
            help="Select a featured video to preview in the player.",
            key="tap_selected_title",
            label_visibility="collapsed",
        )
    with controls[1]:
        show_all_players = st.checkbox(
            "Show all players",
            value=False,
            help="Display every embedded player below the gallery.",
        )

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
    if "recent_client_searches" not in st.session_state:
        st.session_state.recent_client_searches = []

    st.sidebar.header("Filters")
    st.session_state.client_scope = st.sidebar.radio(
        "Overview scope",
        ["This Session", "All Sessions"],
        index=0,
        key="client_scope_radio",
        help="Switch between the selected session only or totals across all sessions.",
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
        st.dataframe(health, width="stretch", height=260, hide_index=True)

    st.markdown('<div id="filter-bar-marker"></div>', unsafe_allow_html=True)
    top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

    with top1:
        st.session_state.client_query = st.text_input(
            "Search client",
            value=st.session_state.client_query,
            placeholder="e.g., City of Austin",
            key="client_query_input",
            help="Search by client name. Suggestions appear when close matches exist.",
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
            help="Choose the legislative session used for filters and totals.",
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
            help="Pick a suggested client to populate the selection.",
        )
        if pick in client_suggestions:
            resolved_client = pick

    st.session_state.client_name = resolved_client or ""
    if st.session_state.client_name:
        _remember_recent_client_search(st.session_state.client_name)

    with top3:
        st.markdown('<div class="small-muted">Client</div>', unsafe_allow_html=True)
        if st.session_state.client_name:
            st.write(st.session_state.client_name)
        else:
            st.write("-")

    recent = st.session_state.get("recent_client_searches", [])
    if recent:
        st.markdown('<div class="section-sub">Recent lookups</div>', unsafe_allow_html=True)
        recent_cols = st.columns(min(len(recent), 4))
        for idx, rec in enumerate(recent[:8]):
            col = recent_cols[idx % len(recent_cols)]
            label = rec if len(rec) <= 28 else rec[:25] + "..."
            if col.button(
                f"Reuse {label}",
                key=f"recent_client_lookup_{idx}",
                help="Reuse a recent client search",
                width="stretch",
            ):
                st.session_state.client_query = rec
                st.session_state.client_query_input = rec
                st.session_state.client_name = ""
                st.session_state.client_bill_search = ""
                st.session_state.client_activity_search = ""
                st.session_state.client_disclosure_search = ""
                st.session_state.client_filter = ""

    tfl_session_val = _tfl_session_for_filter(st.session_state.client_session, tfl_sessions)

    active_parts = [
        f"Session: {_session_label(st.session_state.client_session)}",
        f"Scope: {st.session_state.client_scope}",
    ]
    if st.session_state.client_name:
        active_parts.append(f"Client: {st.session_state.client_name}")
    chips_html = "".join([f'<span class="chip">{html.escape(c)}</span>' for c in active_parts])
    st.markdown('<div id="filter-summary-marker"></div>', unsafe_allow_html=True)
    f1, f2 = st.columns([3, 1])
    with f1:
        st.markdown(
            f'<div class="filter-summary"><span class="filter-summary-label">Active filters</span>{chips_html}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Selected client: {st.session_state.client_name or '-'}")
    with f2:
        if st.button(
            "Clear filters",
            width="stretch",
            help="Reset client search and primary filters to defaults.",
        ):
            reset_client_filters(default_session)

    focus_label = "All Clients"
    if st.session_state.client_name:
        focus_label = f"Client: {st.session_state.client_name}"
    focus_context = {
        "type": "client" if st.session_state.client_name else "",
        "name": st.session_state.client_name,
        "report_title": "Client Report",
        "tables": {
            "Staff_All": Staff_All,
            "Lobby_Sub_All": Lobby_Sub_All,
            "LaFood": data.get("LaFood", pd.DataFrame()),
            "LaEnt": data.get("LaEnt", pd.DataFrame()),
            "LaTran": data.get("LaTran", pd.DataFrame()),
            "LaGift": data.get("LaGift", pd.DataFrame()),
            "LaEvnt": data.get("LaEvnt", pd.DataFrame()),
            "LaAwrd": data.get("LaAwrd", pd.DataFrame()),
            "LaCvr": LaCvr,
            "LaDock": LaDock,
            "LaI4E": LaI4E,
            "LaSub": LaSub,
        },
        "lookups": {
            "name_to_short": name_to_short,
            "short_to_names": short_to_names,
            "filerid_to_short": data.get("filerid_to_short", {}),
        },
    }
    _ = _render_pdf_report_section(
        key_prefix="client",
        session_val=st.session_state.client_session,
        scope_label=st.session_state.client_scope,
        focus_label=focus_label,
        Lobby_TFL_Client_All=Lobby_TFL_Client_All,
        Wit_All=Wit_All,
        Bill_Status_All=Bill_Status_All,
        Bill_Sub_All=Bill_Sub_All,
        tfl_session_val=tfl_session_val,
        focus_context=focus_context,
    )

    @st.cache_data(show_spinner=False, ttl=300, max_entries=4)
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

    def kpi_card(title: str, value: str, sub: str = "", help_text: str = ""):
        tooltip_attr = f' title="{html.escape(help_text, quote=True)}"' if help_text else ""
        st.markdown(
            f"""
<div class="card"{tooltip_attr}>
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
            st.info("No Texas Ethics Commission lobby filing rows found for the selected scope/session.")
        else:
            a1, a2, a3, a4 = st.columns(4)
            with a1:
                kpi_card(
                    "Total Taxpayer Funded",
                    f"{fmt_usd(all_stats.get('tfl_low_total', 0.0))} - {fmt_usd(all_stats.get('tfl_high_total', 0.0))}",
                    help_text="Sum of reported low/high compensation for taxpayer-funded clients in this scope.",
                )
            with a2:
                kpi_card(
                    "Total Private",
                    f"{fmt_usd(all_stats.get('pri_low_total', 0.0))} - {fmt_usd(all_stats.get('pri_high_total', 0.0))}",
                    help_text="Sum of reported low/high compensation for private clients in this scope.",
                )
            with a3:
                kpi_card(
                    "Total Clients",
                    f"{all_stats.get('total_clients', 0):,}",
                    help_text="Unique client count in the selected scope.",
                )
                kpi_card(
                    "Taxpayer Funded Clients",
                    f"{all_stats.get('tfl_clients', 0):,}",
                    help_text="Count of clients marked as taxpayer-funded in this scope.",
                )
            with a4:
                kpi_card(
                    "Private Clients",
                    f"{all_stats.get('private_clients', 0):,}",
                    help_text="Count of clients marked as private in this scope.",
                )

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
                    st.plotly_chart(fig_mix, width="stretch", config=PLOTLY_CONFIG)
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
                    st.plotly_chart(fig_cat, width="stretch", config=PLOTLY_CONFIG)
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
                        width="stretch",
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
                        width="stretch",
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
                        width="stretch",
                        height=360,
                        hide_index=True,
                    )
                with b2:
                    st.markdown('<div class="section-sub">By Entity Type</div>', unsafe_allow_html=True)
                    st.dataframe(
                        by_type[["Entity Type", "Clients", "Total Compensation"]],
                        width="stretch",
                        height=360,
                        hide_index=True,
                    )

            st.session_state.client_filter = st.text_input(
                "Filter client (contains)",
                value=st.session_state.client_filter,
                placeholder="e.g., Austin",
                key="client_filter_input",
                help="Filter the All Clients table by a name substring.",
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
                width="stretch",
                height=560,
                hide_index=True,
            )
            _ = export_dataframe(view_disp[show_cols], "all_clients_overview.csv", label="Download overview CSV")

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

    @st.cache_data(show_spinner=False, ttl=300, max_entries=4)
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
            kpi_card(
                "Session",
                session,
                f"Scope: {st.session_state.client_scope}",
                help_text="Session used for detail tables; scope shows whether totals are this session or all sessions.",
            )
        with o2:
            kpi_card(
                "Client",
                st.session_state.client_name,
                help_text="Resolved client selection from search or suggestions.",
            )
        with o3:
            kpi_card(
                "Taxpayer Funded?",
                "Yes" if client_is_tfl else "No",
                help_text="Whether the selected client is marked as taxpayer-funded in the data.",
            )
        with o4:
            kpi_card(
                "Total Compensation",
                f"{fmt_usd(total_low)} - {fmt_usd(total_high)}",
                help_text="Sum of reported low/high compensation for this client in the selected scope.",
            )

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

        s1, s2, s3, s4 = st.columns(4)
        with s1:
            kpi_card(
                "Lobbyists",
                f"{len(lobbyshorts):,}",
                help_text="Unique lobbyists tied to this client in the selected session.",
            )
        with s2:
            kpi_card(
                "Total Bills (Witness Lists)",
                f"{len(bills):,}",
                help_text="Witness list rows tied to this client in the selected session.",
            )
        with s3:
            passed = int((bills.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not bills.empty else 0
            failed = int((bills.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not bills.empty else 0
            kpi_card(
                "Passed / Failed",
                f"{passed:,} / {failed:,}",
                help_text="Bill outcomes among witness list rows in this view.",
            )
        with s4:
            kpi_card(
                "Sessions with Client",
                f"{client_rows_all['Session'].astype(str).nunique():,}",
                help_text="Number of sessions where this client appears in the data.",
            )

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
            st.plotly_chart(fig_client_mix, width="stretch", config=PLOTLY_CONFIG)
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
            view_disp = view.rename(columns={"LobbyShort": "Last name + first initial"})
            show_cols = ["Lobbyist", "Last name + first initial", "Low", "High"]
            show_cols = [c for c in show_cols if c in view_disp.columns]
            st.dataframe(view_disp[show_cols], width="stretch", height=520, hide_index=True)
            _ = export_dataframe(view_disp[show_cols], "client_lobbyists.csv")

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
                help="Filter bills by bill number, author, caption, organization, or lobbyist.",
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
                status_opts = _clean_options(
                    filtered.get("Status", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                )
                status_opts = sorted(status_opts)
                status_sel = st.multiselect(
                    "Filter by status",
                    status_opts,
                    default=status_opts,
                    key="client_status_filter",
                    help="Limit results to selected bill statuses.",
                )
            with f2:
                pos_opts = _clean_options(
                    filtered.get("Position", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                )
                pos_opts = sorted(pos_opts)
                pos_sel = st.multiselect(
                    "Filter by position",
                    pos_opts,
                    default=pos_opts,
                    key="client_position_filter",
                    help="Limit results to selected witness positions.",
                )
            with f3:
                lobby_opts = _clean_options(
                    filtered.get("Lobbyist", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                )
                lobby_opts = sorted(lobby_opts)
                lobby_sel = st.multiselect(
                    "Filter by lobbyist",
                    lobby_opts,
                    default=lobby_opts,
                    key="client_lobbyist_filter",
                    help="Limit results to selected lobbyists.",
                )

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
            st.dataframe(filtered[show_cols].sort_values(["Bill", "Lobbyist"]), width="stretch", height=520, hide_index=True)
            _ = export_dataframe(filtered[show_cols], "client_bills.csv")

    with tab_policy:
        st.markdown('<div class="section-title">Policy Areas</div>', unsafe_allow_html=True)
        if mentions.empty:
            st.info("No subjects found (Texas Legislature Online bill subject data returned 0 rows).")
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
                st.plotly_chart(fig_share, width="stretch", config=PLOTLY_CONFIG)
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
                st.plotly_chart(fig_tree, width="stretch", config=PLOTLY_CONFIG)

            m2 = mentions.copy()
            m2["Share"] = (m2["Share"] * 100).round(0).astype("Int64").astype(str) + "%"
            m2 = m2.rename(columns={"Subject": "Policy Area"})
            st.dataframe(m2[["Policy Area", "Mentions", "Share"]], width="stretch", height=520, hide_index=True)
            _ = export_dataframe(m2, "client_policy_areas.csv")

        st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
        st.subheader("Reported Subject Matters (Texas Ethics Commission filings)")
        if lobby_sub_counts.empty:
            st.info("No Texas Ethics Commission subject-matter rows found for lobbyists tied to this client/session.")
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
                    col.plotly_chart(fig_topic, width="stretch", config=PLOTLY_CONFIG)

            st.dataframe(
                lobby_sub_counts.rename(columns={"Topic": "Subject Matter"}),
                width="stretch",
                height=420,
                hide_index=True,
            )
            _ = export_dataframe(lobby_sub_counts, "client_reported_subject_matters.csv")

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
            st.dataframe(staff_view, width="stretch", height=380, hide_index=True)
            _ = export_dataframe(staff_view, "client_staff_history.csv")

        if staff_pick_session.empty:
            st.caption("Session-specific staff metrics are not shown because there are no matches for the selected session.")
        elif not staff_stats.empty:
            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.caption("Computed from authored bills intersected with this client's lobbyist witness activity.")
            s2 = staff_stats.copy()
            for col in ["% Against that Failed", "% For that Passed"]:
                s2[col] = pd.to_numeric(s2[col], errors="coerce")
                s2[col] = (s2[col] * 100).round(0)
            st.dataframe(s2, width="stretch", height=320, hide_index=True)
            _ = export_dataframe(s2, "client_staff_stats.csv")

    with tab_activities:
        st.markdown('<div class="section-title">Lobbying Expenditures / Activity</div>', unsafe_allow_html=True)
        if activities.empty:
            st.info("No activity rows found for lobbyists tied to this client/session.")
        else:
            filt = activities.copy()
            t_opts = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
            t_opts = sorted(t_opts)
            sel_types = st.multiselect(
                "Filter by activity type",
                t_opts,
                default=t_opts,
                key="client_activity_types",
                help="Limit results to selected activity categories.",
            )
            if sel_types:
                filt = filt[filt["Type"].isin(sel_types)].copy()

            lobby_opts = _clean_options(filt["Lobbyist"].dropna().astype(str).unique().tolist())
            lobby_opts = sorted(lobby_opts)
            sel_lobby = st.multiselect(
                "Filter by lobbyist",
                lobby_opts,
                default=lobby_opts,
                key="client_activity_lobbyist",
                help="Limit results to selected lobbyists.",
            )
            if sel_lobby:
                filt = filt[filt["Lobbyist"].isin(sel_lobby)].copy()

            st.session_state.client_activity_search = st.text_input(
                "Search activities (lobbyist, filer, member, description)",
                value=st.session_state.client_activity_search,
                key="client_activity_search_input",
                help="Search activity rows by lobbyist, filer, member, or description.",
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
                d_from, d_to = st.date_input(
                    "Date range",
                    (min_d, max_d),
                    key="client_activity_dates",
                    help="Restrict results to activities within this date range.",
                )
                if d_from and d_to:
                    mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                    filt = filt[mask].copy()

            st.caption(f"{len(filt):,} rows")
            st.dataframe(filt, width="stretch", height=560, hide_index=True)
            _ = export_dataframe(filt, "client_activities.csv")

    with tab_disclosures:
        st.markdown('<div class="section-title">Disclosures & Subject Matter Filings</div>', unsafe_allow_html=True)
        if disclosures.empty:
            st.info("No disclosure rows found for lobbyists tied to this client/session.")
        else:
            filt = disclosures.copy()
            d_types = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
            d_types = sorted(d_types)
            sel_types = st.multiselect(
                "Filter by disclosure type",
                d_types,
                default=d_types,
                key="client_disclosure_types",
                help="Limit results to selected disclosure categories.",
            )
            if sel_types:
                filt = filt[filt["Type"].isin(sel_types)].copy()

            lobby_opts = _clean_options(filt["Lobbyist"].dropna().astype(str).unique().tolist())
            lobby_opts = sorted(lobby_opts)
            sel_lobby = st.multiselect(
                "Filter by lobbyist",
                lobby_opts,
                default=lobby_opts,
                key="client_disclosure_lobbyist",
                help="Limit results to selected lobbyists.",
            )
            if sel_lobby:
                filt = filt[filt["Lobbyist"].isin(sel_lobby)].copy()

            st.session_state.client_disclosure_search = st.text_input(
                "Search disclosures (lobbyist, filer, description, entity)",
                value=st.session_state.client_disclosure_search,
                key="client_disclosure_search_input",
                help="Search disclosure rows by lobbyist, filer, description, or entity.",
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
                d_from, d_to = st.date_input(
                    "Date range",
                    (min_d, max_d),
                    key="client_disclosure_dates",
                    help="Restrict results to disclosures within this date range.",
                )
                if d_from and d_to:
                    mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                    filt = filt[mask].copy()

            st.caption(f"{len(filt):,} rows")
            st.dataframe(filt, width="stretch", height=560, hide_index=True)
            _ = export_dataframe(filt, "client_disclosures.csv")

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
    Bill_Sub_All = data.get("Bill_Sub_All", pd.DataFrame())
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
    if "member_filter" not in st.session_state:
        st.session_state.member_filter = ""
    if "recent_member_searches" not in st.session_state:
        st.session_state.recent_member_searches = []

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
        st.dataframe(health, width="stretch", height=260, hide_index=True)

    st.markdown('<div id="filter-bar-marker"></div>', unsafe_allow_html=True)
    top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

    with top1:
        st.session_state.member_query = st.text_input(
            "Search legislator",
            value=st.session_state.member_query,
            placeholder="e.g., Bell, Keith",
            key="member_query_input",
            help="Search by legislator name. Suggestions appear when close matches exist.",
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
            help="Choose the legislative session used for filters and totals.",
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
            help="Pick a suggested legislator to populate the selection.",
        )
        if pick in member_suggestions:
            resolved_member = pick

    st.session_state.member_name = resolved_member or ""
    if st.session_state.member_name:
        _remember_recent_member_search(st.session_state.member_name)

    with top3:
        st.markdown('<div class="small-muted">Member</div>', unsafe_allow_html=True)
        if st.session_state.member_name:
            st.write(st.session_state.member_name)
        else:
            st.write("-")

    recent = st.session_state.get("recent_member_searches", [])
    if recent:
        st.markdown('<div class="section-sub">Recent lookups</div>', unsafe_allow_html=True)
        recent_cols = st.columns(min(len(recent), 4))
        for idx, rec in enumerate(recent[:8]):
            col = recent_cols[idx % len(recent_cols)]
            label = rec if len(rec) <= 28 else rec[:25] + "..."
            if col.button(
                f"Reuse {label}",
                key=f"recent_member_lookup_{idx}",
                help="Reuse a recent legislator search",
                width="stretch",
            ):
                st.session_state.member_query = rec
                st.session_state.member_query_input = rec
                st.session_state.member_name = ""
                st.session_state.member_bill_search = ""
                st.session_state.member_witness_search = ""
                st.session_state.member_activity_search = ""
                st.session_state.member_filter = ""

    tfl_session_val = _tfl_session_for_filter(st.session_state.member_session, tfl_sessions)

    active_parts = [f"Session: {_session_label(st.session_state.member_session)}"]
    if st.session_state.member_name:
        active_parts.append(f"Member: {st.session_state.member_name}")
    chips_html = "".join([f'<span class="chip">{html.escape(c)}</span>' for c in active_parts])
    st.markdown('<div id="filter-summary-marker"></div>', unsafe_allow_html=True)
    f1, f2 = st.columns([3, 1])
    with f1:
        st.markdown(
            f'<div class="filter-summary"><span class="filter-summary-label">Active filters</span>{chips_html}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Selected member: {st.session_state.member_name or '-'}")
    with f2:
        if st.button(
            "Clear filters",
            width="stretch",
            help="Reset legislator search and primary filters to defaults.",
        ):
            reset_member_filters(default_session)

    focus_label = "All Legislators"
    if st.session_state.member_name:
        focus_label = f"Legislator: {st.session_state.member_name}"
    focus_context = {
        "type": "legislator" if st.session_state.member_name else "",
        "name": st.session_state.member_name,
        "report_title": "Legislator Report",
        "tables": {
            "Staff_All": Staff_All,
            "LaFood": data.get("LaFood", pd.DataFrame()),
            "LaEnt": data.get("LaEnt", pd.DataFrame()),
            "LaTran": data.get("LaTran", pd.DataFrame()),
            "LaGift": data.get("LaGift", pd.DataFrame()),
            "LaEvnt": data.get("LaEvnt", pd.DataFrame()),
            "LaAwrd": data.get("LaAwrd", pd.DataFrame()),
            "LaCvr": LaCvr,
            "LaDock": LaDock,
            "LaI4E": LaI4E,
            "LaSub": LaSub,
        },
        "lookups": {
            "name_to_short": name_to_short,
            "short_to_names": short_to_names,
            "filerid_to_short": data.get("filerid_to_short", {}),
        },
    }
    _ = _render_pdf_report_section(
        key_prefix="member",
        session_val=st.session_state.member_session,
        scope_label="Selected Session",
        focus_label=focus_label,
        Lobby_TFL_Client_All=Lobby_TFL_Client_All,
        Wit_All=Wit_All,
        Bill_Status_All=Bill_Status_All,
        Bill_Sub_All=Bill_Sub_All,
        tfl_session_val=tfl_session_val,
        focus_context=focus_context,
    )

    @st.cache_data(show_spinner=False, ttl=300, max_entries=4)
    def build_all_legislators_overview(
        author_bills: pd.DataFrame,
        wit_all: pd.DataFrame,
        session_val: str,
    ) -> tuple[pd.DataFrame, dict]:
        if author_bills.empty:
            return pd.DataFrame(), {}

        session = str(session_val).strip()
        if not session:
            return pd.DataFrame(), {}

        d = author_bills.copy()
        d["Session"] = d["Session"].astype(str).str.strip()
        d = d[d["Session"] == session].copy()
        d = ensure_cols(d, {"Author": "", "Status": "", "Bill": ""})
        d = d[d["Author"].astype(str).str.strip() != ""].copy()
        if d.empty:
            return pd.DataFrame(), {}

        d = d[d["Bill"].notna()].copy()
        d["Bill"] = d["Bill"].astype(str)
        d = d[d["Bill"].str.strip() != ""].copy()
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
            wit["Session"] = wit["Session"].astype(str).str.strip()
            wit = wit[wit["Session"] == session].copy()
            wit = wit[wit["Bill"].notna()].copy()
            wit["Bill"] = wit["Bill"].astype(str)
            wit = wit[wit["Bill"].str.strip() != ""].copy()
            bill_set = set(bills["Bill"].dropna().astype(str).unique().tolist())
            if bill_set:
                wit = wit[wit["Bill"].astype(str).isin(bill_set)].copy()
            wit["LobbyShort"] = wit["LobbyShort"].fillna("").astype(str).str.strip()
            wit = wit[wit["LobbyShort"] != ""].copy()

        witness_rows = int(len(wit)) if not wit.empty else 0
        witness_lobbyists = int(wit["LobbyShort"].nunique()) if not wit.empty else 0
        witness_bills = int(wit["Bill"].nunique()) if not wit.empty else 0

        if not wit.empty:
            bill_authors = bills[["Bill", "Author"]].drop_duplicates()
            bill_authors["Bill"] = bill_authors["Bill"].astype(str)
            wit_join = bill_authors.merge(wit[["Bill", "LobbyShort"]], on="Bill", how="left")
            wit_join = wit_join[wit_join["LobbyShort"].astype(str).str.strip() != ""].copy()
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
        return g, stats

    all_legislators, all_leg_stats = build_all_legislators_overview(
        author_bills_all,
        Wit_All,
        st.session_state.member_session,
    )

    tab_all, tab_overview, tab_bills, tab_witness, tab_activities, tab_staff = st.tabs(
        ["All Legislators", "Overview", "Bills", "Witness Lists", "Activities", "Staff to Lobbyist"]
    )

    def kpi_card(title: str, value: str, sub: str = "", help_text: str = ""):
        tooltip_attr = f' title="{html.escape(help_text, quote=True)}"' if help_text else ""
        st.markdown(
            f"""
<div class="card"{tooltip_attr}>
  <div class="kpi-title">{title}</div>
  <div class="kpi-value">{value}</div>
  <div class="kpi-sub">{sub}</div>
</div>
""",
            unsafe_allow_html=True,
        )

    with tab_all:
        st.markdown('<div class="section-title">All Legislators Overview</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="section-sub">Session: {_session_label(st.session_state.member_session)}</div>',
            unsafe_allow_html=True,
        )

        if all_legislators.empty:
            st.info("No authored bills found for the selected session.")
        else:
            a1, a2, a3, a4 = st.columns(4)
            with a1:
                kpi_card(
                    "Total Legislators",
                    f"{all_leg_stats.get('total_legislators', 0):,}",
                    help_text="Unique legislators with authored bills in the selected session.",
                )
            with a2:
                kpi_card(
                    "Bills Authored",
                    f"{all_leg_stats.get('total_bills', 0):,}",
                    help_text="Unique bills with at least one listed author in the session.",
                )
            with a3:
                kpi_card(
                    "Passed / Failed",
                    f"{all_leg_stats.get('passed', 0):,} / {all_leg_stats.get('failed', 0):,}",
                    help_text="Bill outcomes for authored bills in the session.",
                )
            with a4:
                kpi_card(
                    "Witness Rows",
                    f"{all_leg_stats.get('witness_rows', 0):,}",
                    f"Lobbyists: {all_leg_stats.get('witness_lobbyists', 0):,}",
                    help_text="Witness list rows tied to authored bills in the session.",
                )

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

            t1, t2 = st.columns(2)
            with t1:
                st.markdown('<div class="section-title">Top 5 by Bills Authored</div>', unsafe_allow_html=True)
                top_bills = all_legislators.sort_values(["Bills", "Legislator"], ascending=[False, True]).head(5)
                st.dataframe(
                    top_bills[["Legislator", "Bills", "Passed", "Failed"]],
                    width="stretch",
                    height=240,
                    hide_index=True,
                )
            with t2:
                st.markdown('<div class="section-title">Top 5 by Witness Rows</div>', unsafe_allow_html=True)
                if all_legislators["WitnessRows"].sum() > 0:
                    top_witness = all_legislators.sort_values(
                        ["WitnessRows", "Legislator"], ascending=[False, True]
                    ).head(5)
                    top_witness = top_witness.rename(
                        columns={
                            "WitnessRows": "Witness Rows",
                            "WitnessLobbyists": "Unique Lobbyists",
                            "WitnessBills": "Bills w/ Witness",
                        }
                    )
                    st.dataframe(
                        top_witness[["Legislator", "Witness Rows", "Unique Lobbyists", "Bills w/ Witness"]],
                        width="stretch",
                        height=240,
                        hide_index=True,
                    )
                else:
                    st.info("No witness-list rows found for authored bills in this session.")

            st.session_state.member_filter = st.text_input(
                "Filter legislator (contains)",
                value=st.session_state.member_filter,
                placeholder="e.g., Johnson",
                key="member_filter_input",
                help="Filter the All Legislators table by a name substring.",
            )

            view = all_legislators.copy()
            if st.session_state.member_filter.strip():
                view = view[
                    view["Legislator"].astype(str).str.contains(
                        st.session_state.member_filter.strip(), case=False, na=False
                    )
                ].copy()

            sort_cols = []
            sort_order = []
            if "Bills" in view.columns:
                sort_cols.append("Bills")
                sort_order.append(False)
            if "WitnessRows" in view.columns:
                sort_cols.append("WitnessRows")
                sort_order.append(False)
            if "Legislator" in view.columns:
                sort_cols.append("Legislator")
                sort_order.append(True)
            if sort_cols:
                view = view.sort_values(sort_cols, ascending=sort_order)

            view_disp = view.rename(
                columns={
                    "WitnessRows": "Witness Rows",
                    "WitnessLobbyists": "Unique Lobbyists",
                    "WitnessBills": "Bills w/ Witness",
                }
            )
            show_cols = [
                "Legislator",
                "Bills",
                "Passed",
                "Failed",
                "Bills w/ Witness",
                "Witness Rows",
                "Unique Lobbyists",
            ]
            show_cols = [c for c in show_cols if c in view_disp.columns]
            st.dataframe(
                view_disp[show_cols],
                width="stretch",
                height=560,
                hide_index=True,
            )
            _ = export_dataframe(view_disp[show_cols], "all_legislators_overview.csv", label="Download overview CSV")

    def _no_member_msg():
        st.info("Type a legislator name at the top to view details. The All Legislators tab is available without a selection.")

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
            st.info("No authored bills found for this legislator/session in Texas Legislature Online bill status data.")
        else:
            bill_count = int(authored["Bill"].nunique())
            passed = int((authored.get("Status", pd.Series(dtype=object)) == "Passed").sum())
            failed = int((authored.get("Status", pd.Series(dtype=object)) == "Failed").sum())
            witness_rows = int(len(witness)) if isinstance(witness, pd.DataFrame) else 0
            lobbyist_count = int(witness.get("LobbyShort", pd.Series(dtype=object)).nunique()) if isinstance(witness, pd.DataFrame) and not witness.empty else 0
            tfl_count = int((witness.get("Has TFL Client", pd.Series(dtype=object)) == "Yes").sum()) if isinstance(witness, pd.DataFrame) and not witness.empty else 0

            o1, o2, o3, o4 = st.columns(4)
            with o1:
                kpi_card(
                    "Session",
                    session,
                    help_text="Session used for authored bill counts and witness lists.",
                )
            with o2:
                kpi_card(
                    "Member",
                    member_name,
                    help_text="Resolved legislator selection from search or suggestions.",
                )
            with o3:
                kpi_card(
                    "Bills Authored",
                    f"{bill_count:,}",
                    help_text="Unique bills authored by this member in the session.",
                )
            with o4:
                kpi_card(
                    "Passed / Failed",
                    f"{passed:,} / {failed:,}",
                    help_text="Outcome counts for authored bills in the session.",
                )

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

            s1, s2, s3, s4 = st.columns(4)
            with s1:
                kpi_card(
                    "Witness Rows",
                    f"{witness_rows:,}",
                    help_text="Witness list rows tied to this member's authored bills.",
                )
            with s2:
                kpi_card(
                    "Unique Lobbyists",
                    f"{lobbyist_count:,}",
                    help_text="Distinct lobbyists appearing in the witness lists.",
                )
            with s3:
                kpi_card(
                    "Lobbyists w/ TFL Clients",
                    f"{tfl_count:,}",
                    help_text="Witness rows marked as having a taxpayer-funded client.",
                )
            with s4:
                kpi_card(
                    "Activities Rows",
                    f"{len(activities):,}",
                    help_text="Activity rows where this member is the recipient.",
                )

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
                    st.plotly_chart(fig_tfl, width="stretch", config=PLOTLY_CONFIG)
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
                    st.dataframe(summary_df, width="stretch", height=200, hide_index=True)

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
                    help="Filter authored bills by bill number, caption, or status.",
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
                    width="stretch",
                    height=520,
                    hide_index=True,
                )
                _ = export_dataframe(bill_view[show_cols], "member_bills.csv")

    with tab_witness:
        st.markdown('<div class="section-title">Witness Lists: Lobbyists and Organizations</div>', unsafe_allow_html=True)
        if witness.empty:
            st.info("No witness-list rows found for bills authored by this legislator in the selected session.")
        else:
            st.session_state.member_witness_search = st.text_input(
                "Search witness list (Bill / Lobbyist / Organization)",
                value=st.session_state.member_witness_search,
                key="member_witness_search_input",
                help="Filter witness list rows by bill, lobbyist, organization, or witness name.",
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
                pos_opts = _clean_options(
                    witness_view.get("Position", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                )
                pos_opts = sorted(pos_opts)
                pos_sel = st.multiselect(
                    "Filter by position",
                    pos_opts,
                    default=pos_opts,
                    key="member_pos_filter",
                    help="Limit results to selected witness positions.",
                )
            with f2:
                tfl_opts = _clean_options(
                    witness_view.get("Has TFL Client", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                )
                tfl_opts = sorted(tfl_opts)
                tfl_sel = st.multiselect(
                    "Filter by TFL",
                    tfl_opts,
                    default=tfl_opts,
                    key="member_tfl_filter",
                    help="Filter to rows marked as having a taxpayer-funded client.",
                )
            with f3:
                lob_opts = _clean_options(
                    witness_view.get("Lobbyist", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                )
                lob_opts = sorted(lob_opts)
                lob_sel = st.multiselect(
                    "Filter by lobbyist",
                    lob_opts,
                    default=lob_opts,
                    key="member_lobbyist_filter",
                    help="Limit results to selected lobbyists.",
                )

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
                width="stretch",
                height=560,
                hide_index=True,
            )
            _ = export_dataframe(witness_view[show_cols], "member_witness_lists.csv")

    with tab_activities:
        st.markdown('<div class="section-title">Lobbyist Activity Benefiting the Member</div>', unsafe_allow_html=True)
        if activities.empty:
            st.info("No activity rows found where this legislator is the recipient.")
        else:
            filt = activities.copy()
            t_opts = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
            t_opts = sorted(t_opts)
            sel_types = st.multiselect(
                "Filter by activity type",
                t_opts,
                default=t_opts,
                key="member_activity_types",
                help="Limit results to selected activity categories.",
            )
            if sel_types:
                filt = filt[filt["Type"].isin(sel_types)].copy()

            lobby_opts = _clean_options(filt["Lobbyist"].dropna().astype(str).unique().tolist())
            lobby_opts = sorted(lobby_opts)
            sel_lobby = st.multiselect(
                "Filter by lobbyist",
                lobby_opts,
                default=lobby_opts,
                key="member_activity_lobbyist",
                help="Limit results to selected lobbyists.",
            )
            if sel_lobby:
                filt = filt[filt["Lobbyist"].isin(sel_lobby)].copy()

            st.session_state.member_activity_search = st.text_input(
                "Search activities (lobbyist, description, filer)",
                value=st.session_state.member_activity_search,
                key="member_activity_search_input",
                help="Search activity rows by lobbyist, description, or filer.",
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
                d_from, d_to = st.date_input(
                    "Date range",
                    (min_d, max_d),
                    key="member_activity_dates",
                    help="Restrict results to activities within this date range.",
                )
                if d_from and d_to:
                    mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                    filt = filt[mask].copy()

            show_cols = ["Date", "Type", "Lobbyist", "Has TFL Client", "Description", "Amount"]
            show_cols = [c for c in show_cols if c in filt.columns]
            st.caption(f"{len(filt):,} rows")
            st.dataframe(filt[show_cols], width="stretch", height=560, hide_index=True)
            _ = export_dataframe(filt[show_cols], "member_activities.csv")

    with tab_staff:
        st.markdown('<div class="section-title">Staff Who Became Lobbyists</div>', unsafe_allow_html=True)
        if staff_lobbyists.empty:
            st.info("No staff matches found who appear in lobbyist records.")
        else:
            cols = ["Session", "Legislator", "Title", "Staffer", "Lobbyist", "LobbyShort", "source"]
            cols = [c for c in cols if c in staff_lobbyists.columns]
            staff_view = staff_lobbyists[cols].drop_duplicates().rename(columns={"LobbyShort": "Last name + first initial"})
            sort_cols = [c for c in ["Session", "Legislator", "Staffer"] if c in staff_view.columns]
            if sort_cols:
                staff_view = staff_view.sort_values(sort_cols)
            st.dataframe(staff_view, width="stretch", height=420, hide_index=True)
            _ = export_dataframe(staff_view, "member_staff_to_lobbyists.csv")

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

# Lobby content renders in the main body below; this stub keeps navigation wiring intact.
_lobby_page = st.Page(lambda: None, title="Lobby Look-Up", url_path="lobbyists", default=True)
_client_page = st.Page(_page_client_lookup, title="Client Look-Up", url_path="clients")
_member_page = st.Page(_page_member_lookup, title="Legislators", url_path="legislators")
_about_page = st.Page(_page_about, title="About", url_path="about")
_tap_page = st.Page(_page_turn_off_tap, title="Multimedia", url_path="multimedia")
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
    (_about_page, "About"),
    (_lobby_page, "Lobbyists"),
    (_client_page, "Clients"),
    (_member_page, "Legislators"),
    (_tap_page, "Multimedia"),
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
      <div class="brand-top">Texas</div>
      <div class="brand-bottom">Lobby Data Center</div>
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
if "nav_search_trigger" not in st.session_state:
    st.session_state.nav_search_trigger = False

def _nav_submit() -> None:
    st.session_state.nav_search_trigger = True

nav_query_raw = st.text_input(
    "Nav search",
    key="nav_search_query",
    placeholder="Search bills, clients, members, lobbyists",
    label_visibility="collapsed",
    on_change=_nav_submit,
    help="Global search across bills, clients, members, and lobbyists.",
)
nav_query = nav_query_raw.strip()
nav_search_submitted = False
if nav_query and st.session_state.nav_search_trigger:
    nav_search_submitted = True
    st.session_state.nav_search_last = nav_query
    st.session_state.nav_search_trigger = False
elif not nav_query:
    st.session_state.nav_search_trigger = False
nav_suggest_slot = st.empty()
nav_skip_submit = False

# =========================================================
# HELPERS
# =========================================================
_RE_NONWORD = re.compile(r"[^\w]+", flags=re.UNICODE)
_TITLE_WORDS = {"MR", "MRS", "MS", "MISS", "DR", "HON", "JR", "SR", "II", "III", "IV"}
_NICKNAME_MAP = {
    "CHUCK": {"CHARLES"},
    "CHARLIE": {"CHARLES"},
    "CHARLES": {"CHUCK", "CHARLIE"},
}

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

def clean_person_name(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).replace("\u00A0", " ").strip()
    if not s:
        return ""
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\b(" + "|".join(_TITLE_WORDS) + r")\b\.?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
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
    filer_ids: set[int] | tuple[int, ...] | None = None,
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
    if "FilerID" in d.columns:
        d["FilerID"] = pd.to_numeric(d["FilerID"], errors="coerce").fillna(-1).astype(int)
    elif "filerIdent" in d.columns:
        d["FilerID"] = pd.to_numeric(d["filerIdent"], errors="coerce").fillna(-1).astype(int)
    else:
        d["FilerID"] = -1

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

def first_name_norm_series(s: pd.Series) -> pd.Series:
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
    first_from_comma = (
        s.where(comma_mask, "")
         .astype("string")
         .str.split(",", n=1)
         .str[1]
         .fillna("")
         .astype("string")
         .str.strip()
         .str.split()
         .str[0]
         .fillna("")
         .astype("string")
         .str.strip()
    )
    first_from_space = (
        s.where(~comma_mask, "")
         .astype("string")
         .str.split()
         .str[0]
         .fillna("")
         .astype("string")
         .str.strip()
    )
    first = first_from_comma.where(comma_mask, first_from_space).fillna("")
    return norm_name_series(first)

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
    t = clean_person_name(user_text)
    if not t:
        return set()

    if "," in t:
        parts = [p.strip() for p in t.split(",", 1)]
        last = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        first = rest.split()[0].strip() if rest else ""
    else:
        toks = t.split()
        if len(toks) == 1:
            first, last = "", toks[0]
        else:
            first, last = toks[0], toks[-1]

    variants = {norm_name(t)}
    raw_norm = norm_name(user_text)
    if raw_norm:
        variants.add(raw_norm)
    if first and last:
        variants |= {
            norm_name(f"{first} {last}"),
            norm_name(f"{last}, {first}"),
            norm_name(f"{last} {first}"),
            norm_name(f"{first}{last}"),
            norm_name(f"{last}{first}"),
        }
    return {v for v in variants if v}

def _nickname_variants(first_norm: str) -> set[str]:
    if not first_norm:
        return set()
    variants = {first_norm}
    if first_norm in _NICKNAME_MAP:
        variants |= _NICKNAME_MAP[first_norm]
    for base, nicknames in _NICKNAME_MAP.items():
        if first_norm in nicknames:
            variants.add(base)
            variants |= nicknames
    return {v for v in variants if v}

def norm_person_variants_with_nicknames(user_text: str) -> set[str]:
    variants = norm_person_variants(user_text)
    if not user_text:
        return variants
    t = clean_person_name(user_text)
    if not t:
        return variants

    def _add_nickname_variants(first_val: str, last_val: str) -> None:
        first_norm = norm_name(first_val)
        last_norm = norm_name(last_val)
        if not first_norm or not last_norm:
            return
        for fn in _nickname_variants(first_norm):
            if fn == first_norm:
                continue
            variants.add(f"{fn}{last_norm}")
            variants.add(f"{last_norm}{fn}")

    if "," in t:
        parts = [p.strip() for p in t.split(",", 1)]
        last = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        first = rest.split()[0].strip() if rest else ""
        _add_nickname_variants(first, last)
    else:
        toks = t.split()
        if len(toks) < 2:
            return variants
        first, last = toks[0], toks[-1]
        _add_nickname_variants(first, last)
        if len(toks) == 2:
            _add_nickname_variants(last, first)
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
            return f"{low}--{high}"
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

def _shorten_text(value: str, max_len: int = 36) -> str:
    s = str(value or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."

def render_pill_list(items: list[str], limit: int = 12, empty_label: str = "--") -> str:
    cleaned = [str(i).strip() for i in (items or []) if str(i).strip()]
    if not cleaned:
        return f'<div class="pill-list"><span class="pill pill-muted">{html.escape(empty_label)}</span></div>'
    seen = []
    for item in cleaned:
        if item not in seen:
            seen.append(item)
    shown = seen[:limit]
    pills = [f'<span class="pill">{html.escape(item)}</span>' for item in shown]
    if len(seen) > limit:
        pills.append(f'<span class="pill pill-muted">+{len(seen) - limit} more</span>')
    return '<div class="pill-list">' + "".join(pills) + "</div>"

def _current_filter_parts(extra: list[str] | None = None) -> list[str]:
    parts = []
    session_val = st.session_state.get("session", None)
    session_label = _session_label(session_val) if session_val is not None else ""
    if session_label:
        parts.append(f"Session: {session_label}")
    scope_label = st.session_state.get("scope", "")
    if scope_label:
        parts.append(f"Scope: {scope_label}")
    lobbyshort = st.session_state.get("lobbyshort", "").strip()
    query = st.session_state.get("search_query", "").strip()
    if lobbyshort:
        parts.append(f"Lobbyist: {_shorten_text(lobbyshort, 28)}")
    elif query:
        parts.append(f"Query: {_shorten_text(query, 28)}")
    if extra:
        parts.extend([p for p in extra if p])
    return parts

def _export_context_label(extra: list[str] | None = None, max_len: int = 72) -> str:
    parts = _current_filter_parts(extra)
    if not parts:
        return ""
    return _shorten_text(", ".join(parts), max_len)

def _export_filename(filename: str, extra: list[str] | None = None) -> str:
    parts = _current_filter_parts(extra)
    if not parts:
        return filename
    stem = Path(filename).stem or "export"
    suffix = Path(filename).suffix or ".csv"
    tokens = []
    for part in parts:
        token = re.sub(r"[^A-Za-z0-9]+", "-", part).strip("-").lower()
        if token:
            tokens.append(token)
    tokens = tokens[:4]
    if not tokens:
        return filename
    return f"{stem}__{'__'.join(tokens)}{suffix}"

def export_dataframe(df: pd.DataFrame, filename: str, label: str = "Download CSV", context: list[str] | str | None = None):
    extra = []
    if isinstance(context, str):
        extra = [context]
    elif isinstance(context, (list, tuple)):
        extra = [str(c) for c in context if c]
    context_label = _export_context_label(extra)
    export_label = f"{label} ({context_label})" if context_label else label
    export_name = _export_filename(filename, extra)
    _ = st.download_button(label=export_label, data=df.to_csv(index=False), file_name=export_name, mime="text/csv")
    if context_label:
        st.markdown(f'<div class="section-caption">CSV includes: {context_label}.</div>', unsafe_allow_html=True)
    return ""

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

def require_columns(df: pd.DataFrame, required: list[str], label: str, hint: str = "") -> bool:
    missing = [c for c in required if c not in df.columns]
    if not missing:
        return True
    st.warning(f"{label} is missing required columns: {', '.join(missing)}.")
    if hint:
        st.caption(hint)
    return False

def reset_filters(default_session: str) -> None:
    st.session_state.search_query = ""
    st.session_state.lobbyshort = ""
    st.session_state.lobby_filerid = None
    st.session_state.lobby_selected_key = ""
    st.session_state.lobby_all_matches = False
    st.session_state.lobby_merge_keys = []
    st.session_state.lobby_candidate_map = {}
    st.session_state.lobby_match_query = ""
    st.session_state.lobby_match_select = "No match"
    st.session_state.bill_search = ""
    st.session_state.activity_search = ""
    st.session_state.disclosure_search = ""
    st.session_state.filter_lobbyshort = ""
    st.session_state.scope = "This Session"
    st.session_state.session = default_session


def _remember_recent_search(query: str) -> None:
    """Track recent lobby lookups for quick reuse."""
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_lobby_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_lobby_searches = deduped[:6]


def reset_client_filters(default_session: str) -> None:
    st.session_state.client_query = ""
    st.session_state.client_name = ""
    st.session_state.client_bill_search = ""
    st.session_state.client_activity_search = ""
    st.session_state.client_disclosure_search = ""
    st.session_state.client_filter = ""
    st.session_state.client_scope = "This Session"
    st.session_state.client_session = default_session
    st.session_state.client_scope_radio = "This Session"
    st.session_state.client_session_select = _session_label(default_session)
    st.session_state.client_suggestions_select = "Select a client..."
    st.session_state.client_query_input = ""
    st.session_state.client_bill_search_input = ""
    st.session_state.client_activity_search_input = ""
    st.session_state.client_disclosure_search_input = ""
    st.session_state.client_filter_input = ""


def reset_member_filters(default_session: str) -> None:
    st.session_state.member_query = ""
    st.session_state.member_name = ""
    st.session_state.member_bill_search = ""
    st.session_state.member_witness_search = ""
    st.session_state.member_activity_search = ""
    st.session_state.member_filter = ""
    st.session_state.member_session = default_session
    st.session_state.member_session_select = _session_label(default_session)
    st.session_state.member_suggestions_select = "Select a legislator..."
    st.session_state.member_query_input = ""
    st.session_state.member_bill_search_input = ""
    st.session_state.member_witness_search_input = ""
    st.session_state.member_activity_search_input = ""
    st.session_state.member_filter_input = ""


def _remember_recent_client_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_client_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_client_searches = deduped[:6]


def _remember_recent_member_search(query: str) -> None:
    if not query or not query.strip():
        return
    history = st.session_state.get("recent_member_searches", [])
    q = query.strip()
    deduped = [h for h in history if h.strip().lower() != q.lower()]
    deduped.insert(0, q)
    st.session_state.recent_member_searches = deduped[:6]


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"

def _session_label(session_val: str) -> str:
    s = str(session_val).strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    # Special sessions encoded like 891 -> "89R / 1st Special".
    if s.isdigit():
        if len(s) >= 3:
            base = s[:-1]
            special = s[-1]
            if base.isdigit() and special.isdigit():
                return f"{base}R / {_ordinal(int(special))} Special"
        return _ordinal(int(s))
    return s

def _session_long_label(session_val: str | None) -> str:
    s = str(session_val or "").strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    if s.isdigit() and len(s) >= 3:
        base = s[:-1]
        special = s[-1]
        if base.isdigit() and special.isdigit():
            return f"{_ordinal(int(base))} {_ordinal(int(special))} Special Session"
    m = re.match(r"^(\d+)\s*R$", s, flags=re.IGNORECASE)
    if m:
        return f"{_ordinal(int(m.group(1)))} Regular Session"
    if s.isdigit():
        return f"{_ordinal(int(s))} Regular Session"
    m = re.search(r"(\d+).*(\d+)(?:st|nd|rd|th)?\s*Special", s, flags=re.IGNORECASE)
    if m:
        return f"{_ordinal(int(m.group(1)))} {_ordinal(int(m.group(2)))} Special Session"
    return s

def _session_range_label(series: pd.Series) -> str:
    if series is None or series.empty:
        return "All Sessions"
    base_nums = _session_base_number_series(series)
    base_nums = base_nums.dropna().astype(int)
    if base_nums.empty:
        return "All Sessions"
    min_base = int(base_nums.min())
    max_base = int(base_nums.max())
    if min_base == max_base:
        return f"{_ordinal(min_base)} Regular Session"
    return f"{_ordinal(min_base)} to {_ordinal(max_base)} Sessions"

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

def _pdf_safe_text(text: str) -> str:
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")

PDF_CHART_ERROR_KEY = "pdf_chart_error"

def _record_pdf_chart_error(message: str) -> None:
    if not message:
        return
    if PDF_CHART_ERROR_KEY not in st.session_state:
        st.session_state[PDF_CHART_ERROR_KEY] = message

def _clear_pdf_chart_error() -> None:
    if PDF_CHART_ERROR_KEY in st.session_state:
        del st.session_state[PDF_CHART_ERROR_KEY]

def _configure_kaleido_scope() -> bool:
    try:
        scope = pio.kaleido.scope
    except Exception as exc:
        _record_pdf_chart_error(f"Kaleido unavailable: {exc}")
        return False
    if scope is None:
        _record_pdf_chart_error("Kaleido scope unavailable. Install the kaleido package.")
        return False
    try:
        scope.mathjax = None
        scope.default_format = "png"
    except Exception:
        pass
    return True

def _wrap_pdf_line(pdf: FPDF, text: str, max_w: float) -> list[str]:
    if text is None:
        return [""]
    safe_text = _pdf_safe_text(text)
    if max_w <= 0:
        return [safe_text]
    words = safe_text.split(" ")
    if not words:
        return [""]

    lines = []
    current = ""
    for word in words:
        if word == "":
            continue
        candidate = word if not current else f"{current} {word}"
        if pdf.get_string_width(candidate) <= max_w:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        if pdf.get_string_width(word) <= max_w:
            current = word
            continue

        chunk = ""
        for ch in word:
            if not chunk or pdf.get_string_width(chunk + ch) <= max_w:
                chunk += ch
            else:
                lines.append(chunk)
                chunk = ch
        current = chunk

    if current:
        lines.append(current)
    return lines if lines else [safe_text]

def _apply_pdf_chart_layout(fig):
    if fig is None:
        return fig
    fig.update_layout(
        font=dict(family="Helvetica", size=11, color="#1f2933"),
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    return fig

def _fig_to_png_bytes(fig, width: int = 900, height: int = 500, scale: int = 2) -> bytes | None:
    if fig is None:
        return None
    if not _configure_kaleido_scope():
        return None
    _apply_pdf_chart_layout(fig)
    last_exc = None
    scales = [scale] if scale == 1 else [scale, 1]
    for attempt_scale in scales:
        try:
            return pio.to_image(
                fig,
                format="png",
                width=width,
                height=height,
                scale=attempt_scale,
                engine="kaleido",
            )
        except Exception as exc:
            last_exc = exc
    if last_exc is not None:
        _record_pdf_chart_error(str(last_exc))
    return None

def _coerce_pdf_bytes(data) -> bytes | None:
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("latin-1", errors="replace")
    if hasattr(data, "getvalue"):
        try:
            return data.getvalue()
        except Exception:
            return None
    try:
        return bytes(data)
    except Exception:
        return None

def _pdf_add_rule(pdf: FPDF) -> None:
    y = pdf.get_y()
    pdf.set_draw_color(180, 180, 180)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)

def _pdf_add_heading(pdf: FPDF, text: str, size: int = 13) -> None:
    pdf.set_font("Helvetica", "B", size)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, 7, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

def _pdf_add_subheading(pdf: FPDF, text: str, size: int = 11) -> None:
    pdf.set_font("Helvetica", "B", size)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, 6, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

def _pdf_add_paragraph(pdf: FPDF, text: str, size: int = 11, line_h: int = 6) -> None:
    pdf.set_font("Helvetica", "", size)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin
    for line in _wrap_pdf_line(pdf, text, max_w):
        pdf.cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

def _pdf_add_bullets(pdf: FPDF, bullets: list[str], size: int = 10, line_h: int = 5) -> None:
    pdf.set_font("Helvetica", "", size)
    max_w = pdf.w - pdf.l_margin - pdf.r_margin - 6
    for bullet in bullets:
        pdf.cell(4, line_h, "-", new_x=XPos.RIGHT, new_y=YPos.TOP)
        lines = _wrap_pdf_line(pdf, bullet, max_w)
        if lines:
            pdf.cell(0, line_h, lines[0], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            for cont in lines[1:]:
                pdf.cell(4, line_h, "", new_x=XPos.RIGHT, new_y=YPos.TOP)
                pdf.cell(0, line_h, cont, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.ln(line_h)
    pdf.ln(2)

def _pdf_add_kpi_table(pdf: FPDF, rows: list[tuple[str, str]], size: int = 10) -> None:
    if not rows:
        return
    label_w = 60
    value_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w
    fill = False
    for label, value in rows:
        pdf.set_fill_color(245, 246, 248) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", size)
        pdf.cell(label_w, 6, _pdf_safe_text(label), new_x=XPos.RIGHT, new_y=YPos.TOP, fill=fill)
        pdf.set_font("Helvetica", "", size)
        pdf.cell(value_w, 6, _pdf_safe_text(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=fill)
        fill = not fill
    pdf.ln(2)

def _pdf_ensure_space(pdf: FPDF, height_needed: float) -> None:
    if pdf.get_y() + height_needed > pdf.h - pdf.b_margin:
        pdf.add_page()

def _pdf_add_chart(pdf: FPDF, fig, caption: str, width_px: int = 900, height_px: int = 500) -> None:
    png = _fig_to_png_bytes(fig, width=width_px, height=height_px, scale=2)
    if not png:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, _pdf_safe_text(f"{caption} (chart unavailable)"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        return
    img_w = pdf.w - pdf.l_margin - pdf.r_margin
    img_h = img_w * (height_px / width_px)
    _pdf_ensure_space(pdf, img_h + 12)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, _pdf_safe_text(caption), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.image(BytesIO(png), x=pdf.l_margin, w=img_w, h=img_h)
    pdf.ln(4)

def _pdf_add_section_title(pdf: FPDF, text: str) -> None:
    pdf.set_fill_color(230, 238, 246)
    pdf.set_text_color(16, 35, 58)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe_text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

def _build_focus_chart(chart: dict):
    kind = str(chart.get("kind", "")).strip().lower()
    if kind == "bar":
        df = pd.DataFrame(chart.get("data", []))
        if df.empty or "label" not in df.columns or "value" not in df.columns:
            return None
        orientation = str(chart.get("orientation", "h")).strip().lower()
        if orientation == "v":
            fig = px.bar(
                df,
                x="label",
                y="value",
                text="value",
                color_discrete_sequence=["#4c78a8"],
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(
                template="plotly_white",
                title=chart.get("title", ""),
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=40),
            )
            fig.update_yaxes(tickformat="~s")
        else:
            fig = px.bar(
                df.sort_values("value"),
                x="value",
                y="label",
                orientation="h",
                text="value",
                color_discrete_sequence=["#4c78a8"],
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(
                template="plotly_white",
                title=chart.get("title", ""),
                xaxis_title="",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            fig.update_xaxes(tickformat="~s")
        return fig

    if kind == "grouped_bar":
        df = pd.DataFrame(chart.get("data", []))
        if df.empty or not {"Position", "Funding", "Count"}.issubset(df.columns):
            return None
        fig = px.bar(
            df,
            x="Position",
            y="Count",
            color="Funding",
            barmode="group",
            text="Count",
            color_discrete_map={"Taxpayer Funded": "#d14b4b", "Private": "#4c78a8"},
        )
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(
            template="plotly_white",
            title=chart.get("title", ""),
            xaxis_title="",
            yaxis_title="",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        fig.update_yaxes(tickformat="~s")
        return fig

    return None

def _calc_share_range(tfl_low: float, tfl_high: float, total_low: float, total_high: float) -> tuple[float, float]:
    if total_low <= 0 or total_high <= 0:
        return 0.0, 0.0
    low = tfl_low / total_high if total_high else 0.0
    high = tfl_high / total_low if total_low else 0.0
    low = min(max(low, 0.0), 1.0)
    high = min(max(high, 0.0), 1.0)
    return low * 100, high * 100

def _chart_lines(rows: list[tuple[str, str]]) -> str:
    return "\n".join([f"{label}: {value}" for label, value in rows if label])

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
            base = base[base["Session"] == tfl_session].copy()

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
        subset = df[df["IsTFL"] == is_tfl].copy()
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
            {"Client": row["Client"], "Low": float(row["Low"]), "High": float(row["High"])}
            for _, row in grouped.iterrows()
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
    tfl_clients = base[base["IsTFL"] == 1].copy()
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
            wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)].copy()
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
                against = pos[pos["Position"].astype(str).str.contains("Against", case=False, na=False)].copy()

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
            bill_info = bill_info[bill_info["Session"].astype(str).str.strip() == str(session_val)].copy()
        keep_cols = [c for c in ["Bill", "Caption", "Status"] if c in bill_info.columns]
        if keep_cols:
            bill_info = bill_info[keep_cols].drop_duplicates(subset=["Bill"])
        counts = counts.merge(bill_info, on="Bill", how="left") if keep_cols else counts

        for _, row in counts.iterrows():
            bill_id = str(row.get("Bill", "")).strip() or "-"
            caption = str(row.get("Caption", "")).strip() or "-"
            status = str(row.get("Status", "")).strip()
            summary = f"Status: {status}" if status else "Status: Unknown"
            top_bills.append(
                {
                    "id": bill_id,
                    "caption": caption,
                    "tfl": int(row.get("tfl", 0) or 0),
                    "private": int(row.get("private", 0) or 0),
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
            bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)].copy()
        merged = against[["Bill"]].merge(bill_sub[["Bill", "Subject"]], on="Bill", how="left")
        merged["Subject"] = merged["Subject"].fillna("").astype(str).str.strip()
        merged = merged[merged["Subject"] != ""].copy()
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
        tmp = Lobby_TFL_Client_All[["LobbyShort", "Lobby Name"]].dropna().copy()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
        lobbyshort_to_name = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .agg(lambda s: s.dropna().astype(str).iloc[0] if len(s) else "")
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
            client_rows["ClientNorm"] = client_rows["Client"].map(norm_name)
            client_rows = client_rows[client_rows["ClientNorm"] == norm_name(client_name)].copy()

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
                    wit = wit[wit["LobbyShort"].astype(str).str.strip().isin(lobbyshorts)].copy()
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)].copy()
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
                            bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)].copy()
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
                                for _, row in bill_counts.iterrows():
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
                                bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)].copy()
                            sub_counts = (
                                bill_sub[bill_sub["Bill"].astype(str).isin(bill_list_all)]
                                .groupby("Subject")
                                .size()
                                .reset_index(name="Mentions")
                                .sort_values("Mentions", ascending=False)
                                .head(5)
                            )
                            policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                            for _, row in sub_counts.iterrows():
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
                    lobby_sub = lobby_sub_all.copy()
                    if "Session" in lobby_sub.columns and session_val is not None:
                        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)].copy()
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
                        topic_counts = _top_counts(lobby_sub["Topic"], 5)
                        if topic_counts:
                            topics = ", ".join([f"{t} ({c:,})" for t, c in topic_counts])
                            focus_section["bullets"].append(f"Reported subject matters: {topics}")

                if not staff_all.empty and lobbyist_norms:
                    staff_df = staff_all.copy()
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

                    staff_pick = staff_df[match_mask].copy()
                    staff_pick_session = staff_df[staff_session_mask & match_mask].copy()
                    if not staff_pick.empty:
                        staff_rows = int(len(staff_pick))
                        staff_legs = int(staff_pick.get("Legislator", pd.Series(dtype=object)).nunique()) if "Legislator" in staff_pick.columns else 0
                        focus_section["metrics"].append(("Staff history rows", f"{staff_rows:,}"))
                        if staff_legs:
                            focus_section["metrics"].append(("Legislators w/ staff ties", f"{staff_legs:,}"))
                        top_staff_legs = _top_counts(staff_pick.get("Legislator", pd.Series(dtype=object)), 5)
                        if top_staff_legs:
                            legs = ", ".join([f"{l} ({c:,})" for l, c in top_staff_legs])
                            focus_section["bullets"].append(f"Top legislators in staff history: {legs}")
                    if not staff_pick_session.empty:
                        focus_section["bullets"].append(
                            f"Staff history rows in selected session: {len(staff_pick_session):,}"
                        )

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
            ).copy()
            lobby_rows = lobby_rows[lobby_rows["LobbyShort"].astype(str).str.strip() == lobbyshort].copy()

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
                    wit = wit[wit["LobbyShort"].astype(str).str.strip() == lobbyshort].copy()
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)].copy()
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
                            bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)].copy()
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
                                for _, row in bill_counts.iterrows():
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
                                bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)].copy()
                            sub_counts = (
                                bill_sub[bill_sub["Bill"].astype(str).isin(bill_list_all)]
                                .groupby("Subject")
                                .size()
                                .reset_index(name="Mentions")
                                .sort_values("Mentions", ascending=False)
                                .head(5)
                            )
                            policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                            for _, row in sub_counts.iterrows():
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
                    lobby_sub = lobby_sub_all.copy()
                    if "Session" in lobby_sub.columns and session_val is not None:
                        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)].copy()
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
                    staff_df = staff_all.copy()
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

                    staff_pick = staff_df[match_mask].copy()
                    staff_pick_session = staff_df[staff_session_mask & match_mask].copy()
                    if not staff_pick.empty:
                        staff_rows = int(len(staff_pick))
                        staff_legs = int(staff_pick.get("Legislator", pd.Series(dtype=object)).nunique()) if "Legislator" in staff_pick.columns else 0
                        focus_section["metrics"].append(("Staff history rows", f"{staff_rows:,}"))
                        if staff_legs:
                            focus_section["metrics"].append(("Legislators w/ staff ties", f"{staff_legs:,}"))
                        top_staff_legs = _top_counts(staff_pick.get("Legislator", pd.Series(dtype=object)), 5)
                        if top_staff_legs:
                            legs = ", ".join([f"{l} ({c:,})" for l, c in top_staff_legs])
                            focus_section["bullets"].append(f"Top legislators in staff history: {legs}")
                    if not staff_pick_session.empty:
                        focus_section["bullets"].append(
                            f"Staff history rows in selected session: {len(staff_pick_session):,}"
                        )

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
                authored = authored_all.copy()
                authored = authored[authored["AuthorNorm"] == norm_name(member_name)].copy()
                if session_val is not None and "Session" in authored.columns:
                    authored = authored[authored["Session"].astype(str).str.strip() == str(session_val)].copy()

                bill_count = int(authored["Bill"].nunique()) if not authored.empty else 0
                passed = int((authored.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not authored.empty else 0
                failed = int((authored.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not authored.empty else 0
                bill_list = authored["Bill"].dropna().astype(str).unique().tolist() if not authored.empty else []

                wit = Wit_All if isinstance(Wit_All, pd.DataFrame) else pd.DataFrame()
                witness = pd.DataFrame()
                if bill_list and not wit.empty:
                    if session_val is not None and "Session" in wit.columns:
                        wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)].copy()
                    wit = wit[wit["Bill"].astype(str).isin(bill_list)].copy() if "Bill" in wit.columns else wit.iloc[0:0].copy()
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
                    authored_unique = authored.drop_duplicates(subset=["Bill"]).copy()
                    status_rank = authored_unique.get("Status", pd.Series(dtype=object)).map(
                        {"Passed": 0, "Failed": 1}
                    ).fillna(2)
                    authored_unique = authored_unique.assign(_rank=status_rank)
                    top_authored = authored_unique.sort_values(["_rank", "Bill"]).head(5)
                    for _, row in top_authored.iterrows():
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
                        bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)].copy()
                    sub_counts = (
                        bill_sub[bill_sub["Bill"].astype(str).isin(bill_list)]
                        .groupby("Subject")
                        .size()
                        .reset_index(name="Mentions")
                        .sort_values("Mentions", ascending=False)
                        .head(5)
                    )
                    policy_count = int(sub_counts["Subject"].nunique()) if not sub_counts.empty else 0
                    for _, row in sub_counts.iterrows():
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
                        for _, row in top_lobby.iterrows():
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
                    staff_df = staff_all.copy()
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
                    bs = bs[bs["Session"].astype(str).str.strip() == str(session_val)].copy()
                try:
                    bs["BillNorm"] = bs["Bill"].astype(str).map(normalize_bill)
                except Exception:
                    bs["BillNorm"] = bs["Bill"].astype(str).str.strip()
                bs_match = bs[bs["BillNorm"] == bill_id].copy()
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
                    wit = wit[wit["Session"].astype(str).str.strip() == str(session_val)].copy()
                try:
                    wit["Bill"] = wit["Bill"].astype(str).map(normalize_bill)
                except Exception:
                    wit["Bill"] = wit["Bill"].astype(str).str.strip()
                wit = wit[wit["Bill"] == bill_id].copy()
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
                        tmp = lt[["LobbyShort", "Lobby Name"]].dropna().copy()
                        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str).str.strip()
                        tmp["Lobby Name"] = tmp["Lobby Name"].astype(str).str.strip()
                        name_map = (
                            tmp.groupby("LobbyShort")["Lobby Name"]
                            .agg(lambda s: s.dropna().astype(str).iloc[0] if len(s) else "")
                            .to_dict()
                        )

                    counts = (
                        pos.groupby("LobbyShort")
                        .size()
                        .reset_index(name="Rows")
                        .sort_values("Rows", ascending=False)
                        .head(5)
                    )
                    for _, row in counts.iterrows():
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
                    bill_sub = bill_sub[bill_sub["Session"].astype(str).str.strip() == str(session_val)].copy()
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

def _build_report_pdf_bytes(payload: dict) -> bytes:
    class ReportPDF(FPDF):
        def __init__(self, header_title: str, header_subtitle: str, generated_date: str):
            super().__init__(orientation="P", unit="mm", format="A4")
            self.header_title = header_title
            self.header_subtitle = header_subtitle
            self.generated_date = generated_date

        def header(self):
            if self.page_no() == 1:
                return
            self.set_text_color(60, 60, 60)
            self.set_font("Helvetica", "B", 9)
            self.cell(0, 5, _pdf_safe_text(self.header_title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Helvetica", "", 8)
            subtitle = str(self.header_subtitle or "")
            if len(subtitle) > 110:
                subtitle = subtitle[:107].rstrip() + "..."
            self.cell(0, 4, _pdf_safe_text(subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_draw_color(200, 200, 200)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)
            self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-12)
            self.set_text_color(120, 120, 120)
            self.set_font("Helvetica", "", 8)
            w = self.w - self.l_margin - self.r_margin
            left_w = w * 0.6
            right_w = w - left_w
            self.cell(left_w, 4, _pdf_safe_text(f"Generated {self.generated_date}"), new_x=XPos.RIGHT, new_y=YPos.TOP, align="L")
            self.cell(right_w, 4, _pdf_safe_text(f"Page {self.page_no()}"), new_x=XPos.RIGHT, new_y=YPos.TOP, align="R")
            self.set_text_color(0, 0, 0)

    header_title = payload.get("report_title", "Lobby Look-Up Report")
    scope_sub = payload.get("scope_session_label") or payload.get("scope_label", "")
    header_subtitle = f"{scope_sub} | {payload['focus_label']}".strip(" |")
    pdf = ReportPDF(header_title, header_subtitle, payload["generated_date"])
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_title(_pdf_safe_text(header_title))
    pdf.set_author(_pdf_safe_text("Lobby Look-Up"))
    pdf.add_page()

    pdf.set_fill_color(16, 35, 58)
    pdf.rect(pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin, 2, "F")
    pdf.ln(4)

    _pdf_add_heading(pdf, "TAXPAYER-FUNDED LOBBYING IN TEXAS", size=16)
    _pdf_add_subheading(
        pdf,
        f"Analysis of the {payload['session_label']} Legislative Session",
        size=12,
    )
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, _pdf_safe_text("Prepared by Texas Lobby Data Center"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, _pdf_safe_text(f"Generated: {payload['generated_date']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, _pdf_safe_text(f"Scope: {payload['scope_session_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, _pdf_safe_text(f"Focus: {payload['focus_label']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    _pdf_add_rule(pdf)

    _pdf_add_section_title(pdf, "Executive Summary")
    exec_summary = (
        "Texas taxpayers should not be compelled to finance political advocacy through their own government. "
        f"During the {payload['session_label']} Legislative Session, registered lobbying activity reported "
        f"compensation ranges totaling between {payload['total_low']} and {payload['total_high']}. Within that total, "
        f"taxpayer-funded lobbying activity accounted for approximately {payload['tfl_low']} to {payload['tfl_high']}, "
        f"while privately funded lobbying accounted for approximately {payload['private_low']} to {payload['private_high']}. "
        f"Even under conservative assumptions, taxpayer-funded lobbying represented roughly {payload['tfl_share_low_pct']}% "
        f"to {payload['tfl_share_high_pct']}% of all reported lobbying compensation during this scope."
    )
    _pdf_add_paragraph(pdf, exec_summary, size=11)
    if payload.get("scope_note"):
        _pdf_add_paragraph(pdf, payload["scope_note"], size=10)
    exec_summary_2 = (
        "This report explains why taxpayer-funded lobbying is structurally inconsistent with transparent and "
        "accountable government, documents the scale of the practice in "
        f"{payload['session_label']}, and identifies the legislation and policy areas most frequently opposed by "
        "taxpayer-funded lobbyists. The conclusion is straightforward: Texas should abolish taxpayer-funded lobbying "
        "by political subdivisions and close both direct and indirect funding pathways so public money is used to provide "
        "public services, not to finance political advocacy."
    )
    _pdf_add_paragraph(pdf, exec_summary_2, size=11)

    _pdf_add_subheading(pdf, "Key Metrics", size=11)
    metrics = [
        ("Total lobbying range", f"{payload['total_low']} - {payload['total_high']}"),
        ("Taxpayer-funded range", f"{payload['tfl_low']} - {payload['tfl_high']}"),
        ("Private range", f"{payload['private_low']} - {payload['private_high']}"),
        ("Unique lobbyists", payload["unique_lobbyists_total"]),
        ("Lobbyists w/ TFL clients", payload["unique_lobbyists_tfl"]),
        ("Unique clients", payload["unique_clients_total"]),
        ("Taxpayer-funded clients", payload["unique_clients_tfl"]),
    ]
    _pdf_add_kpi_table(pdf, metrics, size=10)

    highlights = [
        f"Taxpayer-funded share: {payload['tfl_share_low_pct']}% - {payload['tfl_share_high_pct']}%",
        f"Taxpayer-funded range: {payload['tfl_low']} - {payload['tfl_high']}",
        f"Private range: {payload['private_low']} - {payload['private_high']}",
    ]
    _pdf_add_subheading(pdf, "Report Highlights", size=10)
    _pdf_add_bullets(pdf, highlights, size=10)

    focus_section = payload.get("focus_section")
    if focus_section and isinstance(focus_section, dict):
        title = focus_section.get("title", "").strip()
        summary = focus_section.get("summary", "").strip()
        metrics = focus_section.get("metrics", [])
        bullets = focus_section.get("bullets", [])
        charts = focus_section.get("charts", [])

        if title or summary or metrics or bullets or charts:
            _pdf_add_section_title(pdf, "Focus Snapshot")
            if title:
                _pdf_add_subheading(pdf, title, size=11)
            if summary:
                _pdf_add_paragraph(pdf, summary, size=11)
            if metrics:
                _pdf_add_subheading(pdf, "Key Focus Metrics", size=10)
                _pdf_add_kpi_table(pdf, metrics, size=10)
            if bullets:
                _pdf_add_subheading(pdf, "Focus Highlights", size=10)
                _pdf_add_bullets(pdf, bullets, size=10)
            if charts:
                _pdf_add_subheading(pdf, "Focus Charts", size=10)
                for chart in charts:
                    fig = _build_focus_chart(chart if isinstance(chart, dict) else {})
                    if fig:
                        caption = str(chart.get("caption", "Focus Chart")).strip() if isinstance(chart, dict) else "Focus Chart"
                        _pdf_add_chart(pdf, fig, caption)
            _pdf_add_rule(pdf)

    _pdf_add_section_title(pdf, f"I. THE SCALE OF LOBBYING IN {payload['session_label']}")
    scale_p1 = (
        "Lobbying in Texas is a major industry, and the compensation ranges reported to the state reflect the scale "
        "at which public policy is contested. For the "
        f"{payload['session_label']} session, the total reported lobbying compensation range across the selected scope "
        f"was {payload['total_low']} to {payload['total_high']}. Taxpayer-funded entities accounted for "
        f"{payload['tfl_low']} to {payload['tfl_high']} of that total, while privately funded entities accounted for "
        f"{payload['private_low']} to {payload['private_high']}. Because compensation is disclosed in ranges rather than "
        "precise amounts, these figures should be understood as conservative estimates of the activity captured in "
        "the underlying registrations and filings."
    )
    _pdf_add_paragraph(pdf, scale_p1, size=11)
    scale_p2 = (
        "The composition of the participating universe underscores why taxpayer-funded lobbying is not a marginal "
        "phenomenon. Across this scope, "
        f"{payload['unique_lobbyists_total']} unique lobbyists were observed, including {payload['unique_lobbyists_tfl']} "
        "who represented at least one taxpayer-funded client. Likewise, "
        f"{payload['unique_clients_total']} clients appeared in the data, including {payload['unique_clients_tfl']} that "
        "qualify as governmental or taxpayer-funded entities. The point is not merely that local governments participate "
        "in the process; it is that they do so at a scale capable of shaping agendas, crowding out citizen influence, "
        "and resisting reforms that would otherwise be evaluated on their merits."
    )
    _pdf_add_paragraph(pdf, scale_p2, size=11)

    comp_df = pd.DataFrame(
        [
            {"Funding": "Taxpayer Funded", "Low": payload["tfl_low_value"], "High": payload["tfl_high_value"]},
            {"Funding": "Private", "Low": payload["private_low_value"], "High": payload["private_high_value"]},
        ]
    )
    comp_long = comp_df.melt(id_vars="Funding", value_vars=["Low", "High"], var_name="Estimate", value_name="Total")
    if not comp_long.empty and comp_long["Total"].sum() > 0:
        fig_comp = px.bar(
            comp_long,
            x="Funding",
            y="Total",
            color="Estimate",
            barmode="group",
            text="Total",
            color_discrete_map={"Low": "#004c6d", "High": "#1f77b4"},
        )
        fig_comp.update_traces(texttemplate="$%{text:,.0f}", textposition="outside", cliponaxis=False)
        fig_comp.update_layout(
            template="plotly_white",
            title="Lobbying Compensation Range by Funding Type",
            yaxis_title="Reported compensation",
            xaxis_title="",
            legend_title="Estimate",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        fig_comp.update_yaxes(tickprefix="$", tickformat="~s")
        _pdf_add_chart(pdf, fig_comp, "Chart 1. Lobbying Compensation Range by Funding Type")

    tfl_mid = (payload["tfl_low_value"] + payload["tfl_high_value"]) / 2
    pri_mid = (payload["private_low_value"] + payload["private_high_value"]) / 2
    if (tfl_mid + pri_mid) > 0:
        share_df = pd.DataFrame(
            {"Funding": ["Taxpayer Funded", "Private"], "Total": [tfl_mid, pri_mid]}
        )
        fig_share = px.pie(
            share_df,
            names="Funding",
            values="Total",
            hole=0.5,
            color="Funding",
            color_discrete_map={"Taxpayer Funded": "#0ea5a4", "Private": "#4c78a8"},
        )
        fig_share.update_layout(
            template="plotly_white",
            title="Share of Total Lobbying (Midpoint)",
            margin=dict(l=20, r=20, t=50, b=20),
        )
        _pdf_add_chart(pdf, fig_share, "Chart 2. Share of Total Lobbying - Taxpayer vs Private", width_px=700, height_px=420)

    _pdf_add_section_title(pdf, "II. WHAT TAXPAYER-FUNDED LOBBYING IS - AND WHY IT MATTERS")
    def_p1 = (
        "Taxpayer-funded lobbying occurs when political subdivisions use public funds to employ registered lobbyists, "
        "contract with lobbying firms, or pay dues and assessments to associations that, in turn, employ lobbyists. "
        "In practice, the entities involved often include cities, counties, independent school districts, special "
        "districts, authorities, and intergovernmental associations funded by member governments. The distinctive "
        "feature is not the subject matter they address -- nearly any policy can be lobbied -- but the source of the "
        "money used to do it. When advocacy is financed with tax revenue or statutorily compelled fees, citizens are "
        "required to fund political activity as a condition of living, owning property, or receiving basic public services."
    )
    _pdf_add_paragraph(pdf, def_p1, size=11)
    def_p2 = (
        "That is why taxpayer-funded lobbying is a different category of problem than private-sector lobbying. "
        "Private entities spend their own money and must persuade contributors, shareholders, or members that the "
        "advocacy is worthwhile. Public entities spend money that was collected under compulsion and therefore operate "
        "without meaningful donor consent. This creates an unavoidable mismatch between who pays and who benefits. "
        "It also creates a confidence problem: citizens reasonably conclude that government is using their money to "
        "entrench itself, grow its authority, and resist reforms -- especially reforms aimed at fiscal restraint, "
        "regulatory limits, or transparency."
    )
    _pdf_add_paragraph(pdf, def_p2, size=11)

    entity_counts = payload.get("chart_entity_types_data", [])
    if entity_counts:
        entity_df = pd.DataFrame(entity_counts)
        fig_entities = px.bar(
            entity_df.sort_values("count"),
            x="count",
            y="type",
            orientation="h",
            text="count",
            color_discrete_sequence=["#4c78a8"],
        )
        fig_entities.update_traces(textposition="outside", cliponaxis=False)
        fig_entities.update_layout(
            template="plotly_white",
            title="Taxpayer-Funded Clients by Entity Type",
            xaxis_title="Clients",
            yaxis_title="",
            margin=dict(l=40, r=20, t=50, b=30),
        )
        _pdf_add_chart(pdf, fig_entities, "Chart 3. Taxpayer-Funded Clients by Entity Type")

    _pdf_add_section_title(pdf, f"III. LEGISLATIVE ACTIVITY PATTERNS IN {payload['session_label']}")
    act_p1 = (
        "Compensation totals explain scale, but legislative activity signals show how that scale is used. "
        f"Across the {payload['session_label']} session, taxpayer-funded lobbyists appeared repeatedly in committee "
        "processes, filing and testifying in ways that illustrate institutional priorities. The witness-list record "
        "indicates that taxpayer-funded entities did not simply monitor legislation; they frequently intervened in it "
        "-- especially on proposals with direct implications for local discretion, budgets, and oversight."
    )
    _pdf_add_paragraph(pdf, act_p1, size=11)
    act_p2 = (
        "Within this scope, witness positions for taxpayer-funded and privately funded interests can be summarized as follows: "
        f"{payload['witness_activity_summary']} The distribution of positions matters because it is a proxy for the "
        "incentives embedded in taxpayer-funded lobbying."
    )
    _pdf_add_paragraph(pdf, act_p2, size=11)

    w_counts = payload.get("witness_counts", {})
    if w_counts:
        w_rows = []
        for position in ["Against", "For", "On"]:
            w_rows.append(
                {
                    "Position": position,
                    "Taxpayer Funded": int(w_counts.get("tfl", {}).get(position, 0)),
                    "Private": int(w_counts.get("private", {}).get(position, 0)),
                }
            )
        w_df = pd.DataFrame(w_rows)
        if not w_df.empty and w_df[["Taxpayer Funded", "Private"]].sum().sum() > 0:
            w_long = w_df.melt(id_vars="Position", var_name="Funding", value_name="Count")
            fig_wit = px.bar(
                w_long,
                x="Position",
                y="Count",
                color="Funding",
                barmode="group",
                text="Count",
                color_discrete_map={"Taxpayer Funded": "#ff6b6b", "Private": "#4c78a8"},
            )
            fig_wit.update_traces(textposition="outside", cliponaxis=False)
            fig_wit.update_layout(
                template="plotly_white",
                title="Witness Positions by Funding Type",
                yaxis_title="Positions",
                xaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_wit, "Chart 4. Witness Positions by Funding Type")

    _pdf_add_section_title(pdf, "IV. THE BILLS MOST OPPOSED BY TAXPAYER-FUNDED LOBBYISTS")
    if payload.get("has_top_bills"):
        bills_p = (
            "The most direct way to see taxpayer-funded lobbying in action is to identify the bills that generated "
            "concentrated opposition from taxpayer-funded entities. The bills below are ranked by the number of "
            "Against filings by taxpayer-funded lobbyists."
        )
        _pdf_add_paragraph(pdf, bills_p, size=11)
        top_bills = payload.get("top_bills", [])
        if top_bills:
            bill_df = pd.DataFrame(
                [{"Bill": b["id"], "Oppositions": b.get("tfl", 0)} for b in top_bills]
            )
            fig_bills = px.bar(
                bill_df.sort_values("Oppositions"),
                x="Oppositions",
                y="Bill",
                orientation="h",
                text="Oppositions",
                color_discrete_sequence=["#d14b4b"],
            )
            fig_bills.update_traces(textposition="outside", cliponaxis=False)
            fig_bills.update_layout(
                template="plotly_white",
                title="Top Bills Opposed by Taxpayer-Funded Lobbyists",
                xaxis_title="Oppositions",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_bills, "Chart 5. Top 5 Bills Opposed by Taxpayer-Funded Lobbyists")
    else:
        _pdf_add_paragraph(pdf, "No bill-level opposition data was available for the selected scope/session.", size=11)

    _pdf_add_section_title(pdf, "V. THE POLICY AREAS MOST OPPOSED BY TAXPAYER-FUNDED LOBBYISTS")
    if payload.get("has_top_subjects"):
        subject_p = (
            "Bills are discrete, but policy areas reveal patterns. When opposition is aggregated by subject matter, "
            "taxpayer-funded lobbying tends to cluster in the places where the Legislature can most directly alter "
            "local fiscal and regulatory authority."
        )
        _pdf_add_paragraph(pdf, subject_p, size=11)
        top_subjects = payload.get("top_subjects", [])
        if top_subjects:
            subj_df = pd.DataFrame(
                [{"Subject": s["Subject"], "Oppositions": s.get("Oppositions", 0)} for s in top_subjects]
            )
            fig_subjects = px.bar(
                subj_df.sort_values("Oppositions"),
                x="Oppositions",
                y="Subject",
                orientation="h",
                text="Oppositions",
                color_discrete_sequence=["#7aa6c2"],
            )
            fig_subjects.update_traces(textposition="outside", cliponaxis=False)
            fig_subjects.update_layout(
                template="plotly_white",
                title="Top Policy Areas Opposed by Taxpayer-Funded Lobbyists",
                xaxis_title="Oppositions",
                yaxis_title="",
                margin=dict(l=40, r=20, t=50, b=30),
            )
            _pdf_add_chart(pdf, fig_subjects, "Chart 6. Top 5 Policy Areas Opposed by Taxpayer-Funded Lobbyists")
    else:
        _pdf_add_paragraph(pdf, "No subject-level opposition data was available for the selected scope/session.", size=11)

    _pdf_add_section_title(pdf, "VI. STRUCTURAL INCENTIVES AND THE COMPULSION PROBLEM")
    _pdf_add_paragraph(
        pdf,
        "Taxpayer-funded lobbying persists because it is rational for institutions. Political subdivisions face "
        "budget pressures, political pressures, and administrative demands, and they naturally seek to preserve the "
        "widest possible discretion to manage those pressures. But rationality for institutions is not the same as "
        "legitimacy for taxpayers. When the money used to lobby is collected under compulsion, the normal disciplining "
        "forces of voluntary association are absent. The cost of advocacy is dispersed across taxpayers, while the "
        "perceived benefits -- expanded authority, preserved revenues, reduced oversight -- accrue to the institution.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "The result is a misalignment: the payer is not the decision-maker, and the decision-maker has an incentive "
        "to externalize the cost. That is why taxpayer-funded lobbying is not merely politics as usual. It is a "
        "financing structure that undermines accountability and encourages institutional self-protection. Over time, "
        "it becomes a form of self-reinforcing governance: public entities use public funds to defend and expand the "
        "very powers that allow them to collect and deploy public funds.",
        size=11,
    )

    _pdf_add_section_title(pdf, "VII. LEGAL PARITY AND STATUTORY INCONSISTENCY")
    _pdf_add_paragraph(
        pdf,
        "Texas has already recognized that using public money to hire lobbyists raises concerns. State agencies face "
        "statutory restrictions that prevent them from employing registered lobbyists with public funds. Yet political "
        "subdivisions are not subject to uniform prohibitions, and the result is a parity failure. "
        f"{payload['existing_law_gap_summary']}",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "If the state has concluded that state agencies should not use taxpayer dollars to hire registered lobbyists, "
        "the same logic applies -- often more urgently -- to political subdivisions. Local entities are numerous, "
        "collectively spend vast sums, and frequently coordinate through associations that amplify their influence. "
        "In that environment, the absence of a clear prohibition invites continual expansion of the practice and "
        "continued erosion of public trust.",
        size=11,
    )

    _pdf_add_section_title(pdf, "VIII. POLICY SOLUTION: A COMPREHENSIVE BAN ON TAXPAYER-FUNDED LOBBYING")
    _pdf_add_paragraph(
        pdf,
        "The policy principle is simple: public money should not be used to lobby government. A workable statutory "
        "approach is equally straightforward: Texas should extend the existing state-agency prohibition framework to "
        "political subdivisions and close indirect funding pathways that allow local governments to outsource lobbying "
        "through membership associations.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        f"A recommended statutory reform is: {payload['recommended_fix_statute']}. Under this approach, the law should "
        "prohibit political subdivisions from using public funds to employ registered lobbyists directly, contract with "
        "registered lobbyists, or pay membership dues or assessments to organizations that employ registered lobbyists "
        "for the purpose of influencing legislation. The ban must be drafted to address both direct payments and indirect "
        "routing of funds. Otherwise, enforcement will become a game of accounting rather than a real protection for taxpayers.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "Implementation should include clear definitions of political subdivision, public funds, and lobbying "
        "services, and should make explicit that the prohibition applies regardless of whether the money is labeled "
        "appropriated, fee-based, enterprise, or interlocal. The Legislature should also specify enforceable remedies. "
        f"{payload['implementation_notes']}",
        size=11,
    )

    _pdf_add_section_title(pdf, "IX. DATA SOURCES AND METHODOLOGY")
    _pdf_add_paragraph(pdf, "This report is based on public information drawn from:", size=11)
    bullets = [
        b.strip().lstrip("- ").strip()
        for b in payload.get("data_sources_bullets", "").splitlines()
        if b.strip()
    ]
    _pdf_add_bullets(pdf, bullets, size=10)
    _pdf_add_paragraph(
        pdf,
        "Compensation figures reflect statutory reporting ranges filed with the Texas Ethics Commission. Totals were "
        "calculated by aggregating minimum and maximum disclosed ranges within the selected scope. Witness list activity "
        "reflects publicly available committee records compiled into the Lobby Look-Up dataset. Because compensation is "
        "reported in ranges rather than exact amounts, the totals presented here should be interpreted as conservative "
        "estimates rather than precise expenditures.",
        size=11,
    )

    _pdf_add_section_title(pdf, "CONCLUSION")
    _pdf_add_paragraph(
        pdf,
        f"During the {payload['session_label']} Legislative Session, taxpayers indirectly financed lobbying activity "
        f"totaling between {payload['tfl_low']} and {payload['tfl_high']} in reported compensation ranges. This practice "
        "compels political financing, entrenches institutional self-interest, and undermines public confidence that "
        "government is operating transparently and accountably.",
        size=11,
    )
    _pdf_add_paragraph(
        pdf,
        "Texas should abolish taxpayer-funded lobbying by political subdivisions and close both direct and indirect "
        "funding pathways. Public money should be used to provide public services -- not to finance political advocacy.",
        size=11,
    )
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, _pdf_safe_text("Prepared by Texas Lobby Data Center"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, _pdf_safe_text(payload["disclaimer_note"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    output = pdf.output()
    return output if isinstance(output, (bytes, bytearray)) else output.encode("latin-1")

def _render_pdf_report_section(
    *,
    key_prefix: str,
    session_val: str | None,
    scope_label: str,
    focus_label: str,
    Lobby_TFL_Client_All: pd.DataFrame,
    Wit_All: pd.DataFrame,
    Bill_Status_All: pd.DataFrame,
    Bill_Sub_All: pd.DataFrame,
    tfl_session_val: str | None,
    focus_context: dict | None = None,
) -> None:
    """Render PDF report generation section in an expander."""
    with st.expander("Custom PDF report", expanded=False):
        st.caption("Generate a PDF report using the current filters and selections.")

        sig_key = f"{key_prefix}_report_sig"
        pdf_key = f"{key_prefix}_report_pdf"
        name_key = f"{key_prefix}_report_name"
        signature = f"{session_val}|{scope_label}|{focus_label}"

        if st.session_state.get(sig_key) != signature:
            st.session_state[sig_key] = signature
            if pdf_key in st.session_state:
                del st.session_state[pdf_key]
            if name_key in st.session_state:
                del st.session_state[name_key]

        generate_clicked = st.button(
            "Generate report",
            key=f"{key_prefix}_report_build",
            width="stretch",
            help="Build a PDF using the current filters and selections.",
        )

        if generate_clicked:
            _clear_pdf_chart_error()
            try:
                with st.status("Generating PDF...", expanded=False):
                    payload = _build_report_payload(
                        session_val=session_val,
                        scope_label=scope_label,
                        focus_label=focus_label,
                        Lobby_TFL_Client_All=Lobby_TFL_Client_All,
                        Wit_All=Wit_All,
                        Bill_Status_All=Bill_Status_All,
                        Bill_Sub_All=Bill_Sub_All,
                        tfl_session_val=tfl_session_val,
                        focus_context=focus_context,
                    )
                    pdf_bytes = _coerce_pdf_bytes(_build_report_pdf_bytes(payload))
                    if pdf_bytes and len(pdf_bytes) > 0:
                        st.session_state[pdf_key] = pdf_bytes
                        st.session_state[name_key] = f"tfl-report-{_slugify(focus_label)}.pdf"
                        st.success("Report generated")
            except Exception as e:
                st.error(f"Report generation failed: {str(e)}")

        if pdf_key in st.session_state and st.session_state.get(PDF_CHART_ERROR_KEY):
            st.warning(
                "PDF rendering encountered an issue (charts). "
                "Common cause: missing Kaleido for Plotly images."
            )
            st.caption(st.session_state[PDF_CHART_ERROR_KEY])

        if pdf_key in st.session_state and isinstance(st.session_state[pdf_key], bytes):
            st.download_button(
                "Download PDF",
                st.session_state[pdf_key],
                st.session_state.get(name_key, "report.pdf"),
                "application/pdf",
                key=f"{key_prefix}_dl",
                width="stretch",
            )

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

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
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

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
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

    bills = bill_pos.copy()
    if not bill_status_all.empty and {"Session", "Bill"}.issubset(bill_status_all.columns):
        bills = bill_pos.merge(bill_status_all, on=["Session", "Bill"], how="left")

    if not fiscal_impact.empty and {"Session", "Bill", "Version", "EstimatedTwoYearNetImpactGR"}.issubset(fiscal_impact.columns):
        fi = fiscal_impact[fiscal_impact["Session"].astype(str).str.strip() == str(session_val)].copy()
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

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
def build_policy_mentions(bills: pd.DataFrame, bill_sub_all: pd.DataFrame, session_val: str) -> pd.DataFrame:
    if bills.empty or bill_sub_all.empty or "Bill" not in bills.columns:
        return pd.DataFrame(columns=["Subject", "Mentions", "Share"])
    if "Subject" not in bill_sub_all.columns:
        return pd.DataFrame(columns=["Subject", "Mentions", "Share"])

    bill_subjects = bill_sub_all.copy()
    if "Session" in bill_subjects.columns:
        bill_subjects = bill_subjects[bill_subjects["Session"].astype(str).str.strip() == str(session_val)].copy()
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

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
def build_lobby_subject_counts(
    lobby_sub_all: pd.DataFrame,
    session_val: str,
    lobbyshort: str,
    lobbyshort_norm: str,
    selected_filer_ids: tuple[int, ...],
) -> tuple[pd.DataFrame, float]:
    if lobby_sub_all.empty:
        return pd.DataFrame(columns=["Topic", "Mentions"]), 0.0

    lobby_sub = lobby_sub_all.copy()
    if "Session" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["Session"].astype(str).str.strip() == str(session_val)].copy()
    elif "session" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["session"].astype(str).str.strip() == str(session_val)].copy()

    if selected_filer_ids and "FilerID" in lobby_sub.columns:
        fid = pd.to_numeric(lobby_sub["FilerID"], errors="coerce").fillna(-1).astype(int)
        lobby_sub = lobby_sub[fid.isin(selected_filer_ids)].copy()
    elif "LobbyShortNorm" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["LobbyShortNorm"] == lobbyshort_norm].copy()
    elif "LobbyShort" in lobby_sub.columns:
        lobby_sub = lobby_sub[lobby_sub["LobbyShort"].astype(str).str.strip() == lobbyshort].copy()
    else:
        lobby_sub = lobby_sub.iloc[0:0].copy()

    if lobby_sub.empty:
        return pd.DataFrame(columns=["Topic", "Mentions"]), 0.0

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
    return lobby_sub_counts, subject_non_empty

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
def build_lobbyist_trend(
    df: pd.DataFrame,
    lobbyshort: str,
    filer_ids: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    if df.empty or not lobbyshort:
        return pd.DataFrame(columns=["Session", "Funding", "Mid", "SessionBase", "SessionLabel"])
    d = df.copy()
    d = d[d.get("LobbyShort", pd.Series(dtype=object)).astype(str).str.strip() == str(lobbyshort)].copy()
    if d.empty:
        return pd.DataFrame(columns=["Session", "Funding", "Mid", "SessionBase", "SessionLabel"])
    if filer_ids and "FilerID" in d.columns:
        fid = pd.to_numeric(d["FilerID"], errors="coerce").fillna(-1).astype(int)
        d = d[fid.isin(filer_ids)].copy()
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
    g = g[g["SessionBase"].notna()].copy()
    g["SessionLabel"] = g["SessionBase"].apply(_session_base_label)
    return g[["Session", "Funding", "Mid", "SessionBase", "SessionLabel"]]

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
def build_top_clients(lt: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    if lt.empty or "Client" not in lt.columns:
        return pd.DataFrame(columns=["Client", "Funding", "Low", "High", "Mid"])
    d = lt.copy()
    d["Client"] = d["Client"].fillna("").astype(str).str.strip()
    d = d[d["Client"] != ""].copy()
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

    scores = {}
    if q in known_shorts:
        scores[q] = 100

    q_norm = norm_name(q)
    norm_variants = {n for n in norm_person_variants_with_nicknames(q) if n}
    if q_norm:
        norm_variants.add(q_norm)
    for n in norm_variants:
        if n in name_to_short:
            short = str(name_to_short[n])
            if short and short.lower() not in {"nan", "none"}:
                scores[short] = max(scores.get(short, 0), 95)

    d = lobby_index
    if not norm_variants or d.empty:
        if not scores:
            return "", []

    info = parse_person_name(q)
    q_first = info.get("first_norm", "")
    q_last = info.get("last_norm", "")
    q_initial = info.get("first_initial", "")
    q_first_variants = _nickname_variants(q_first) if q_first else set()

    if q_norm and "LobbyShortNorm" in d.columns:
        exact_short = d["LobbyShortNorm"] == q_norm
        for short in d.loc[exact_short, "LobbyShort"].dropna().unique().tolist():
            scores[short] = max(scores.get(short, 0), 95)

    # Prefix matches on LobbyShort and Lobby Name keys
    if not d.empty and norm_variants:
        prefix_cols = [
            c for c in [
                "LobbyShortNorm",
                "LobbyNameNorm",
                "LobbyNameCleanNorm",
                "LastFirstNorm",
                "FirstLastNorm",
                "LastFirstInitialNorm",
            ]
            if c in d.columns
        ]
        if prefix_cols:
            prefix_mask = pd.Series(False, index=d.index)
            for n in norm_variants:
                for col in prefix_cols:
                    prefix_mask = prefix_mask | d[col].str.startswith(n, na=False)
            for short in d.loc[prefix_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 90)

    # Contains matches on LobbyShort and Lobby Name keys
    if not d.empty and norm_variants:
        contains_cols = [
            c for c in [
                "LobbyShortNorm",
                "LobbyNameNorm",
                "LobbyNameCleanNorm",
                "LastFirstNorm",
                "FirstLastNorm",
            ]
            if c in d.columns
        ]
        if contains_cols:
            contains_mask = pd.Series(False, index=d.index)
            for n in norm_variants:
                for col in contains_cols:
                    contains_mask = contains_mask | d[col].str.contains(n, na=False)
            for short in d.loc[contains_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 70)

    # First/last-name alignment
    if q_last and "LastNorm" in d.columns:
        last_mask = d["LastNorm"] == q_last
        for short in d.loc[last_mask, "LobbyShort"].dropna().unique().tolist():
            scores[short] = max(scores.get(short, 0), 75)
        if q_first and "FirstNorm" in d.columns:
            exact_mask = last_mask & (d["FirstNorm"] == q_first)
            for short in d.loc[exact_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 96)
            if q_first_variants:
                nick_mask = last_mask & d["FirstNorm"].isin(q_first_variants)
                for short in d.loc[nick_mask, "LobbyShort"].dropna().unique().tolist():
                    scores[short] = max(scores.get(short, 0), 94)
            prefix_mask = last_mask & d["FirstNorm"].str.startswith(q_first, na=False)
            for short in d.loc[prefix_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 90)
        if q_initial and "FirstInitial" in d.columns:
            init_mask = last_mask & (d["FirstInitial"] == q_initial)
            for short in d.loc[init_mask, "LobbyShort"].dropna().unique().tolist():
                scores[short] = max(scores.get(short, 0), 86)

    # Fuzzy matches against normalized names for minor typos
    if not d.empty and norm_variants:
        fuzzy_seed = max(norm_variants, key=len, default="")
        if len(fuzzy_seed) >= 3:
            name_norms = d.get("LobbyNameCleanNorm", d.get("LobbyNameNorm", pd.Series(dtype=object))).dropna().unique().tolist()
            close = difflib.get_close_matches(fuzzy_seed, name_norms, n=5, cutoff=0.78)
            if close:
                close_set = set(close)
                if "LobbyNameCleanNorm" in d.columns:
                    match_mask = d["LobbyNameCleanNorm"].isin(close_set)
                else:
                    match_mask = d["LobbyNameNorm"].isin(close_set)
                for short in d.loc[match_mask, "LobbyShort"].dropna().unique().tolist():
                    scores[short] = max(scores.get(short, 0), 60)

    if not scores:
        return "", []

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    top_score = ranked[0][1]
    top = [s for s, sc in ranked if sc == top_score]

    suggestions = [_candidate_label(s, short_to_names) for s, _ in ranked][:10]
    if len(top) == 1 and top_score >= 90:
        return top[0], suggestions

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

    if "LobbyShortNorm" not in d.columns:
        d["LobbyShortNorm"] = norm_name_series(d["LobbyShort"])
    q_norms = {n for n in norm_person_variants_with_nicknames(q) if n}
    q_norm = norm_name(q)
    if q_norm:
        q_norms.add(q_norm)
    if not q_norms:
        return "", []

    scores = {}
    prefix_mask = pd.Series(False, index=d.index)
    for n in q_norms:
        prefix_mask = prefix_mask | d["LobbyShortNorm"].str.startswith(n, na=False)
    for short in d.loc[prefix_mask, "LobbyShort"].dropna().unique().tolist():
        scores[short] = max(scores.get(short, 0), 90)

    contains_mask = pd.Series(False, index=d.index)
    for n in q_norms:
        contains_mask = contains_mask | d["LobbyShortNorm"].str.contains(n, na=False)
    for short in d.loc[contains_mask, "LobbyShort"].dropna().unique().tolist():
        scores[short] = max(scores.get(short, 0), 70)

    if "NameNorm" in d.columns or "name" in d.columns:
        name_norm = d.get("NameNorm", d["name"].fillna("").astype(str).map(norm_name))
        name_prefix = pd.Series(False, index=d.index)
        name_contains = pd.Series(False, index=d.index)
        for n in q_norms:
            name_prefix = name_prefix | name_norm.str.startswith(n, na=False)
            name_contains = name_contains | name_norm.str.contains(n, na=False)
        for short in d.loc[name_prefix, "LobbyShort"].dropna().unique().tolist():
            scores[short] = max(scores.get(short, 0), 80)
        for short in d.loc[name_contains, "LobbyShort"].dropna().unique().tolist():
            scores[short] = max(scores.get(short, 0), 60)

    if not scores:
        return "", []

    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    top_score = ranked[0][1]
    top = [s for s, sc in ranked if sc == top_score]

    if len(top) == 1 and top_score >= 90:
        return top[0], []

    suggestions = [s for s, _ in ranked][:10]
    return "", suggestions

def format_lobbyist_label(name: str, lobbyshort: str, filer_id) -> str:
    base = str(name).strip() if name else str(lobbyshort).strip()
    short_val = str(lobbyshort).strip()
    details = []
    if short_val and name:
        details.append(f"Last name + first initial: {short_val}")
    if pd.notna(filer_id):
        try:
            fid_val = int(filer_id)
        except Exception:
            fid_val = str(filer_id)
        details.append(f"FilerID {fid_val}")
    if details:
        return f"{base} ({' | '.join(details)})" if base else " | ".join(details)
    return base

def lobby_candidate_key(cand: dict) -> str:
    short = str(cand.get("lobbyshort", "") or "").strip()
    fid = cand.get("filerid", None)
    name = str(cand.get("name", "") or "").strip()
    try:
        if pd.notna(fid):
            return f"fid:{int(fid)}"
    except Exception:
        pass
    if short and name:
        return f"short:{short}|name:{norm_name(name)}"
    if short:
        return f"short:{short}"
    if name:
        return f"name:{norm_name(name)}"
    return "unknown"

def lobbyist_autocomplete_candidates(query: str, lobbyist_index: pd.DataFrame, limit: int = 12) -> list[dict]:
    q = (query or "").strip()
    if not q or lobbyist_index.empty:
        return []

    q_norm = norm_name(q)
    q_variants = {n for n in norm_person_variants_with_nicknames(q) if n}
    if q_norm:
        q_variants.add(q_norm)

    info = parse_person_name(q)
    q_first = info.get("first_norm", "")
    q_last = info.get("last_norm", "")
    q_initial = info.get("first_initial", "")
    q_first_variants = _nickname_variants(q_first) if q_first else set()

    d = lobbyist_index.copy()
    d["Score"] = 0

    def apply_score(mask: pd.Series, value: int) -> None:
        if mask.any():
            d.loc[mask, "Score"] = d.loc[mask, "Score"].where(d.loc[mask, "Score"] > value, value)

    if q_norm:
        apply_score(d["LobbyNameNorm"] == q_norm, 100)
        if "LobbyNameCleanNorm" in d.columns:
            apply_score(d["LobbyNameCleanNorm"] == q_norm, 100)
        apply_score(d["LobbyShortNorm"] == q_norm, 95)

    for n in q_variants:
        if not n:
            continue
        if "LobbyNameCleanNorm" in d.columns:
            apply_score(d["LobbyNameCleanNorm"] == n, 98)
            apply_score(d["LobbyNameCleanNorm"].str.startswith(n, na=False), 94)
            if len(n) >= 3:
                apply_score(d["LobbyNameCleanNorm"].str.contains(n, na=False), 80)
        apply_score(d["LobbyNameNorm"] == n, 97)
        apply_score(d["LobbyNameNorm"].str.startswith(n, na=False), 93)
        if len(n) >= 3:
            apply_score(d["LobbyNameNorm"].str.contains(n, na=False), 78)
            apply_score(d["LobbyShortNorm"].str.startswith(n, na=False), 85)
            apply_score(d["LobbyShortNorm"].str.contains(n, na=False), 65)
        if "LastFirstNorm" in d.columns:
            apply_score(d["LastFirstNorm"] == n, 98)
            apply_score(d["FirstLastNorm"] == n, 98)
        if "LastFirstInitialNorm" in d.columns:
            apply_score(d["LastFirstInitialNorm"] == n, 88)

    if q_last:
        apply_score(d["LastNorm"] == q_last, 75)
        if q_first:
            apply_score((d["LastNorm"] == q_last) & (d["FirstNorm"] == q_first), 97)
            if q_first_variants:
                apply_score((d["LastNorm"] == q_last) & (d["FirstNorm"].isin(q_first_variants)), 95)
            apply_score((d["LastNorm"] == q_last) & (d["FirstNorm"].str.startswith(q_first, na=False)), 90)
        if q_initial:
            apply_score((d["LastNorm"] == q_last) & (d["FirstInitial"] == q_initial), 86)

    if q_norm and len(q_norm) >= 3:
        name_norms = d.get("LobbyNameCleanNorm", d.get("LobbyNameNorm", pd.Series(dtype=object))).dropna().unique().tolist()
        close = difflib.get_close_matches(q_norm, name_norms, n=8, cutoff=0.78)
        if close:
            if "LobbyNameCleanNorm" in d.columns:
                apply_score(d["LobbyNameCleanNorm"].isin(close), 70)
            else:
                apply_score(d["LobbyNameNorm"].isin(close), 70)

    d = d[d["Score"] > 0].copy()
    if d.empty:
        return []

    d = d.sort_values(["Score", "Lobby Name", "LobbyShort"], ascending=[False, True, True])
    out = []
    for _, row in d.head(limit).iterrows():
        label = format_lobbyist_label(row.get("Lobby Name", ""), row.get("LobbyShort", ""), row.get("FilerID", None))
        out.append({
            "label": label,
            "lobbyshort": row.get("LobbyShort", ""),
            "filerid": row.get("FilerID", None),
            "name": row.get("Lobby Name", ""),
            "score": int(row.get("Score", 0)),
        })
    return out

@st.cache_data(show_spinner=False, ttl=300, max_entries=4)
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

@st.cache_data(show_spinner=False, ttl=300, max_entries=4)
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

@st.cache_data(show_spinner=False, ttl=300, max_entries=4)
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
    t = clean_person_name(member_name)
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

def parse_person_name(person_name: str) -> dict:
    return parse_member_name(person_name)

@st.cache_data(show_spinner=False, ttl=300, max_entries=4)
def build_lobbyist_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "LobbyShort" not in df.columns or "Lobby Name" not in df.columns:
        return pd.DataFrame(columns=[
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
        ])

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
    base["FirstNorm"] = parsed.map(lambda d: d.get("first_norm", "")).fillna("")
    base["LastNorm"] = parsed.map(lambda d: d.get("last_norm", "")).fillna("")
    base["FirstInitial"] = parsed.map(lambda d: d.get("first_initial", "")).fillna("")
    base["FirstLastNorm"] = (base["FirstNorm"] + base["LastNorm"]).where(
        (base["FirstNorm"] != "") & (base["LastNorm"] != ""), ""
    )
    base["LastFirstNorm"] = (base["LastNorm"] + base["FirstNorm"]).where(
        (base["FirstNorm"] != "") & (base["LastNorm"] != ""), ""
    )
    base["LastFirstInitialNorm"] = (base["LastNorm"] + base["FirstInitial"]).where(
        (base["LastNorm"] != "") & (base["FirstInitial"] != ""), ""
    )

    return base

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

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
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
                f"Found {total_rows} witness-list rows for {q}, but none matched a lobbyist in Texas Ethics Commission filings "
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
    st.dataframe(view, width="stretch", height=520, hide_index=True)
    _ = export_dataframe(view, "bill_lobbyists.csv")
    return True

# =========================================================
# FAST MONEY PARSING (vectorized) for Lobby_TFL_Client_All
# =========================================================
_MONEY_RANGE = re.compile(r"(-?\d[\d,]*\.?\d*)\s*(?:-|to)\s*(-?\d[\d,]*\.?\d*)", re.IGNORECASE)

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
    amt_clean = (
        amt.str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("\u2013", "-", regex=False)
    )

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

@st.cache_data(show_spinner=False, ttl=600, max_entries=2)
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
    lobby_name_rows = []

    def _append_lobby_names(df: pd.DataFrame, name_col: str, short_col: str, fid_col: str) -> None:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return
        if name_col not in df.columns or short_col not in df.columns:
            return
        tmp = df[[name_col, short_col]].copy()
        tmp = tmp.rename(columns={name_col: "Lobby Name", short_col: "LobbyShort"})
        tmp["FilerID"] = df[fid_col] if fid_col in df.columns else pd.NA
        lobby_name_rows.append(tmp)

    _append_lobby_names(data.get("Lobby_TFL_Client_All"), "Lobby Name", "LobbyShort", "FilerID")
    _append_lobby_names(data.get("Lobby_Sub_All"), "Lobby Name", "LobbyShort", "FilerID")
    _append_lobby_names(data.get("Lobbyist_Pol_Funds"), "Lobbyist", "LobbyShort", "FilerID")

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
    name_to_short = {}
    short_to_names = {}
    known_shorts = set()
    initial_to_short = {}

    if not lobbyist_index.empty:
        known_shorts = set(
            lobbyist_index["LobbyShort"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        tmp = lobbyist_index[["LobbyShort", "Lobby Name"]].dropna().copy()
        tmp["LobbyShort"] = tmp["LobbyShort"].astype(str)
        short_to_names = (
            tmp.groupby("LobbyShort")["Lobby Name"]
            .agg(lambda s: sorted(set(map(str, s)))[:6])
            .to_dict()
        )

        key_frames = []
        for col in ["LobbyNameNorm", "LobbyNameCleanNorm", "LastFirstNorm", "FirstLastNorm", "LastFirstInitialNorm"]:
            if col in lobbyist_index.columns:
                key_frames.append(lobbyist_index[[col, "LobbyShort"]].rename(columns={col: "Key"}))
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

        # Map last name + first initial to LobbyShort (helps when names don't match exactly)
        tmp_short = lobbyist_index[["LobbyShort"]].dropna().copy()
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

    # Map FilerID -> LobbyShort (used for activity matching)
    filerid_to_short = _build_filerid_map([
        (data.get("Lobby_TFL_Client_All"), "FilerID", "LobbyShort"),
        (data.get("Lobby_Sub_All"), "FilerID", "LobbyShort"),
        (data.get("Lobbyist_Pol_Funds"), "FilerID", "LobbyShort"),
    ])

    # Map witness list names/orgs to LobbyShort where possible
    wit = data.get("Wit_All")
    if isinstance(wit, pd.DataFrame) and not wit.empty:
        wit = wit.copy()
        if "LobbyShort" not in wit.columns:
            wit["LobbyShort"] = ""
        name_series = wit.get("name", pd.Series([""] * len(wit))).fillna("").astype(str)
        if "name" in wit.columns:
            wit["NameNorm"] = norm_name_series(name_series)
            wit["NameLastNorm"] = last_name_norm_series(name_series)
            wit["NameFirstNorm"] = first_name_norm_series(name_series)
            wit["NameFirstInitialNorm"] = wit["NameFirstNorm"].str.slice(0, 1)
        if name_to_short:
            name_norm = wit.get("NameNorm", name_series.map(norm_name))
            mapped = name_norm.map(name_to_short)
            if initial_to_short:
                init_key = name_series.map(_last_first_initial_key)
                mapped_init = init_key.map(initial_to_short)
                mapped = mapped.where(mapped.notna() & mapped.astype(str).str.strip().ne(""), mapped_init)
            if "org" in wit.columns:
                org_series = wit.get("org", pd.Series([""] * len(wit))).fillna("").astype(str)
                org_norm = norm_name_series(org_series)
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
    data["lobbyist_index"] = lobbyist_index
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

DATA_SOURCE_LABELS = {
    "Wit_All": "Texas Legislature Online (Witness lists)",
    "Bill_Status_All": "Texas Legislature Online (Bill status)",
    "Fiscal_Impact": "Texas Legislature Online (Fiscal notes)",
    "Bill_Sub_All": "Texas Legislature Online (Bill subjects)",
    "Lobby_Sub_All": "Texas Ethics Commission (Subject matter filings)",
    "Lobby_TFL_Client_All": "Texas Ethics Commission (Lobbyist filings and compensation)",
    "Staff_All": "House Research Organization (Legislative staff lists)",
    "LaFood": "Texas Ethics Commission (Activity: Food)",
    "LaEnt": "Texas Ethics Commission (Activity: Entertainment)",
    "LaTran": "Texas Ethics Commission (Activity: Travel)",
    "LaGift": "Texas Ethics Commission (Activity: Gifts)",
    "LaEvnt": "Texas Ethics Commission (Activity: Events)",
    "LaAwrd": "Texas Ethics Commission (Activity: Awards)",
    "LaCvr": "Texas Ethics Commission (Disclosure: Coverage)",
    "LaDock": "Texas Ethics Commission (Disclosure: Docket)",
    "LaI4E": "Texas Ethics Commission (Disclosure: On Behalf)",
    "LaSub": "Texas Ethics Commission (Disclosure: Subject Matter)",
}

def _source_label(key: str) -> str:
    return DATA_SOURCE_LABELS.get(key, key)

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
        label = _source_label(key)
        if isinstance(df, pd.DataFrame):
            sess_count = int(df["Session"].dropna().astype(str).nunique()) if "Session" in df.columns else 0
            lobby_count = int(df["LobbyShort"].dropna().astype(str).nunique()) if "LobbyShort" in df.columns else 0
            rows.append({
                "Source": label,
                "Rows": int(len(df)),
                "Cols": int(len(df.columns)),
                "Has Session": "Yes" if "Session" in df.columns else "No",
                "Empty": "Yes" if df.empty else "No",
                "Sessions": sess_count,
                "Last name + first initial": lobby_count,
            })
        else:
            rows.append({
                "Source": label,
                "Rows": 0,
                "Cols": 0,
                "Has Session": "No",
                "Empty": "Yes",
                "Sessions": 0,
                "Last name + first initial": 0,
            })
    return pd.DataFrame(rows)

# =========================================================
# ACTIVITIES (unchanged logic, still cached)
# =========================================================
@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
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
        route = (d.get("departureCity", "").fillna("").astype(str) + " -> " + d.get("arrivalCity", "").fillna("").astype(str)).str.strip()
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

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
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

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
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
            d.get("onbehalfName", "").fillna("").astype(str)
            + " -- "
            + d.get("onbehalfMailingCity", "").fillna("").astype(str)
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

@st.cache_data(show_spinner=False, ttl=300, max_entries=8)
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

nav_suggestions = []
nav_suggestion_map = {}
if nav_query and len(nav_query) >= 2 and not is_bill_query(nav_query):
    if PATH and (_is_url(PATH) or os.path.exists(PATH)):
        data = load_workbook(PATH)
        client_index = build_client_index(data.get("Lobby_TFL_Client_All", pd.DataFrame()))
        author_bills_all = build_author_bill_index(data.get("Bill_Status_All", pd.DataFrame()))
        member_index = build_member_index(author_bills_all)

        _, client_suggestions = resolve_client_name(nav_query, client_index)
        _, member_suggestions = resolve_member_name(nav_query, member_index)
        lobby_candidates = lobbyist_autocomplete_candidates(nav_query, data.get("lobbyist_index", pd.DataFrame()))
        lobby_suggestions = []
        if not lobby_candidates:
            _, lobby_suggestions = resolve_lobbyshort(
                nav_query,
                data.get("lobby_index", pd.DataFrame()),
                data.get("name_to_short", {}),
                data.get("known_shorts", set()),
                data.get("short_to_names", {}),
            )

        for s in client_suggestions:
            label = f"Client: {s}"
            nav_suggestions.append(label)
            nav_suggestion_map[label] = ("client", s)
        for s in member_suggestions:
            label = f"Legislator: {s}"
            nav_suggestions.append(label)
            nav_suggestion_map[label] = ("member", s)
        if lobby_candidates:
            for cand in lobby_candidates[:10]:
                label = f"Lobbyist: {cand['label']}"
                nav_suggestions.append(label)
                nav_suggestion_map[label] = ("lobbyist", cand)
        else:
            for s in lobby_suggestions:
                short_code = s.split(" - ")[0]
                label = f"Lobbyist: {s}"
                nav_suggestions.append(label)
                nav_suggestion_map[label] = ("lobbyist", {"lobbyshort": short_code, "name": short_code, "label": s, "filerid": None})

if nav_suggestions:
    nav_pick = nav_suggest_slot.selectbox(
        "Nav suggestions",
        ["Select a match..."] + nav_suggestions,
        index=0,
        key="nav_suggestions_select",
        label_visibility="collapsed",
    )
    if nav_pick in nav_suggestion_map:
        nav_skip_submit = True
        target, value = nav_suggestion_map[nav_pick]
        st.session_state.nav_search_query = value
        st.session_state.nav_search_last = value
        if target == "client":
            st.session_state.client_query = value
            st.session_state.client_query_input = value
            if _active_page != _client_page:
                st.switch_page(_client_page)
                st.stop()
        elif target == "member":
            st.session_state.member_query = value
            st.session_state.member_query_input = value
            if _active_page != _member_page:
                st.switch_page(_member_page)
                st.stop()
        else:
            sel = value if isinstance(value, dict) else {"lobbyshort": value, "name": value, "label": value, "filerid": None}
            sel_name = sel.get("name", "") or sel.get("lobbyshort", "")
            st.session_state.search_query = sel_name
            st.session_state.lobby_match_query = sel_name
            if sel.get("label"):
                st.session_state.lobby_match_select = sel.get("label")
            if sel.get("filerid") is not None:
                try:
                    st.session_state.lobby_filerid = int(sel.get("filerid"))
                except Exception:
                    st.session_state.lobby_filerid = sel.get("filerid")
            if sel.get("lobbyshort"):
                st.session_state.lobbyshort = sel.get("lobbyshort")
            if _active_page != _lobby_page:
                st.switch_page(_lobby_page)
                st.stop()
else:
    nav_suggest_slot.empty()

if nav_search_submitted and not nav_skip_submit:
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

            lobby_candidates = lobbyist_autocomplete_candidates(nav_query, data.get("lobbyist_index", pd.DataFrame()))
            resolved_lobby = ""
            resolved_lobby_filer = None
            resolved_lobby_name = ""
            lobby_suggestions = []
            if lobby_candidates:
                lobby_suggestions = [c.get("lobbyshort", "") for c in lobby_candidates if c.get("lobbyshort")]
                q_info = parse_person_name(nav_query)
                q_first = q_info.get("first_norm", "")
                q_last = q_info.get("last_norm", "")
                q_full = bool(q_first and q_last and len(q_first) >= 2 and len(q_last) >= 2)
                top = lobby_candidates[0]
                top_score = top.get("score", 0)
                if top_score >= 95 or (top_score >= 92 and q_full):
                    resolved_lobby = top.get("lobbyshort", "")
                    resolved_lobby_filer = top.get("filerid", None)
                    resolved_lobby_name = top.get("name", "")
            else:
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
                st.session_state.client_query_input = resolved_client
            elif resolved_member:
                target_page = _member_page
                st.session_state.member_query = resolved_member
                st.session_state.member_query_input = resolved_member
            elif resolved_lobby:
                target_page = _lobby_page
                st.session_state.search_query = resolved_lobby_name or nav_query
                if resolved_lobby_filer is not None:
                    st.session_state.lobby_filerid = resolved_lobby_filer
                if lobby_candidates:
                    st.session_state.lobby_match_query = st.session_state.search_query
                    st.session_state.lobby_match_select = lobby_candidates[0].get("label", "")
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
                    st.session_state.client_query_input = nav_query
                elif target_page == _member_page:
                    st.session_state.member_query = nav_query
                    st.session_state.member_query_input = nav_query
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
cta_left, cta_right = st.columns([3, 1])
with cta_left:
    st.markdown(
        """
<div class="callout fade-up">
  <div class="callout-title">Why this matters</div>
  <div class="callout-body">Taxpayer-funded lobbying means public dollars are used to influence public policy. This dashboard shows who is paid, which clients fund the work, and where they show up on legislation so Texans can see the full picture.</div>
</div>
""",
        unsafe_allow_html=True,
    )
with cta_right:
    if st.button("Read the policy fix", width="stretch", help="Open the Solutions page."):
        st.switch_page(_solutions_page)

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
lobbyist_index = data.get("lobbyist_index", pd.DataFrame())
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
if "lobby_filerid" not in st.session_state:
    st.session_state.lobby_filerid = None
if "lobby_selected_key" not in st.session_state:
    st.session_state.lobby_selected_key = ""
if "lobby_all_matches" not in st.session_state:
    st.session_state.lobby_all_matches = False
if "lobby_merge_keys" not in st.session_state:
    st.session_state.lobby_merge_keys = []
if "lobby_candidate_map" not in st.session_state:
    st.session_state.lobby_candidate_map = {}
if "lobby_override_same" not in st.session_state:
    st.session_state.lobby_override_same = {}
if "lobby_override_diff" not in st.session_state:
    st.session_state.lobby_override_diff = {}
if "lobby_match_query" not in st.session_state:
    st.session_state.lobby_match_query = ""
if "lobby_match_select" not in st.session_state:
    st.session_state.lobby_match_select = "No match"
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
if "recent_lobby_searches" not in st.session_state:
    st.session_state.recent_lobby_searches = []

st.sidebar.header("Data")

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
default_session = _default_session_from_list(sessions)
default_label = _session_label(default_session)

with st.sidebar.expander("Data health", expanded=False):
    st.caption(f"Data path: {PATH}")
    health = data_health_table(data)
    st.dataframe(health, width="stretch", height=260, hide_index=True)


# =========================================================
# TOP CONTROLS
#   - lobbyist name box (optional)
#   - session selector (All + ordinals)
# =========================================================
st.markdown('<div id="filter-bar-marker"></div>', unsafe_allow_html=True)
top1, top2, top3 = st.columns([2.2, 1.2, 1.2])

with top1:
    st.session_state.search_query = st.text_input(
        "Search lobbyist or bill",
        value=st.session_state.search_query,
        placeholder="e.g., Abbott or HB 4",
        help="Type a lobbyist name as Last, First or First Last. Use Autocomplete matches to pick the exact match.",
    )

with top2:
    label_to_session = {}
    session_labels = []
    for s in sessions:
        lab = _session_label(s)
        session_labels.append(lab)
        label_to_session[lab] = s

    # initialize once
    if st.session_state.session is None or str(st.session_state.session).strip().lower() in {"none", "nan", "null", ""}:
        st.session_state.session = default_session

    current_label = _session_label(st.session_state.session)
    if current_label not in session_labels:
        current_label = default_label if default_label in session_labels else session_labels[0]

    chosen_label = st.selectbox(
        "Session",
        session_labels,
        index=session_labels.index(current_label),
        help="Choose the legislative session used for filters and totals.",
    )
    st.session_state.session = label_to_session.get(chosen_label, default_session)

with top3:
    scope_opts = ["This Session", "All Sessions"]
    scope_index = scope_opts.index(st.session_state.scope) if st.session_state.scope in scope_opts else 0
    st.session_state.scope = st.radio(
        "Overview scope",
        scope_opts,
        index=scope_index,
        horizontal=True,
        help="Switch between the selected session only or totals across all sessions.",
    )

recent = st.session_state.get("recent_lobby_searches", [])
if recent:
    st.markdown('<div class="section-sub">Recent lookups</div>', unsafe_allow_html=True)
    recent_cols = st.columns(min(len(recent), 4))
    for idx, rec in enumerate(recent[:8]):
        col = recent_cols[idx % len(recent_cols)]
        label = rec if len(rec) <= 28 else rec[:25] + "..."
        if col.button(
            f"Reuse {label}",
            key=f"recent_lookup_{idx}",
            help="Reuse a recent lobbyist or bill search",
            width="stretch",
        ):
            st.session_state.search_query = rec
            st.session_state.lobbyshort = ""
            st.session_state.lobby_filerid = None
            st.session_state.lobby_selected_key = ""
            st.session_state.lobby_all_matches = False
            st.session_state.lobby_merge_keys = []
            st.session_state.lobby_candidate_map = {}
            st.session_state.lobby_match_query = rec
            st.session_state.lobby_match_select = "No match"
            st.session_state.bill_search = ""
            st.session_state.activity_search = ""
            st.session_state.disclosure_search = ""
            st.session_state.filter_lobbyshort = ""

tfl_session_val = _tfl_session_for_filter(st.session_state.session, tfl_sessions)

st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

# Resolve lobbyist match (autocomplete + disambiguation)
bill_mode = is_bill_query(st.session_state.search_query)
typed_norms = norm_person_variants_with_nicknames(st.session_state.search_query) if not bill_mode else set()
typed_init_key = _last_first_initial_key(st.session_state.search_query) if not bill_mode else ""
if typed_init_key:
    typed_norms.add(typed_init_key)

resolved_short = ""
resolved_filerid = None
match_candidates = []
candidate_map = {}
fallback_short = ""
q_norm = norm_name(st.session_state.search_query)
query_info = parse_person_name(st.session_state.search_query)
q_first = query_info.get("first_norm", "")
q_last = query_info.get("last_norm", "")
selected_match = None

if not bill_mode and st.session_state.search_query.strip():
    match_candidates = lobbyist_autocomplete_candidates(st.session_state.search_query, lobbyist_index)

    if q_norm and not lobbyist_index.empty:
        short_hits = lobbyist_index.loc[
            lobbyist_index["LobbyShortNorm"] == q_norm, "LobbyShort"
        ].dropna().unique().tolist()
        if len(short_hits) == 1:
            fallback_short = short_hits[0]

    if not match_candidates:
        resolved_from_wit, wit_suggestions = resolve_lobbyshort_from_wit(
            st.session_state.search_query,
            Wit_All,
            st.session_state.session,
        )
        if resolved_from_wit:
            fallback_short = resolved_from_wit
        for s in wit_suggestions:
            name_hint = short_to_names.get(s, [])
            display_name = name_hint[0] if name_hint else s
            label = format_lobbyist_label(display_name, s, None)
            match_candidates.append({
                "label": label,
                "lobbyshort": s,
                "filerid": None,
                "name": display_name,
                "score": 60,
            })

    if match_candidates:
        match_candidates = sorted(
            match_candidates,
            key=lambda x: (-int(x.get("score", 0)), str(x.get("label", "")))
        )
        for cand in match_candidates:
            cand["key"] = lobby_candidate_key(cand)
            if cand.get("key") and not cand.get("all_matches"):
                candidate_map[cand["key"]] = cand
        diff_map = st.session_state.lobby_override_diff or {}
        diff_keys_all = set()
        for keys in diff_map.values():
            diff_keys_all |= set(keys or [])
        shorts_with_diff = set()
        if diff_keys_all:
            for key in diff_keys_all:
                cand = candidate_map.get(key, {})
                short = cand.get("lobbyshort", "")
                if short:
                    shorts_with_diff.add(short)
        short_groups = {}
        for cand in match_candidates:
            short = cand.get("lobbyshort", "")
            if not short:
                continue
            entry = short_groups.get(short, {"count": 0, "score": 0})
            entry["count"] += 1
            entry["score"] = max(entry["score"], cand.get("score", 0))
            short_groups[short] = entry

        short_candidates = []
        for short, meta in short_groups.items():
            if meta["count"] > 1:
                if short in shorts_with_diff:
                    label = f"{short} (all matches: {meta['count']} variants, overrides set)"
                else:
                    label = f"{short} (all matches: {meta['count']} variants)"
                short_candidates.append({
                    "label": label,
                    "lobbyshort": short,
                    "filerid": None,
                    "name": "",
                    "score": meta["score"],
                    "all_matches": True,
                    "group_size": meta["count"],
                    "has_diff_override": short in shorts_with_diff,
                    "key": f"all:{short}",
                })

        preferred_all = None
        if short_candidates:
            eligible = [c for c in short_candidates if not c.get("has_diff_override")]
            if eligible:
                preferred_all = sorted(eligible, key=lambda x: (-x["score"], x["label"]))[0]

        auto_match = preferred_all
        if auto_match is None:
            if len(match_candidates) == 1:
                auto_match = match_candidates[0]
            if auto_match is None and q_norm:
                exact_name = [
                    c for c in match_candidates
                    if c.get("name") and norm_name(c.get("name")) == q_norm
                ]
                if len(exact_name) == 1:
                    auto_match = exact_name[0]
            if auto_match is None and q_norm and short_candidates:
                for cand in short_candidates:
                    if norm_name(cand["lobbyshort"]) == q_norm:
                        if not cand.get("has_diff_override"):
                            auto_match = cand
                        break
            if auto_match is None:
                top_score = match_candidates[0]["score"]
                top = [c for c in match_candidates if c["score"] == top_score]
                q_full = bool(q_first and q_last and len(q_first) >= 2 and len(q_last) >= 2)
                if len(top) == 1 and (top_score >= 95 or (top_score >= 92 and q_full)):
                    auto_match = top[0]
        if auto_match is not None and auto_match.get("all_matches") and auto_match.get("has_diff_override"):
            auto_match = None

        match_options = []
        match_map = {}
        for cand in sorted(short_candidates, key=lambda x: (-x["score"], x["label"])):
            match_options.append(cand["label"])
            match_map[cand["label"]] = cand
        for cand in match_candidates:
            if cand["label"] in match_map:
                continue
            match_options.append(cand["label"])
            match_map[cand["label"]] = cand

        if match_options:
            match_labels = ["No match"] + match_options
            default_label = auto_match["label"] if auto_match else "No match"
            if st.session_state.lobby_match_query != st.session_state.search_query:
                st.session_state.lobby_match_query = st.session_state.search_query
                st.session_state.lobby_match_select = default_label if default_label in match_labels else "No match"
            if st.session_state.lobby_match_select not in match_labels:
                st.session_state.lobby_match_select = default_label if default_label in match_labels else "No match"

            pick = st.selectbox(
                "Autocomplete matches (choose one)",
                match_labels,
                key="lobby_match_select",
                help="Pick the exact lobbyist entry. '(all matches)' merges name variants.",
            )
            st.caption("Each option lists the last name + first initial (and FilerID when available).")
            if pick in match_map:
                chosen = match_map[pick]
                selected_match = chosen
                st.session_state.lobby_selected_key = chosen.get("key", "")
                st.session_state.lobby_all_matches = bool(chosen.get("all_matches"))
                resolved_short = chosen.get("lobbyshort", "")
                resolved_filerid = chosen.get("filerid", None)
            else:
                resolved_short = ""
                st.session_state.lobby_selected_key = ""
                st.session_state.lobby_all_matches = False
            if st.session_state.search_query.strip() and not resolved_short:
                st.caption("Select a match to load results. Choose the '(all matches)' option to combine name variants that share the same last name + first initial.")

            if selected_match and selected_match.get("lobbyshort") and not selected_match.get("all_matches"):
                canon_key = st.session_state.lobby_selected_key
                if not canon_key:
                    canon_key = "unknown"
                canon_key_safe = re.sub(r"[^A-Za-z0-9_]+", "_", canon_key)
                same_map = st.session_state.lobby_override_same or {}
                diff_map = st.session_state.lobby_override_diff or {}
                same_keys = set(same_map.get(canon_key, []))
                diff_keys = set(diff_map.get(canon_key, []))
                override_candidates = [
                    c for c in match_candidates
                    if not c.get("all_matches")
                    and c.get("lobbyshort") == selected_match.get("lobbyshort")
                    and c.get("key") != canon_key
                ]
                if override_candidates:
                    used = {}
                    option_labels = []
                    label_to_key = {}
                    for cand in override_candidates:
                        base_label = (cand.get("label") or cand.get("name") or cand.get("lobbyshort") or "").strip()
                        label = base_label if base_label else "Unknown"
                        if label in used:
                            used[label] += 1
                            label = f"{label} ({used[label]})"
                        else:
                            used[label] = 1
                        option_labels.append(label)
                        label_to_key[label] = cand.get("key", lobby_candidate_key(cand))

                    with st.expander("Match overrides", expanded=False):
                        st.caption("Use this when you know two names refer to the same lobbyist or are definitely different.")
                        same_default = [lab for lab in option_labels if label_to_key.get(lab) in same_keys]
                        diff_default = [lab for lab in option_labels if label_to_key.get(lab) in diff_keys]

                        same_pick = st.multiselect(
                            "Same lobbyist (merge these into the selection)",
                            option_labels,
                            default=same_default,
                            key=f"lobby_override_same_select_{canon_key_safe}",
                            help="Treat these names as the same person and merge results.",
                        )
                        diff_pick = st.multiselect(
                            "Different lobbyist (keep these separate)",
                            option_labels,
                            default=diff_default,
                            key=f"lobby_override_diff_select_{canon_key_safe}",
                            help="Force these names to remain separate from the selection.",
                        )

                        new_same_keys = {label_to_key.get(lab) for lab in same_pick if label_to_key.get(lab)}
                        new_diff_keys = {label_to_key.get(lab) for lab in diff_pick if label_to_key.get(lab)}
                        new_same_keys = new_same_keys - new_diff_keys

                        same_map[canon_key] = sorted(new_same_keys)
                        diff_map[canon_key] = sorted(new_diff_keys)
                        st.session_state.lobby_override_same = same_map
                        st.session_state.lobby_override_diff = diff_map
                        st.session_state.lobby_merge_keys = sorted(new_same_keys)
                else:
                    st.session_state.lobby_merge_keys = []
            else:
                st.session_state.lobby_merge_keys = []
        else:
            resolved_short = fallback_short
    else:
        resolved_short = fallback_short
else:
    st.session_state.lobby_selected_key = ""
    st.session_state.lobby_all_matches = False
    st.session_state.lobby_merge_keys = []

st.session_state.lobbyshort = resolved_short or ""
st.session_state.lobby_filerid = resolved_filerid
st.session_state.lobby_candidate_map = candidate_map
if st.session_state.lobby_filerid and not lobbyist_index.empty:
    filer_series = pd.to_numeric(lobbyist_index.get("FilerID", pd.Series(dtype=float)), errors="coerce")
    match_row = lobbyist_index[
        (lobbyist_index["LobbyShort"].astype(str).str.strip() == st.session_state.lobbyshort) &
        (filer_series == int(st.session_state.lobby_filerid))
    ]
    if not match_row.empty:
        typed_norms |= norm_person_variants_with_nicknames(match_row["Lobby Name"].iloc[0])
merge_keys = st.session_state.lobby_merge_keys or []
candidate_map = st.session_state.lobby_candidate_map or {}
for key in merge_keys:
    cand = candidate_map.get(key, {})
    name = cand.get("name", "")
    if name:
        typed_norms |= norm_person_variants_with_nicknames(name)

# Track recent lookups for quick reuse
if st.session_state.lobbyshort:
    _remember_recent_search(st.session_state.search_query or st.session_state.lobbyshort)
elif st.session_state.search_query.strip():
    _remember_recent_search(st.session_state.search_query)

# Active filters summary + match details
match_line = "No match selected"
if st.session_state.lobbyshort:
    if st.session_state.lobby_filerid and not lobbyist_index.empty:
        filer_series = pd.to_numeric(lobbyist_index.get("FilerID", pd.Series(dtype=float)), errors="coerce")
        match_row = lobbyist_index[
            (lobbyist_index["LobbyShort"].astype(str).str.strip() == str(st.session_state.lobbyshort)) &
            (filer_series == int(st.session_state.lobby_filerid))
        ]
        if not match_row.empty:
            match_name = match_row["Lobby Name"].iloc[0]
            match_line = format_lobbyist_label(match_name, st.session_state.lobbyshort, st.session_state.lobby_filerid)
        else:
            match_line = st.session_state.lobbyshort
    else:
        match_line = st.session_state.lobbyshort

extra_parts = ["Mode: Bill search"] if bill_mode else []
active_parts = _current_filter_parts(extra_parts)
chips_html = "".join([f'<span class="chip">{html.escape(c)}</span>' for c in active_parts])

st.markdown('<div id="filter-summary-marker"></div>', unsafe_allow_html=True)
f1, f2 = st.columns([3, 1])
with f1:
    st.markdown(
        f'<div class="filter-summary"><span class="filter-summary-label">Active filters</span>{chips_html}</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Selected match: {match_line}")
    merge_names = []
    if st.session_state.lobby_merge_keys:
        cand_map = st.session_state.lobby_candidate_map or {}
        for key in st.session_state.lobby_merge_keys:
            cand = cand_map.get(key, {})
            name = cand.get("name", "")
            short = cand.get("lobbyshort", "")
            fid = cand.get("filerid", None)
            if name or short:
                merge_names.append(format_lobbyist_label(name, short, fid))
    if merge_names:
        st.caption("Merged variants: " + ", ".join(merge_names[:4]))
        st.caption("Use Autocomplete matches to change the selection.")
    names_hint = short_to_names.get(st.session_state.lobbyshort, []) if st.session_state.lobbyshort else []
    if names_hint:
        st.caption("Also seen as: " + ", ".join(names_hint[:6]))
with f2:
    if st.button(
        "Clear filters",
        width="stretch",
        help="Reset search, match, and table filters to defaults.",
    ):
        reset_filters(default_session)
if st.session_state.lobbyshort and not st.session_state.lobby_filerid and not lobbyist_index.empty:
    dup = lobbyist_index[lobbyist_index["LobbyShort"].astype(str).str.strip() == st.session_state.lobbyshort]
    if dup["FilerID"].nunique(dropna=True) > 1 or dup["Lobby Name"].nunique() > 1:
        if not st.session_state.lobby_all_matches:
            st.caption("Note: multiple name variants share this last name + first initial. Choose a specific match above to narrow results. Witness-list and bill activity remain combined.")

focus_label = "All Lobbyists"
if st.session_state.lobbyshort:
    display_name = ""
    if st.session_state.lobby_filerid and not lobbyist_index.empty:
        filer_series = pd.to_numeric(lobbyist_index.get("FilerID", pd.Series(dtype=float)), errors="coerce")
        match_row = lobbyist_index[
            (lobbyist_index["LobbyShort"].astype(str).str.strip() == str(st.session_state.lobbyshort)) &
            (filer_series == int(st.session_state.lobby_filerid))
        ]
        if not match_row.empty:
            display_name = match_row["Lobby Name"].iloc[0]
    if not display_name:
        name_hint = short_to_names.get(st.session_state.lobbyshort, []) if isinstance(short_to_names, dict) else []
        display_name = name_hint[0] if name_hint else st.session_state.lobbyshort
    if display_name != st.session_state.lobbyshort:
        focus_label = f"Lobbyist: {display_name} ({st.session_state.lobbyshort})"
    else:
        focus_label = f"Lobbyist: {st.session_state.lobbyshort}"
elif st.session_state.search_query.strip():
    focus_label = f"Lobbyist search: {st.session_state.search_query.strip()}"

report_title = "Bill Report" if bill_mode and st.session_state.search_query.strip() else "Lobbyist Report"
focus_tables = {
    "Staff_All": Staff_All,
    "Lobby_Sub_All": Lobby_Sub_All,
    "LaFood": data.get("LaFood", pd.DataFrame()),
    "LaEnt": data.get("LaEnt", pd.DataFrame()),
    "LaTran": data.get("LaTran", pd.DataFrame()),
    "LaGift": data.get("LaGift", pd.DataFrame()),
    "LaEvnt": data.get("LaEvnt", pd.DataFrame()),
    "LaAwrd": data.get("LaAwrd", pd.DataFrame()),
    "LaCvr": LaCvr,
    "LaDock": LaDock,
    "LaI4E": LaI4E,
    "LaSub": LaSub,
}
focus_lookups = {
    "name_to_short": name_to_short,
    "short_to_names": short_to_names,
    "filerid_to_short": data.get("filerid_to_short", {}),
}

focus_context = {
    "type": "",
    "report_title": report_title,
    "tables": focus_tables,
    "lookups": focus_lookups,
}
if bill_mode and st.session_state.search_query.strip():
    bill_id = ""
    try:
        bill_id = normalize_bill(st.session_state.search_query.strip())
    except Exception:
        bill_id = ""
    focus_context.update(
        {
            "type": "bill",
            "bill": bill_id or st.session_state.search_query.strip(),
            "query": st.session_state.search_query.strip(),
        }
    )
elif st.session_state.lobbyshort:
    focus_context.update(
        {
            "type": "lobbyist",
            "lobbyshort": st.session_state.lobbyshort,
            "display_name": display_name,
        }
    )

_ = _render_pdf_report_section(
    key_prefix="lobby",
    session_val=st.session_state.session,
    scope_label=st.session_state.scope,
    focus_label=focus_label,
    Lobby_TFL_Client_All=Lobby_TFL_Client_All,
    Wit_All=Wit_All,
    Bill_Status_All=Bill_Status_All,
    Bill_Sub_All=Bill_Sub_All,
    tfl_session_val=tfl_session_val,
    focus_context=focus_context,
)

# =========================================================
# FAST ALL-LOBBYISTS OVERVIEW (cached and uses Low_num/High_num)
# =========================================================
@st.cache_data(show_spinner=False, ttl=300, max_entries=4)
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

def kpi_card(title: str, value: str, sub: str = "", help_text: str = ""):
    tooltip_attr = f' title="{html.escape(help_text, quote=True)}"' if help_text else ""
    st.markdown(
        f"""
<div class="card"{tooltip_attr}>
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
    st.markdown(
        """
<div class="callout fade-up">
  <div class="callout-title">What this means</div>
<div class="callout-body">Totals are reported compensation ranges from Texas Ethics Commission lobby filings. Use Scope to switch between session-only and all-session aggregates, then narrow by last name + initial below.</div>
</div>
""",
        unsafe_allow_html=True,
    )

    if not require_columns(
        Lobby_TFL_Client_All,
        ["Session", "LobbyShort"],
        "All Lobbyists overview",
        "Check Texas Ethics Commission lobby filings in Data health.",
    ):
        st.info("This view needs Texas Ethics Commission lobby filings with Session and LobbyShort columns.")
    elif all_pivot.empty:
        st.info("No Texas Ethics Commission lobby filing rows found for the selected scope/session. Try a different session or verify the data path.")
    else:
        total_low = all_stats.get("tfl_low_total", 0.0) + all_stats.get("pri_low_total", 0.0)
        total_high = all_stats.get("tfl_high_total", 0.0) + all_stats.get("pri_high_total", 0.0)
        tfl_mid = (all_stats.get("tfl_low_total", 0.0) + all_stats.get("tfl_high_total", 0.0)) / 2
        pri_mid = (all_stats.get("pri_low_total", 0.0) + all_stats.get("pri_high_total", 0.0)) / 2
        total_mid = tfl_mid + pri_mid
        tfl_share_pct = (tfl_mid / total_mid * 100) if total_mid else 0.0
        lobby_total = all_stats.get("total_lobbyists", 0) or 0
        lobby_with_tfl = all_stats.get("has_tfl", 0) or 0
        lobby_with_tfl_pct = (lobby_with_tfl / lobby_total * 100) if lobby_total else 0.0
        mixed_pct = (all_stats.get("mixed", 0) / lobby_total * 100) if lobby_total else 0.0
        only_tfl_pct = (all_stats.get("only_tfl", 0) / lobby_total * 100) if lobby_total else 0.0

        insight_items = [
            f"Reported compensation ranges total {fmt_usd(total_low)} to {fmt_usd(total_high)} across this scope.",
            f"Taxpayer-funded clients account for about {tfl_share_pct:.0f}% of midpoint totals.",
            f"{lobby_with_tfl:,} lobbyists ({lobby_with_tfl_pct:.0f}%) work for at least one taxpayer-funded client.",
            f"Only taxpayer-funded: {only_tfl_pct:.0f}% of lobbyists; mixed funding: {mixed_pct:.0f}%.",
        ]
        insight_html = "".join([f"<li>{html.escape(item)}</li>" for item in insight_items])
        st.markdown(
            f"""
<div class="insight-panel fade-up">
  <div class="insight-card">
    <div class="insight-kicker">Statewide Snapshot</div>
    <div class="insight-title">Taxpayer-funded lobbying footprint</div>
    <ul class="insight-list">{insight_html}</ul>
  </div>
  <div class="insight-card">
    <div class="insight-kicker">Key ratios</div>
    <div class="mini-kpi-grid">
      <div class="mini-kpi">
        <div class="label">TFL Share</div>
        <div class="value">{tfl_share_pct:.0f}%</div>
        <div class="sub">Midpoint of total compensation</div>
      </div>
      <div class="mini-kpi">
        <div class="label">TFL Lobbyists</div>
        <div class="value">{lobby_with_tfl:,}</div>
        <div class="sub">{lobby_with_tfl_pct:.0f}% of all lobbyists</div>
      </div>
      <div class="mini-kpi">
        <div class="label">Only TFL</div>
        <div class="value">{all_stats.get('only_tfl', 0):,}</div>
        <div class="sub">{only_tfl_pct:.0f}% of all lobbyists</div>
      </div>
      <div class="mini-kpi">
        <div class="label">Mixed Funding</div>
        <div class="value">{all_stats.get('mixed', 0):,}</div>
        <div class="sub">{mixed_pct:.0f}% of all lobbyists</div>
      </div>
    </div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        a1, a2, a3, a4 = st.columns(4)
        with a1:
            kpi_card(
                "Total Taxpayer Funded",
                f"{fmt_usd(all_stats.get('tfl_low_total', 0.0))} - {fmt_usd(all_stats.get('tfl_high_total', 0.0))}",
                help_text="Sum of reported low/high compensation for taxpayer-funded clients in this scope.",
            )
        with a2:
            kpi_card(
                "Total Private",
                f"{fmt_usd(all_stats.get('pri_low_total', 0.0))} - {fmt_usd(all_stats.get('pri_high_total', 0.0))}",
                help_text="Sum of reported low/high compensation for private clients in this scope.",
            )
        with a3:
            kpi_card(
                "Total Lobbyists",
                f"{all_stats.get('total_lobbyists', 0):,}",
                help_text="Unique lobbyists in the selected scope.",
            )
            kpi_card(
                "Lobbyists w/ >=1 Taxpayer Funded client",
                f"{all_stats.get('has_tfl', 0):,}",
                help_text="Lobbyists with at least one taxpayer-funded client in this scope.",
            )
        with a4:
            kpi_card(
                "Only Private",
                f"{all_stats.get('only_private', 0):,}",
                help_text="Lobbyists with only private clients in this scope.",
            )
            kpi_card(
                "Only Taxpayer Funded",
                f"{all_stats.get('only_tfl', 0):,}",
                f"Mixed: {all_stats.get('mixed', 0):,}",
                help_text="Lobbyists with only taxpayer-funded clients; mixed count shown below.",
            )

        st.markdown('<div class="section-sub">Funding Mix (Midpoint)</div>', unsafe_allow_html=True)
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
                hole=0.6,
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
            st.plotly_chart(fig_mix, width="stretch", config=PLOTLY_CONFIG)
            st.markdown(
                '<div class="section-caption">Funding mix uses midpoint totals to compare taxpayer-funded vs private compensation ranges.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("No totals available for funding mix in this scope.")

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
            st.plotly_chart(fig_trend, width="stretch", config=PLOTLY_CONFIG)
            st.markdown('<div class="section-caption">Trend uses midpoint totals for taxpayer-funded clients across the 85th-89th sessions.</div>', unsafe_allow_html=True)
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
                    width="stretch",
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
                    width="stretch",
                    height=240,
                    hide_index=True,
                )
            else:
                st.info("No taxpayer funded clients found for the selected scope/session.")

        st.session_state.filter_lobbyshort = st.text_input(
            "Filter last name + first initial (contains)",
            value=st.session_state.filter_lobbyshort,
            placeholder="e.g., Abbott",
            help="Filter the All Lobbyists table by a name substring.",
        )
        st.markdown('<div class="section-caption">Tip: Use the table filters to narrow the list; CSV exports include the active scope and session.</div>', unsafe_allow_html=True)
        flt = st.session_state.filter_lobbyshort
        c1, c2, c3 = st.columns(3)
        with c1:
            only_tfl = st.checkbox(
                "Only taxpayer funded",
                value=False,
                help="Show lobbyists with taxpayer-funded clients only.",
            )
        with c2:
            only_private = st.checkbox(
                "Only private",
                value=False,
                help="Show lobbyists with private clients only.",
            )
        with c3:
            mixed_only = st.checkbox(
                "Mixed only",
                value=False,
                help="Show lobbyists with both taxpayer-funded and private clients.",
            )

        view = all_pivot.copy()
        view["Total_Low"] = view["Low_TFL"] + view["Low_Private"]
        view["Total_High"] = view["High_TFL"] + view["High_Private"]
        view["TFL_Mid"] = (view["Low_TFL"] + view["High_TFL"]) / 2
        view["Private_Mid"] = (view["Low_Private"] + view["High_Private"]) / 2
        view["Total_Mid"] = view["TFL_Mid"] + view["Private_Mid"]
        view["TFL_Share"] = view["TFL_Mid"] / view["Total_Mid"].where(view["Total_Mid"] != 0, 1)
        view["TFL_Share"] = view["TFL_Share"].fillna(0)
        if flt.strip():
            view = view[view["LobbyShort"].astype(str).str.contains(flt.strip(), case=False, na=False)].copy()
        if only_tfl:
            view = view[view.get("Only_TFL", False)].copy()
        if only_private:
            view = view[view.get("Only_Private", False)].copy()
        if mixed_only:
            view = view[view.get("Mixed", False)].copy()

        threshold_col1, threshold_col2 = st.columns(2)
        with threshold_col1:
            max_mid = int(view["Total_Mid"].max()) if not view.empty else 0
            min_mid = 0
            if max_mid > 0:
                step = max(int(max_mid / 50), 1000)
                step = min(step, max_mid)
                min_mid = st.slider(
                    "Minimum midpoint total",
                    0,
                    max_mid,
                    0,
                    step=step,
                    format="$%d",
                    help="Filter lobbyists by midpoint totals (uses low/high averages).",
                )
            else:
                st.caption("No compensation totals available for threshold filtering.")
        with threshold_col2:
            share_opts = {"Any": 0.0, ">= 50% TFL": 0.5, ">= 75% TFL": 0.75}
            share_choice = st.selectbox(
                "Taxpayer-funded share filter",
                list(share_opts.keys()),
                index=0,
                help="Limit lobbyists by share of taxpayer-funded midpoint totals.",
            )
            share_threshold = share_opts.get(share_choice, 0.0)

        if min_mid > 0:
            view = view[view["Total_Mid"] >= min_mid].copy()
        if share_threshold > 0:
            view = view[view["TFL_Share"] >= share_threshold].copy()

        view_disp = view.copy()
        for c in ["Low_TFL", "High_TFL", "Low_Private", "High_Private"]:
            if c in view_disp.columns:
                view_disp[c] = view_disp[c].astype(float).apply(lambda x: fmt_usd(x))
        if "Total_Mid" in view_disp.columns:
            view_disp["Total_Mid"] = view_disp["Total_Mid"].astype(float).apply(lambda x: fmt_usd(x))
        if "TFL_Share" in view_disp.columns:
            view_disp["TFL_Share"] = (
                (view_disp["TFL_Share"].fillna(0) * 100).round(0).astype("Int64").astype(str) + "%"
            )

        rename_cols = {
            "LobbyShort": "Last name + first initial",
            "Has_TFL": "Has Taxpayer Funded",
            "Only_TFL": "Only Taxpayer Funded",
            "Clients_TFL": "Taxpayer Funded Clients",
            "Low_TFL": "Taxpayer Funded Low",
            "High_TFL": "Taxpayer Funded High",
            "Total_Mid": "Midpoint Total",
            "TFL_Share": "Taxpayer Funded Share",
        }
        view_disp = view_disp.rename(columns=rename_cols)

        cols = [
            "LobbyShort",
            "Has_TFL", "Has_Private", "Only_TFL", "Only_Private", "Mixed",
            "Total_Mid", "TFL_Share",
            "Clients_TFL", "Low_TFL", "High_TFL",
            "Clients_Private", "Low_Private", "High_Private",
        ]
        cols = [rename_cols.get(c, c) for c in cols]
        cols = [c for c in cols if c in view_disp.columns]

        sort_cols = [c for c in ["Has Taxpayer Funded", "Mixed", "Last name + first initial"] if c in view_disp.columns]
        if sort_cols:
            view_disp = view_disp.sort_values(sort_cols, ascending=[False, False, True][:len(sort_cols)])
        st.dataframe(
            view_disp[cols],
            width="stretch",
            height=560,
            hide_index=True,
        )
        export_context = []
        if flt.strip():
            export_context.append(f"Name filter: {_shorten_text(flt, 24)}")
        if only_tfl:
            export_context.append("Only taxpayer funded")
        if only_private:
            export_context.append("Only private")
        if mixed_only:
            export_context.append("Mixed only")
        if min_mid > 0:
            export_context.append(f"Min midpoint: {fmt_usd(min_mid)}")
        if share_threshold > 0:
            export_context.append(f"TFL share: {share_choice}")
        _ = export_dataframe(
            view_disp[cols],
            "all_lobbyists_overview.csv",
            label="Download overview CSV",
            context=export_context,
        )

# -----------------------------
# Per-lobbyist tabs: only compute when lobbyist is selected AND session != All
# -----------------------------
def _no_lobbyist_msg():
    st.info("Type a lobbyist name at the top to view details. Use Clear filters to reset or switch to All Lobbyists for a full overview.")

def _need_specific_session_msg():
    st.info("Select a specific session (e.g., 89th) to view lobbyist details. Use All Sessions for high-level totals only.")

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
        selected_filer_ids = set()
        if st.session_state.lobby_filerid is not None:
            try:
                selected_filer_ids = {int(st.session_state.lobby_filerid)}
            except Exception:
                selected_filer_ids = set()
        lobbyist_label = lobbyshort
        selected_names = []
        candidate_map = st.session_state.lobby_candidate_map or {}
        merge_keys = st.session_state.lobby_merge_keys or []
        if st.session_state.lobby_filerid and not lobbyist_index.empty:
            filer_series = pd.to_numeric(lobbyist_index.get("FilerID", pd.Series(dtype=float)), errors="coerce")
            match_row = lobbyist_index[
                (lobbyist_index["LobbyShort"].astype(str).str.strip() == lobbyshort) &
                (filer_series == int(st.session_state.lobby_filerid))
            ]
            if not match_row.empty:
                lobbyist_label = match_row["Lobby Name"].iloc[0]
                selected_names = match_row["Lobby Name"].dropna().astype(str).unique().tolist()

        if merge_keys:
            for key in merge_keys:
                cand = candidate_map.get(key, {})
                name = cand.get("name", "")
                if name and name not in selected_names:
                    selected_names.append(name)
                fid = cand.get("filerid", None)
                if fid is not None:
                    try:
                        selected_filer_ids.add(int(fid))
                    except Exception:
                        pass

        # Wit_All filtered
        lobbyshort_norm = norm_name(lobbyshort)
        wit_all = ensure_cols(
            Wit_All,
            {"Session": "", "Bill": "", "LobbyShort": "", "IsFor": 0, "IsAgainst": 0, "IsOn": 0},
        )
        if "LobbyShortNorm" not in wit_all.columns:
            wit_all = wit_all.copy()
            wit_all["LobbyShortNorm"] = norm_name_series(wit_all["LobbyShort"])
        session_col = wit_all["Session"].astype(str).str.strip()
        base_wit = wit_all[session_col == session].copy()
        witness_match_note = ""
        if selected_names:
            name_variants = set()
            name_pairs = []
            for name in selected_names:
                if not name:
                    continue
                name_variants |= norm_person_variants_with_nicknames(name)
                info = parse_person_name(name)
                first_norm = info.get("first_norm", "")
                last_norm = info.get("last_norm", "")
                first_initial = info.get("first_initial", "")
                if first_norm and last_norm:
                    name_pairs.append((first_norm, last_norm, first_initial))

            name_mask = pd.Series(False, index=base_wit.index)
            if name_variants:
                name_norm = base_wit.get("NameNorm")
                if not isinstance(name_norm, pd.Series):
                    name_norm = base_wit.get("name", pd.Series([""] * len(base_wit))).fillna("").astype(str).map(norm_name)
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
                wit = base_wit.iloc[0:0].copy()
                witness_match_note = "No witness-list rows matched the selected name. Clear the specific match to see all rows for that last name + first initial."
        else:
            if "LobbyShortNorm" in base_wit.columns:
                wit = base_wit[base_wit["LobbyShortNorm"] == lobbyshort_norm].copy()
                if not wit.empty:
                    wit["LobbyShort"] = lobbyshort
            else:
                wit = base_wit[
                    base_wit["LobbyShort"].astype(str).str.strip() == lobbyshort
                ].copy()

        bills = build_bills_with_status(wit, Bill_Status_All, Fiscal_Impact, session)
        mentions = build_policy_mentions(bills, Bill_Sub_All, session)

        # Lobbyist-reported subject matters (Lobby_Sub_All)
        lobby_sub_counts, subject_non_empty = build_lobby_subject_counts(
            Lobby_Sub_All,
            session,
            lobbyshort,
            lobbyshort_norm,
            tuple(sorted(selected_filer_ids)) if selected_filer_ids else tuple(),
        )

        # Lobbyist clients + totals (use precomputed Low_num/High_num)
        tfl_session = str(tfl_session_val) if tfl_session_val is not None else session
        lt = Lobby_TFL_Client_All[
            (Lobby_TFL_Client_All["Session"].astype(str).str.strip() == tfl_session) &
            (Lobby_TFL_Client_All["LobbyShort"].astype(str).str.strip() == lobbyshort)
        ].copy()
        if selected_filer_ids and "FilerID" in lt.columns:
            fid = pd.to_numeric(lt["FilerID"], errors="coerce").fillna(-1).astype(int)
            lt = lt[fid.isin(selected_filer_ids)].copy()
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

        @st.cache_data(show_spinner=False, ttl=300, max_entries=4)
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
            filer_ids=tuple(sorted(selected_filer_ids)) if selected_filer_ids else None,
        )

        disclosures = build_disclosures(
            LaCvr, LaDock, LaI4E, LaSub,
            lobbyshort=lobbyshort,
            session=session,
            name_to_short=name_to_short,
            lobbyist_norms_tuple=typed_norms_tuple,
            filerid_to_short=data.get("filerid_to_short", {}),
            filer_ids=tuple(sorted(selected_filer_ids)) if selected_filer_ids else None,
        )

        # ---- Overview tab
        with tab_overview:
            st.markdown('<div class="section-title">Overview</div>', unsafe_allow_html=True)
            st.markdown(
                """
<div class="callout fade-up">
  <div class="callout-title">What this means</div>
  <div class="callout-body">Client totals are reported ranges (low-high). Funding mix uses midpoints to show relative share, not exact spend.</div>
</div>
""",
                unsafe_allow_html=True,
            )
            _ = require_columns(
                Lobby_TFL_Client_All,
                ["Client", "IsTFL"],
                "Overview",
                "Texas Ethics Commission lobby filings are required for compensation and client totals.",
            )
            passed = int((bills.get("Status", pd.Series(dtype=object)) == "Passed").sum()) if not bills.empty else 0
            failed = int((bills.get("Status", pd.Series(dtype=object)) == "Failed").sum()) if not bills.empty else 0
            total_clients = len(set(tfl_clients + private_clients))
            total_low = tfl_low + pri_low
            total_high = tfl_high + pri_high
            tfl_mid = (tfl_low + tfl_high) / 2
            pri_mid = (pri_low + pri_high) / 2
            total_mid = tfl_mid + pri_mid
            tfl_share_pct = (tfl_mid / total_mid * 100) if total_mid else 0.0
            top_clients = build_top_clients(lt, top_n=10)
            top_client_label = ""
            top_client_range = ""
            if not top_clients.empty:
                top_row = top_clients.iloc[0]
                top_client_label = str(top_row.get("Client", "")).strip()
                top_client_range = f"{fmt_usd(float(top_row.get('Low', 0.0)))} - {fmt_usd(float(top_row.get('High', 0.0)))}"
            top_subject = ""
            top_subject_pct = None
            if not mentions.empty:
                top_subject = str(mentions.iloc[0].get("Subject", "")).strip()
                try:
                    top_subject_pct = float(mentions.iloc[0].get("Share", 0.0)) * 100
                except Exception:
                    top_subject_pct = None

            insight_items = []
            if total_clients:
                insight_items.append(
                    f"{total_clients} unique clients this session: {len(tfl_clients)} taxpayer funded and {len(private_clients)} private."
                )
            if total_mid > 0:
                insight_items.append(
                    f"Reported compensation ranges total {fmt_usd(total_low)} to {fmt_usd(total_high)}; taxpayer funded share is about {tfl_share_pct:.0f}%."
                )
            if top_client_label:
                insight_items.append(f"Largest client by midpoint: {top_client_label} ({top_client_range}).")
            if top_subject:
                if top_subject_pct is not None:
                    insight_items.append(f"Top policy area: {top_subject} ({top_subject_pct:.1f}% of witness-list bills).")
                else:
                    insight_items.append(f"Top policy area: {top_subject}.")
            if bills.empty:
                insight_items.append("No witness-list bills recorded for this session.")

            insight_html = "".join([f"<li>{html.escape(item)}</li>" for item in insight_items]) or "<li>No summary available.</li>"
            focus_title = "Top Policy Area" if top_subject else "Top Client"
            focus_value = _shorten_text(top_subject, 28) if top_subject else (_shorten_text(top_client_label, 28) if top_client_label else "--")
            focus_sub = f"{top_subject_pct:.1f}% of bills" if top_subject and top_subject_pct is not None else (top_client_range if top_client_label else "")

            st.markdown(
                f"""
<div class="insight-panel fade-up">
  <div class="insight-card">
    <div class="insight-kicker">Insight Briefing</div>
    <div class="insight-title">Session highlights for this lobbyist</div>
    <ul class="insight-list">{insight_html}</ul>
  </div>
  <div class="insight-card">
    <div class="insight-kicker">At a glance</div>
    <div class="mini-kpi-grid">
      <div class="mini-kpi">
        <div class="label">Clients</div>
        <div class="value">{total_clients:,}</div>
        <div class="sub">TFL {len(tfl_clients)} / Private {len(private_clients)}</div>
      </div>
      <div class="mini-kpi">
        <div class="label">Total Range</div>
        <div class="value">{fmt_usd(total_low)} - {fmt_usd(total_high)}</div>
        <div class="sub">Midpoint share {tfl_share_pct:.0f}% TFL</div>
      </div>
      <div class="mini-kpi">
        <div class="label">Bills</div>
        <div class="value">{len(bills):,}</div>
        <div class="sub">Passed {passed:,} / Failed {failed:,}</div>
      </div>
      <div class="mini-kpi">
        <div class="label">{focus_title}</div>
        <div class="value">{html.escape(focus_value) if focus_value else "--"}</div>
        <div class="sub">{html.escape(focus_sub) if focus_sub else ""}</div>
      </div>
    </div>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )
            o1, o2, o3, o4 = st.columns(4)
            with o1:
                kpi_card(
                    "Session",
                    session,
                    f"Scope: {st.session_state.scope}",
                    help_text="Session used for detail tables; scope shows whether totals are this session or all sessions.",
                )
            with o2:
                kpi_card(
                    "Lobbyist",
                    lobbyist_label,
                    st.session_state.search_query.strip() or "--",
                    help_text="Resolved lobbyist selection; subtitle shows the search query.",
                )
            with o3:
                kpi_card(
                    "Taxpayer Funded Totals",
                    f"{fmt_usd(tfl_low)} - {fmt_usd(tfl_high)}",
                    help_text="Sum of reported low/high totals for taxpayer-funded clients tied to this lobbyist.",
                )
            with o4:
                kpi_card(
                    "Private Totals",
                    f"{fmt_usd(pri_low)} - {fmt_usd(pri_high)}",
                    help_text="Sum of reported low/high totals for private clients tied to this lobbyist.",
                )

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

            s1, s2, s3, s4 = st.columns(4)
            with s1:
                kpi_card(
                    "Taxpayer Funded?",
                    "Yes" if has_tfl else "No",
                    help_text="Whether this lobbyist has any taxpayer-funded clients in the selected scope.",
                )
            with s2:
                kpi_card(
                    "Private Funded?",
                    "Yes" if has_private else "No",
                    help_text="Whether this lobbyist has any private clients in the selected scope.",
                )
            with s3:
                kpi_card(
                    "Total Bills (Witness Lists)",
                    f"{len(bills):,}",
                    help_text="Witness list rows tied to this lobbyist in the selected session.",
                )
            with s4:
                kpi_card(
                    "Passed / Failed",
                    f"{passed:,} / {failed:,}",
                    help_text="Bill outcomes among witness list rows in this view.",
                )

            st.markdown('<div class="section-sub">Activity & Filings tempo</div>', unsafe_allow_html=True)
            act_rows = len(activities) if isinstance(activities, pd.DataFrame) else 0
            disc_rows = len(disclosures) if isinstance(disclosures, pd.DataFrame) else 0
            activity_timeline = build_timeline_counts(activities, "Date") if isinstance(activities, pd.DataFrame) else pd.DataFrame()
            disclosure_timeline = build_timeline_counts(disclosures, "Date") if isinstance(disclosures, pd.DataFrame) else pd.DataFrame()
            if not activity_timeline.empty or not disclosure_timeline.empty:
                act_merge = activity_timeline.rename(columns={"Count": "Activities"})[["Period", "Label", "Activities"]] if not activity_timeline.empty else pd.DataFrame(columns=["Period", "Label", "Activities"])
                disc_merge = disclosure_timeline.rename(columns={"Count": "Disclosures"})[["Period", "Label", "Disclosures"]] if not disclosure_timeline.empty else pd.DataFrame(columns=["Period", "Label", "Disclosures"])
                tempo = act_merge.merge(disc_merge, on=["Period", "Label"], how="outer").fillna(0)
                tempo = tempo.sort_values("Period")
                tempo_long = tempo.melt(id_vars=["Period", "Label"], value_vars=["Activities", "Disclosures"], var_name="Type", value_name="Count")
                tempo_long["Count"] = pd.to_numeric(tempo_long["Count"], errors="coerce").fillna(0)
                fig_tempo = px.line(
                    tempo_long,
                    x="Period",
                    y="Count",
                    color="Type",
                    markers=True,
                    color_discrete_map={"Activities": "#00e0b8", "Disclosures": "#8cc9ff"},
                )
                fig_tempo.update_traces(
                    mode="lines+markers",
                    line=dict(width=3),
                    marker=dict(size=6),
                    hovertemplate="%{x|%b %Y}: %{y} %{fullData.name}<extra></extra>",
                )
                _apply_plotly_layout(fig_tempo, showlegend=True, legend_title="", margin_top=8)
                fig_tempo.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", title_text="")
                fig_tempo.update_xaxes(title_text="")
                st.plotly_chart(fig_tempo, width="stretch", config=PLOTLY_CONFIG)
                st.caption(f"Activities: {act_rows:,} rows | Disclosures: {disc_rows:,} rows")
            else:
                st.info("No activities or disclosures recorded for this lobbyist/session.")

            st.markdown('<div class="section-sub">Compensation Trend by Session (Midpoint)</div>', unsafe_allow_html=True)
            trend_df = build_lobbyist_trend(
                Lobby_TFL_Client_All,
                lobbyshort,
                tuple(sorted(selected_filer_ids)) if selected_filer_ids else None,
            )
            if not trend_df.empty:
                session_order = sorted(trend_df["SessionBase"].dropna().unique().tolist())
                session_labels = [_session_base_label(s) for s in session_order]
                fig_trend = px.line(
                    trend_df,
                    x="SessionLabel",
                    y="Mid",
                    color="Funding",
                    markers=True,
                    category_orders={"SessionLabel": session_labels},
                    color_discrete_map=FUNDING_COLOR_MAP,
                )
                fig_trend.update_traces(
                    mode="lines+markers",
                    line=dict(width=3),
                    marker=dict(size=6),
                    hovertemplate="%{x} - %{fullData.name}: $%{y:,.0f}<extra></extra>",
                )
                _apply_plotly_layout(fig_trend, showlegend=True, legend_title="", margin_top=12)
                fig_trend.update_layout(hovermode="x unified")
                fig_trend.update_yaxes(
                    tickprefix="$",
                    tickformat="~s",
                    showgrid=True,
                    gridcolor="rgba(255,255,255,0.08)",
                )
                fig_trend.update_xaxes(title_text="")
                st.plotly_chart(fig_trend, width="stretch", config=PLOTLY_CONFIG)
                st.markdown(
                    '<div class="section-caption">Trend shows midpoint totals for taxpayer funded vs private clients across sessions.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("No multi-session trend available for this lobbyist.")

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
                st.plotly_chart(fig_lobby_mix, width="stretch", config=PLOTLY_CONFIG)
                st.markdown('<div class="section-caption">Funding mix uses midpoint values to highlight relative scale.</div>', unsafe_allow_html=True)
            else:
                st.info("No totals available for funding mix. Try selecting a different session or clearing the lobbyist filter.")

            st.markdown('<div class="section-sub">Top Clients by Reported Compensation (Midpoint)</div>', unsafe_allow_html=True)
            if not top_clients.empty:
                top_clients = top_clients.sort_values("Mid", ascending=True)
                fig_clients = px.bar(
                    top_clients,
                    x="Mid",
                    y="Client",
                    orientation="h",
                    color="Funding",
                    color_discrete_map=FUNDING_COLOR_MAP,
                    text="Mid",
                )
                fig_clients.update_traces(
                    texttemplate="$%{text:,.0f}",
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="%{y}<br>%{fullData.name}: $%{x:,.0f}<extra></extra>",
                )
                _apply_plotly_layout(fig_clients, showlegend=True, legend_title="", margin_top=12)
                fig_clients.update_layout(margin=dict(l=8, r=48, t=12, b=8))
                fig_clients.update_xaxes(
                    tickprefix="$",
                    tickformat="~s",
                    showgrid=True,
                    gridcolor="rgba(255,255,255,0.08)",
                    title_text="Midpoint total",
                )
                fig_clients.update_yaxes(title_text="")
                st.plotly_chart(fig_clients, width="stretch", config=PLOTLY_CONFIG)
            else:
                st.info("No client totals available to rank for this session.")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            cA, cB = st.columns(2)
            with cA:
                st.subheader("Taxpayer Funded Clients")
                st.markdown(render_pill_list(tfl_clients, limit=14), unsafe_allow_html=True)
            with cB:
                st.subheader("Private Clients")
                st.markdown(render_pill_list(private_clients, limit=14), unsafe_allow_html=True)

        # ---- Bills tab
        with tab_bills:
            st.markdown('<div class="section-title">Bills with Witness-List Activity</div>', unsafe_allow_html=True)
            st.markdown(
                """
<div class="callout fade-up">
  <div class="callout-title">What this means</div>
  <div class="callout-body">Witness-list rows indicate where a lobbyist filed testimony or positions. Use status/position filters to focus on the most relevant activity.</div>
</div>
""",
                unsafe_allow_html=True,
            )
            if witness_match_note:
                st.caption(witness_match_note)
            if not require_columns(
                bills,
                ["Bill", "Position"],
                "Bills view",
                "Texas Legislature Online witness lists and bill status data are required for bill-level activity.",
            ):
                st.info("Bills view needs Texas Legislature Online witness-list data. Check the Data health panel.")
            elif bills.empty:
                st.info("No witness-list rows found for this lobbyist/session. Try another session or clear the specific match.")
            else:
                st.session_state.bill_search = st.text_input(
                    "Search bills (Bill / Author / Caption)",
                    value=st.session_state.bill_search,
                    placeholder="e.g., HB 4 or Bettencourt or housing",
                    help="Filter bills by bill number, author, or caption text.",
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
                    status_opts = _clean_options(
                        filtered.get("Status", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                    )
                    status_opts = sorted(status_opts)
                    status_sel = st.multiselect(
                        "Filter by status",
                        status_opts,
                        default=status_opts,
                        help="Limit results to selected bill statuses.",
                    )
                with f2:
                    pos_opts = _clean_options(
                        filtered.get("Position", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()
                    )
                    pos_opts = sorted(pos_opts)
                    pos_sel = st.multiselect(
                        "Filter by position",
                        pos_opts,
                        default=pos_opts,
                        help="Limit results to selected witness positions.",
                    )

                if status_sel:
                    filtered = filtered[filtered["Status"].astype(str).isin(status_sel)].copy()
                if pos_sel:
                    filtered = filtered[filtered["Position"].astype(str).isin(pos_sel)].copy()

                bsum1, bsum2 = st.columns(2)
                with bsum1:
                    if "Status" in filtered.columns:
                        status_counts = (
                            filtered["Status"]
                            .fillna("Unknown")
                            .astype(str)
                            .str.strip()
                            .replace("", "Unknown")
                            .value_counts()
                            .reset_index()
                        )
                        status_counts.columns = ["Status", "Count"]
                        fig_status = px.bar(
                            status_counts.sort_values("Count"),
                            x="Count",
                            y="Status",
                            orientation="h",
                            text="Count",
                        )
                        fig_status.update_traces(
                            textposition="outside",
                            marker_color="#8cc9ff",
                            cliponaxis=False,
                            hovertemplate="%{y}: %{x}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_status, showlegend=False, height=220, margin_top=8)
                        fig_status.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                        fig_status.update_xaxes(showgrid=False, title_text="")
                        fig_status.update_yaxes(title_text="")
                        st.plotly_chart(fig_status, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("Status summary unavailable.")
                with bsum2:
                    if "Position" in filtered.columns:
                        pos_counts = (
                            filtered["Position"]
                            .fillna("Unknown")
                            .astype(str)
                            .str.strip()
                            .replace("", "Unknown")
                            .value_counts()
                            .reset_index()
                        )
                        pos_counts.columns = ["Position", "Count"]
                        fig_pos = px.bar(
                            pos_counts.sort_values("Count"),
                            x="Count",
                            y="Position",
                            orientation="h",
                            text="Count",
                        )
                        fig_pos.update_traces(
                            textposition="outside",
                            marker_color="#1e90ff",
                            cliponaxis=False,
                            hovertemplate="%{y}: %{x}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_pos, showlegend=False, height=220, margin_top=8)
                        fig_pos.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                        fig_pos.update_xaxes(showgrid=False, title_text="")
                        fig_pos.update_yaxes(title_text="")
                        st.plotly_chart(fig_pos, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("Position summary unavailable.")

                for col in ["Fiscal Impact H", "Fiscal Impact S"]:
                    if col in filtered.columns:
                        filtered[col] = pd.to_numeric(filtered[col], errors="coerce").fillna(0)

                show_cols = ["Bill", "Author", "Caption", "Position", "Fiscal Impact H", "Fiscal Impact S", "Status"]
                show_cols = [c for c in show_cols if c in filtered.columns]

                st.caption(f"{len(filtered):,} bills")
                st.dataframe(filtered[show_cols].sort_values(["Bill"]), width="stretch", height=520, hide_index=True)
                export_context = []
                if st.session_state.bill_search.strip():
                    export_context.append(f"Bill search: {_shorten_text(st.session_state.bill_search, 28)}")
                if status_sel and len(status_sel) != len(status_opts):
                    status_label = ", ".join(status_sel[:3])
                    if len(status_sel) > 3:
                        status_label += "..."
                    export_context.append(f"Status: {status_label}")
                if pos_sel and len(pos_sel) != len(pos_opts):
                    pos_label = ", ".join(pos_sel[:3])
                    if len(pos_sel) > 3:
                        pos_label += "..."
                    export_context.append(f"Position: {pos_label}")
                _ = export_dataframe(filtered[show_cols], "bills.csv", context=export_context)

        # ---- Policy tab
        with tab_policy:
            st.markdown('<div class="section-title">Policy Areas</div>', unsafe_allow_html=True)
            st.markdown(
                """
<div class="callout fade-up">
  <div class="callout-title">What this means</div>
  <div class="callout-body">Policy areas are derived from subjects tied to bills where the lobbyist appeared on a witness list. Counts reflect unique bills, not dollars.</div>
</div>
""",
                unsafe_allow_html=True,
            )
            if not require_columns(
                Bill_Sub_All,
                ["Bill", "Subject"],
                "Policy areas",
                "Texas Legislature Online bill subject data is required for policy analysis.",
            ):
                st.info("Policy area view needs Texas Legislature Online bill subject data with Bill and Subject columns.")
            elif mentions.empty:
                st.info("No subjects found (Texas Legislature Online bill subject data returned 0 rows). Try another session or clear the lobbyist filter.")
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
                    st.plotly_chart(fig_share, width="stretch", config=PLOTLY_CONFIG)
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
                    st.plotly_chart(fig_tree, width="stretch", config=PLOTLY_CONFIG)

                m2 = mentions.copy()
                m2["Share"] = (m2["Share"] * 100).round(0).astype("Int64").astype(str) + "%"
                m2 = m2.rename(columns={"Subject": "Policy Area"})
                st.dataframe(m2[["Policy Area", "Mentions", "Share"]], width="stretch", height=520, hide_index=True)
                _ = export_dataframe(m2, "policy_areas.csv")

            st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
            st.subheader("Reported Subject Matters (Texas Ethics Commission filings)")
            if lobby_sub_counts.empty:
                st.info("No Texas Ethics Commission subject-matter rows found for this lobbyist/session. Try a different session or verify the Texas Ethics Commission subject-matter data in Data health.")
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
                        col.plotly_chart(fig_topic, width="stretch", config=PLOTLY_CONFIG)

                st.dataframe(
                    lobby_sub_counts.rename(columns={"Topic": "Subject Matter"}),
                    width="stretch",
                    height=420,
                    hide_index=True,
                )
                _ = export_dataframe(lobby_sub_counts, "reported_subject_matters.csv")

        # ---- Staff tab
        with tab_staff:
            st.markdown('<div class="section-title">Legislative Staffer History</div>', unsafe_allow_html=True)
            st.markdown(
                """
<div class="callout fade-up">
  <div class="callout-title">What this means</div>
  <div class="callout-body">Staff history shows overlap between lobbyist names and legislative staff records. Use it to identify staff-to-lobbyist transitions.</div>
</div>
""",
                unsafe_allow_html=True,
            )
            if not require_columns(
                Staff_All,
                ["Legislator", "Staffer"],
                "Staff history",
                "House Research Organization staff lists are required for staff history.",
            ):
                st.info("Staff view needs House Research Organization staff lists with Legislator and Staffer columns.")
            elif staff_pick.empty:
                st.info("No staff-history rows matched for this lobbyist. Try a broader lobbyist match or check House Research Organization staff data.")
            else:
                st.caption("Showing staff history across all sessions.")
                cols = ["Session", "Legislator", "Title", "Staffer"]
                staff_view = staff_pick[cols].drop_duplicates().sort_values(["Session", "Legislator", "Title"])
                st.dataframe(staff_view, width="stretch", height=380, hide_index=True)
                _ = export_dataframe(staff_view, "staff_history.csv")

            if staff_pick_session.empty:
                st.caption("Session-specific staff metrics are not shown because there are no matches for the selected session.")
            elif not staff_stats.empty:
                st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
                st.caption("Computed from authored bills intersected with this lobbyist's witness activity.")
                s2 = staff_stats.copy()
                for col in ["% Against that Failed", "% For that Passed"]:
                    s2[col] = pd.to_numeric(s2[col], errors="coerce")
                    s2[col] = (s2[col] * 100).round(0)
                st.dataframe(s2, width="stretch", height=320, hide_index=True)
                _ = export_dataframe(s2, "staff_stats.csv")

        # ---- Activities tab
        with tab_activities:
            st.markdown('<div class="section-title">Lobbying Expenditures / Activity</div>', unsafe_allow_html=True)
            st.markdown(
                """
<div class="callout fade-up">
  <div class="callout-title">What this means</div>
  <div class="callout-body">Activity rows summarize reportable expenditures (food, travel, gifts, events). Use type and date filters to focus on a specific time window.</div>
</div>
""",
                unsafe_allow_html=True,
            )
            if not require_columns(
                activities,
                ["Date", "Type", "Description"],
                "Activities view",
                "Texas Ethics Commission activity reports (Food, Entertainment, Travel, Gifts, Events, Awards) are required.",
            ):
                st.info("Activities view needs the Texas Ethics Commission activity reports listed in Data health.")
            elif activities.empty:
                st.info("No activity rows found for this lobbyist/session (after matching). Try a different session or clear the specific match.")
                st.caption("If Excel still shows rows, your workbook may key activities on a different ID (e.g., filerID).")
            else:
                filt = activities.copy()
                t_opts = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
                t_opts = sorted(t_opts)
                sel_types = st.multiselect(
                    "Filter by activity type",
                    t_opts,
                    default=t_opts,
                    help="Limit results to selected activity categories.",
                )
                if sel_types:
                    filt = filt[filt["Type"].isin(sel_types)].copy()

                st.session_state.activity_search = st.text_input(
                    "Search activities (filer, member, description)",
                    value=st.session_state.activity_search,
                    help="Search activity rows by filer, member, or description.",
                )
                if st.session_state.activity_search.strip():
                    q = st.session_state.activity_search.strip()
                    filt = filt[
                        filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Member"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Description"].astype(str).str.contains(q, case=False, na=False)
                    ].copy()

                date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                d_from = None
                d_to = None
                if date_parsed.notna().any():
                    min_d = date_parsed.min().date()
                    max_d = date_parsed.max().date()
                    d_from, d_to = st.date_input(
                        "Date range",
                        (min_d, max_d),
                        help="Restrict results to activities within this date range.",
                    )
                    if d_from and d_to:
                        mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                        filt = filt[mask].copy()

                a1, a2 = st.columns(2)
                with a1:
                    type_counts = (
                        filt["Type"]
                        .fillna("Unknown")
                        .astype(str)
                        .str.strip()
                        .replace("", "Unknown")
                        .value_counts()
                        .reset_index()
                    )
                    type_counts.columns = ["Type", "Count"]
                    if not type_counts.empty:
                        fig_type = px.bar(
                            type_counts.sort_values("Count"),
                            x="Count",
                            y="Type",
                            orientation="h",
                            text="Count",
                        )
                        fig_type.update_traces(
                            textposition="outside",
                            marker_color="#00e0b8",
                            cliponaxis=False,
                            hovertemplate="%{y}: %{x}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_type, showlegend=False, height=220, margin_top=8)
                        fig_type.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                        fig_type.update_xaxes(showgrid=False, title_text="")
                        fig_type.update_yaxes(title_text="")
                        st.plotly_chart(fig_type, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("No activity types to summarize.")
                with a2:
                    timeline = build_timeline_counts(filt, "Date")
                    if not timeline.empty:
                        fig_time = px.line(
                            timeline,
                            x="Period",
                            y="Count",
                            markers=True,
                        )
                        fig_time.update_traces(
                            line=dict(width=3, color="#1e90ff"),
                            marker=dict(size=6),
                            hovertemplate="%{x|%b %Y}: %{y}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_time, showlegend=False, height=220, margin_top=8)
                        fig_time.update_layout(margin=dict(l=8, r=16, t=8, b=8))
                        fig_time.update_xaxes(title_text="")
                        fig_time.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", title_text="")
                        st.plotly_chart(fig_time, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("No activity timeline available.")

                st.caption(f"{len(filt):,} rows")
                st.dataframe(filt, width="stretch", height=560, hide_index=True)
                export_context = []
                if sel_types and len(sel_types) != len(t_opts):
                    type_label = ", ".join(sel_types[:3])
                    if len(sel_types) > 3:
                        type_label += "..."
                    export_context.append(f"Types: {type_label}")
                if st.session_state.activity_search.strip():
                    export_context.append(f"Search: {_shorten_text(st.session_state.activity_search, 28)}")
                if d_from and d_to:
                    export_context.append(f"Dates: {d_from} to {d_to}")
                _ = export_dataframe(filt, "activities.csv", context=export_context)

        # ---- Disclosures tab
        with tab_disclosures:
            st.markdown('<div class="section-title">Disclosures & Subject Matter Filings</div>', unsafe_allow_html=True)
            st.markdown(
                """
<div class="callout fade-up">
  <div class="callout-title">What this means</div>
  <div class="callout-body">Disclosures capture coverage, dockets, and subject-matter filings tied to lobbyist activity. Use date filters to align with the reporting period.</div>
</div>
""",
                unsafe_allow_html=True,
            )
            if not require_columns(
                disclosures,
                ["Date", "Type", "Description"],
                "Disclosures view",
                "Texas Ethics Commission disclosure filings (Coverage, Docket, On Behalf, Subject Matter) are required.",
            ):
                st.info("Disclosures view needs Texas Ethics Commission disclosure filings (Coverage, Docket, On Behalf, Subject Matter) in the workbook.")
            elif disclosures.empty:
                st.info("No disclosure rows found for this lobbyist/session. Try another session or clear the specific match.")
            else:
                filt = disclosures.copy()
                d_types = _clean_options(filt["Type"].dropna().astype(str).unique().tolist())
                d_types = sorted(d_types)
                sel_types = st.multiselect(
                    "Filter by disclosure type",
                    d_types,
                    default=d_types,
                    help="Limit results to selected disclosure categories.",
                )
                if sel_types:
                    filt = filt[filt["Type"].isin(sel_types)].copy()

                st.session_state.disclosure_search = st.text_input(
                    "Search disclosures (filer, description, entity)",
                    value=st.session_state.disclosure_search,
                    help="Search disclosure rows by filer, description, or entity.",
                )
                if st.session_state.disclosure_search.strip():
                    q = st.session_state.disclosure_search.strip()
                    filt = filt[
                        filt["Filer"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Description"].astype(str).str.contains(q, case=False, na=False) |
                        filt["Entity"].astype(str).str.contains(q, case=False, na=False)
                    ].copy()

                date_parsed = pd.to_datetime(filt["Date"], errors="coerce")
                d_from = None
                d_to = None
                if date_parsed.notna().any():
                    min_d = date_parsed.min().date()
                    max_d = date_parsed.max().date()
                    d_from, d_to = st.date_input(
                        "Date range",
                        (min_d, max_d),
                        key="disclosure_dates",
                        help="Restrict results to disclosures within this date range.",
                    )
                    if d_from and d_to:
                        mask = (date_parsed.dt.date >= d_from) & (date_parsed.dt.date <= d_to)
                        filt = filt[mask].copy()

                d1, d2 = st.columns(2)
                with d1:
                    type_counts = (
                        filt["Type"]
                        .fillna("Unknown")
                        .astype(str)
                        .str.strip()
                        .replace("", "Unknown")
                        .value_counts()
                        .reset_index()
                    )
                    type_counts.columns = ["Type", "Count"]
                    if not type_counts.empty:
                        fig_type = px.bar(
                            type_counts.sort_values("Count"),
                            x="Count",
                            y="Type",
                            orientation="h",
                            text="Count",
                        )
                        fig_type.update_traces(
                            textposition="outside",
                            marker_color="#1e90ff",
                            cliponaxis=False,
                            hovertemplate="%{y}: %{x}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_type, showlegend=False, height=220, margin_top=8)
                        fig_type.update_layout(margin=dict(l=8, r=28, t=8, b=8))
                        fig_type.update_xaxes(showgrid=False, title_text="")
                        fig_type.update_yaxes(title_text="")
                        st.plotly_chart(fig_type, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("No disclosure types to summarize.")
                with d2:
                    timeline = build_timeline_counts(filt, "Date")
                    if not timeline.empty:
                        fig_time = px.line(
                            timeline,
                            x="Period",
                            y="Count",
                            markers=True,
                        )
                        fig_time.update_traces(
                            line=dict(width=3, color="#00e0b8"),
                            marker=dict(size=6),
                            hovertemplate="%{x|%b %Y}: %{y}<extra></extra>",
                        )
                        _apply_plotly_layout(fig_time, showlegend=False, height=220, margin_top=8)
                        fig_time.update_layout(margin=dict(l=8, r=16, t=8, b=8))
                        fig_time.update_xaxes(title_text="")
                        fig_time.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", title_text="")
                        st.plotly_chart(fig_time, width="stretch", config=PLOTLY_CONFIG)
                    else:
                        st.info("No disclosure timeline available.")

                st.caption(f"{len(filt):,} rows")
                st.dataframe(filt, width="stretch", height=560, hide_index=True)
                export_context = []
                if sel_types and len(sel_types) != len(d_types):
                    type_label = ", ".join(sel_types[:3])
                    if len(sel_types) > 3:
                        type_label += "..."
                    export_context.append(f"Types: {type_label}")
                if st.session_state.disclosure_search.strip():
                    export_context.append(f"Search: {_shorten_text(st.session_state.disclosure_search, 28)}")
                if d_from and d_to:
                    export_context.append(f"Dates: {d_from} to {d_to}")
                _ = export_dataframe(filt, "disclosures.csv", context=export_context)

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
