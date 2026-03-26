from __future__ import annotations

import math


def _mp5_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    try:
        d_lat = math.radians(float(lat2) - float(lat1))
        d_lon = math.radians(float(lon2) - float(lon1))
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(float(lat1)))
            * math.cos(math.radians(float(lat2)))
            * (math.sin(d_lon / 2) ** 2)
        )
        return 3958.7613 * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
    except Exception:
        return float("nan")


_MP5_METHOD_WEIGHTS: dict[str, float] = {
    "spatial boundary (code)": 1.00,
    "spatial boundary (name)": 0.94,
    "spatial boundary (fuzzy)": 0.78,
}


def _mp5_method_weight(method: str) -> float:
    normalized = str(method).strip().lower()
    weight = _MP5_METHOD_WEIGHTS.get(normalized)
    if weight is not None:
        return weight
    if "name + geocode context" in normalized:
        return 0.62
    if "name anchored" in normalized:
        return 0.50
    return 0.66


_MP5_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "high": 1.00,
    "medium": 0.72,
    "low": 0.46,
    "unknown": 0.28,
}


def _mp5_confidence_weight(conf: str) -> float:
    return _MP5_CONFIDENCE_WEIGHTS.get(str(conf).strip().lower(), 0.30)


def _mp5_priority_from_score(score: float) -> str:
    value = float(score or 0.0)
    if value >= 78:
        return "Tier 1"
    if value >= 58:
        return "Tier 2"
    return "Tier 3"


def _mp5_geocode_badge(score, floor: float) -> str:
    if score is None:
        return '<span class="mp5-badge mp5-badge-mid">Coordinate mode</span>'
    value = float(score)
    if value >= floor:
        return f'<span class="mp5-badge mp5-badge-high">Geocode {value:.0f}</span>'
    if value >= 70:
        return f'<span class="mp5-badge mp5-badge-mid">Geocode {value:.0f} &#8212; below floor</span>'
    return f'<span class="mp5-badge mp5-badge-low">Geocode {value:.0f} &#8212; weak</span>'


def _build_mp5_css() -> str:
    return """
<style>
/* -- mp5 shell ------------------------------------------- */
.mp5-glass{
  border:1px solid rgba(130,219,248,.22);
  border-radius:20px;
  padding:18px 20px 14px 20px;
  background:
    radial-gradient(960px 260px at 6% 0%,rgba(0,224,184,.12),transparent 66%),
    radial-gradient(840px 280px at 94% 8%,rgba(30,144,255,.14),transparent 60%),
    linear-gradient(138deg,rgba(7,26,41,.95),rgba(7,19,32,.93));
  box-shadow:0 16px 36px rgba(0,0,0,.28);
}
.mp5-glass-inner{
  border:1px solid rgba(255,255,255,.12);
  border-radius:16px;
  padding:14px 16px;
  background:
    linear-gradient(115deg,rgba(14,45,68,.86),rgba(9,26,41,.86)),
    radial-gradient(460px 180px at 88% 8%,rgba(245,166,68,.12),transparent 70%);
}
.mp5-kicker{
  text-transform:uppercase;
  letter-spacing:.12em;
  font-size:.68rem;
  font-weight:700;
  color:rgba(203,245,255,.88);
  margin-bottom:2px;
}
.mp5-title{
  font-size:1.08rem;
  font-weight:700;
  color:rgba(247,252,255,.97);
  margin-top:2px;
}
.mp5-sub{
  color:rgba(206,229,242,.82);
  font-size:.86rem;
  margin-top:4px;
  line-height:1.45;
}
/* -- metric grid ----------------------------------------- */
.mp5-metrics{
  display:grid;
  gap:10px;
  grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  margin-top:12px;
}
.mp5-card{
  border-radius:14px;
  border:1px solid rgba(255,255,255,.12);
  padding:11px 13px 9px 13px;
  background:rgba(255,255,255,.038);
  transition:border-color .18s,box-shadow .18s;
}
.mp5-card:hover{
  border-color:rgba(130,219,248,.38);
  box-shadow:0 0 14px rgba(130,219,248,.10);
}
.mp5-card-lbl{
  text-transform:uppercase;
  letter-spacing:.09em;
  font-size:.67rem;
  font-weight:600;
  color:rgba(180,216,235,.80);
}
.mp5-card-val{
  margin-top:3px;
  font-size:1.28rem;
  font-weight:800;
  color:rgba(247,253,255,.98);
  letter-spacing:-.01em;
}
.mp5-card-sub{
  margin-top:2px;
  font-size:.76rem;
  color:rgba(195,220,236,.78);
  line-height:1.35;
}
/* -- context anchor -------------------------------------- */
.mp5-anchor{
  border:1px solid rgba(255,255,255,.13);
  border-left:3px solid rgba(0,224,184,.82);
  border-radius:12px;
  padding:10px 13px;
  background:rgba(0,224,184,.045);
  margin-top:6px;
}
.mp5-anchor-empty{
  border:1px dashed rgba(255,255,255,.16);
  border-radius:12px;
  padding:10px 13px;
  background:rgba(255,255,255,.02);
  color:rgba(180,210,230,.70);
  font-size:.84rem;
  margin-top:6px;
}
/* -- badges ---------------------------------------------- */
.mp5-badge{
  display:inline-block;
  padding:3px 10px;
  border-radius:999px;
  font-size:.72rem;
  font-weight:700;
  letter-spacing:.02em;
}
.mp5-badge-high{
  border:1px solid rgba(143,235,197,.52);
  background:rgba(73,211,155,.14);
  color:rgba(220,255,240,.96);
}
.mp5-badge-mid{
  border:1px solid rgba(251,204,122,.52);
  background:rgba(255,190,76,.13);
  color:rgba(255,240,204,.96);
}
.mp5-badge-low{
  border:1px solid rgba(247,146,149,.52);
  background:rgba(247,85,97,.13);
  color:rgba(255,220,223,.96);
}
/* -- section divider ------------------------------------- */
.mp5-divider{
  border:0;
  border-top:1px solid rgba(255,255,255,.08);
  margin:18px 0 14px 0;
}
/* -- narrative callout ----------------------------------- */
.mp5-narrative{
  border-left:3px solid rgba(100,180,255,.55);
  padding:8px 12px;
  background:rgba(100,180,255,.06);
  border-radius:0 10px 10px 0;
  font-size:.84rem;
  color:rgba(210,232,248,.90);
  line-height:1.5;
  margin:8px 0;
}
/* -- plotly chart container ------------------------------ */
.mp5-chart-wrap{
  border:1px solid rgba(255,255,255,.10);
  border-radius:14px;
  padding:8px;
  background:rgba(0,0,0,.12);
  margin-top:8px;
}

/* -- v6 ENHANCED DESIGN TOKENS --------------------------- */

/* -- animated gradient border cards ---------------------- */
.mp5-card{
  position:relative;
  overflow:hidden;
  transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease;
}
.mp5-card::after{
  content:"";
  position:absolute;
  inset:0;
  border-radius:14px;
  background:linear-gradient(135deg,rgba(0,224,184,.06),transparent 40%,rgba(30,144,255,.06));
  opacity:0;
  transition:opacity .22s ease;
  pointer-events:none;
}
.mp5-card:hover{
  transform:translateY(-2px);
  border-color:rgba(130,219,248,.42);
  box-shadow:0 8px 24px rgba(0,224,184,.08),0 0 14px rgba(130,219,248,.10);
}
.mp5-card:hover::after{ opacity:1; }

/* -- progress / health bar ------------------------------- */
.mp5-health{
  margin:12px 0 8px 0;
}
.mp5-health-label{
  display:flex;
  justify-content:space-between;
  font-size:.72rem;
  color:rgba(195,220,236,.80);
  margin-bottom:4px;
  text-transform:uppercase;
  letter-spacing:.08em;
  font-weight:600;
}
.mp5-health-track{
  height:10px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.08);
  overflow:hidden;
  position:relative;
}
.mp5-health-fill{
  height:100%;
  border-radius:999px;
  transition:width .6s ease;
  position:relative;
}
.mp5-health-fill.is-strong{
  background:linear-gradient(90deg,#10b981,#6ee7b7);
}
.mp5-health-fill.is-moderate{
  background:linear-gradient(90deg,#f59e0b,#fcd34d);
}
.mp5-health-fill.is-weak{
  background:linear-gradient(90deg,#ef4444,#fca5a5);
}

/* -- quick preset buttons -------------------------------- */
.mp5-preset-row{
  display:flex;
  flex-wrap:wrap;
  gap:6px;
  margin:8px 0 4px 0;
}
.mp5-preset-btn{
  display:inline-flex;
  align-items:center;
  gap:5px;
  padding:5px 12px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.16);
  background:rgba(255,255,255,.04);
  color:rgba(220,238,252,.92);
  font-size:.73rem;
  font-weight:600;
  cursor:pointer;
  transition:all .18s ease;
  text-decoration:none;
}
.mp5-preset-btn:hover{
  border-color:rgba(130,219,248,.5);
  background:rgba(130,219,248,.12);
  box-shadow:0 0 10px rgba(130,219,248,.12);
}
.mp5-preset-btn.is-active{
  border-color:rgba(0,224,184,.6);
  background:rgba(0,224,184,.14);
  color:#6ee7b7;
}

/* -- evidence quality meter ------------------------------ */
.mp5-meter{
  display:flex;
  align-items:center;
  gap:12px;
  padding:10px 14px;
  border-radius:14px;
  border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.03);
  margin:8px 0;
}
.mp5-meter-gauge{
  position:relative;
  width:56px;
  height:56px;
  flex:0 0 56px;
}
.mp5-meter-gauge svg{
  width:100%;
  height:100%;
  transform:rotate(-90deg);
}
.mp5-meter-gauge .track{
  fill:none;
  stroke:rgba(255,255,255,.08);
  stroke-width:5;
}
.mp5-meter-gauge .fill{
  fill:none;
  stroke-width:5;
  stroke-linecap:round;
  transition:stroke-dashoffset .8s ease;
}
.mp5-meter-body{
  flex:1;
}
.mp5-meter-title{
  font-size:.86rem;
  font-weight:700;
  color:rgba(247,252,255,.96);
}
.mp5-meter-sub{
  font-size:.76rem;
  color:rgba(195,220,236,.78);
  margin-top:2px;
  line-height:1.38;
}

/* -- status tags for case docket ------------------------- */
.mp5-status{
  display:inline-flex;
  align-items:center;
  gap:4px;
  padding:3px 10px;
  border-radius:999px;
  font-size:.68rem;
  font-weight:700;
  letter-spacing:.03em;
}
.mp5-status-new{
  border:1px solid rgba(130,219,248,.45);
  background:rgba(130,219,248,.12);
  color:rgba(180,240,255,.96);
}
.mp5-status-investigating{
  border:1px solid rgba(251,204,122,.45);
  background:rgba(255,190,76,.11);
  color:rgba(255,240,204,.96);
}
.mp5-status-resolved{
  border:1px solid rgba(143,235,197,.45);
  background:rgba(73,211,155,.12);
  color:rgba(220,255,240,.96);
}

/* -- section hero banner --------------------------------- */
.mp5-section-hero{
  position:relative;
  overflow:hidden;
  border:1px solid rgba(130,219,248,.22);
  border-radius:16px;
  padding:14px 18px 12px 18px;
  margin-bottom:12px;
  background:
    linear-gradient(135deg,rgba(0,224,184,.08),transparent 45%,rgba(30,144,255,.10)),
    linear-gradient(180deg,rgba(14,30,48,.96),rgba(9,22,36,.92));
}
.mp5-section-hero::before{
  content:"";
  position:absolute;
  top:-20px;right:-20px;
  width:160px;height:160px;
  background:radial-gradient(circle,rgba(30,144,255,.2),transparent 70%);
  pointer-events:none;
}
.mp5-section-hero > *{ position:relative; z-index:1; }
.mp5-section-num{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  width:26px;height:26px;
  border-radius:8px;
  background:rgba(0,224,184,.16);
  border:1px solid rgba(0,224,184,.35);
  color:#6ee7b7;
  font-size:.74rem;
  font-weight:800;
  margin-bottom:6px;
}

/* -- gap alert card -------------------------------------- */
.mp5-gap-alert{
  display:flex;
  align-items:flex-start;
  gap:10px;
  padding:10px 12px;
  border-radius:12px;
  border:1px solid rgba(247,146,149,.3);
  background:rgba(247,85,97,.06);
  margin-top:8px;
}
.mp5-gap-icon{
  flex:0 0 auto;
  width:28px;height:28px;
  border-radius:8px;
  background:rgba(247,85,97,.14);
  border:1px solid rgba(247,146,149,.3);
  display:flex;align-items:center;justify-content:center;
  color:#fca5a5;
  font-size:.86rem;
  font-weight:800;
}
.mp5-gap-body{
  flex:1;
}
.mp5-gap-title{
  font-size:.82rem;
  font-weight:700;
  color:rgba(255,220,223,.96);
}
.mp5-gap-sub{
  font-size:.74rem;
  color:rgba(247,186,189,.80);
  line-height:1.38;
  margin-top:2px;
}

/* -- info/action strip ----------------------------------- */
.mp5-action-strip{
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:12px;
  border:1px solid rgba(255,255,255,.10);
  background:rgba(255,255,255,.025);
  margin:8px 0;
}
.mp5-action-label{
  font-size:.72rem;
  text-transform:uppercase;
  letter-spacing:.1em;
  font-weight:600;
  color:rgba(180,216,235,.72);
}

/* -- summary snapshot card ------------------------------- */
.mp5-snapshot{
  border:1px solid rgba(130,219,248,.24);
  border-radius:16px;
  padding:14px 16px;
  background:
    linear-gradient(145deg,rgba(14,45,68,.80),rgba(9,22,36,.90)),
    radial-gradient(380px 160px at 85% 10%,rgba(0,224,184,.10),transparent 65%);
  margin:10px 0;
}
.mp5-snapshot-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin-bottom:8px;
}
.mp5-snapshot-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:8px;
}
.mp5-snapshot-item{
  padding:6px 8px;
  border-radius:10px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
}
.mp5-snapshot-item-lbl{
  font-size:.6rem;
  text-transform:uppercase;
  letter-spacing:.1em;
  font-weight:600;
  color:rgba(180,216,235,.74);
}
.mp5-snapshot-item-val{
  font-size:.94rem;
  font-weight:700;
  color:rgba(247,253,255,.96);
  margin-top:1px;
}

/* -- cross-tab navigation strips ------------------------ */
.mp5-crosslink{
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:10px;
  padding:10px 14px;
  border-radius:14px;
  border:1px solid rgba(30,144,255,.18);
  background:linear-gradient(135deg,rgba(30,144,255,.08),rgba(0,224,184,.06));
  margin:10px 0;
  backdrop-filter:blur(2px);
}
.mp5-crosslink-title{
  font-size:.7rem;
  text-transform:uppercase;
  letter-spacing:.12em;
  font-weight:700;
  color:rgba(30,144,255,.82);
  flex-shrink:0;
}
.mp5-crosslink-sep{
  width:1px;
  height:18px;
  background:rgba(255,255,255,.12);
  flex-shrink:0;
}
.mp5-crosslink-hint{
  font-size:.72rem;
  color:rgba(210,230,245,.52);
  margin-left:auto;
}
.mp5-context-strip{
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:12px;
  border:1px solid rgba(0,224,184,.18);
  background:linear-gradient(135deg,rgba(0,224,184,.06),rgba(30,144,255,.04));
  margin:4px 0 10px 0;
}
.mp5-context-badge{
  display:inline-flex;
  align-items:center;
  gap:4px;
  padding:3px 10px;
  border-radius:8px;
  font-size:.7rem;
  font-weight:600;
  background:rgba(0,224,184,.12);
  border:1px solid rgba(0,224,184,.22);
  color:rgba(210,240,230,.88);
}
.mp5-context-badge.docket{
  background:rgba(30,144,255,.12);
  border-color:rgba(30,144,255,.22);
  color:rgba(200,225,255,.88);
}
.mp5-context-badge.empty{
  background:rgba(255,255,255,.04);
  border-color:rgba(255,255,255,.10);
  color:rgba(210,230,245,.45);
}

/* -- responsive refinements ------------------------------ */
@media (max-width:768px){
  .mp5-metrics{ grid-template-columns:repeat(2,minmax(0,1fr)); }
  .mp5-preset-row{ gap:4px; }
  .mp5-preset-btn{ font-size:.66rem; padding:4px 8px; }
  .mp5-meter{ flex-direction:column; text-align:center; }
  .mp5-snapshot-grid{ grid-template-columns:1fr 1fr; }
  .mp5-crosslink{ flex-direction:column; align-items:flex-start; }
}
</style>
"""
