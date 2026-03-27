
(function () {
  let app = null;
  let booting = false;
  let pendingArgs = null;
  let arcgisAssetsPromise = null;
  const ARC_GIS_JS_URL = "https://js.arcgis.com/4.30/";
  const ARC_GIS_CSS_URL = "https://js.arcgis.com/4.30/esri/themes/dark/main.css";

  function send(type, extra) {
    const msg = { isStreamlitMessage: true, type: type };
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        msg[key] = extra[key];
      });
    }
    window.parent.postMessage(msg, "*");
  }

  send("streamlit:componentReady", { apiVersion: 1 });
  send("streamlit:setFrameHeight", { height: 648 });

  function setFrameHeight(height) {
    send("streamlit:setFrameHeight", { height: height });
  }

  function el(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatUsd(value) {
    return Number(value || 0).toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0
    });
  }

  function normalizeArgs(raw) {
    const args = raw || {};
    return {
      payload: Array.isArray(args.payload) ? args.payload : [],
      signature: String(args.signature || ""),
      basemap: String(args.basemap || "gray-vector").trim() || "gray-vector",
      height: Math.max(320, Number(args.height || 640)),
      typeColors: args.type_colors || {},
      typeHexColors: args.type_hex_colors || {},
      urls: args.urls || {}
    };
  }

  function ensureArcgisAssets() {
    if (typeof window.require === "function") {
      return Promise.resolve();
    }
    if (arcgisAssetsPromise) {
      return arcgisAssetsPromise;
    }
    arcgisAssetsPromise = new Promise(function (resolve, reject) {
      if (!document.querySelector('link[data-tfl-arcgis-theme="1"]')) {
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = ARC_GIS_CSS_URL;
        css.setAttribute("data-tfl-arcgis-theme", "1");
        document.head.appendChild(css);
      }
      const script = document.createElement("script");
      script.src = ARC_GIS_JS_URL;
      script.async = true;
      script.onload = function () {
        resolve();
      };
      script.onerror = function () {
        reject(new Error("ArcGIS loader failed"));
      };
      document.head.appendChild(script);
    });
    return arcgisAssetsPromise;
  }

  function broadcastBridge(payload) {
    try {
      const frames = window.parent.frames;
      for (let i = 0; i < frames.length; i += 1) {
        try {
          frames[i].postMessage(payload, "*");
        } catch (err) {
        }
      }
    } catch (err) {
    }
  }

  function setShellHeight(height) {
    const root = el("root");
    const collector = el("tfl-sub-collector");
    if (root) {
      root.style.height = height + "px";
    }
    if (collector) {
      collector.style.maxHeight = Math.max(180, height - 100) + "px";
    }
  }

  function showToast(message, type) {
    const container = el("tfl-sub-toast-container");
    const icons = { success: "\u2713", info: "\u2139\uFE0F", warn: "\u26A0\uFE0F" };
    if (!container) {
      return;
    }
    const toast = document.createElement("div");
    toast.className = "tfl-toast " + (type || "info");
    toast.innerHTML = '<span class="toast-icon">' + (icons[type || "info"] || "") + '</span><span>' + escapeHtml(message) + "</span>";
    container.appendChild(toast);
    window.setTimeout(function () {
      toast.classList.add("out");
      window.setTimeout(function () {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 320);
    }, 2600);
  }

  function updateCollectorUI() {
    const countEl = el("tfl-sub-addr-count");
    const listEl = el("tfl-sub-addr-list");
    if (!app) {
      return;
    }
    if (countEl) {
      countEl.textContent = String(app.collectedAddresses.length);
    }
    if (!listEl) {
      return;
    }
    if (!app.collectedAddresses.length) {
      listEl.innerHTML = '<div class="dc-empty">Click on the map, use Search, or draw an area to collect addresses.</div>';
      return;
    }
    listEl.innerHTML = app.collectedAddresses.map(function (addr, index) {
      return (
        '<div class="dc-item">'
        + '<div class="dc-num">' + (index + 1) + "</div>"
        + '<div style="flex:1;min-width:0;">'
        + '<div class="dc-addr">' + escapeHtml(addr.address || "Unknown") + "</div>"
        + '<div class="dc-coord">' + Number(addr.lat).toFixed(5) + "\u00b0 N, " + Math.abs(Number(addr.lon)).toFixed(5) + "\u00b0 W</div>'
        + "</div>"
        + '<div class="dc-del" onclick="window._tflRemoveAddr(' + index + ')" title="Remove">\u00d7</div>'
        + "</div>"
      );
    }).join("");
  }

  function clearCollectedAddresses(options) {
    const opts = options || {};
    if (!app) {
      return;
    }
    const count = app.collectedAddresses.length;
    app.collectedAddresses.length = 0;
    if (app.pinsLayer) {
      app.pinsLayer.removeAll();
    }
    if (app.sketchLayer) {
      app.sketchLayer.removeAll();
    }
    if (app.view && app.view.graphics) {
      app.view.graphics.removeAll();
    }
    updateCollectorUI();
    if (el("tfl-sub-badge")) {
      el("tfl-sub-badge").textContent = "Click map or search to collect addresses";
    }
    if (el("tfl-sub-sel-info")) {
      el("tfl-sub-sel-info").style.display = "none";
    }
    if (!opts.silent && count > 0) {
      showToast(count + " address(es) cleared", "info");
    }
  }

  function removeAddress(index) {
    if (!app || index < 0 || index >= app.collectedAddresses.length) {
      return;
    }
    app.collectedAddresses.splice(index, 1);
    if (app.pinsLayer) {
      app.pinsLayer.removeAll();
      app.collectedAddresses.forEach(function (addr) {
        app.pinsLayer.add(new app.Graphic({
          geometry: { type: "point", longitude: addr.lon, latitude: addr.lat },
          symbol: {
            type: "simple-marker",
            style: "circle",
            size: 10,
            color: [30, 144, 255, 0.85],
            outline: { color: [255, 255, 255, 0.8], width: 1.5 }
          },
          attributes: { address: addr.address, lat: addr.lat, lon: addr.lon },
          popupTemplate: {
            title: addr.address || "Point",
            content: "Lat: " + Number(addr.lat).toFixed(5) + ", Lon: " + Number(addr.lon).toFixed(5)
          }
        }));
      });
    }
    updateCollectorUI();
    showToast("Address removed", "info");
  }

  function addAddress(address, lat, lon) {
    if (!app) {
      return;
    }
    const latVal = Number(lat);
    const lonVal = Number(lon);
    const exists = app.collectedAddresses.some(function (addr) {
      return Math.abs(Number(addr.lat) - latVal) < 0.0001 && Math.abs(Number(addr.lon) - lonVal) < 0.0001;
    });
    if (exists) {
      showToast("Address already collected", "warn");
      return;
    }
    app.collectedAddresses.push({ address: address || "", lat: latVal, lon: lonVal });
    app.pinsLayer.add(new app.Graphic({
      geometry: { type: "point", longitude: lonVal, latitude: latVal },
      symbol: {
        type: "simple-marker",
        style: "circle",
        size: 12,
        color: [30, 144, 255, 0.85],
        outline: { color: [255, 255, 255, 0.9], width: 2 }
      },
      attributes: { address: address || "", lat: latVal, lon: lonVal },
      popupTemplate: {
        title: address || "Point",
        content: "Lat: " + latVal.toFixed(5) + ", Lon: " + lonVal.toFixed(5)
      }
    }));
    updateCollectorUI();
    showToast(((address || "Point").slice(0, 50)) + " added", "success");
    if (app.view) {
      app.view.goTo({ center: [lonVal, latVal], zoom: Math.max(app.view.zoom || 10, 12) }, { duration: 700, easing: "ease-in-out" }).catch(function () {});
    }
    try {
      window.parent.postMessage({
        type: "tfl-draw-address-found",
        address: address || "",
        lat: latVal,
        lon: lonVal,
        allAddresses: app.collectedAddresses.slice()
      }, "*");
    } catch (err) {
    }
  }

  function reverseGeocode(lat, lon) {
    if (!app || !app.urls.geocode) {
      addAddress("Point: " + Number(lat).toFixed(5) + ", " + Number(lon).toFixed(5), lat, lon);
      return;
    }
    const url = app.urls.geocode.replace("findAddressCandidates", "reverseGeocode")
      + "?location=" + lon + "," + lat
      + "&outSR=4326&langCode=en&f=json";
    fetch(url)
      .then(function (response) { return response.json(); })
      .then(function (data) {
        const addr = (data.address && (data.address.LongLabel || data.address.ShortLabel)) || ("Point: " + Number(lat).toFixed(5) + ", " + Number(lon).toFixed(5));
        addAddress(addr, lat, lon);
      })
      .catch(function () {
        addAddress("Point: " + Number(lat).toFixed(5) + ", " + Number(lon).toFixed(5), lat, lon);
      });
  }

  function markerSize(highTotal) {
    if (!app || !(app.maxHigh > 0)) {
      return 9;
    }
    const value = Math.max(0, Number(highTotal || 0));
    return Math.max(8, Math.min(30, 8 + (Math.log10(value + 1) / Math.log10(app.maxHigh + 1)) * 22));
  }

  function popupHtml(row) {
    const colorHex = app.typeHexColors[row.subdivision_type] || "#718191";
    const preview = String(row.match_clients_preview || "");
    const extra = Number(row.extra_count || 0) > 0 ? ", +" + Number(row.extra_count || 0) + " more" : "";
    return (
      "<div style=\"font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;line-height:1.5;\">"
      + "<div style=\"display:flex;align-items:center;gap:8px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(140,160,180,0.15);\">"
      + "<div style=\"width:10px;height:10px;border-radius:50%;background:" + escapeHtml(colorHex) + ";flex-shrink:0;border:1px solid rgba(255,255,255,0.15);\"></div>"
      + "<span style=\"font-size:10px;color:rgba(150,175,200,0.70);text-transform:uppercase;letter-spacing:0.08em;font-weight:600;\">" + escapeHtml(row.subdivision_type || "") + "</span>"
      + "</div>"
      + "<table style=\"border-collapse:collapse;width:100%;\">"
      + "<tr><td style=\"color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;\">Code</td><td style=\"font-weight:500;\">" + escapeHtml(row.subdivision_code || "N/A") + "</td></tr>"
      + "<tr><td style=\"color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;\">TFL high est.</td><td style=\"font-weight:700;color:rgba(100,200,255,0.95);\">" + escapeHtml(formatUsd(row.high_total)) + "</td></tr>"
      + "<tr><td style=\"color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;\">Source</td><td>" + escapeHtml(row.source_name || "N/A") + "</td></tr>"
      + "<tr><td style=\"color:#7a94ab;padding:3px 8px 3px 0;font-size:11px;\">Matched clients</td><td style=\"font-weight:600;\">" + escapeHtml(row.match_count || 0) + "</td></tr>"
      + "</table>"
      + "<div style=\"margin-top:6px;padding-top:5px;border-top:1px solid rgba(140,160,180,0.12);font-size:10.5px;line-height:1.6;color:rgba(200,215,230,0.80);\">" + escapeHtml(preview) + escapeHtml(extra) + "</div>"
      + "</div>"
    );
  }

  function updateStats() {
    const countEl = el("tfl-sub-stats-count");
    const highEl = el("tfl-sub-stats-high");
    let visibleCount = 0;
    let visibleHigh = 0;
    if (app && app.dataLayer) {
      app.dataLayer.graphics.forEach(function (graphic) {
        if (graphic.visible !== false && graphic.attributes) {
          visibleCount += 1;
          visibleHigh += Number(graphic.attributes.high_total || 0);
        }
      });
    }
    if (countEl) {
      countEl.textContent = visibleCount.toLocaleString();
    }
    if (highEl) {
      highEl.textContent = formatUsd(visibleHigh);
    }
  }

  function applyLegendFilter() {
    if (!app || !app.dataLayer) {
      return;
    }
    app.dataLayer.graphics.forEach(function (graphic) {
      if (!graphic.attributes || !graphic.attributes.subdivision_type) {
        return;
      }
      graphic.visible = !app.hiddenTypes.has(graphic.attributes.subdivision_type);
    });
    updateStats();
  }

  function renderLegend() {
    const body = el("tfl-sub-legend-body");
    if (!body || !app) {
      return;
    }
    const counts = {};
    app.payload.forEach(function (row) {
      const key = String(row.subdivision_type || "").trim();
      if (!key) {
        return;
      }
      counts[key] = (counts[key] || 0) + 1;
    });
    body.innerHTML = "";
    Object.keys(counts).sort(function (a, b) {
      if (counts[b] !== counts[a]) {
        return counts[b] - counts[a];
      }
      return a.localeCompare(b);
    }).forEach(function (type) {
      const row = document.createElement("div");
      row.className = "leg-row";
      row.setAttribute("data-type", type);
      row.innerHTML = '<div class="leg-left"><span class="leg-chip" style="background:' + escapeHtml(app.typeHexColors[type] || "#718191") + ';"></span><span class="leg-label">' + escapeHtml(type) + '</span></div><span class="leg-count">' + counts[type] + "</span>";
      row.addEventListener("click", function () {
        if (app.hiddenTypes.has(type)) {
          app.hiddenTypes.delete(type);
          row.classList.remove("dimmed");
        } else {
          app.hiddenTypes.add(type);
          row.classList.add("dimmed");
        }
        applyLegendFilter();
      });
      body.appendChild(row);
    });
  }

  function fitToGraphics() {
    if (!app || !app.view || !app.dataLayer || !app.view.ready) {
      return;
    }
    const graphics = app.dataLayer.graphics.toArray().filter(function (graphic) {
      return graphic.visible !== false;
    });
    if (!graphics.length) {
      return;
    }
    app.view.goTo(graphics, {
      padding: { top: 50, right: 50, bottom: 50, left: 50 },
      duration: 1000,
      easing: "ease-in-out"
    }).catch(function () {});
  }

  function resetTransientState() {
    if (!app) {
      return;
    }
    app.hiddenTypes.clear();
    if (app.hoverLayer) {
      app.hoverLayer.removeAll();
    }
    if (app.view && app.view.popup) {
      app.view.popup.close();
    }
    clearCollectedAddresses({ silent: true });
    if (el("tfl-sub-tooltip")) {
      el("tfl-sub-tooltip").style.display = "none";
    }
    if (el("tfl-sub-sel-info")) {
      el("tfl-sub-sel-info").style.display = "none";
    }
    if (el("tfl-sub-legend")) {
      el("tfl-sub-legend").classList.add("collapsed");
    }
    document.querySelectorAll("#tfl-sub-legend .leg-row.dimmed").forEach(function (row) {
      row.classList.remove("dimmed");
    });
    if (el("tfl-sub-collector")) {
      el("tfl-sub-collector").classList.remove("collapsed");
    }
    if (el("tfl-sub-toggle-house")) {
      el("tfl-sub-toggle-house").checked = false;
    }
    if (el("tfl-sub-toggle-senate")) {
      el("tfl-sub-toggle-senate").checked = false;
    }
    if (app.houseLayer) {
      app.houseLayer.visible = false;
    }
    if (app.senateLayer) {
      app.senateLayer.visible = false;
    }
  }

  function rebuildDataGraphics() {
    if (!app) {
      return;
    }
    app.maxHigh = 0;
    app.dataLayer.removeAll();
    app.payload.forEach(function (row) {
      app.maxHigh = Math.max(app.maxHigh, Number(row.high_total || 0));
    });
    app.payload.forEach(function (row) {
      app.dataLayer.add(new app.Graphic({
        geometry: {
          type: "point",
          longitude: Number(row.lon || 0),
          latitude: Number(row.lat || 0)
        },
        symbol: {
          type: "simple-marker",
          size: markerSize(row.high_total),
          color: app.typeColors[row.subdivision_type] || [113, 129, 145, 0.9],
          outline: { color: [255, 255, 255, 0.7], width: 1 }
        },
        attributes: row,
        popupTemplate: {
          title: row.subdivision_name || "Political Subdivision",
          content: popupHtml(row)
        }
      }));
    });
  }

  function updateLabels() {
    if (!app || !app.view) {
      return;
    }
    const zoom = Number(app.view.zoom || 0);
    app.countyLayer.labelsVisible = zoom >= 5;
    app.cityLayer.labelsVisible = zoom >= 6.2;
    app.districtLayer.labelsVisible = zoom >= 8.5;
    app.houseLayer.labelsVisible = zoom >= 8;
    app.senateLayer.labelsVisible = zoom >= 7;
  }

  function applyArgs(args) {
    if (!app) {
      return;
    }
    app.urls = args.urls;
    app.typeColors = args.typeColors;
    app.typeHexColors = args.typeHexColors;
    app.payload = args.payload;
    setShellHeight(args.height);
    if (app.view) {
      window.setTimeout(function () {
        app.view.resize();
      }, 0);
    }
    if (app.map && app.currentBasemap !== args.basemap) {
      app.currentBasemap = args.basemap;
      app.map.basemap = args.basemap;
    }
    if (app.basemapToggle) {
      app.basemapToggle.nextBasemap = args.basemap === "hybrid" ? "gray-vector" : "hybrid";
    }
    resetTransientState();
    if (args.signature !== app.signature) {
      app.signature = args.signature;
      rebuildDataGraphics();
      renderLegend();
    }
    applyLegendFilter();
    updateLabels();
    fitToGraphics();
  }

  function bootApp(args) {
    if (booting || app) {
      return;
    }
    booting = true;
    ensureArcgisAssets().then(function () {
      if (el("tfl-sub-loading")) {
        const label = el("tfl-sub-loading").querySelector(".ld-label");
        if (label) {
          label.textContent = "Loading map layers...";
        }
      }
      window.require([
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
      ], function (
      Map,
      MapView,
      FeatureLayer,
      GraphicsLayer,
      Graphic,
      Home,
      ScaleBar,
      BasemapToggle,
      Compass,
      Fullscreen,
      Search,
      Locate,
      Sketch,
      Expand,
      geometryEngine
    ) {
      const map = new Map({ basemap: args.basemap });
      const districtLayer = new FeatureLayer({
        url: args.urls.school_districts,
        outFields: ["FID", "NAME20", "DISTRICT"],
        popupEnabled: false,
        labelsVisible: false,
        labelingInfo: [{
          labelExpressionInfo: { expression: "$feature.NAME20" },
          symbol: { type: "text", color: [73, 112, 150, 0.65], haloColor: [13, 23, 36, 0.8], haloSize: 0.6, font: { size: 8, family: "Avenir Next LT Pro", weight: "normal" } }
        }],
        renderer: { type: "simple", symbol: { type: "simple-fill", color: [0, 0, 0, 0], outline: { color: [73, 112, 150, 0.25], width: 0.6 } } },
        opacity: 0.4
      });
      const countyLayer = new FeatureLayer({
        url: args.urls.counties,
        outFields: ["FENAME", "FIPS"],
        popupEnabled: false,
        labelsVisible: false,
        labelingInfo: [{
          labelExpressionInfo: { expression: "$feature.FENAME + ' County'" },
          symbol: { type: "text", color: [160, 140, 110, 0.8], haloColor: [13, 23, 36, 0.82], haloSize: 0.9, font: { size: 12, family: "Avenir Next LT Pro", weight: "600" } }
        }],
        renderer: { type: "simple", symbol: { type: "simple-fill", color: [0, 0, 0, 0], outline: { color: [145, 111, 63, 0.22], width: 0.6 } } },
        opacity: 0.35
      });
      const cityLayer = new FeatureLayer({
        url: args.urls.cities,
        outFields: ["NAME", "BASENAME", "GEOID", "STATE"],
        definitionExpression: "STATE = '48'",
        popupEnabled: false,
        labelsVisible: false,
        labelingInfo: [{
          labelExpressionInfo: { expression: "DefaultValue($feature.BASENAME, $feature.NAME)" },
          symbol: { type: "text", color: [165, 100, 105, 0.8], haloColor: [13, 23, 36, 0.76], haloSize: 0.7, font: { size: 9, family: "Avenir Next LT Pro", weight: "500" } }
        }],
        renderer: { type: "simple", symbol: { type: "simple-fill", color: [0, 0, 0, 0], outline: { color: [158, 42, 43, 0.12], width: 0.4 } } },
        opacity: 0.2
      });
      const houseLayer = new FeatureLayer({
        url: args.urls.house_districts,
        outFields: ["*"],
        popupEnabled: true,
        popupTemplate: { title: "TX House District {DISTRICT}", content: "Texas House of Representatives District {DISTRICT}" },
        labelsVisible: false,
        labelingInfo: [{
          labelExpressionInfo: { expression: "'HD ' + $feature.DISTRICT" },
          symbol: { type: "text", color: [90, 180, 130, 0.7], haloColor: [13, 23, 36, 0.75], haloSize: 0.6, font: { size: 8, family: "Avenir Next LT Pro", weight: "600" } }
        }],
        renderer: { type: "simple", symbol: { type: "simple-fill", color: [40, 180, 100, 0.03], outline: { color: [40, 180, 100, 0.3], width: 0.8 } } },
        opacity: 0.3,
        visible: false
      });
      const senateLayer = new FeatureLayer({
        url: args.urls.senate_districts,
        outFields: ["*"],
        popupEnabled: true,
        popupTemplate: { title: "TX Senate District {DISTRICT}", content: "Texas Senate District {DISTRICT}" },
        labelsVisible: false,
        labelingInfo: [{
          labelExpressionInfo: { expression: "'SD ' + $feature.DISTRICT" },
          symbol: { type: "text", color: [180, 130, 90, 0.7], haloColor: [13, 23, 36, 0.75], haloSize: 0.6, font: { size: 9, family: "Avenir Next LT Pro", weight: "600" } }
        }],
        renderer: { type: "simple", symbol: { type: "simple-fill", color: [200, 140, 60, 0.03], outline: { color: [200, 140, 60, 0.3], width: 0.8 } } },
        opacity: 0.3,
        visible: false
      });
      const dataLayer = new GraphicsLayer();
      const hoverLayer = new GraphicsLayer();
      const sketchLayer = new GraphicsLayer();
      const pinsLayer = new GraphicsLayer();
      map.add(districtLayer);
      map.add(countyLayer);
      map.add(houseLayer);
      map.add(senateLayer);
      map.add(cityLayer);
      map.add(dataLayer);
      map.add(sketchLayer);
      map.add(pinsLayer);
      map.add(hoverLayer);

      const view = new MapView({
        container: "tfl-subdivision-map",
        map: map,
        center: [-99.3, 31.1],
        zoom: 5,
        constraints: { minZoom: 5 },
        popup: { dockEnabled: true, dockOptions: { position: "bottom-right", breakpoint: false } },
        ui: { padding: { top: 10, right: 10, bottom: 30, left: 10 } }
      });

      app = {
        Map: Map,
        Graphic: Graphic,
        geometryEngine: geometryEngine,
        map: map,
        view: view,
        dataLayer: dataLayer,
        hoverLayer: hoverLayer,
        sketchLayer: sketchLayer,
        pinsLayer: pinsLayer,
        districtLayer: districtLayer,
        countyLayer: countyLayer,
        cityLayer: cityLayer,
        houseLayer: houseLayer,
        senateLayer: senateLayer,
        currentBasemap: args.basemap,
        signature: "",
        payload: [],
        maxHigh: 0,
        typeColors: {},
        typeHexColors: {},
        urls: args.urls,
        hiddenTypes: new Set(),
        collectedAddresses: [],
        basemapToggle: null,
        sketch: null
      };
      window._tflRemoveAddr = removeAddress;

      const home = new Home({ view: view });
      const basemapToggle = new BasemapToggle({ view: view, nextBasemap: args.basemap === "hybrid" ? "gray-vector" : "hybrid" });
      const scaleBar = new ScaleBar({ view: view, unit: "dual" });
      const compass = new Compass({ view: view });
      const fullscreen = new Fullscreen({ view: view });
      const locate = new Locate({ view: view });
      const search = new Search({
        view: view,
        popupEnabled: true,
        resultGraphicEnabled: true,
        goToOverride: function (targetView, options) {
          return targetView.goTo(options.target, { duration: 800, easing: "ease-in-out" });
        }
      });
      search.on("select-result", function (evt) {
        if (evt.result && evt.result.feature && evt.result.feature.geometry) {
          addAddress(evt.result.name || "", evt.result.feature.geometry.latitude, evt.result.feature.geometry.longitude);
        }
      });

      const sketch = new Sketch({
        view: view,
        layer: sketchLayer,
        creationMode: "single",
        availableCreateTools: ["polygon", "circle", "rectangle"],
        defaultCreateOptions: { mode: "freehand" },
        visibleElements: { selectionTools: { "lasso-selection": false, "rectangle-selection": false }, settingsMenu: false, undoRedoMenu: true },
        defaultUpdateOptions: { tool: "reshape" }
      });
      const sketchExpand = new Expand({
        view: view,
        content: sketch,
        expandIconClass: "esri-icon-polygon",
        expandTooltip: "Draw area for batch analysis",
        group: "tools"
      });

      const layerDiv = document.createElement("div");
      layerDiv.style.cssText = "background:rgba(13,23,36,0.94);border-radius:8px;padding:10px;font-family:'Avenir Next LT Pro',system-ui,sans-serif;font-size:12px;color:rgba(210,225,240,0.90);min-width:160px;";
      layerDiv.innerHTML = '<div style="font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(150,175,200,0.65);font-weight:700;margin-bottom:6px;">Legislative Districts</div>'
        + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sub-toggle-house" style="accent-color:#28b464;"><span>TX House Districts</span></label>'
        + '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;"><input type="checkbox" id="tfl-sub-toggle-senate" style="accent-color:#c88c3c;"><span>TX Senate Districts</span></label>';
      const layerExpand = new Expand({
        view: view,
        content: layerDiv,
        expandIconClass: "esri-icon-layer-list",
        expandTooltip: "Toggle legislative districts",
        group: "tools"
      });

      app.basemapToggle = basemapToggle;
      app.sketch = sketch;

      view.ui.add(home, "top-left");
      view.ui.add(compass, "top-left");
      view.ui.add(fullscreen, "top-left");
      view.ui.add(locate, "top-left");
      view.ui.add(sketchExpand, "top-left");
      view.ui.add(layerExpand, "top-left");
      view.ui.add(search, "top-right");
      view.ui.add(basemapToggle, "top-right");
      view.ui.add(scaleBar, "bottom-left");

      el("tfl-sub-legend-toggle").addEventListener("click", function () {
        el("tfl-sub-legend").classList.toggle("collapsed");
      });
      el("tfl-sub-collector-toggle").addEventListener("click", function () {
        el("tfl-sub-collector").classList.toggle("collapsed");
      });
      el("tfl-sub-send-forensics-btn").addEventListener("click", function () {
        if (!app.collectedAddresses.length) {
          showToast("No addresses collected yet", "warn");
          return;
        }
        broadcastBridge({
          type: "tfl-send-address",
          action: "forensics",
          address: app.collectedAddresses[0].address || "",
          addresses: app.collectedAddresses.map(function (addr) { return addr.address; }),
          nonce: Date.now()
        });
        showToast("Sent to Address Forensics", "success");
      });
      el("tfl-sub-send-batch-btn").addEventListener("click", function () {
        if (!app.collectedAddresses.length) {
          showToast("No addresses collected yet", "warn");
          return;
        }
        broadcastBridge({
          type: "tfl-send-address",
          action: "batch",
          address: app.collectedAddresses[0].address || "",
          addresses: app.collectedAddresses.map(function (addr) { return addr.address; }),
          nonce: Date.now()
        });
        showToast(app.collectedAddresses.length + " address(es) sent to Batch", "success");
      });
      el("tfl-sub-clear-btn").addEventListener("click", function () {
        clearCollectedAddresses();
      });

      view.when(function () {
        window.setTimeout(function () {
          const loader = el("tfl-sub-loading");
          if (loader) {
            loader.style.opacity = "0";
            window.setTimeout(function () {
              if (loader.parentNode) {
                loader.parentNode.removeChild(loader);
              }
            }, 600);
          }
        }, 900);
        updateLabels();
        const houseBox = el("tfl-sub-toggle-house");
        const senateBox = el("tfl-sub-toggle-senate");
        if (houseBox) {
          houseBox.addEventListener("change", function () {
            houseLayer.visible = !!houseBox.checked;
          });
        }
        if (senateBox) {
          senateBox.addEventListener("change", function () {
            senateLayer.visible = !!senateBox.checked;
          });
        }
        applyArgs(pendingArgs || args);
      });

      view.watch("zoom", updateLabels);
      view.on("click", function (evt) {
        if (evt.mapPoint) {
          reverseGeocode(evt.mapPoint.latitude, evt.mapPoint.longitude);
        }
      });
      view.on("pointer-move", function (evt) {
        const point = view.toMap(evt);
        if (point && el("tfl-sub-coord")) {
          el("tfl-sub-coord").textContent = point.latitude.toFixed(5) + "\u00b0 N, " + Math.abs(point.longitude).toFixed(5) + "\u00b0 W";
        }
      });
      view.on("pointer-move", function (evt) {
        const tooltip = el("tfl-sub-tooltip");
        view.hitTest(evt, { include: [dataLayer] }).then(function (result) {
          const hit = result.results && result.results.find(function (entry) {
            return entry.graphic && entry.graphic.attributes && entry.graphic.attributes.subdivision_name;
          });
          el("tfl-subdivision-map").style.cursor = hit ? "pointer" : "default";
          hoverLayer.removeAll();
          if (hit && hit.graphic && hit.graphic.geometry) {
            hoverLayer.add(new Graphic({
              geometry: hit.graphic.geometry,
              symbol: { type: "simple-marker", style: "circle", size: 30, color: [255, 255, 255, 0], outline: { color: [255, 255, 255, 0.55], width: 2 } }
            }));
            if (tooltip) {
              tooltip.querySelector(".tt-name").textContent = hit.graphic.attributes.subdivision_name || "";
              tooltip.querySelector(".tt-val").textContent = formatUsd(hit.graphic.attributes.high_total);
              tooltip.querySelector(".tt-type").textContent = hit.graphic.attributes.subdivision_type || "";
              tooltip.style.display = "block";
              tooltip.style.left = (evt.x + 14) + "px";
              tooltip.style.top = (evt.y - 10) + "px";
            }
          } else if (tooltip) {
            tooltip.style.display = "none";
          }
        });
      });

      sketch.on("create", function (evt) {
        if (evt.state !== "complete") {
          return;
        }
        const drawn = evt.graphic.geometry;
        const contained = [];
        dataLayer.graphics.forEach(function (graphic) {
          if (graphic.visible !== false && graphic.geometry && geometryEngine.contains(drawn, graphic.geometry)) {
            contained.push(graphic.attributes || {});
          }
        });
        const selInfo = el("tfl-sub-sel-info");
        if (selInfo && contained.length > 0) {
          const total = contained.reduce(function (sum, row) { return sum + Number(row.high_total || 0); }, 0);
          const types = Array.from(new Set(contained.map(function (row) { return row.subdivision_type; }).filter(Boolean)));
          selInfo.style.display = "block";
          selInfo.innerHTML = '<div class="sel-title">Area Selection</div>'
            + '<div><strong>' + contained.length + '</strong> subdivision(s) in area</div>'
            + '<div>Combined TFL est.: <strong>' + escapeHtml(formatUsd(total)) + '</strong></div>'
            + '<div style="font-size:10px;color:rgba(180,200,220,0.65);margin-top:3px;">' + escapeHtml(types.join(", ")) + "</div>";
          try {
            window.parent.postMessage({ type: "tfl-map-area-select", count: contained.length, totalHigh: total, types: types }, "*");
          } catch (err) {
          }
        } else if (selInfo) {
          selInfo.style.display = "block";
          selInfo.innerHTML = '<div class="sel-title">Area Selection</div><div>No subdivisions in drawn area.</div>';
          window.setTimeout(function () {
            selInfo.style.display = "none";
          }, 3000);
        }
        const ext = drawn.extent;
        if (!ext) {
          return;
        }
        const centerX = ext.center.longitude;
        const centerY = ext.center.latitude;
        const width = ext.xmax - ext.xmin;
        const height = ext.ymax - ext.ymin;
        const samples = 5;
        reverseGeocode(centerY, centerX);
        for (let xi = 0; xi < samples; xi += 1) {
          for (let yi = 0; yi < samples; yi += 1) {
            const px = ext.xmin + (width * (xi + 0.5) / samples);
            const py = ext.ymin + (height * (yi + 0.5) / samples);
            const testPoint = { type: "point", longitude: px, latitude: py, spatialReference: { wkid: 4326 } };
            if (geometryEngine.contains(drawn, testPoint)) {
              reverseGeocode(py, px);
            }
          }
        }
        if (el("tfl-sub-badge")) {
          el("tfl-sub-badge").textContent = "Area scanned \u2014 see collected addresses \u2192";
        }
        window.setTimeout(function () {
          try {
            window.parent.postMessage({ type: "tfl-draw-area-addresses", allAddresses: app.collectedAddresses.slice() }, "*");
          } catch (err) {
          }
        }, 3000);
      });

      booting = false;
      });
    }).catch(function () {
      booting = false;
      const loader = el("tfl-sub-loading");
      if (loader) {
        const label = loader.querySelector(".ld-label");
        if (label) {
          label.textContent = "Map libraries failed to load.";
        }
      }
    });
  }

  function handleRender(rawArgs) {
    const args = normalizeArgs(rawArgs);
    pendingArgs = args;
    setShellHeight(args.height);
    setFrameHeight(args.height + 8);
    if (app) {
      applyArgs(args);
      return;
    }
    bootApp(args);
  }

  window.addEventListener("message", function (event) {
    const data = event.data;
    if (!data) {
      return;
    }
    if (data.type === "streamlit:render") {
      handleRender(data.args || {});
    }
  });
})();
