/**
 * BMS / RMS Dashboard — line_1 (折线1) SVG card renderer.
 */
(function (global) {
  "use strict";

  var DEFAULT_LINE_COLOR = "#63aa82";
  var VALUE_MODES = ["sum", "latest", "average", "max"];

  function fmtNum(v) {
    if (v == null || Number.isNaN(Number(v))) return "0";
    var n = Number(v);
    if (Number.isInteger(n)) return n.toLocaleString();
    return n.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }

  function formatValue(prefix, suffix, value) {
    return (prefix || "") + fmtNum(value) + (suffix || "");
  }

  function resolveMainValue(points, apiData, cfg) {
    var mode = String(cfg.line1_value_mode || "sum").trim();
    if (VALUE_MODES.indexOf(mode) < 0) mode = "sum";
    if (!points.length) return 0;
    if (mode === "latest") return points[points.length - 1].value;
    if (mode === "max") {
      var peak = points[0].value;
      for (var i = 1; i < points.length; i++) {
        if (points[i].value > peak) peak = points[i].value;
      }
      return peak;
    }
    if (mode === "average") {
      var sum = points.reduce(function (s, p) { return s + p.value; }, 0);
      return sum / points.length;
    }
    if (apiData && apiData.total != null && Number.isFinite(Number(apiData.total))) {
      return Number(apiData.total);
    }
    return points.reduce(function (s, p) { return s + p.value; }, 0);
  }

  function resolveDeltaText(apiData, cfg) {
    if (!apiData || typeof apiData !== "object") return null;
    if (apiData.delta_label != null && String(apiData.delta_label).trim()) {
      return String(apiData.delta_label).trim();
    }
    var delta = apiData.delta;
    var pct = apiData.delta_percent;
    if (delta == null && pct == null) return null;
    var parts = [];
    if (delta != null && Number.isFinite(Number(delta))) {
      var d = Number(delta);
      parts.push((d >= 0 ? "+" : "") + fmtNum(d));
    }
    if (pct != null && Number.isFinite(Number(pct))) {
      parts.push("(" + fmtNum(Number(pct)) + "%)");
    }
    var range = cfg.line1_range_label || "全部";
    if (parts.length) return parts.join(" ") + " · " + range;
    return null;
  }

  function computeYDomain(values) {
    if (!values.length) return { min: 0, max: 1 };
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    if (min === max) {
      var pad = Math.abs(min) > 0 ? Math.abs(min) * 0.1 : 1;
      return { min: min - pad, max: max + pad };
    }
    var span = max - min;
    return { min: min - span * 0.08, max: max + span * 0.08 };
  }

  function thinAxisLabels(labels, maxLabels) {
    maxLabels = maxLabels || 8;
    if (labels.length <= maxLabels) {
      return labels.map(function (lab, i) { return { label: lab, index: i, show: true }; });
    }
    var step = Math.ceil(labels.length / maxLabels);
    return labels.map(function (lab, i) {
      return { label: lab, index: i, show: i === 0 || i === labels.length - 1 || i % step === 0 };
    });
  }

  function formatYTick(v) {
    if (Math.abs(v) >= 1000) return fmtNum(v);
    if (Number.isInteger(v)) return String(v);
    return v.toFixed(1);
  }

  function createChartGeometry(points) {
    var w = 1000;
    var h = 320;
    var padL = 52;
    var padR = 12;
    var padT = 16;
    var padB = 28;
    var chartW = w - padL - padR;
    var chartH = h - padT - padB;
    var values = points.map(function (p) { return p.value; });
    var domain = computeYDomain(values);
    var n = points.length;
    function xAt(i) {
      if (n <= 1) return padL + chartW / 2;
      return padL + (i / (n - 1)) * chartW;
    }
    function xPctAt(i) {
      return (xAt(i) / w) * 100;
    }
    function yAt(v) {
      var t = (v - domain.min) / (domain.max - domain.min || 1);
      return padT + chartH - t * chartH;
    }
    function indexAtClientX(clientX, rect) {
      if (!rect || !rect.width) return 0;
      var pct = (clientX - rect.left) / rect.width;
      var svgX = pct * w;
      if (n <= 1) return 0;
      var raw = ((svgX - padL) / chartW) * (n - 1);
      return Math.max(0, Math.min(n - 1, Math.round(raw)));
    }
    return { w: w, h: h, padT: padT, padB: padB, domain: domain, n: n, xAt: xAt, xPctAt: xPctAt, yAt: yAt, indexAtClientX: indexAtClientX };
  }

  function buildStaticSvg(points, accent, showGrid) {
    var geo = createChartGeometry(points);
    var w = geo.w;
    var h = geo.h;
    var padL = 52;
    var padR = 12;
    var padT = geo.padT;
    var padB = geo.padB;
    var chartW = w - padL - padR;
    var chartH = h - padT - padB;
    var n = geo.n;
    var svgParts = [];
    svgParts.push('<svg class="line1-svg" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" aria-hidden="true">');
    svgParts.push('<defs><linearGradient id="line1-area-grad" x1="0" y1="0" x2="0" y2="1">');
    svgParts.push('<stop offset="0%" stop-color="' + accent + '" stop-opacity="0.18"/>');
    svgParts.push('<stop offset="100%" stop-color="' + accent + '" stop-opacity="0"/>');
    svgParts.push("</linearGradient></defs>");

    if (showGrid !== false) {
      var gridRows = 4;
      for (var gi = 0; gi <= gridRows; gi++) {
        var gy = padT + (gi / gridRows) * chartH;
        svgParts.push('<line class="line1-grid-h" x1="' + padL + '" y1="' + gy.toFixed(2) + '" x2="' + (w - padR) + '" y2="' + gy.toFixed(2) + '" stroke="#e5e7eb" stroke-width="1" stroke-dasharray="2 6"/>');
      }
      for (var gj = 0; gj <= 6; gj++) {
        var gx = padL + (gj / 6) * chartW;
        svgParts.push('<line class="line1-grid-v" x1="' + gx.toFixed(2) + '" y1="' + padT + '" x2="' + gx.toFixed(2) + '" y2="' + (padT + chartH) + '" stroke="#eef0f2" stroke-width="1"/>');
      }
      for (var yi = 0; yi <= gridRows; yi++) {
        var yVal = geo.domain.max - (yi / gridRows) * (geo.domain.max - geo.domain.min);
        var yLabelY = padT + (yi / gridRows) * chartH + 4;
        svgParts.push('<text class="line1-y-label" x="' + (padL - 8) + '" y="' + yLabelY.toFixed(2) + '" text-anchor="end" fill="#9ca3af" font-size="11">' + formatYTick(yVal) + "</text>");
      }
    }

    if (n >= 2) {
      var linePts = [];
      var areaPts = [];
      for (var i = 0; i < n; i++) {
        var x = geo.xAt(i);
        var y = geo.yAt(points[i].value);
        linePts.push(x.toFixed(2) + "," + y.toFixed(2));
        areaPts.push(x.toFixed(2) + "," + y.toFixed(2));
      }
      var baseY = (padT + chartH).toFixed(2);
      var areaPath = "M" + areaPts[0] + " L" + areaPts.slice(1).join(" L") + " L" + geo.xAt(n - 1).toFixed(2) + "," + baseY + " L" + geo.xAt(0).toFixed(2) + "," + baseY + " Z";
      svgParts.push('<path class="line1-area" d="' + areaPath + '" fill="url(#line1-area-grad)"/>');
      svgParts.push('<polyline class="line1-path" fill="none" stroke="' + accent + '" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" points="' + linePts.join(" ") + '"/>');
    } else if (n === 1) {
      var sx = geo.xAt(0);
      var sy = geo.yAt(points[0].value);
      svgParts.push('<circle cx="' + sx.toFixed(2) + '" cy="' + sy.toFixed(2) + '" r="3" fill="' + accent + '"/>');
    }
    svgParts.push("</svg>");
    return { html: svgParts.join(""), geometry: geo };
  }

  function setupHoverInteraction(chartWrap, model, accent, geometry, prefix, suffix) {
    var cursor = document.createElement("div");
    cursor.className = "line1-cursor";
    var activePoint = document.createElement("div");
    activePoint.className = "line1-active-point";
    var tip = document.createElement("div");
    tip.className = "line1-tooltip";

    chartWrap.appendChild(cursor);
    chartWrap.appendChild(activePoint);
    chartWrap.appendChild(tip);

    function accentHaloShadow(color) {
      var hex = String(color || "#1e96e8").replace("#", "");
      if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
      var r = parseInt(hex.slice(0, 2), 16);
      var g = parseInt(hex.slice(2, 4), 16);
      var b = parseInt(hex.slice(4, 6), 16);
      if (!Number.isFinite(r) || !Number.isFinite(g) || !Number.isFinite(b)) {
        return "0 0 0 7px rgba(30, 150, 232, 0.2)";
      }
      return "0 0 0 7px rgba(" + r + "," + g + "," + b + ",0.2)";
    }

    function setActive(idx, visible) {
      if (!visible || idx == null || !model.points[idx]) {
        cursor.classList.remove("is-active");
        activePoint.classList.remove("is-active");
        tip.classList.remove("is-active");
        chartWrap.classList.remove("line1-hover-live");
        return;
      }
      var firstFrame = !chartWrap.classList.contains("line1-hover-live");
      if (firstFrame) chartWrap.classList.add("line1-hover-instant");

      var py = geometry.yAt(model.points[idx].value);
      var xPct = geometry.xPctAt(idx);
      var yPct = (py / geometry.h) * 100;
      var plotBottomPct = ((geometry.h - geometry.padB) / geometry.h) * 100;
      cursor.style.left = xPct + "%";
      cursor.style.top = yPct + "%";
      cursor.style.bottom = (100 - plotBottomPct) + "%";
      activePoint.style.left = xPct + "%";
      activePoint.style.top = yPct + "%";
      activePoint.style.boxShadow = accentHaloShadow(accent);
      tip.textContent = formatValue(prefix, suffix, model.points[idx].value);
      tip.style.left = xPct + "%";
      tip.style.top = yPct + "%";

      cursor.classList.add("is-active");
      activePoint.classList.add("is-active");
      tip.classList.add("is-active");
      chartWrap.classList.add("line1-hover-live");

      if (firstFrame) {
        void chartWrap.offsetWidth;
        chartWrap.classList.remove("line1-hover-instant");
      }
    }

    function onMove(e) {
      var rect = chartWrap.getBoundingClientRect();
      setActive(geometry.indexAtClientX(e.clientX, rect), true);
    }
    function onLeave() {
      chartWrap.classList.remove("line1-hover-instant");
      setActive(null, false);
    }

    chartWrap.addEventListener("mousemove", onMove);
    chartWrap.addEventListener("mouseleave", onLeave);

    return function cleanupHover() {
      chartWrap.removeEventListener("mousemove", onMove);
      chartWrap.removeEventListener("mouseleave", onLeave);
    };
  }

  function normalizeLine1Data(widget, apiData) {
    var cfg = (widget && widget.config) || {};
    if (!apiData || apiData.status !== "ok" || apiData.kind !== "series") {
      return { empty: true, title: (widget && widget.title) || "", cfg: cfg, points: [] };
    }
    var labels = apiData.labels || [];
    var values = apiData.values || [];
    var points = [];
    var i;
    for (i = 0; i < labels.length; i++) {
      var val = Number(values[i]);
      if (!Number.isFinite(val)) continue;
      points.push({ label: String(labels[i]), value: val });
    }
    var prefix = cfg.prefix != null && cfg.prefix !== "" ? cfg.prefix : (apiData.prefix || "");
    var suffix = cfg.suffix != null && cfg.suffix !== "" ? cfg.suffix : (apiData.suffix || "");
    return {
      empty: !points.length,
      title: (widget && widget.title) || "",
      cfg: cfg,
      points: points,
      prefix: prefix,
      suffix: suffix,
      mainValue: resolveMainValue(points, apiData, cfg),
      deltaText: resolveDeltaText(apiData, cfg),
    };
  }

  function destroy(container) {
    if (!container) return;
    if (typeof container._line1Cleanup === "function") {
      container._line1Cleanup();
      container._line1Cleanup = null;
    }
    container.innerHTML = "";
  }

  function render(container, widget, apiData, options) {
    options = options || {};
    if (!container) return;
    destroy(container);
    var model = normalizeLine1Data(widget, apiData);
    var cfg = model.cfg || {};
    var accent = options.lineColor || DEFAULT_LINE_COLOR;
    var showGrid = cfg.show_line1_grid !== false;
    var card = document.createElement("div");
    card.className = "line1-card";

    var topRow = document.createElement("div");
    topRow.className = "line1-top-row";

    var metrics = document.createElement("div");
    metrics.className = "line1-metrics";
    if (model.empty) {
      var emptyVal = document.createElement("div");
      emptyVal.className = "line1-main-value line1-empty";
      emptyVal.textContent = "暂无数据";
      metrics.appendChild(emptyVal);
    } else {
      var mainVal = document.createElement("div");
      mainVal.className = "line1-main-value";
      mainVal.style.color = accent;
      mainVal.textContent = formatValue(model.prefix, model.suffix, model.mainValue);
      metrics.appendChild(mainVal);
    }
    topRow.appendChild(metrics);

    if (cfg.show_line1_range !== false) {
      var actions = document.createElement("div");
      actions.className = "line1-header-actions";
      var pill = document.createElement("span");
      pill.className = "line1-range-pill";
      pill.textContent = options.rangeLabel || cfg.line1_range_label || "全部";
      actions.appendChild(pill);
      topRow.appendChild(actions);
    }

    card.appendChild(topRow);

    var chartWrap = document.createElement("div");
    chartWrap.className = "line1-chart-wrap";
    var hoverCleanup = null;
    if (!model.empty) {
      var built = buildStaticSvg(model.points, accent, showGrid);
      chartWrap.innerHTML = built.html;
      hoverCleanup = setupHoverInteraction(chartWrap, model, accent, built.geometry, model.prefix, model.suffix);
      var axis = document.createElement("div");
      axis.className = "line1-x-axis";
      var thinned = thinAxisLabels(model.points.map(function (p) { return p.label; }));
      thinned.forEach(function (item) {
        if (!item.show) return;
        var lbl = document.createElement("span");
        lbl.className = "line1-x-label";
        lbl.textContent = item.label;
        lbl.title = item.label;
        lbl.style.left = built.geometry.xPctAt(item.index) + "%";
        axis.appendChild(lbl);
      });
      card.appendChild(chartWrap);
      card.appendChild(axis);
    } else {
      chartWrap.innerHTML = '<div class="line1-chart-empty">暂无数据</div>';
      card.appendChild(chartWrap);
    }

    container.appendChild(card);
    var ro = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(function () {});
      ro.observe(container);
    }
    container._line1Cleanup = function () {
      if (hoverCleanup) hoverCleanup();
      if (ro) ro.disconnect();
    };
  }

  global.CrmLine1ChartKit = {
    render: render,
    destroy: destroy,
    normalizeLine1Data: normalizeLine1Data,
    resolveMainValue: resolveMainValue,
  };
})(typeof window !== "undefined" ? window : globalThis);
