from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import streamlit as st
    import streamlit.components.v1 as components
except ModuleNotFoundError:  # pragma: no cover - import smoke fallback
    class _SessionStateStub(dict):
        pass

    class _ComponentStub:
        @staticmethod
        def declare_component(*args, **kwargs):
            def _component(*component_args, **component_kwargs):
                return None
            return _component

        @staticmethod
        def html(*args, **kwargs):
            return None

    class _StreamlitStub:
        session_state: dict[str, Any] = _SessionStateStub()

        def __getattr__(self, name: str):
            raise AttributeError(name)

    st = _StreamlitStub()
    components = _ComponentStub()

from tfl_app.config.paths import COMPONENTS_DIR
from tfl_app.charts.runtime import stable_json_signature
from tfl_app.map.geo_runtime import SUBDIVISION_TYPE_COLORS, _hex_to_rgba, _subdivision_color_hex
from tfl_app.map.reference_runtime import (
    ARCGIS_GEOCODER_URL,
    CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
    TEA_ARCGIS_COUNTY_LAYER_URL,
    TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL,
    TEXAS_HOUSE_DISTRICTS_LAYER_URL,
    TEXAS_SENATE_DISTRICTS_LAYER_URL,
)


_COMPONENT_ROOT = COMPONENTS_DIR
_TFL_BRIDGE_DIR = _COMPONENT_ROOT / '_atlas_bridge'
_atlas_bridge = components.declare_component('atlas_bridge', path=str(_TFL_BRIDGE_DIR))
_PERSISTENT_HTML_FRAME_DIR = _COMPONENT_ROOT / '_persistent_html_frame'
_persistent_html_frame = components.declare_component(
    'persistent_html_frame',
    path=str(_PERSISTENT_HTML_FRAME_DIR),
)


def _clone_session_cache_value(value):
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, pd.Series):
        return value.copy()
    if isinstance(value, dict):
        return {k: _clone_session_cache_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone_session_cache_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_clone_session_cache_value(v) for v in value)
    return value


def _session_cached_value(cache_key: str, signature: str, builder):
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict) and cached.get('signature') == signature and 'value' in cached:
        return _clone_session_cache_value(cached['value'])
    value = builder()
    st.session_state[cache_key] = {
        'signature': signature,
        'value': _clone_session_cache_value(value),
    }
    return _clone_session_cache_value(value)


def render_draw_area_search_map(
    height: int = 520,
    basemap: str = "gray-vector",
    map_id: str = "tfl-draw-area-map",
    markers: list[dict] | None = None,
) -> None:
    """Render an ArcGIS JS 4.30 map with drawing tools, address search,
    click-to-reverse-geocode, and an address collector panel.

    Users can:
    * Click anywhere on the map to reverse-geocode that point
    * Use the Search widget to find an address
    * Draw polygon / circle / rectangle areas; all click-points within
      the area are collected
    * Copy discovered addresses from the in-map panel

    The map posts messages (``tfl-draw-address-found``, ``tfl-draw-area-addresses``)
    via ``window.parent.postMessage`` so that the Python layer can listen
    for them (via adjacent Streamlit widgets that manually capture the data).

    Parameters
    ----------
    height : int
        Map container height in pixels.
    basemap : str
        ArcGIS basemap identifier (``"gray-vector"``, ``"streets-vector"``, ``"hybrid"``).
    map_id : str
        HTML element id for the map container (must be unique per page render).
    markers : list[dict] | None
        Optional list of ``{"lat": float, "lon": float, "label": str}`` dicts
        to render pre-existing pins on the map (e.g. docket entity addresses).
    """
    basemap_safe = json.dumps(str(basemap).strip() or "gray-vector")
    markers_json = json.dumps(markers or [], ensure_ascii=True)
    draw_map_signature = stable_json_signature(
        {
            "map_id": str(map_id).strip(),
            "markers": markers or [],
            "basemap": str(basemap).strip() or "gray-vector",
            "height": int(height),
        }
    )
    draw_map_cache_key = re.sub(r"[^0-9A-Za-z_]+", "_", str(map_id).strip()) or "tfl_draw_area_map"
    arcgis_html = _session_cached_value(
        f"_mp5_draw_map_html_{draw_map_cache_key}_v1",
        draw_map_signature,
        lambda: f"""
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css"/>
<style>
  #{map_id} {{ width:100%; height:{height}px; border-radius:14px; overflow:hidden; position:relative; }}

  /* Dark popup */
  .esri-popup__main-container {{
    background:rgba(13,23,36,0.96) !important; color:rgba(220,230,240,0.95) !important;
    border:1px solid rgba(100,140,180,0.22) !important; border-radius:10px !important;
    backdrop-filter:blur(10px) !important; box-shadow:0 8px 32px rgba(0,0,0,0.45) !important;
  }}
  .esri-popup__header-title {{ color:rgba(235,242,250,0.97) !important; font-weight:600 !important; }}
  .esri-popup__content {{ color:rgba(200,215,230,0.92) !important; }}
  .esri-popup__button {{ color:rgba(180,200,220,0.85) !important; }}
  .esri-popup__button:hover {{ color:#fff !important; background:rgba(100,180,255,0.18) !important; }}
  .esri-sketch {{ background:rgba(13,23,36,0.92) !important; border-radius:8px !important; border:1px solid rgba(100,140,180,0.22) !important; }}

  /* Coordinate bar */
  #tfl-draw-coord {{
    position:absolute; bottom:6px; left:50%; transform:translateX(-50%); z-index:90;
    background:rgba(10,20,32,0.88); border:1px solid rgba(100,140,180,0.15);
    border-radius:8px; padding:3px 10px; font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    font-size:10.5px; color:rgba(180,200,220,0.75); white-space:nowrap;
    backdrop-filter:blur(6px); pointer-events:none;
  }}

  /* Address collector panel */
  #tfl-draw-collector {{
    position:absolute; top:12px; right:12px; z-index:95;
    background:rgba(10,20,32,0.94); border:1px solid rgba(30,144,255,0.22);
    border-radius:12px; padding:10px 12px; min-width:240px; max-width:300px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11.5px;
    color:rgba(210,225,240,0.90); backdrop-filter:blur(10px);
    max-height:{height - 40}px; overflow-y:auto;
    box-shadow:0 8px 28px rgba(0,0,0,0.40);
  }}
  #tfl-draw-collector .dc-title {{
    text-transform:uppercase; letter-spacing:0.14em; font-size:8.5px;
    color:rgba(30,144,255,0.82); font-weight:700; margin-bottom:6px;
    display:flex; align-items:center; justify-content:space-between;
  }}
  #tfl-draw-collector .dc-item {{
    display:flex; align-items:flex-start; gap:6px; padding:5px 0;
    border-bottom:1px solid rgba(255,255,255,0.06);
  }}
  #tfl-draw-collector .dc-item:last-child {{ border-bottom:none; }}
  #tfl-draw-collector .dc-num {{
    flex-shrink:0; width:18px; height:18px; border-radius:50%;
    background:rgba(30,144,255,0.18); border:1px solid rgba(30,144,255,0.30);
    display:flex; align-items:center; justify-content:center;
    font-size:9px; font-weight:700; color:rgba(30,144,255,0.90);
  }}
  #tfl-draw-collector .dc-addr {{
    font-size:11px; line-height:1.35; color:rgba(210,230,245,0.85);
  }}
  #tfl-draw-collector .dc-coord {{
    font-size:9px; color:rgba(160,185,210,0.55); margin-top:1px;
  }}
  #tfl-draw-collector .dc-empty {{
    text-align:center; padding:10px 0; color:rgba(180,200,220,0.45); font-size:10.5px;
  }}
  #tfl-draw-collector .dc-actions {{
    display:flex; gap:6px; margin-top:6px;
  }}
  #tfl-draw-collector .dc-btn {{
    flex:1; padding:5px 8px; border-radius:8px; border:1px solid rgba(30,144,255,0.25);
    background:rgba(30,144,255,0.10); color:rgba(30,144,255,0.90); cursor:pointer;
    font-size:10px; font-weight:600; text-align:center; transition:all 0.2s;
  }}
  #tfl-draw-collector .dc-btn:hover {{ background:rgba(30,144,255,0.22); border-color:rgba(30,144,255,0.40); }}
  #tfl-draw-collector .dc-btn.clear {{ background:rgba(255,80,80,0.08); border-color:rgba(255,80,80,0.20); color:rgba(255,120,120,0.85); }}
  #tfl-draw-collector .dc-btn.clear:hover {{ background:rgba(255,80,80,0.18); }}
  #tfl-draw-badge {{
    position:absolute; top:12px; left:12px; z-index:95;
    background:rgba(10,20,32,0.90); border:1px solid rgba(0,224,184,0.22);
    border-radius:10px; padding:6px 12px; font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    font-size:10.5px; color:rgba(0,224,184,0.85); backdrop-filter:blur(8px);
  }}

  /* Loading overlay */
  @keyframes tfl-draw-pulse {{ 0%,100%{{transform:scale(1);opacity:0.92;}} 50%{{transform:scale(1.35);opacity:0.45;}} }}
  #tfl-draw-loading {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    background:rgba(10,16,26,0.92); display:flex; flex-direction:column;
    align-items:center; justify-content:center; z-index:100;
    transition:opacity 0.5s ease;
  }}
  #tfl-draw-loading .ld-dot {{
    width:10px; height:10px; border-radius:50%; background:rgba(30,144,255,0.82);
    animation:tfl-draw-pulse 1.2s ease-in-out infinite;
  }}
  #tfl-draw-loading .ld-text {{
    margin-top:8px; font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    font-size:11px; color:rgba(180,200,220,0.65);
  }}

  /* Pin markers */
  .tfl-pin-marker {{
    width:10px; height:10px; border-radius:50%;
    background:rgba(0,224,184,0.85); border:2px solid rgba(255,255,255,0.70);
    box-shadow:0 2px 8px rgba(0,0,0,0.35);
  }}
</style>

<div id="{map_id}" style="position:relative;">
  <div id="tfl-draw-loading"><div class="ld-dot"></div><div class="ld-text">Initializing map\u2026</div></div>
  <div id="tfl-draw-coord">\u2014</div>
  <div id="tfl-draw-badge">Click map or search to collect addresses</div>
  <div id="tfl-draw-collector">
    <div class="dc-title"><span>&#x1F4CD; Collected Addresses</span><span id="tfl-draw-count">0</span></div>
    <div id="tfl-draw-list"><div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div></div>
    <div class="dc-actions">
      <div class="dc-btn" id="tfl-draw-copy-btn">Copy All</div>
      <div class="dc-btn clear" id="tfl-draw-clear-btn">Clear</div>
    </div>
  </div>
</div>

<script src="https://js.arcgis.com/4.30/"></script>
<script>
  require([
    "esri/Map", "esri/views/MapView", "esri/layers/GraphicsLayer",
    "esri/Graphic", "esri/widgets/Home", "esri/widgets/BasemapToggle",
    "esri/widgets/ScaleBar", "esri/widgets/Compass", "esri/widgets/Fullscreen",
    "esri/widgets/Locate", "esri/widgets/Search", "esri/widgets/Sketch",
    "esri/widgets/Expand", "esri/geometry/geometryEngine",
    "esri/layers/FeatureLayer", "esri/rest/locator"
  ], (Map, MapView, GraphicsLayer, Graphic, Home, BasemapToggle, ScaleBar,
      Compass, Fullscreen, Locate, Search, Sketch, Expand, geometryEngine,
      FeatureLayer, locator) => {{

    const collectedAddresses = [];
    const markersLayer = new GraphicsLayer();
    const sketchLayer = new GraphicsLayer();
    const pinsLayer = new GraphicsLayer();

    /* Reference layers */
    const countyLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_COUNTY_LAYER_URL}",
      opacity: 0.35, labelsVisible: false, popupEnabled: false,
      renderer: {{ type:"simple", symbol:{{ type:"simple-fill", color:[0,0,0,0], outline:{{ color:[180,200,220,0.3], width:0.6 }} }} }}
    }});
    const cityLayer = new FeatureLayer({{
      url: "{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}",
      definitionExpression: "STATE='48'", opacity: 0.30, labelsVisible: false, visible: false, popupEnabled: false,
      renderer: {{ type:"simple", symbol:{{ type:"simple-fill", color:[0,0,0,0], outline:{{ color:[150,190,210,0.25], width:0.5 }} }} }}
    }});
    const districtLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}",
      opacity: 0.25, labelsVisible: false, visible: false, popupEnabled: false,
      renderer: {{ type:"simple", symbol:{{ type:"simple-fill", color:[0,0,0,0], outline:{{ color:[100,160,200,0.22], width:0.4 }} }} }}
    }});

    const map = new Map({{
      basemap: {basemap_safe},
      layers: [countyLayer, cityLayer, districtLayer, markersLayer, pinsLayer, sketchLayer]
    }});

    const view = new MapView({{
      container: "{map_id}",
      map, center: [-99.0, 31.2], zoom: 6,
      constraints: {{ minZoom: 4, maxZoom: 18 }},
      popup: {{ dockEnabled: true, dockOptions: {{ breakpoint: false, position: "bottom-left" }} }}
    }});

    /* Pre-existing markers */
    const preMarkers = {markers_json};
    preMarkers.forEach((m, i) => {{
      markersLayer.add(new Graphic({{
        geometry: {{ type: "point", longitude: m.lon, latitude: m.lat }},
        symbol: {{ type: "simple-marker", style: "diamond", size: 11, color: [0,224,184,0.85], outline: {{ color: [255,255,255,0.75], width: 1.5 }} }},
        attributes: {{ label: m.label || "", lat: m.lat, lon: m.lon }},
        popupTemplate: {{ title: m.label || "Marker " + (i+1), content: "Lat: " + m.lat.toFixed(5) + ", Lon: " + m.lon.toFixed(5) }}
      }}));
    }});

    /* Geocoder URL */
    const geocodeUrl = "{ARCGIS_GEOCODER_URL}";

    /* Helpers */
    function updateCollectorUI() {{
      const listEl = document.getElementById("tfl-draw-list");
      const countEl = document.getElementById("tfl-draw-count");
      if (countEl) countEl.textContent = collectedAddresses.length;
      if (!listEl) return;
      if (collectedAddresses.length === 0) {{
        listEl.innerHTML = '<div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div>';
        return;
      }}
      listEl.innerHTML = collectedAddresses.map((a, i) =>
        '<div class="dc-item">'
        + '<div class="dc-num">' + (i + 1) + '</div>'
        + '<div><div class="dc-addr">' + (a.address || "Unknown") + '</div>'
        + '<div class="dc-coord">' + Number(a.lat).toFixed(5) + '\\u00b0 N, ' + Math.abs(a.lon).toFixed(5) + '\\u00b0 W</div>'
        + '</div></div>'
      ).join("");
    }}

    function addAddress(address, lat, lon) {{
      const exists = collectedAddresses.some(a =>
        Math.abs(a.lat - lat) < 0.0001 && Math.abs(a.lon - lon) < 0.0001
      );
      if (exists) return;
      collectedAddresses.push({{ address, lat, lon }});

      /* Drop a pin */
      pinsLayer.add(new Graphic({{
        geometry: {{ type: "point", longitude: lon, latitude: lat }},
        symbol: {{ type: "simple-marker", style: "circle", size: 10, color: [30,144,255,0.85], outline: {{ color: [255,255,255,0.80], width: 1.5 }} }},
        attributes: {{ address, lat, lon }},
        popupTemplate: {{ title: address || "Point", content: "Lat: " + lat.toFixed(5) + ", Lon: " + lon.toFixed(5) }}
      }}));

      updateCollectorUI();

      /* Notify parent */
      try {{
        window.parent.postMessage({{
          type: "tfl-draw-address-found",
          address: address, lat: lat, lon: lon,
          allAddresses: collectedAddresses.slice()
        }}, "*");
      }} catch(e) {{}}
    }}

    function reverseGeocode(lat, lon) {{
      const url = geocodeUrl.replace("findAddressCandidates", "reverseGeocode")
        + "?location=" + lon + "," + lat
        + "&outSR=4326&langCode=en&f=json";
      fetch(url).then(r => r.json()).then(data => {{
        const addr = (data.address && data.address.LongLabel) || (data.address && data.address.ShortLabel) || ("Point: " + lat.toFixed(5) + ", " + lon.toFixed(5));
        addAddress(addr, lat, lon);
      }}).catch(() => {{
        addAddress("Point: " + lat.toFixed(5) + ", " + lon.toFixed(5), lat, lon);
      }});
    }}

    /* Click Ã¢â€ â€™ reverse geocode */
    view.on("click", (evt) => {{
      if (evt.mapPoint) {{
        reverseGeocode(evt.mapPoint.latitude, evt.mapPoint.longitude);
      }}
    }});

    /* Coordinate readout */
    view.on("pointer-move", (evt) => {{
      const pt = view.toMap(evt);
      const el = document.getElementById("tfl-draw-coord");
      if (pt && el) el.textContent = pt.latitude.toFixed(5) + "\\u00b0 N, " + Math.abs(pt.longitude).toFixed(5) + "\\u00b0 W";
    }});

    /* Widgets */
    const home = new Home({{ view }});
    const basemapToggle = new BasemapToggle({{ view, nextBasemap: {basemap_safe} === "hybrid" ? "gray-vector" : "hybrid" }});
    const scaleBar = new ScaleBar({{ view, unit: "dual" }});
    const compass = new Compass({{ view }});
    const fullscreen = new Fullscreen({{ view }});
    const locate = new Locate({{ view }});

    const search = new Search({{
      view, popupEnabled: true, resultGraphicEnabled: true,
      goToOverride: (view, opts) => view.goTo(opts.target, {{ duration: 800, easing: "ease-in-out" }})
    }});
    search.on("select-result", (evt) => {{
      if (evt.result && evt.result.feature && evt.result.feature.geometry) {{
        const geom = evt.result.feature.geometry;
        addAddress(evt.result.name || "", geom.latitude, geom.longitude);
      }}
    }});

    const sketch = new Sketch({{
      view, layer: sketchLayer, creationMode: "single",
      availableCreateTools: ["polygon", "circle", "rectangle"],
      defaultCreateOptions: {{ mode: "freehand" }},
      visibleElements: {{ selectionTools: {{ "lasso-selection": false, "rectangle-selection": false }}, settingsMenu: false, undoRedoMenu: true }},
      defaultUpdateOptions: {{ tool: "reshape" }}
    }});
    const sketchExpand = new Expand({{
      view, content: sketch, expandIconClass: "esri-icon-polygon",
      expandTooltip: "Draw area to collect addresses", group: "tools"
    }});

    /* Layer toggle */
    const layerDiv = document.createElement("div");
    layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
    layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Reference Layers</div>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-draw-toggle-city" style="accent-color:#28b464;"><span>City Boundaries</span></label>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-draw-toggle-district" style="accent-color:#c88c3c;"><span>School Districts</span></label>';
    const layerExpand = new Expand({{ view, content: layerDiv, expandIconClass: "esri-icon-layer-list", expandTooltip: "Toggle reference layers", group: "tools" }});

    view.ui.add(home, "top-left");
    view.ui.add(compass, "top-left");
    view.ui.add(fullscreen, "top-left");
    view.ui.add(locate, "top-left");
    view.ui.add(sketchExpand, "top-left");
    view.ui.add(layerExpand, "top-left");
    view.ui.add(search, "top-right");
    view.ui.add(basemapToggle, "top-right");
    view.ui.add(scaleBar, "bottom-left");

    view.when(() => {{
      const cBox = document.getElementById("tfl-draw-toggle-city");
      const dBox = document.getElementById("tfl-draw-toggle-district");
      if (cBox) cBox.addEventListener("change", () => {{ cityLayer.visible = cBox.checked; }});
      if (dBox) dBox.addEventListener("change", () => {{ districtLayer.visible = dBox.checked; }});
    }});

    /* Sketch complete Ã¢â€ â€™ reverse-geocode the centroid of the drawn area */
    sketch.on("create", (evt) => {{
      if (evt.state !== "complete") return;
      const geom = evt.graphic.geometry;
      const ext = geom.extent;
      if (!ext) return;

      /* Sample grid of points inside the drawn area for reverse geocoding */
      const cx = ext.center.longitude;
      const cy = ext.center.latitude;
      const dx = (ext.xmax - ext.xmin);
      const dy = (ext.ymax - ext.ymin);
      const SAMPLES = 5;
      const promises = [];

      /* Always geocode the centroid */
      reverseGeocode(cy, cx);

      /* Sample a NxN grid within the extent, but only inside the polygon */
      for (let xi = 0; xi < SAMPLES; xi++) {{
        for (let yi = 0; yi < SAMPLES; yi++) {{
          const px = ext.xmin + (dx * (xi + 0.5) / SAMPLES);
          const py = ext.ymin + (dy * (yi + 0.5) / SAMPLES);
          const testPt = {{ type: "point", longitude: px, latitude: py, spatialReference: {{ wkid: 4326 }} }};
          if (geometryEngine.contains(geom, testPt)) {{
            reverseGeocode(py, px);
          }}
        }}
      }}

      /* Update badge */
      const badge = document.getElementById("tfl-draw-badge");
      if (badge) badge.textContent = "Area scanned Ã¢â‚¬â€ see collected addresses \\u2192";

      /* Post area addresses */
      setTimeout(() => {{
        try {{
          window.parent.postMessage({{
            type: "tfl-draw-area-addresses",
            allAddresses: collectedAddresses.slice()
          }}, "*");
        }} catch(e) {{}}
      }}, 3000);
    }});

    /* Copy all button */
    document.getElementById("tfl-draw-copy-btn").addEventListener("click", () => {{
      if (collectedAddresses.length === 0) return;
      const text = collectedAddresses.map(a => a.address).join("\\n");
      navigator.clipboard.writeText(text).then(() => {{
        const btn = document.getElementById("tfl-draw-copy-btn");
        if (btn) {{ btn.textContent = "Copied!"; setTimeout(() => {{ btn.textContent = "Copy All"; }}, 2000); }}
      }}).catch(() => {{}});

      /* Also post to parent */
      try {{
        window.parent.postMessage({{
          type: "tfl-draw-copy-all",
          allAddresses: collectedAddresses.slice(),
          text: text
        }}, "*");
      }} catch(e) {{}}
    }});

    /* Clear button */
    document.getElementById("tfl-draw-clear-btn").addEventListener("click", () => {{
      collectedAddresses.length = 0;
      pinsLayer.removeAll();
      sketchLayer.removeAll();
      updateCollectorUI();
      const badge = document.getElementById("tfl-draw-badge");
      if (badge) badge.textContent = "Click map or search to collect addresses";
    }});

    /* Loading done */
    view.when(() => {{
      const loader = document.getElementById("tfl-draw-loading");
      if (loader) {{ loader.style.opacity = "0"; setTimeout(() => loader.remove(), 600); }}
      if (preMarkers.length > 0) {{
        view.goTo(markersLayer.graphics.toArray(), {{ padding: {{ top:50, right:50, bottom:50, left:50 }}, duration:1000, easing:"ease-in-out" }}).catch(() => {{}});
      }}
    }});
  }});
</script>
"""
    )
    _persistent_html_frame(
        html=arcgis_html,
        signature=draw_map_signature,
        height=int(height) + 8,
        key=f"mp5_draw_area_map_{draw_map_cache_key}_v1",
        default=None,
    )

def render_address_overlap_arcgis_map(
    lon: float,
    lat: float,
    matched_address: str,
    overlap_points: pd.DataFrame,
    height: int = 440,
    basemap: str = "gray-vector",
) -> None:
    try:
        lon_val = float(lon)
        lat_val = float(lat)
    except Exception:
        return

    # PERFORMANCE: Vectorized point_rows builder Ã¢â‚¬â€ avoids per-row itertuples + html.escape loop
    point_rows: list[dict] = []
    legend_types: dict[str, str] = {}
    if isinstance(overlap_points, pd.DataFrame) and not overlap_points.empty:
        _op = overlap_points.copy()
        for col in ("subdivision_type", "subdivision_name", "subdivision_code", "match_method", "source_name"):
            if col in _op.columns:
                _op[col] = _op[col].fillna("").astype(str).str.strip()
            else:
                _op[col] = ""
        _op["lon"] = pd.to_numeric(_op.get("lon", 0.0), errors="coerce").fillna(0.0)
        _op["lat"] = pd.to_numeric(_op.get("lat", 0.0), errors="coerce").fillna(0.0)
        _op["match_count"] = pd.to_numeric(_op.get("match_count", 0), errors="coerce").fillna(0).astype(int)
        _op["high_total"] = pd.to_numeric(_op.get("high_total", 0.0), errors="coerce").fillna(0.0)
        # Pre-compute colors and escape in bulk
        _color_cache: dict[str, list[float]] = {}
        for st_val in _op["subdivision_type"].unique():
            hex_c = _subdivision_color_hex(st_val)
            _color_cache[st_val] = _hex_to_rgba(hex_c)
            if st_val:
                legend_types[html.escape(st_val, quote=True)] = hex_c
        point_rows = [
            {
                "subdivision_type": html.escape(r.subdivision_type, quote=True),
                "subdivision_name": html.escape(r.subdivision_name, quote=True),
                "subdivision_code": html.escape(r.subdivision_code, quote=True),
                "lon": r.lon,
                "lat": r.lat,
                "match_count": r.match_count,
                "high_total": r.high_total,
                "match_method": html.escape(r.match_method, quote=True),
                "source_name": html.escape(r.source_name, quote=True),
                "color": _color_cache.get(r.subdivision_type, [113, 129, 145, 0.88]),
            }
            for r in _op.itertuples(index=False)
        ]
        del _op

    points_json = json.dumps(point_rows, ensure_ascii=True)
    address_json = json.dumps(
        {
            "lon": lon_val,
            "lat": lat_val,
            "matched_address": html.escape(str(matched_address).strip(), quote=True),
        },
        ensure_ascii=True,
    )
    basemap_safe = json.dumps(str(basemap).strip() or "gray-vector")

    legend_json = json.dumps(
        [{"type": t, "color": c} for t, c in legend_types.items()],
        ensure_ascii=True,
    )
    address_map_signature = stable_json_signature(
        {
            "address": {
                "lon": lon_val,
                "lat": lat_val,
                "matched_address": str(matched_address).strip(),
            },
            "points": point_rows,
            "basemap": str(basemap).strip() or "gray-vector",
            "height": int(height),
        }
    )
    arcgis_html = _session_cached_value(
        "_mp5_address_overlap_html_v2",
        address_map_signature,
        lambda: f"""
<link rel="preload" href="https://js.arcgis.com/4.30/" as="script"/>
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css"/>
<style>
  /* -- Dark popup theme -- */
  .esri-popup__main-container {{
    background: rgba(13,23,36,0.96) !important;
    color: rgba(220,230,240,0.95) !important;
    border: 1px solid rgba(100,140,180,0.22) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.45) !important;
  }}
  .esri-popup__header-title {{ color: rgba(235,242,250,0.97) !important; font-weight: 600 !important; }}
  .esri-popup__content {{ color: rgba(200,215,230,0.92) !important; }}
  .esri-popup__button {{ color: rgba(180,200,220,0.85) !important; }}
  .esri-popup__button:hover {{ color: #fff !important; background: rgba(100,180,255,0.18) !important; }}
  .esri-popup__pointer-direction {{ background: rgba(13,23,36,0.96) !important; }}

  /* -- Sketch toolbar styling -- */
  .esri-sketch {{ background: rgba(13,23,36,0.92) !important; border-radius: 8px !important; border: 1px solid rgba(100,140,180,0.22) !important; }}

  /* -- Legend Ã¢â‚¬â€ bottom-right, compact -- */
  #tfl-addr-legend {{
    position: absolute; bottom: 36px; right: 12px; z-index: 90;
    background: rgba(10,20,32,0.92); border: 1px solid rgba(100,140,180,0.18);
    border-radius: 10px; padding: 6px 10px; max-width: 210px;
    font-family: 'Avenir Next LT Pro', system-ui, sans-serif; font-size: 10.5px;
    color: rgba(210,225,240,0.90); backdrop-filter: blur(8px);
    max-height: 160px; overflow-y: auto;
  }}
  #tfl-addr-legend .leg-title {{
    text-transform: uppercase; letter-spacing: 0.14em; font-size: 8px;
    color: rgba(150,175,200,0.70); margin-bottom: 3px; font-weight: 700;
  }}
  #tfl-addr-legend .leg-row {{ display: flex; align-items: center; gap: 5px; padding: 1.5px 0; }}
  #tfl-addr-legend .leg-chip {{
    width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
    border: 1px solid rgba(255,255,255,0.18);
  }}

  /* -- Loading overlay -- */
  @keyframes tfl-pulse {{ 0%,100% {{ transform:scale(1); opacity:0.92; }} 50% {{ transform:scale(1.35); opacity:0.45; }} }}
  #tfl-addr-loading {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    background:rgba(10,16,26,0.92); display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:10px;
    z-index:100; border-radius:14px; transition:opacity 0.6s ease;
  }}
  #tfl-addr-loading .ld-spinner {{
    width:30px; height:30px; border:2.5px solid rgba(100,140,180,0.18);
    border-top:2.5px solid rgba(100,180,255,0.80); border-radius:50%;
    animation: tfl-ld-spin 0.8s linear infinite;
  }}
  #tfl-addr-loading .ld-label {{
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(160,185,210,0.65); letter-spacing:0.06em;
  }}
  @keyframes tfl-ld-spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}

  /* -- Coordinate bar -- */
  #tfl-addr-coord {{
    position:absolute; bottom:10px; left:50%; transform:translateX(-50%); z-index:90;
    background:rgba(10,16,26,0.85); border:1px solid rgba(100,140,180,0.15);
    border-radius:6px; padding:2px 10px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(180,200,220,0.75); pointer-events:none; backdrop-filter:blur(6px);
    white-space:nowrap; letter-spacing:0.04em;
  }}

  /* -- Lasso/selection feedback -- */
  #tfl-addr-sel-info {{
    position:absolute; bottom:36px; left:12px; z-index:90;
    background:rgba(10,16,26,0.92); border:1px solid rgba(0,180,255,0.25);
    border-radius:8px; padding:6px 12px; backdrop-filter:blur(6px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11px;
    color:rgba(200,220,240,0.90); display:none; max-width:280px;
  }}
  #tfl-addr-sel-info .sel-title {{
    font-weight:700; color:rgba(100,200,255,0.95); font-size:10px;
    text-transform:uppercase; letter-spacing:0.08em; margin-bottom:3px;
  }}
  #tfl-addr-adv-btn {{
    position:absolute; top:12px; right:12px; z-index:95;
    border:1px solid rgba(100,180,255,0.32);
    background:rgba(10,20,32,0.92);
    color:rgba(190,220,245,0.92);
    border-radius:8px;
    padding:5px 10px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    font-size:10px;
    letter-spacing:0.04em;
    cursor:pointer;
    backdrop-filter:blur(6px);
    transition:all .2s ease;
  }}
  #tfl-addr-adv-btn:hover {{
    border-color:rgba(100,180,255,0.52);
    background:rgba(16,34,52,0.95);
  }}
  #tfl-addr-adv-btn[disabled] {{
    opacity:0.7;
    cursor:default;
  }}
</style>
<div style="width:100%;height:{height}px;position:relative;">
  <div id="tfl-address-overlap-map" style="width:100%;height:100%;border-radius:14px;overflow:hidden;"></div>
  <div id="tfl-addr-legend"></div>
  <button id="tfl-addr-adv-btn" type="button">Load advanced tools</button>
  <div id="tfl-addr-loading"><div class="ld-spinner"></div><div class="ld-label">Loading map layers&hellip;</div></div>
  <div id="tfl-addr-coord">&ndash;</div>
  <div id="tfl-addr-sel-info"></div>
</div>
<script src="https://js.arcgis.com/4.30/"></script>
<script>
  const overlapPoints = {points_json};
  const addressPoint = {address_json};
  const baseMapId = {basemap_safe};
  const legendEntries = {legend_json};
  const advBtn = document.getElementById("tfl-addr-adv-btn");
  const scheduleAdvancedLoad = (fn) => {{
    if (typeof window.requestIdleCallback === "function") {{
      window.requestIdleCallback(fn, {{ timeout: 2600 }});
    }} else {{
      setTimeout(fn, 1500);
    }}
  }};

  /* Build on-map legend */
  (function() {{
    const el = document.getElementById("tfl-addr-legend");
    if (!el || legendEntries.length === 0) {{ if (el) el.style.display = "none"; return; }}
    let h = '<div class="leg-title">Subdivision Types</div>';
    for (const e of legendEntries) {{
      h += '<div class="leg-row"><span class="leg-chip" style="background:' + e.color + ';"></span><span>' + e.type + '</span></div>';
    }}
    h += '<div class="leg-row" style="margin-top:2px;"><span class="leg-chip" style="background:#c92234;transform:rotate(45deg);border-radius:2px;"></span><span>Queried Address</span></div>';
    el.innerHTML = h;
  }})();

  require([
    "esri/Map",
    "esri/views/MapView",
    "esri/layers/GraphicsLayer",
    "esri/Graphic",
    "esri/widgets/Home",
    "esri/widgets/ScaleBar",
    "esri/widgets/BasemapToggle"
  ], function(Map, MapView, GraphicsLayer, Graphic, Home, ScaleBar, BasemapToggle) {{
    const map = new Map({{ basemap: baseMapId }});

    const overlapLayer = new GraphicsLayer();
    const addressLayer = new GraphicsLayer();
    const sketchLayer = new GraphicsLayer();
    map.add(overlapLayer);
    map.add(addressLayer);
    map.add(sketchLayer);

    const view = new MapView({{
      container: "tfl-address-overlap-map",
      map,
      center: [addressPoint.lon, addressPoint.lat],
      zoom: 11,
      constraints: {{ minZoom: 5 }},
      popup: {{ dockEnabled: true, dockOptions: {{ position: "bottom-right", breakpoint: false }} }},
      ui: {{ padding: {{ top: 10, right: 10, bottom: 30, left: 10 }} }}
    }});

    const formatUsd = (v) => Number(v||0).toLocaleString("en-US",{{style:"currency",currency:"USD",maximumFractionDigits:0}});
    const maxHigh = overlapPoints.reduce((a,r) => Math.max(a, Number(r.high_total||0)), 0);
    const sz = (v) => {{ if(maxHigh<=0) return 10; const n=Math.max(0,Number(v||0)); return Math.max(9,Math.min(28,9+(Math.log10(n+1)/Math.log10(maxHigh+1))*19)); }};
    const badge = (m) => {{
      const l=(m||"").toLowerCase();
      if(l.includes("spatial")||l.includes("boundary")) return '<span style="display:inline-block;padding:1px 6px;border-radius:5px;font-size:9.5px;font-weight:600;background:rgba(0,200,140,0.18);color:#00c88c;">Spatial</span>';
      if(l.includes("name")||l.includes("anchor")) return '<span style="display:inline-block;padding:1px 6px;border-radius:5px;font-size:9.5px;font-weight:600;background:rgba(255,180,40,0.18);color:#ffb428;">Name-anchored</span>';
      return '<span style="display:inline-block;padding:1px 6px;border-radius:5px;font-size:9.5px;font-weight:600;background:rgba(130,145,160,0.18);color:#8291a0;">Unknown</span>';
    }};

    /* -- Render overlap points and address marker immediately (no layer fetch needed) -- */
    for (const row of overlapPoints) {{
      const g = new Graphic({{
        geometry: {{ type: "point", longitude: row.lon, latitude: row.lat }},
        symbol: {{
          type: "simple-marker", size: sz(row.high_total),
          color: row.color || [113,129,145,0.85],
          outline: {{ color: [255,255,255,0.70], width: 1 }}
        }},
        attributes: row,
        popupTemplate: {{
          title: row.subdivision_name || "Overlapping subdivision",
          content: `<div style="font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;line-height:1.5;">
            <div style="margin-bottom:5px;">${{badge(row.match_method)}}</div>
            <table style="border-collapse:collapse;width:100%;">
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Type</td><td style="font-weight:600;">${{row.subdivision_type||"N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Code</td><td>${{row.subdivision_code||"N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Matched clients</td><td style="font-weight:600;">${{row.match_count||0}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">TFL high est.</td><td style="font-weight:600;">${{formatUsd(row.high_total)}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Method</td><td>${{row.match_method||"N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Source</td><td>${{row.source_name||"N/A"}}</td></tr>
            </table>
          </div>`
        }}
      }});
      overlapLayer.add(g);
    }}

    /* Address marker with pulse */
    addressLayer.add(new Graphic({{
      geometry: {{ type: "point", longitude: addressPoint.lon, latitude: addressPoint.lat }},
      symbol: {{ type: "simple-marker", style: "circle", size: 24, color: [201,34,52,0.0], outline: {{ color: [201,34,52,0.50], width: 2 }} }}
    }}));
    addressLayer.add(new Graphic({{
      geometry: {{ type: "point", longitude: addressPoint.lon, latitude: addressPoint.lat }},
      symbol: {{ type: "simple-marker", style: "diamond", size: 14, color: [201,34,52,0.95], outline: {{ color: [255,255,255,0.90], width: 1.8 }} }},
      popupTemplate: {{
        title: "Queried Address",
        content: `<div style="font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;">
          <div style="font-weight:600;margin-bottom:3px;">${{addressPoint.matched_address||"Address point"}}</div>
          <div style="color:#7a94ab;font-size:10.5px;">Lat ${{Number(addressPoint.lat).toFixed(5)}}, Lon ${{Number(addressPoint.lon).toFixed(5)}}</div>
        </div>`
      }}
    }}));

    /* -- Essential widgets (loaded in initial bundle) -- */
    const home = new Home({{ view }});
    const basemapToggle = new BasemapToggle({{ view, nextBasemap: baseMapId === "hybrid" ? "gray-vector" : "hybrid" }});
    const scaleBar = new ScaleBar({{ view, unit: "dual" }});
    view.ui.add(home, "top-left");
    view.ui.add(basemapToggle, "top-right");
    view.ui.add(scaleBar, "bottom-left");

    /* Coordinate readout */
    view.on("pointer-move", (evt) => {{
      const pt = view.toMap(evt);
      const el = document.getElementById("tfl-addr-coord");
      if (pt && el) el.textContent = pt.latitude.toFixed(5) + "\u00b0 N, " + Math.abs(pt.longitude).toFixed(5) + "\u00b0 W";
    }});

    /* Hover highlight */
    let hoverHL = null;
    view.on("pointer-move", (evt) => {{
      view.hitTest(evt, {{ include: [overlapLayer] }}).then((r) => {{
        const hit = r.results && r.results.find(x => x.graphic);
        document.getElementById("tfl-address-overlap-map").style.cursor = hit ? "pointer" : "default";
        if (hoverHL) {{ overlapLayer.remove(hoverHL); hoverHL = null; }}
        if (hit && hit.graphic && hit.graphic.geometry) {{
          hoverHL = new Graphic({{
            geometry: hit.graphic.geometry,
            symbol: {{ type: "simple-marker", style: "circle", size: 32, color: [255,255,255,0.0], outline: {{ color: [255,255,255,0.55], width: 2 }} }}
          }});
          overlapLayer.add(hoverHL);
        }}
      }});
    }});

    /* -- Phase 1: View ready Ã¢â‚¬â€ dismiss loading overlay and zoom to graphics -- */
    view.when(() => {{
      const loader = document.getElementById("tfl-addr-loading");
      if (loader) {{ loader.style.opacity = "0"; setTimeout(() => loader.remove(), 600); }}
      const all = [...overlapLayer.graphics.toArray(), ...addressLayer.graphics.toArray()];
      if (all.length > 0) {{
        view.goTo(all, {{ padding: {{ top: 50, right: 50, bottom: 50, left: 50 }}, duration: 1000, easing: "ease-in-out" }}).catch(() => {{}});
      }}

      /* -- Phase 2: Deferred load of reference FeatureLayers and secondary widgets -- */
      let advancedLoaded = false;
      const loadAdvanced = () => {{
        if (advancedLoaded) return;
        advancedLoaded = true;
        if (advBtn) {{
          advBtn.textContent = "Loading advanced tools...";
          advBtn.disabled = true;
        }}
        require([
        "esri/layers/FeatureLayer",
        "esri/widgets/Compass",
        "esri/widgets/Fullscreen",
        "esri/widgets/Search",
        "esri/widgets/Locate",
        "esri/widgets/Sketch",
        "esri/widgets/Expand",
        "esri/geometry/geometryEngine"
      ], function(FeatureLayer, Compass, Fullscreen, Search, Locate, Sketch, Expand, geometryEngine) {{

        /* -- Reference boundary layers (deferred Ã¢â‚¬â€ not needed for initial render) -- */
        const countyLayer = new FeatureLayer({{
          url: "{TEA_ARCGIS_COUNTY_LAYER_URL}",
          outFields: ["FENAME", "FIPS"],
          popupEnabled: false, labelsVisible: false,
          minScale: 2000000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "$feature.FENAME + ' County'" }},
            symbol: {{ type: "text", color: [160, 140, 110, 0.75], haloColor: [13, 23, 36, 0.80], haloSize: 0.8,
              font: {{ size: 11, family: "Avenir Next LT Pro", weight: "600" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [145, 111, 63, 0.22], width: 0.6 }} }} }},
          opacity: 0.35
        }});

        const districtLayer = new FeatureLayer({{
          url: "{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}",
          outFields: ["FID", "NAME20", "DISTRICT"],
          popupEnabled: false, labelsVisible: false,
          minScale: 500000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "$feature.NAME20" }},
            symbol: {{ type: "text", color: [73, 112, 150, 0.65], haloColor: [13, 23, 36, 0.8], haloSize: 0.6,
              font: {{ size: 8, family: "Avenir Next LT Pro", weight: "normal" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [30, 144, 255, 0.20], width: 0.5 }} }} }},
          opacity: 0.35
        }});

        const cityLayer = new FeatureLayer({{
          url: "{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}",
          outFields: ["NAME", "BASENAME", "GEOID", "STATE"],
          definitionExpression: "STATE = '48'",
          popupEnabled: false, labelsVisible: false,
          minScale: 1000000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "DefaultValue($feature.BASENAME, $feature.NAME)" }},
            symbol: {{ type: "text", color: [165, 100, 105, 0.80], haloColor: [13, 23, 36, 0.76], haloSize: 0.7,
              font: {{ size: 9, family: "Avenir Next LT Pro", weight: "500" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [158, 42, 43, 0.12], width: 0.4 }} }} }},
          opacity: 0.20
        }});

        const houseLayer = new FeatureLayer({{
          url: "{TEXAS_HOUSE_DISTRICTS_LAYER_URL}",
          outFields: ["DISTRICT"],
          popupEnabled: true,
          popupTemplate: {{ title: "TX House District {{{{DISTRICT}}}}", content: "Texas House of Representatives District {{{{DISTRICT}}}}" }},
          labelsVisible: false,
          minScale: 2000000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "'HD ' + $feature.DISTRICT" }},
            symbol: {{ type: "text", color: [90, 180, 130, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
              font: {{ size: 8, family: "Avenir Next LT Pro", weight: "600" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [40, 180, 100, 0.03], outline: {{ color: [40, 180, 100, 0.30], width: 0.8 }} }} }},
          opacity: 0.30, visible: false
        }});

        const senateLayer = new FeatureLayer({{
          url: "{TEXAS_SENATE_DISTRICTS_LAYER_URL}",
          outFields: ["DISTRICT"],
          popupEnabled: true,
          popupTemplate: {{ title: "TX Senate District {{{{DISTRICT}}}}", content: "Texas Senate District {{{{DISTRICT}}}}" }},
          labelsVisible: false,
          minScale: 2000000,
          labelingInfo: [{{
            labelExpressionInfo: {{ expression: "'SD ' + $feature.DISTRICT" }},
            symbol: {{ type: "text", color: [180, 130, 90, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
              font: {{ size: 9, family: "Avenir Next LT Pro", weight: "600" }} }}
          }}],
          renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [200, 140, 60, 0.03], outline: {{ color: [200, 140, 60, 0.30], width: 0.8 }} }} }},
          opacity: 0.30, visible: false
        }});

        /* Insert reference layers below overlap graphics */
        map.add(countyLayer, 0);
        map.add(districtLayer, 1);
        map.add(houseLayer, 2);
        map.add(senateLayer, 3);
        map.add(cityLayer, 4);

        /* -- Zoom-dependent label visibility -- */
        const updateLabels = () => {{
          const z = Number(view.zoom || 0);
          countyLayer.labelsVisible = z >= 6;
          cityLayer.labelsVisible = z >= 7;
          districtLayer.labelsVisible = z >= 9;
          houseLayer.labelsVisible = z >= 8;
          senateLayer.labelsVisible = z >= 7;
        }};
        view.watch("zoom", updateLabels);
        updateLabels();

        /* -- Secondary widgets -- */
        const compass = new Compass({{ view }});
        const fullscreen = new Fullscreen({{ view }});
        const locate = new Locate({{ view }});

        const search = new Search({{
          view,
          popupEnabled: true,
          resultGraphicEnabled: true,
          goToOverride: (view, opts) => view.goTo(opts.target, {{ duration: 800, easing: "ease-in-out" }})
        }});
        search.on("select-result", (evt) => {{
          if (evt.result && evt.result.name) {{
            try {{ window.parent.postMessage({{ type: "tfl-map-address-search", address: evt.result.name }}, "*"); }} catch(e) {{}}
          }}
        }});

        const sketch = new Sketch({{
          view,
          layer: sketchLayer,
          creationMode: "single",
          availableCreateTools: ["polygon", "circle", "rectangle"],
          defaultCreateOptions: {{ mode: "freehand" }},
          visibleElements: {{ selectionTools: {{ "lasso-selection": false, "rectangle-selection": false }}, settingsMenu: false, undoRedoMenu: true }},
          defaultUpdateOptions: {{ tool: "reshape" }}
        }});
        const sketchExpand = new Expand({{
          view,
          content: sketch,
          expandIconClass: "esri-icon-polygon",
          expandTooltip: "Draw area for batch analysis",
          group: "tools"
        }});

        const layerDiv = document.createElement("div");
        layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
        layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Legislative Districts</div>'
          + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-toggle-house" style="accent-color:#28b464;"><span>TX House Districts</span></label>'
          + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-toggle-senate" style="accent-color:#c88c3c;"><span>TX Senate Districts</span></label>';
        const layerExpand = new Expand({{
          view,
          content: layerDiv,
          expandIconClass: "esri-icon-layer-list",
          expandTooltip: "Toggle legislative districts",
          group: "tools"
        }});

        view.ui.add(compass, "top-left");
        view.ui.add(fullscreen, "top-left");
        view.ui.add(locate, "top-left");
        view.ui.add(sketchExpand, "top-left");
        view.ui.add(layerExpand, "top-left");
        view.ui.add(search, "top-right");

        /* Wire layer toggles */
        const hBox = document.getElementById("tfl-toggle-house");
        const sBox = document.getElementById("tfl-toggle-senate");
        if (hBox) hBox.addEventListener("change", () => {{ houseLayer.visible = hBox.checked; }});
        if (sBox) sBox.addEventListener("change", () => {{ senateLayer.visible = sBox.checked; }});

        /* Sketch complete Ã¢â€ â€™ batch analysis info */
        sketch.on("create", (evt) => {{
          if (evt.state !== "complete") return;
          const drawn = evt.graphic.geometry;
          const selInfo = document.getElementById("tfl-addr-sel-info");
          const contained = [];
          overlapLayer.graphics.forEach((g) => {{
            if (g.geometry && geometryEngine.contains(drawn, g.geometry)) {{
              contained.push(g.attributes || {{}});
            }}
          }});
          if (selInfo && contained.length > 0) {{
            const total = contained.reduce((a,r) => a + Number(r.high_total||0), 0);
            const types = [...new Set(contained.map(r => r.subdivision_type).filter(Boolean))];
            selInfo.style.display = "block";
            selInfo.innerHTML = '<div class="sel-title">Area Selection</div>'
              + '<div><strong>' + contained.length + '</strong> subdivision(s) in area</div>'
              + '<div>Combined TFL est.: <strong>' + formatUsd(total) + '</strong></div>'
              + '<div style="font-size:10px;color:rgba(180,200,220,0.65);margin-top:3px;">' + types.join(", ") + '</div>';
            try {{
              const names = contained.map(r => r.subdivision_name).filter(Boolean);
              window.parent.postMessage({{ type: "tfl-map-area-select", count: contained.length, totalHigh: total, names: names, types: types }}, "*");
            }} catch(e) {{}}
          }} else if (selInfo) {{
            selInfo.style.display = "block";
            selInfo.innerHTML = '<div class="sel-title">Area Selection</div><div>No subdivisions in drawn area.</div>';
            setTimeout(() => {{ selInfo.style.display = "none"; }}, 3000);
          }}
        }});
        if (advBtn) {{
          advBtn.textContent = "Advanced tools ready";
          setTimeout(() => {{
            try {{ advBtn.remove(); }} catch (e) {{}}
          }}, 1100);
        }}
      }}); /* end deferred require */
      }};
      if (advBtn) {{
        advBtn.addEventListener("click", () => loadAdvanced(), {{ once: true }});
      }}
      scheduleAdvancedLoad(() => loadAdvanced());
    }}); /* end view.when */
  }});
</script>
"""
    )
    _persistent_html_frame(
        html=arcgis_html,
        signature=address_map_signature,
        height=int(height) + 8,
        key="mp5_address_overlap_map_v2",
        default=None,
    )

def render_tfl_school_district_arcgis_map(matches: pd.DataFrame, height: int = 620, basemap: str = "gray-vector") -> None:
    if matches.empty:
        st.info("No matching school-district clients to plot on the map.")
        return

    payload_rows = []
    for row in matches.itertuples(index=False):
        clients = row.match_clients if isinstance(row.match_clients, list) else []
        safe_clients = [html.escape(str(c), quote=True) for c in clients]
        payload_rows.append(
            {
                "fid": int(row.fid),
                "district_name": html.escape(str(row.district_name), quote=True),
                "district_code": html.escape(str(row.district_code), quote=True),
                "lon": float(row.lon),
                "lat": float(row.lat),
                "match_count": int(row.match_count),
                "high_total": float(getattr(row, "high_total", 0.0) or 0.0),
                "match_clients_preview": html.escape(str(row.match_clients_preview), quote=True),
                "match_clients": safe_clients[:14],
                "extra_count": max(0, len(safe_clients) - 14),
            }
        )
    payload_json = json.dumps(payload_rows, ensure_ascii=True)
    basemap_safe = json.dumps(str(basemap).strip() or "gray-vector")

    total_districts = len(payload_rows)
    total_high = sum(r["high_total"] for r in payload_rows)
    total_high_fmt = f"${total_high:,.0f}"
    arcgis_html = f"""
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css"/>
<style>
  /* -- Dark popup theme -- */
  .esri-popup__main-container {{
    background: rgba(13,23,36,0.96) !important;
    color: rgba(220,230,240,0.95) !important;
    border: 1px solid rgba(100,140,180,0.22) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.45) !important;
  }}
  .esri-popup__header-title {{ color: rgba(235,242,250,0.97) !important; font-weight: 600 !important; }}
  .esri-popup__content {{ color: rgba(200,215,230,0.92) !important; }}
  .esri-popup__button {{ color: rgba(180,200,220,0.85) !important; }}
  .esri-popup__button:hover {{ color: #fff !important; background: rgba(0,224,184,0.18) !important; }}
  .esri-popup__pointer-direction {{ background: rgba(13,23,36,0.96) !important; }}

  .esri-sketch {{ background: rgba(13,23,36,0.92) !important; border-radius: 8px !important; border: 1px solid rgba(100,140,180,0.22) !important; }}

  #tfl-sd-loading {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    background:rgba(10,16,26,0.92); display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:10px;
    z-index:100; border-radius:14px; transition:opacity 0.6s ease;
  }}
  #tfl-sd-loading .ld-spinner {{
    width:30px; height:30px; border:2.5px solid rgba(100,140,180,0.18);
    border-top:2.5px solid rgba(0,224,184,0.80); border-radius:50%;
    animation: tfl-sd-spin 0.8s linear infinite;
  }}
  #tfl-sd-loading .ld-label {{
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(160,185,210,0.65); letter-spacing:0.06em;
  }}
  @keyframes tfl-sd-spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
  #tfl-sd-coord {{
    position:absolute; bottom:10px; left:50%; transform:translateX(-50%); z-index:90;
    background:rgba(10,16,26,0.85); border:1px solid rgba(100,140,180,0.15);
    border-radius:6px; padding:2px 10px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(180,200,220,0.75); pointer-events:none; backdrop-filter:blur(6px);
    white-space:nowrap; letter-spacing:0.04em;
  }}
  #tfl-sd-legend {{
    position:absolute; bottom:36px; right:12px; z-index:90;
    background:rgba(10,20,32,0.92); border:1px solid rgba(100,140,180,0.18);
    border-radius:10px; padding:6px 10px; max-width:210px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10.5px;
    color:rgba(210,225,240,0.90); backdrop-filter:blur(8px);
  }}
  #tfl-sd-legend .leg-title {{
    text-transform:uppercase; letter-spacing:0.14em; font-size:8px;
    color:rgba(150,175,200,0.70); margin-bottom:3px; font-weight:700;
  }}
  #tfl-sd-legend .leg-row {{ display:flex; align-items:center; gap:5px; padding:1.5px 0; }}
  #tfl-sd-legend .leg-chip {{
    width:9px; height:9px; border-radius:50%; flex-shrink:0;
    border:1px solid rgba(255,255,255,0.18);
  }}
  #tfl-sd-sel-info {{
    position:absolute; bottom:36px; left:12px; z-index:90;
    background:rgba(10,16,26,0.92); border:1px solid rgba(0,224,184,0.25);
    border-radius:8px; padding:6px 12px; backdrop-filter:blur(6px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11px;
    color:rgba(200,220,240,0.90); display:none; max-width:280px;
  }}
  #tfl-sd-sel-info .sel-title {{
    font-weight:700; color:rgba(0,224,184,0.95); font-size:10px;
    text-transform:uppercase; letter-spacing:0.08em; margin-bottom:3px;
  }}
</style>
<div style="width:100%;height:{height}px;position:relative;">
  <div id="tfl-arcgis-map" style="width:100%;height:100%;border-radius:14px;overflow:hidden;"></div>
  <div id="tfl-sd-legend">
    <div class="leg-title">Legend</div>
    <div class="leg-row"><span class="leg-chip" style="background:#00e0b8;"></span><span>School District ({total_districts})</span></div>
    <div class="leg-row"><span class="leg-chip" style="background:rgba(145,111,63,0.5);border-color:rgba(145,111,63,0.6);"></span><span style="font-size:10px;color:rgba(180,195,210,0.70);">County boundary</span></div>
    <div class="leg-row"><span class="leg-chip" style="background:rgba(30,144,255,0.3);border-color:rgba(30,144,255,0.5);"></span><span style="font-size:10px;color:rgba(180,195,210,0.70);">District boundary</span></div>
  </div>
  <div id="tfl-sd-loading"><div class="ld-spinner"></div><div class="ld-label">Loading map layers&hellip;</div></div>
  <div id="tfl-sd-coord">&ndash;</div>
  <div id="tfl-sd-sel-info"></div>
</div>
<script src="https://js.arcgis.com/4.30/"></script>
<script>
  const tflPoints = {payload_json};
  const baseMapId = {basemap_safe};
  require([
    "esri/Map",
    "esri/views/MapView",
    "esri/layers/FeatureLayer",
    "esri/layers/GraphicsLayer",
    "esri/Graphic",
    "esri/widgets/Home",
    "esri/widgets/ScaleBar",
    "esri/widgets/BasemapToggle",
    "esri/widgets/Compass",
    "esri/widgets/Fullscreen",
    "esri/widgets/Search",
    "esri/widgets/Locate",
    "esri/widgets/Sketch",
    "esri/widgets/Expand",
    "esri/geometry/geometryEngine"
  ], function(Map, MapView, FeatureLayer, GraphicsLayer, Graphic, Home, ScaleBar, BasemapToggle, Compass, Fullscreen, Search, Locate, Sketch, Expand, geometryEngine) {{
    const map = new Map({{ basemap: baseMapId }});

    const countyLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_COUNTY_LAYER_URL}",
      outFields: ["FENAME", "FIPS"],
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "$feature.FENAME + ' County'" }},
        symbol: {{ type: "text", color: [160, 140, 110, 0.75], haloColor: [13, 23, 36, 0.80], haloSize: 0.8,
          font: {{ size: 11, family: "Avenir Next LT Pro", weight: "600" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [145, 111, 63, 0.22], width: 0.6 }} }} }},
      opacity: 0.35
    }});

    const districtLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}",
      outFields: ["FID", "NAME20", "DISTRICT"],
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "$feature.NAME20" }},
        symbol: {{ type: "text", color: [73, 112, 150, 0.65], haloColor: [13, 23, 36, 0.8], haloSize: 0.6,
          font: {{ size: 8, family: "Avenir Next LT Pro", weight: "normal" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [30, 144, 255, 0.25], width: 0.6 }} }} }},
      opacity: 0.40
    }});

    /* TX House & Senate district boundaries */
    const houseLayer = new FeatureLayer({{
      url: "{TEXAS_HOUSE_DISTRICTS_LAYER_URL}",
      outFields: ["*"], popupEnabled: true,
      popupTemplate: {{ title: "TX House District {{{{DISTRICT}}}}", content: "Texas House of Representatives District {{{{DISTRICT}}}}" }},
      labelsVisible: false,
      labelingInfo: [{{ labelExpressionInfo: {{ expression: "'HD ' + $feature.DISTRICT" }},
        symbol: {{ type: "text", color: [90, 180, 130, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
          font: {{ size: 8, family: "Avenir Next LT Pro", weight: "600" }} }} }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [40, 180, 100, 0.03], outline: {{ color: [40, 180, 100, 0.30], width: 0.8 }} }} }},
      opacity: 0.30, visible: false
    }});
    const senateLayer = new FeatureLayer({{
      url: "{TEXAS_SENATE_DISTRICTS_LAYER_URL}",
      outFields: ["*"], popupEnabled: true,
      popupTemplate: {{ title: "TX Senate District {{{{DISTRICT}}}}", content: "Texas Senate District {{{{DISTRICT}}}}" }},
      labelsVisible: false,
      labelingInfo: [{{ labelExpressionInfo: {{ expression: "'SD ' + $feature.DISTRICT" }},
        symbol: {{ type: "text", color: [180, 130, 90, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
          font: {{ size: 9, family: "Avenir Next LT Pro", weight: "600" }} }} }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [200, 140, 60, 0.03], outline: {{ color: [200, 140, 60, 0.30], width: 0.8 }} }} }},
      opacity: 0.30, visible: false
    }});

    map.add(countyLayer);
    map.add(districtLayer);
    map.add(houseLayer);
    map.add(senateLayer);

    const graphics = new GraphicsLayer();
    const sketchLayer = new GraphicsLayer();
    map.add(graphics);
    map.add(sketchLayer);

    const view = new MapView({{
      container: "tfl-arcgis-map",
      map,
      center: [-99.3, 31.1],
      zoom: 5,
      constraints: {{ minZoom: 4 }},
      popup: {{ dockEnabled: true, dockOptions: {{ position: "bottom-right", breakpoint: false }} }},
      ui: {{ padding: {{ top: 10, right: 10, bottom: 30, left: 10 }} }}
    }});

    const formatUsd = (v) => Number(v||0).toLocaleString("en-US",{{style:"currency",currency:"USD",maximumFractionDigits:0}});
    const maxHigh = tflPoints.reduce((a, r) => Math.max(a, Number(r.high_total || 0)), 0);
    const sz = (row) => {{
      if (maxHigh > 0) {{
        const n = Math.max(0, Number(row.high_total || 0));
        return Math.max(8, Math.min(28, 8 + (Math.log10(n+1)/Math.log10(maxHigh+1))*20));
      }}
      return Math.min(26, 8 + Math.log2((row.match_count || 1) + 1) * 5);
    }};

    for (const row of tflPoints) {{
      const clientsHtml = (row.match_clients || []).join(", ");
      const extraHtml = row.extra_count > 0 ? `, +${{row.extra_count}} more` : "";
      const g = new Graphic({{
        geometry: {{ type: "point", longitude: row.lon, latitude: row.lat }},
        symbol: {{
          type: "simple-marker", size: sz(row),
          color: [0, 224, 184, 0.85],
          outline: {{ color: [7, 22, 39, 0.95], width: 1 }}
        }},
        attributes: row,
        popupTemplate: {{
          title: row.district_name || "School District",
          content: `<div style="font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;line-height:1.5;">
            <table style="border-collapse:collapse;width:100%;">
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">District code</td><td style="font-weight:600;">${{row.district_code || "N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">TFL high est.</td><td style="font-weight:600;">${{formatUsd(row.high_total)}}</td></tr>
              <tr><td style="color:#7a94ab;padding:2px 6px 2px 0;font-size:11px;">Matched clients</td><td style="font-weight:600;">${{row.match_count}}</td></tr>
            </table>
            <div style="margin-top:5px;padding-top:4px;border-top:1px solid rgba(140,160,180,0.20);font-size:11px;">${{clientsHtml}}${{extraHtml}}</div>
          </div>`
        }}
      }});
      graphics.add(g);
    }}

    const updateLabels = () => {{
      const z = Number(view.zoom || 0);
      countyLayer.labelsVisible = z >= 6;
      districtLayer.labelsVisible = z >= 8.5;
      houseLayer.labelsVisible = z >= 8;
      senateLayer.labelsVisible = z >= 7;
    }};
    view.watch("zoom", updateLabels);

    /* -- Widgets -- */
    const home = new Home({{ view }});
    const basemapToggle = new BasemapToggle({{ view, nextBasemap: baseMapId === "hybrid" ? "gray-vector" : "hybrid" }});
    const scaleBar = new ScaleBar({{ view, unit: "dual" }});
    const compass = new Compass({{ view }});
    const fullscreen = new Fullscreen({{ view }});
    const locate = new Locate({{ view }});
    const search = new Search({{
      view, popupEnabled: true, resultGraphicEnabled: true,
      goToOverride: (view, opts) => view.goTo(opts.target, {{ duration: 800, easing: "ease-in-out" }})
    }});

    /* Sketch tool for encircling areas */
    const sketch = new Sketch({{
      view, layer: sketchLayer, creationMode: "single",
      availableCreateTools: ["polygon", "circle", "rectangle"],
      defaultCreateOptions: {{ mode: "freehand" }},
      visibleElements: {{ selectionTools: {{ "lasso-selection": false, "rectangle-selection": false }}, settingsMenu: false, undoRedoMenu: true }},
      defaultUpdateOptions: {{ tool: "reshape" }}
    }});
    const sketchExpand = new Expand({{
      view, content: sketch, expandIconClass: "esri-icon-polygon",
      expandTooltip: "Draw area for batch analysis", group: "tools"
    }});

    /* House/Senate layer toggle */
    const layerDiv = document.createElement("div");
    layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
    layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Legislative Districts</div>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sd-toggle-house" style="accent-color:#28b464;"><span>TX House Districts</span></label>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sd-toggle-senate" style="accent-color:#c88c3c;"><span>TX Senate Districts</span></label>';
    const layerExpand = new Expand({{
      view, content: layerDiv, expandIconClass: "esri-icon-layer-list",
      expandTooltip: "Toggle legislative districts", group: "tools"
    }});

    view.ui.add(home, "top-left");
    view.ui.add(compass, "top-left");
    view.ui.add(fullscreen, "top-left");
    view.ui.add(locate, "top-left");
    view.ui.add(sketchExpand, "top-left");
    view.ui.add(layerExpand, "top-left");
    view.ui.add(search, "top-right");
    view.ui.add(basemapToggle, "top-right");
    view.ui.add(scaleBar, "bottom-left");

    /* Wire layer toggles */
    view.when(() => {{
      const hBox = document.getElementById("tfl-sd-toggle-house");
      const sBox = document.getElementById("tfl-sd-toggle-senate");
      if (hBox) hBox.addEventListener("change", () => {{ houseLayer.visible = hBox.checked; }});
      if (sBox) sBox.addEventListener("change", () => {{ senateLayer.visible = sBox.checked; }});
    }});

    /* Sketch complete Ã¢â€ â€™ batch analysis info */
    sketch.on("create", (evt) => {{
      if (evt.state !== "complete") return;
      const drawn = evt.graphic.geometry;
      const selInfo = document.getElementById("tfl-sd-sel-info");
      const contained = [];
      graphics.graphics.forEach((g) => {{
        if (g.geometry && geometryEngine.contains(drawn, g.geometry)) contained.push(g.attributes || {{}});
      }});
      if (selInfo && contained.length > 0) {{
        const total = contained.reduce((a,r) => a + Number(r.high_total||0), 0);
        selInfo.style.display = "block";
        selInfo.innerHTML = '<div class="sel-title">Area Selection</div>'
          + '<div><strong>' + contained.length + '</strong> district(s) in area</div>'
          + '<div>Combined TFL est.: <strong>' + formatUsd(total) + '</strong></div>';
        try {{ window.parent.postMessage({{ type: "tfl-map-area-select", count: contained.length, totalHigh: total }}, "*"); }} catch(e) {{}}
      }} else if (selInfo) {{
        selInfo.style.display = "block";
        selInfo.innerHTML = '<div class="sel-title">Area Selection</div><div>No districts in drawn area.</div>';
        setTimeout(() => {{ selInfo.style.display = "none"; }}, 3000);
      }}
    }});

    /* Coordinate readout */
    view.on("pointer-move", (evt) => {{
      const pt = view.toMap(evt);
      const el = document.getElementById("tfl-sd-coord");
      if (pt && el) el.textContent = pt.latitude.toFixed(5) + "\u00b0 N, " + Math.abs(pt.longitude).toFixed(5) + "\u00b0 W";
    }});

    /* Hover highlight */
    let hoverHL = null;
    view.on("pointer-move", (evt) => {{
      view.hitTest(evt, {{ include: [graphics] }}).then((r) => {{
        const hit = r.results && r.results.find(x => x.graphic);
        document.getElementById("tfl-arcgis-map").style.cursor = hit ? "pointer" : "default";
        if (hoverHL) {{ graphics.remove(hoverHL); hoverHL = null; }}
        if (hit && hit.graphic && hit.graphic.geometry) {{
          hoverHL = new Graphic({{
            geometry: hit.graphic.geometry,
            symbol: {{ type: "simple-marker", style: "circle", size: 30, color: [255,255,255,0.0], outline: {{ color: [0,224,184,0.55], width: 2 }} }}
          }});
          graphics.add(hoverHL);
        }}
      }});
    }});

    view.when(() => {{
      const loader = document.getElementById("tfl-sd-loading");
      if (loader) {{ loader.style.opacity = "0"; setTimeout(() => loader.remove(), 600); }}
      updateLabels();
      if (graphics.graphics.length > 0) {{
        view.goTo(graphics.graphics.toArray(), {{ padding: {{ top: 50, right: 50, bottom: 50, left: 50 }}, duration: 1000, easing: "ease-in-out" }}).catch(() => {{}});
      }}
    }});
  }});
</script>
"""
    components.html(arcgis_html, height=height + 8, scrolling=False)

def render_tfl_subdivision_arcgis_map(
    matches: pd.DataFrame,
    height: int = 640,
    basemap: str = "gray-vector",
) -> None:
    if matches.empty:
        st.info("No matching political-subdivision clients to plot on the map.")
        return

    type_colors = {
        subtype: _hex_to_rgba(color_hex, alpha=0.9)
        for subtype, color_hex in SUBDIVISION_TYPE_COLORS.items()
    }
    type_colors_json = json.dumps(type_colors, ensure_ascii=True)

    # Build hex color map for the on-map legend
    type_hex_colors = {
        subtype: color_hex
        for subtype, color_hex in SUBDIVISION_TYPE_COLORS.items()
    }

    payload_rows = []
    for row in matches.itertuples(index=False):
        clients = row.match_clients if isinstance(row.match_clients, list) else []
        safe_clients = [str(c).strip() for c in clients if str(c).strip()]
        preview = str(getattr(row, "match_clients_preview", "")).strip() or ", ".join(safe_clients[:14])
        payload_rows.append(
            {
                "subdivision_type": html.escape(str(row.subdivision_type), quote=True),
                "subdivision_name": html.escape(str(row.subdivision_name), quote=True),
                "subdivision_code": html.escape(str(row.subdivision_code), quote=True),
                "source_name": html.escape(str(getattr(row, "source_name", "")), quote=True),
                "lon": float(row.lon),
                "lat": float(row.lat),
                "match_count": int(row.match_count),
                "high_total": float(getattr(row, "high_total", 0.0) or 0.0),
                "match_clients_preview": html.escape(preview, quote=True),
                "extra_count": max(0, len(safe_clients) - 14),
            }
        )
    payload_json = json.dumps(payload_rows, ensure_ascii=True)
    basemap_safe = json.dumps(str(basemap).strip() or "gray-vector")

    # Determine which subdivision types are actually present for the legend
    present_types: dict[str, tuple[str, int]] = {}
    for pr in payload_rows:
        st_key = pr["subdivision_type"]
        if st_key:
            if st_key not in present_types:
                present_types[st_key] = (type_hex_colors.get(st_key, "#718191"), 0)
            present_types[st_key] = (present_types[st_key][0], present_types[st_key][1] + 1)
    legend_items_json = json.dumps(
        [{"type": t, "color": c, "count": n} for t, (c, n) in sorted(present_types.items(), key=lambda x: -x[1][1])],
        ensure_ascii=True,
    )

    total_sub = len(payload_rows)
    total_sub_high = sum(r["high_total"] for r in payload_rows)
    total_sub_high_fmt = f"${total_sub_high:,.0f}"
    subdivision_map_signature = stable_json_signature(
        {
            "renderer_version": 3,
            "points": payload_rows,
            "basemap": str(basemap).strip() or "gray-vector",
            "height": int(height),
        }
    )
    arcgis_html = _session_cached_value(
        "_mp5_subdivision_map_html_v3",
        subdivision_map_signature,
        lambda: f"""
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/dark/main.css"/>
<style>
  /* -- Dark popup theme -- */
  .esri-popup__main-container {{
    background: rgba(13,23,36,0.96) !important;
    color: rgba(220,230,240,0.95) !important;
    border: 1px solid rgba(100,140,180,0.22) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(10px) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.45) !important;
  }}
  .esri-popup__header-title {{ color: rgba(235,242,250,0.97) !important; font-weight: 600 !important; }}
  .esri-popup__content {{ color: rgba(200,215,230,0.92) !important; }}
  .esri-popup__button {{ color: rgba(180,200,220,0.85) !important; }}
  .esri-popup__button:hover {{ color: #fff !important; background: rgba(100,180,255,0.18) !important; }}
  .esri-popup__pointer-direction {{ background: rgba(13,23,36,0.96) !important; }}

  .esri-sketch {{ background: rgba(13,23,36,0.92) !important; border-radius: 8px !important; border: 1px solid rgba(100,140,180,0.22) !important; }}

  #tfl-sub-legend {{
    position: absolute; bottom: 90px; right: 12px; z-index: 90;
    background: rgba(10,20,32,0.92); border: 1px solid rgba(100,140,180,0.18);
    border-radius: 11px; padding: 0; max-width: 240px; overflow: hidden;
    font-family: 'Avenir Next LT Pro', system-ui, sans-serif; font-size: 10.5px;
    color: rgba(210,225,240,0.90); backdrop-filter: blur(8px);
    transition: max-height 0.3s ease;
  }}
  #tfl-sub-legend .leg-hdr {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 10px 4px 10px; cursor: pointer; user-select: none;
  }}
  #tfl-sub-legend .leg-title {{
    text-transform: uppercase; letter-spacing: 0.14em; font-size: 8px;
    color: rgba(150,175,200,0.70); font-weight: 700;
  }}
  #tfl-sub-legend .leg-toggle {{
    font-size: 12px; color: rgba(150,175,200,0.60); transition: transform 0.25s;
  }}
  #tfl-sub-legend .leg-body {{
    padding: 0 10px 6px 10px; max-height: 180px; overflow-y: auto;
  }}
  #tfl-sub-legend .leg-body::-webkit-scrollbar {{ width:4px; }}
  #tfl-sub-legend .leg-body::-webkit-scrollbar-thumb {{ background:rgba(100,140,180,0.25); border-radius:4px; }}
  #tfl-sub-legend .leg-body::-webkit-scrollbar-track {{ background:transparent; }}
  #tfl-sub-legend .leg-row {{
    display: flex; align-items: center; justify-content: space-between; gap: 5px; padding: 2px 0;
    cursor: pointer; border-radius: 4px; padding-left: 3px; padding-right: 3px;
    transition: background 0.15s, opacity 0.25s;
  }}
  #tfl-sub-legend .leg-row:hover {{ background: rgba(255,255,255,0.06); }}
  #tfl-sub-legend .leg-row.dimmed {{ opacity: 0.28; }}
  #tfl-sub-legend .leg-left {{ display: flex; align-items: center; gap: 5px; min-width: 0; }}
  #tfl-sub-legend .leg-chip {{
    width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
    border: 1px solid rgba(255,255,255,0.18);
  }}
  #tfl-sub-legend .leg-label {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  #tfl-sub-legend .leg-count {{ font-weight: 600; flex-shrink: 0; color: rgba(200,215,230,0.75); font-size: 9.5px; }}
  #tfl-sub-legend.collapsed .leg-body {{ display: none; }}
  #tfl-sub-legend.collapsed .leg-toggle {{ transform: rotate(180deg); }}

  #tfl-sub-loading {{
    position:absolute; top:0; left:0; width:100%; height:100%;
    background:rgba(10,16,26,0.92); display:flex; flex-direction:column;
    align-items:center; justify-content:center; gap:10px;
    z-index:100; border-radius:14px; transition:opacity 0.6s ease;
  }}
  #tfl-sub-loading .ld-spinner {{
    width:30px; height:30px; border:2.5px solid rgba(100,140,180,0.18);
    border-top:2.5px solid rgba(100,180,255,0.80); border-radius:50%;
    animation: tfl-sub-spin 0.8s linear infinite;
  }}
  #tfl-sub-loading .ld-label {{
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(160,185,210,0.65); letter-spacing:0.06em;
  }}
  @keyframes tfl-sub-spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
  #tfl-sub-coord {{
    position:absolute; bottom:10px; left:50%; transform:translateX(-50%); z-index:90;
    background:rgba(10,16,26,0.85); border:1px solid rgba(100,140,180,0.15);
    border-radius:6px; padding:2px 10px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:10px;
    color:rgba(180,200,220,0.75); pointer-events:none; backdrop-filter:blur(6px);
    white-space:nowrap; letter-spacing:0.04em;
  }}
  #tfl-sub-sel-info {{
    position:absolute; top:52px; right:12px; z-index:90;
    background:rgba(10,16,26,0.92); border:1px solid rgba(0,180,255,0.25);
    border-radius:8px; padding:6px 12px; backdrop-filter:blur(6px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11px;
    color:rgba(200,220,240,0.90); display:none; max-width:260px;
  }}
  #tfl-sub-sel-info .sel-title {{
    font-weight:700; color:rgba(100,200,255,0.95); font-size:10px;
    text-transform:uppercase; letter-spacing:0.08em; margin-bottom:3px;
  }}

  /* -- Address Collector Panel -- */
  #tfl-sub-collector {{
    position:absolute; bottom:40px; left:12px; z-index:95;
    background:rgba(10,20,32,0.94); border:1px solid rgba(30,144,255,0.22);
    border-radius:12px; padding:10px 12px; min-width:210px; max-width:260px;
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11.5px;
    color:rgba(210,225,240,0.90); backdrop-filter:blur(10px);
    max-height:{height - 100}px; overflow-y:auto;
    box-shadow:0 8px 28px rgba(0,0,0,0.40);
    transition: max-height 0.3s ease, opacity 0.3s ease;
  }}
  #tfl-sub-collector::-webkit-scrollbar {{ width:4px; }}
  #tfl-sub-collector::-webkit-scrollbar-thumb {{ background:rgba(30,144,255,0.25); border-radius:4px; }}
  #tfl-sub-collector::-webkit-scrollbar-track {{ background:transparent; }}
  }}
  #tfl-sub-collector.collapsed {{ max-height:32px; overflow:hidden; }}
  #tfl-sub-collector .dc-title {{
    text-transform:uppercase; letter-spacing:0.14em; font-size:8.5px;
    color:rgba(30,144,255,0.82); font-weight:700; margin-bottom:6px;
    display:flex; align-items:center; justify-content:space-between;
    cursor:pointer; user-select:none;
  }}
  #tfl-sub-collector .dc-toggle {{
    font-size:11px; color:rgba(150,175,200,0.60); transition:transform 0.25s;
  }}
  #tfl-sub-collector.collapsed .dc-toggle {{ transform:rotate(180deg); }}
  #tfl-sub-collector .dc-body {{ }}
  #tfl-sub-collector.collapsed .dc-body {{ display:none; }}
  #tfl-sub-collector .dc-item {{
    display:flex; align-items:flex-start; gap:6px; padding:5px 0;
    border-bottom:1px solid rgba(255,255,255,0.06);
  }}
  #tfl-sub-collector .dc-item:last-child {{ border-bottom:none; }}
  #tfl-sub-collector .dc-num {{
    flex-shrink:0; width:18px; height:18px; border-radius:50%;
    background:rgba(30,144,255,0.18); border:1px solid rgba(30,144,255,0.30);
    display:flex; align-items:center; justify-content:center;
    font-size:9px; font-weight:700; color:rgba(30,144,255,0.90);
  }}
  #tfl-sub-collector .dc-addr {{
    font-size:11px; line-height:1.35; color:rgba(210,230,245,0.85);
  }}
  #tfl-sub-collector .dc-coord {{
    font-size:9px; color:rgba(160,185,210,0.55); margin-top:1px;
  }}
  #tfl-sub-collector .dc-empty {{
    text-align:center; padding:10px 0; color:rgba(180,200,220,0.45); font-size:10.5px;
  }}
  #tfl-sub-collector .dc-actions {{
    display:flex; gap:6px; margin-top:6px;
  }}
  #tfl-sub-collector .dc-btn {{
    flex:1; padding:5px 8px; border-radius:8px; border:1px solid rgba(30,144,255,0.25);
    background:rgba(30,144,255,0.10); color:rgba(30,144,255,0.90); cursor:pointer;
    font-size:10px; font-weight:600; text-align:center; transition:all 0.2s;
  }}
  #tfl-sub-collector .dc-btn:hover {{ background:rgba(30,144,255,0.22); border-color:rgba(30,144,255,0.40); }}
  #tfl-sub-collector .dc-btn.clear {{ background:rgba(255,80,80,0.08); border-color:rgba(255,80,80,0.20); color:rgba(255,120,120,0.85); }}
  #tfl-sub-collector .dc-btn.clear:hover {{ background:rgba(255,80,80,0.18); }}
  #tfl-sub-badge {{
    display:none;
  }}

  /* -- Toast Notification System -- */
  #tfl-sub-toast-container {{
    position:absolute; bottom:50px; left:50%; transform:translateX(-50%); z-index:200;
    display:flex; flex-direction:column-reverse; align-items:center; gap:8px;
    pointer-events:none;
  }}
  .tfl-toast {{
    background:rgba(10,20,32,0.95); border:1px solid rgba(30,144,255,0.30);
    border-radius:10px; padding:8px 18px; backdrop-filter:blur(12px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:12px;
    color:rgba(210,230,245,0.95); box-shadow:0 6px 24px rgba(0,0,0,0.45);
    display:flex; align-items:center; gap:8px; white-space:nowrap;
    animation: tfl-toast-in 0.35s ease-out forwards;
    pointer-events:auto;
  }}
  .tfl-toast.success {{ border-color:rgba(40,180,100,0.40); }}
  .tfl-toast.success .toast-icon {{ color:#28b464; }}
  .tfl-toast.info {{ border-color:rgba(30,144,255,0.40); }}
  .tfl-toast.info .toast-icon {{ color:#1e90ff; }}
  .tfl-toast.warn {{ border-color:rgba(255,170,50,0.40); }}
  .tfl-toast.warn .toast-icon {{ color:#ffaa32; }}
  .tfl-toast.out {{ animation: tfl-toast-out 0.3s ease-in forwards; }}
  .toast-icon {{ font-size:15px; }}
  @keyframes tfl-toast-in {{ 0%{{opacity:0;transform:translateY(16px);}} 100%{{opacity:1;transform:translateY(0);}} }}
  @keyframes tfl-toast-out {{ 0%{{opacity:1;transform:translateY(0);}} 100%{{opacity:0;transform:translateY(-12px);}} }}

  /* -- Stats ribbon -- */
  #tfl-sub-stats {{
    position:absolute; top:10px; left:56px; z-index:90;
    background:rgba(10,16,26,0.88); border:1px solid rgba(100,140,180,0.15);
    border-radius:20px; padding:4px 16px; backdrop-filter:blur(8px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif; font-size:11px;
    color:rgba(200,220,240,0.85); pointer-events:none;
    display:flex; align-items:center; gap:14px; white-space:nowrap;
    animation: tfl-toast-in 0.5s ease-out 1.2s both;
  }}
  #tfl-sub-stats .stat-val {{ font-weight:700; color:rgba(100,200,255,0.95); }}
  #tfl-sub-stats .stat-sep {{ color:rgba(100,140,180,0.30); }}

  /* -- Hover tooltip -- */
  #tfl-sub-tooltip {{
    position:absolute; z-index:110; pointer-events:none;
    background:rgba(10,16,26,0.94); border:1px solid rgba(100,180,255,0.22);
    border-radius:8px; padding:5px 10px; backdrop-filter:blur(8px);
    font-family:'Avenir Next LT Pro',system-ui,sans-serif;
    color:rgba(210,230,245,0.92); display:none;
    box-shadow:0 4px 16px rgba(0,0,0,0.35);
    max-width:240px;
  }}
  #tfl-sub-tooltip .tt-name {{ font-size:11.5px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  #tfl-sub-tooltip .tt-val {{ font-size:10px; color:rgba(100,200,255,0.85); margin-top:2px; }}
  #tfl-sub-tooltip .tt-type {{ font-size:9px; color:rgba(150,175,200,0.55); margin-top:1px; }}

  /* -- Address delete button -- */
  #tfl-sub-collector .dc-del {{
    flex-shrink:0; width:16px; height:16px; border-radius:50%; margin-left:auto;
    background:rgba(255,80,80,0.08); border:1px solid rgba(255,80,80,0.20);
    color:rgba(255,120,120,0.70); font-size:10px; line-height:14px;
    text-align:center; cursor:pointer; transition:all 0.2s;
    display:flex; align-items:center; justify-content:center;
  }}
  #tfl-sub-collector .dc-del:hover {{ background:rgba(255,80,80,0.22); color:rgba(255,120,120,1); }}
</style>
<div style="width:100%;height:{height}px;position:relative;">
  <div id="tfl-subdivision-map" style="width:100%;height:100%;border-radius:14px;overflow:hidden;"></div>
  <div id="tfl-sub-legend" class="collapsed">
    <div class="leg-hdr" onclick="this.parentElement.classList.toggle('collapsed')">
      <span class="leg-title">Subdivisions &middot; click to filter</span>
      <span class="leg-toggle">&#9650;</span>
    </div>
    <div class="leg-body" id="tfl-sub-legend-body"></div>
  </div>
  <div id="tfl-sub-loading"><div class="ld-spinner"></div><div class="ld-label">Loading map layers&hellip;</div></div>
  <div id="tfl-sub-coord">&ndash;</div>
  <div id="tfl-sub-sel-info"></div>
  <div id="tfl-sub-badge">Click map or search to collect addresses</div>
  <div id="tfl-sub-toast-container"></div>
  <div id="tfl-sub-stats">
    <span><span class="stat-val" id="tfl-sub-stats-count">{total_sub}</span> subdivisions</span>
    <span class="stat-sep">|</span>
    <span>TFL est. <span class="stat-val" id="tfl-sub-stats-high">{total_sub_high_fmt}</span></span>
  </div>
  <div id="tfl-sub-tooltip"><div class="tt-name"></div><div class="tt-val"></div><div class="tt-type"></div></div>
  <div id="tfl-sub-collector">
    <div class="dc-title" onclick="this.parentElement.classList.toggle('collapsed')">
      <span>&#x1F4CD; Collected Addresses <span id="tfl-sub-addr-count">0</span></span>
      <span class="dc-toggle">&#9650;</span>
    </div>
    <div class="dc-body">
      <div id="tfl-sub-addr-list"><div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div></div>
      <div class="dc-actions">
        <div class="dc-btn" id="tfl-sub-send-forensics-btn">&#x1F50D; Send to Forensics</div>
        <div class="dc-btn" id="tfl-sub-send-batch-btn">&#x1F4E5; Send to Batch</div>
      </div>
      <div class="dc-actions" style="margin-top:4px;">
        <div class="dc-btn clear" id="tfl-sub-clear-btn">Clear</div>
      </div>
    </div>
  </div>
</div>
<script src="https://js.arcgis.com/4.30/"></script>
<script>
  const tflPoints = {payload_json};
  const baseMapId = {basemap_safe};
  const typeColors = {type_colors_json};
  const legendItems = {legend_items_json};

  /* Track hidden types for interactive legend filtering */
  const hiddenTypes = new Set();
  function broadcastAddressPayload(payload) {{
    try {{
      window.parent.postMessage(payload, "*");
    }} catch (_) {{}}
    try {{
      if (window.top && window.top !== window.parent) {{
        window.top.postMessage(payload, "*");
      }}
    }} catch (_) {{}}
    try {{
      const frames = window.parent.frames;
      for (let i = 0; i < frames.length; i++) {{
        try {{ frames[i].postMessage(payload, "*"); }} catch(_) {{}}
      }}
    }} catch (_) {{}}
  }}

  /* Build interactive legend */
  let filterCallback = null;
  (function() {{
    const body = document.getElementById("tfl-sub-legend-body");
    if (!body || legendItems.length === 0) return;
    let h = "";
    for (const e of legendItems) {{
      h += '<div class="leg-row" data-type="' + e.type + '"><div class="leg-left"><span class="leg-chip" style="background:' + e.color + ';"></span><span class="leg-label">' + e.type + '</span></div><span class="leg-count">' + e.count + '</span></div>';
    }}
    body.innerHTML = h;
    body.querySelectorAll(".leg-row").forEach(row => {{
      row.addEventListener("click", () => {{
        const t = row.getAttribute("data-type");
        if (hiddenTypes.has(t)) {{ hiddenTypes.delete(t); row.classList.remove("dimmed"); }}
        else {{ hiddenTypes.add(t); row.classList.add("dimmed"); }}
        if (filterCallback) filterCallback();
      }});
    }});
  }})();

  require([
    "esri/Map",
    "esri/views/MapView",
    "esri/layers/FeatureLayer",
    "esri/layers/GraphicsLayer",
    "esri/Graphic",
    "esri/widgets/Home",
    "esri/widgets/ScaleBar",
    "esri/widgets/BasemapToggle",
    "esri/widgets/Compass",
    "esri/widgets/Fullscreen",
    "esri/widgets/Search",
    "esri/widgets/Locate",
    "esri/widgets/Sketch",
    "esri/widgets/Expand",
    "esri/geometry/geometryEngine"
  ], function(Map, MapView, FeatureLayer, GraphicsLayer, Graphic, Home, ScaleBar, BasemapToggle, Compass, Fullscreen, Search, Locate, Sketch, Expand, geometryEngine) {{
    const map = new Map({{ basemap: baseMapId }});

    /* -- Address collector state -- */
    const collectedAddresses = [];
    const pinsLayer = new GraphicsLayer();
    const geocodeUrl = "{ARCGIS_GEOCODER_URL}";

    const districtLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL}",
      outFields: ["FID", "NAME20", "DISTRICT"],
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "$feature.NAME20" }},
        symbol: {{ type: "text", color: [73, 112, 150, 0.65], haloColor: [13, 23, 36, 0.80], haloSize: 0.6,
          font: {{ size: 8, family: "Avenir Next LT Pro", weight: "normal" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [73, 112, 150, 0.25], width: 0.6 }} }} }},
      opacity: 0.40
    }});

    const countyLayer = new FeatureLayer({{
      url: "{TEA_ARCGIS_COUNTY_LAYER_URL}",
      outFields: ["FENAME", "FIPS"],
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "$feature.FENAME + ' County'" }},
        symbol: {{ type: "text", color: [160, 140, 110, 0.80], haloColor: [13, 23, 36, 0.82], haloSize: 0.9,
          font: {{ size: 12, family: "Avenir Next LT Pro", weight: "600" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [145, 111, 63, 0.22], width: 0.6 }} }} }},
      opacity: 0.35
    }});

    const cityLayer = new FeatureLayer({{
      url: "{CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL}",
      outFields: ["NAME", "BASENAME", "GEOID", "STATE"],
      definitionExpression: "STATE = '48'",
      popupEnabled: false, labelsVisible: false,
      labelingInfo: [{{
        labelExpressionInfo: {{ expression: "DefaultValue($feature.BASENAME, $feature.NAME)" }},
        symbol: {{ type: "text", color: [165, 100, 105, 0.80], haloColor: [13, 23, 36, 0.76], haloSize: 0.7,
          font: {{ size: 9, family: "Avenir Next LT Pro", weight: "500" }} }}
      }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [0,0,0,0], outline: {{ color: [158, 42, 43, 0.12], width: 0.4 }} }} }},
      opacity: 0.20
    }});

    /* TX House & Senate district boundaries */
    const houseLayer = new FeatureLayer({{
      url: "{TEXAS_HOUSE_DISTRICTS_LAYER_URL}",
      outFields: ["*"], popupEnabled: true,
      popupTemplate: {{ title: "TX House District {{{{DISTRICT}}}}", content: "Texas House of Representatives District {{{{DISTRICT}}}}" }},
      labelsVisible: false,
      labelingInfo: [{{ labelExpressionInfo: {{ expression: "'HD ' + $feature.DISTRICT" }},
        symbol: {{ type: "text", color: [90, 180, 130, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
          font: {{ size: 8, family: "Avenir Next LT Pro", weight: "600" }} }} }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [40, 180, 100, 0.03], outline: {{ color: [40, 180, 100, 0.30], width: 0.8 }} }} }},
      opacity: 0.30, visible: false
    }});
    const senateLayer = new FeatureLayer({{
      url: "{TEXAS_SENATE_DISTRICTS_LAYER_URL}",
      outFields: ["*"], popupEnabled: true,
      popupTemplate: {{ title: "TX Senate District {{{{DISTRICT}}}}", content: "Texas Senate District {{{{DISTRICT}}}}" }},
      labelsVisible: false,
      labelingInfo: [{{ labelExpressionInfo: {{ expression: "'SD ' + $feature.DISTRICT" }},
        symbol: {{ type: "text", color: [180, 130, 90, 0.70], haloColor: [13, 23, 36, 0.75], haloSize: 0.6,
          font: {{ size: 9, family: "Avenir Next LT Pro", weight: "600" }} }} }}],
      renderer: {{ type: "simple", symbol: {{ type: "simple-fill", color: [200, 140, 60, 0.03], outline: {{ color: [200, 140, 60, 0.30], width: 0.8 }} }} }},
      opacity: 0.30, visible: false
    }});

    map.add(districtLayer);
    map.add(countyLayer);
    map.add(houseLayer);
    map.add(senateLayer);
    map.add(cityLayer);

    const graphics = new GraphicsLayer();
    const sketchLayer = new GraphicsLayer();
    map.add(graphics);
    map.add(sketchLayer);
    map.add(pinsLayer);

    const view = new MapView({{
      container: "tfl-subdivision-map",
      map,
      center: [-99.3, 31.1],
      zoom: 5,
      constraints: {{ minZoom: 5 }},
      popup: {{ dockEnabled: true, dockOptions: {{ position: "bottom-right", breakpoint: false }} }},
      ui: {{ padding: {{ top: 10, right: 10, bottom: 30, left: 10 }} }}
    }});

    /* -- Address collector helper functions -- */
    function updateCollectorUI() {{
      const listEl = document.getElementById("tfl-sub-addr-list");
      const countEl = document.getElementById("tfl-sub-addr-count");
      if (countEl) countEl.textContent = collectedAddresses.length;
      if (!listEl) return;
      if (collectedAddresses.length === 0) {{
        listEl.innerHTML = '<div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div>';
        return;
      }}
      listEl.innerHTML = collectedAddresses.map((a, i) =>
        '<div class="dc-item">'
        + '<div class="dc-num">' + (i + 1) + '</div>'
        + '<div style="flex:1;min-width:0;"><div class="dc-addr">' + (a.address || "Unknown") + '</div>'
        + '<div class="dc-coord">' + Number(a.lat).toFixed(5) + '\u00b0 N, ' + Math.abs(a.lon).toFixed(5) + '\u00b0 W</div>'
        + '</div>'
        + '<div class="dc-del" onclick="window._tflRemoveAddr(' + i + ')" title="Remove">\u00d7</div>'
        + '</div>'
      ).join("");
    }}

    /* Toast notification system */
    function showToast(message, type) {{
      type = type || "info";
      const icons = {{ success: "\u2713", info: "\u2139\uFE0F", warn: "\u26A0\uFE0F" }};
      const container = document.getElementById("tfl-sub-toast-container");
      if (!container) return;
      const toast = document.createElement("div");
      toast.className = "tfl-toast " + type;
      toast.innerHTML = '<span class="toast-icon">' + (icons[type] || "") + '</span><span>' + message + '</span>';
      container.appendChild(toast);
      setTimeout(() => {{ toast.classList.add("out"); setTimeout(() => toast.remove(), 320); }}, 2600);
    }}

    /* Remove individual address by index */
    function removeAddress(idx) {{
      if (idx < 0 || idx >= collectedAddresses.length) return;
      collectedAddresses.splice(idx, 1);
      /* Rebuild pins layer to match */
      pinsLayer.removeAll();
      collectedAddresses.forEach((a) => {{
        pinsLayer.add(new Graphic({{
          geometry: {{ type: "point", longitude: a.lon, latitude: a.lat }},
          symbol: {{ type: "simple-marker", style: "circle", size: 10, color: [30,144,255,0.85], outline: {{ color: [255,255,255,0.80], width: 1.5 }} }},
          attributes: {{ address: a.address, lat: a.lat, lon: a.lon }},
          popupTemplate: {{ title: a.address || "Point", content: "Lat: " + a.lat.toFixed(5) + ", Lon: " + a.lon.toFixed(5) }}
        }}));
      }});
      updateCollectorUI();
      showToast("Address removed", "info");
    }}
    /* Expose removeAddress globally for inline onclick */
    window._tflRemoveAddr = removeAddress;

    function addAddress(address, lat, lon) {{
      const exists = collectedAddresses.some(a =>
        Math.abs(a.lat - lat) < 0.0001 && Math.abs(a.lon - lon) < 0.0001
      );
      if (exists) {{
        showToast("Address already collected", "warn");
        return;
      }}
      collectedAddresses.push({{ address, lat, lon }});
      pinsLayer.add(new Graphic({{
        geometry: {{ type: "point", longitude: lon, latitude: lat }},
        symbol: {{ type: "simple-marker", style: "circle", size: 12, color: [30,144,255,0.85], outline: {{ color: [255,255,255,0.90], width: 2 }} }},
        attributes: {{ address, lat, lon }},
        popupTemplate: {{ title: address || "Point", content: "Lat: " + lat.toFixed(5) + ", Lon: " + lon.toFixed(5) }}
      }}));
      updateCollectorUI();
      showToast((address || "Point").substring(0, 50) + " added", "success");
      /* Fly to the newly added point */
      view.goTo({{ center: [lon, lat], zoom: Math.max(view.zoom || 10, 12) }}, {{ duration: 700, easing: "ease-in-out" }}).catch(() => {{}});
      try {{
        window.parent.postMessage({{
          type: "tfl-draw-address-found",
          address: address, lat: lat, lon: lon,
          allAddresses: collectedAddresses.slice()
        }}, "*");
      }} catch(e) {{}}
    }}

    function reverseGeocode(lat, lon) {{
      const url = geocodeUrl.replace("findAddressCandidates", "reverseGeocode")
        + "?location=" + lon + "," + lat
        + "&outSR=4326&langCode=en&f=json";
      fetch(url).then(r => r.json()).then(data => {{
        const addr = (data.address && data.address.LongLabel) || (data.address && data.address.ShortLabel) || ("Point: " + lat.toFixed(5) + ", " + lon.toFixed(5));
        addAddress(addr, lat, lon);
      }}).catch(() => {{
        addAddress("Point: " + lat.toFixed(5) + ", " + lon.toFixed(5), lat, lon);
      }});
    }}

    const formatUsd = (v) => Number(v||0).toLocaleString("en-US",{{style:"currency",currency:"USD",maximumFractionDigits:0}});
    const maxHigh = tflPoints.reduce((a, r) => Math.max(a, Number(r.high_total || 0)), 0);
    const sz = (v) => {{
      if (maxHigh <= 0) return 9;
      const n = Math.max(0, Number(v || 0));
      return Math.max(8, Math.min(30, 8 + (Math.log10(n+1)/Math.log10(maxHigh+1))*22));
    }};

    for (const row of tflPoints) {{
      const clientsHtml = row.match_clients_preview || "";
      const extraHtml = row.extra_count > 0 ? `, +${{row.extra_count}} more` : "";
      const g = new Graphic({{
        geometry: {{ type: "point", longitude: row.lon, latitude: row.lat }},
        symbol: {{
          type: "simple-marker", size: sz(row.high_total),
          color: typeColors[row.subdivision_type] || [113, 129, 145, 0.9],
          outline: {{ color: [255, 255, 255, 0.70], width: 1 }}
        }},
        attributes: row,
        popupTemplate: {{
          title: row.subdivision_name || "Political Subdivision",
          content: `<div style="font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;line-height:1.5;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(140,160,180,0.15);">
              <div style="width:10px;height:10px;border-radius:50%;background:${{(Object.values(typeColors).find((_, idx) => Object.keys(typeColors)[idx] === row.subdivision_type) || [113,129,145]).slice(0,3).map(v => typeof v === 'number' ? v : 113).join(',') }};flex-shrink:0;border:1px solid rgba(255,255,255,0.15);"></div>
              <span style="font-size:10px;color:rgba(150,175,200,0.70);text-transform:uppercase;letter-spacing:0.08em;font-weight:600;">${{row.subdivision_type}}</span>
            </div>
            <table style="border-collapse:collapse;width:100%;">
              <tr><td style="color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;">Code</td><td style="font-weight:500;">${{row.subdivision_code || "N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;">TFL high est.</td><td style="font-weight:700;color:rgba(100,200,255,0.95);">${{formatUsd(row.high_total)}}</td></tr>
              <tr><td style="color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;">Source</td><td>${{row.source_name || "N/A"}}</td></tr>
              <tr><td style="color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;">Matched clients</td><td style="font-weight:600;">${{row.match_count}}</td></tr>
            </table>
            <div style="margin-top:6px;padding-top:5px;border-top:1px solid rgba(140,160,180,0.12);font-size:10.5px;line-height:1.6;color:rgba(200,215,230,0.80);">${{clientsHtml}}${{extraHtml}}</div>
          </div>`
        }}
      }});
      graphics.add(g);
    }}

    /* Interactive legend filtering callback */
    filterCallback = () => {{
      let visCount = 0, visHigh = 0;
      graphics.graphics.forEach(g => {{
        if (g.attributes && g.attributes.subdivision_type) {{
          const vis = !hiddenTypes.has(g.attributes.subdivision_type);
          g.visible = vis;
          if (vis) {{ visCount++; visHigh += Number(g.attributes.high_total || 0); }}
        }}
      }});
      /* Update stats ribbon */
      const cEl = document.getElementById("tfl-sub-stats-count");
      const hEl = document.getElementById("tfl-sub-stats-high");
      if (cEl) cEl.textContent = visCount.toLocaleString();
      if (hEl) hEl.textContent = formatUsd(visHigh);
    }};

    const updateLabels = () => {{
      const z = Number(view.zoom || 0);
      countyLayer.labelsVisible = z >= 5;
      cityLayer.labelsVisible = z >= 6.2;
      districtLayer.labelsVisible = z >= 8.5;
      houseLayer.labelsVisible = z >= 8;
      senateLayer.labelsVisible = z >= 7;
    }};
    view.watch("zoom", updateLabels);

    /* -- Widgets -- */
    const home = new Home({{ view }});
    const basemapToggle = new BasemapToggle({{ view, nextBasemap: baseMapId === "hybrid" ? "gray-vector" : "hybrid" }});
    const scaleBar = new ScaleBar({{ view, unit: "dual" }});
    const compass = new Compass({{ view }});
    const fullscreen = new Fullscreen({{ view }});
    const locate = new Locate({{ view }});
    const search = new Search({{
      view, popupEnabled: true, resultGraphicEnabled: true,
      goToOverride: (view, opts) => view.goTo(opts.target, {{ duration: 800, easing: "ease-in-out" }})
    }});
    search.on("select-result", (evt) => {{
      if (evt.result && evt.result.feature && evt.result.feature.geometry) {{
        const geom = evt.result.feature.geometry;
        addAddress(evt.result.name || "", geom.latitude, geom.longitude);
      }}
    }});

    /* Sketch tool for encircling areas */
    const sketch = new Sketch({{
      view, layer: sketchLayer, creationMode: "single",
      availableCreateTools: ["polygon", "circle", "rectangle"],
      defaultCreateOptions: {{ mode: "freehand" }},
      visibleElements: {{ selectionTools: {{ "lasso-selection": false, "rectangle-selection": false }}, settingsMenu: false, undoRedoMenu: true }},
      defaultUpdateOptions: {{ tool: "reshape" }}
    }});
    const sketchExpand = new Expand({{
      view, content: sketch, expandIconClass: "esri-icon-polygon",
      expandTooltip: "Draw area for batch analysis", group: "tools"
    }});

    /* House/Senate layer toggle */
    const layerDiv = document.createElement("div");
    layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
    layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Legislative Districts</div>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sub-toggle-house" style="accent-color:#28b464;"><span>TX House Districts</span></label>'
      + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sub-toggle-senate" style="accent-color:#c88c3c;"><span>TX Senate Districts</span></label>';
    const layerExpand = new Expand({{
      view, content: layerDiv, expandIconClass: "esri-icon-layer-list",
      expandTooltip: "Toggle legislative districts", group: "tools"
    }});

    view.ui.add(home, "top-left");
    view.ui.add(compass, "top-left");
    view.ui.add(fullscreen, "top-left");
    view.ui.add(locate, "top-left");
    view.ui.add(sketchExpand, "top-left");
    view.ui.add(layerExpand, "top-left");
    view.ui.add(search, "top-right");
    view.ui.add(basemapToggle, "top-right");
    view.ui.add(scaleBar, "bottom-left");

    /* Wire layer toggles */
    view.when(() => {{
      const hBox = document.getElementById("tfl-sub-toggle-house");
      const sBox = document.getElementById("tfl-sub-toggle-senate");
      if (hBox) hBox.addEventListener("change", () => {{ houseLayer.visible = hBox.checked; }});
      if (sBox) sBox.addEventListener("change", () => {{ senateLayer.visible = sBox.checked; }});
    }});

    /* Sketch complete Ã¢â€ â€™ batch analysis info + address scanning */
    sketch.on("create", (evt) => {{
      if (evt.state !== "complete") return;
      const drawn = evt.graphic.geometry;
      const selInfo = document.getElementById("tfl-sub-sel-info");
      const contained = [];
      graphics.graphics.forEach((g) => {{
        if (g.visible !== false && g.geometry && geometryEngine.contains(drawn, g.geometry)) contained.push(g.attributes || {{}});
      }});
      if (selInfo && contained.length > 0) {{
        const total = contained.reduce((a,r) => a + Number(r.high_total||0), 0);
        const types = [...new Set(contained.map(r => r.subdivision_type).filter(Boolean))];
        selInfo.style.display = "block";
        selInfo.innerHTML = '<div class="sel-title">Area Selection</div>'
          + '<div><strong>' + contained.length + '</strong> subdivision(s) in area</div>'
          + '<div>Combined TFL est.: <strong>' + formatUsd(total) + '</strong></div>'
          + '<div style="font-size:10px;color:rgba(180,200,220,0.65);margin-top:3px;">' + types.join(", ") + '</div>';
        try {{ window.parent.postMessage({{ type: "tfl-map-area-select", count: contained.length, totalHigh: total, types: types }}, "*"); }} catch(e) {{}}
      }} else if (selInfo) {{
        selInfo.style.display = "block";
        selInfo.innerHTML = '<div class="sel-title">Area Selection</div><div>No subdivisions in drawn area.</div>';
        setTimeout(() => {{ selInfo.style.display = "none"; }}, 3000);
      }}

      /* Reverse-geocode sampled points within the drawn area */
      const ext = drawn.extent;
      if (ext) {{
        const cx = ext.center.longitude, cy = ext.center.latitude;
        const dx = (ext.xmax - ext.xmin), dy = (ext.ymax - ext.ymin);
        const SAMPLES = 5;
        reverseGeocode(cy, cx);
        for (let xi = 0; xi < SAMPLES; xi++) {{
          for (let yi = 0; yi < SAMPLES; yi++) {{
            const px = ext.xmin + (dx * (xi + 0.5) / SAMPLES);
            const py = ext.ymin + (dy * (yi + 0.5) / SAMPLES);
            const testPt = {{ type: "point", longitude: px, latitude: py, spatialReference: {{ wkid: 4326 }} }};
            if (geometryEngine.contains(drawn, testPt)) {{
              reverseGeocode(py, px);
            }}
          }}
        }}
        const badge = document.getElementById("tfl-sub-badge");
        if (badge) badge.textContent = "Area scanned \u2014 see collected addresses \u2192";
        setTimeout(() => {{
          try {{ window.parent.postMessage({{ type: "tfl-draw-area-addresses", allAddresses: collectedAddresses.slice() }}, "*"); }} catch(e) {{}}
        }}, 3000);
      }}
    }});

    /* Click Ã¢â€ â€™ reverse geocode for address collection */
    view.on("click", (evt) => {{
      if (evt.mapPoint) {{
        reverseGeocode(evt.mapPoint.latitude, evt.mapPoint.longitude);
      }}
    }});

    /* Coordinate readout */
    view.on("pointer-move", (evt) => {{
      const pt = view.toMap(evt);
      const el = document.getElementById("tfl-sub-coord");
      if (pt && el) el.textContent = pt.latitude.toFixed(5) + "\u00b0 N, " + Math.abs(pt.longitude).toFixed(5) + "\u00b0 W";
    }});

    /* Hover highlight + tooltip */
    let hoverHL = null;
    view.on("pointer-move", (evt) => {{
      const tooltip = document.getElementById("tfl-sub-tooltip");
      view.hitTest(evt, {{ include: [graphics] }}).then((r) => {{
        const hit = r.results && r.results.find(x => x.graphic && x.graphic.attributes && x.graphic.attributes.subdivision_name);
        document.getElementById("tfl-subdivision-map").style.cursor = hit ? "pointer" : "default";
        if (hoverHL) {{ graphics.remove(hoverHL); hoverHL = null; }}
        if (hit && hit.graphic && hit.graphic.geometry) {{
          hoverHL = new Graphic({{
            geometry: hit.graphic.geometry,
            symbol: {{ type: "simple-marker", style: "circle", size: 30, color: [255,255,255,0.0], outline: {{ color: [255,255,255,0.55], width: 2 }} }}
          }});
          graphics.add(hoverHL);
          /* Show tooltip */
          if (tooltip) {{
            const a = hit.graphic.attributes;
            tooltip.querySelector(".tt-name").textContent = a.subdivision_name || "";
            tooltip.querySelector(".tt-val").textContent = formatUsd(a.high_total);
            tooltip.querySelector(".tt-type").textContent = a.subdivision_type || "";
            tooltip.style.display = "block";
            tooltip.style.left = (evt.x + 14) + "px";
            tooltip.style.top = (evt.y - 10) + "px";
          }}
        }} else {{
          if (tooltip) tooltip.style.display = "none";
        }}
      }});
    }});

    /* -- Send to Forensics (first address) -- */
    document.getElementById("tfl-sub-send-forensics-btn").addEventListener("click", () => {{
      if (collectedAddresses.length === 0) {{ showToast("No addresses collected yet", "warn"); return; }}
      const payload = {{
        type: "tfl-send-address",
        action: "forensics",
        address: collectedAddresses[0].address || "",
        addresses: collectedAddresses.map(a => a.address),
        nonce: Date.now()
      }};
      broadcastAddressPayload(payload);
      showToast("Sent to Address Forensics", "success");
    }});

    /* -- Send All to Batch -- */
    document.getElementById("tfl-sub-send-batch-btn").addEventListener("click", () => {{
      if (collectedAddresses.length === 0) {{ showToast("No addresses collected yet", "warn"); return; }}
      const payload = {{
        type: "tfl-send-address",
        action: "batch",
        address: collectedAddresses[0].address || "",
        addresses: collectedAddresses.map(a => a.address),
        nonce: Date.now()
      }};
      broadcastAddressPayload(payload);
      showToast(collectedAddresses.length + " address(es) sent to Batch", "success");
    }});

    /* Clear button */
    document.getElementById("tfl-sub-clear-btn").addEventListener("click", () => {{
      const count = collectedAddresses.length;
      collectedAddresses.length = 0;
      pinsLayer.removeAll();
      sketchLayer.removeAll();
      updateCollectorUI();
      const badge = document.getElementById("tfl-sub-badge");
      if (badge) badge.textContent = "Click map or search to collect addresses";
      const selInfo = document.getElementById("tfl-sub-sel-info");
      if (selInfo) selInfo.style.display = "none";
      if (count > 0) showToast(count + " address(es) cleared", "info");
    }});

    view.when(() => {{
      const loader = document.getElementById("tfl-sub-loading");
      const ldLabel = loader && loader.querySelector(".ld-label");
      if (ldLabel) ldLabel.textContent = "Rendering " + tflPoints.length + " subdivisions\u2026";
      setTimeout(() => {{
        if (ldLabel) ldLabel.textContent = "Almost ready\u2026";
      }}, 600);
      setTimeout(() => {{
        if (loader) {{ loader.style.opacity = "0"; setTimeout(() => loader.remove(), 600); }}
      }}, 900);
      updateLabels();
      if (graphics.graphics.length > 0) {{
        view.goTo(graphics.graphics.toArray(), {{ padding: {{ top: 50, right: 50, bottom: 50, left: 50 }}, duration: 1000, easing: "ease-in-out" }}).catch(() => {{}});
      }}
    }});
  }});
</script>
"""
    )
    _persistent_html_frame(
        html=arcgis_html,
        signature=subdivision_map_signature,
        height=int(height) + 8,
        key="mp5_tfl_subdivision_map_v3",
        default=None,
    )

__all__ = [
    '_atlas_bridge',
    'render_address_overlap_arcgis_map',
    'render_draw_area_search_map',
    'render_tfl_school_district_arcgis_map',
    'render_tfl_subdivision_arcgis_map',
]

