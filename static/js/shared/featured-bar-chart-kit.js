/**
 * BMS Dashboard — featured_bar (重点柱状) SVG card renderer.
 */
(function (global) {
  "use strict";

  var FEATURED_BLUE = "#1e96e8";
  var MAX_POINTS = 12;
  var AXIS_LABEL_FONT_SIZE = 22;
  var AXIS_LABEL_FONT_SIZE_FEW = 23;
  var BAR_VALUE_LABEL_FONT_SIZE = 22;
  var MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function fmtNum(v) {
    if (v == null || Number.isNaN(Number(v))) return "0";
    var n = Number(v);
    if (Number.isInteger(n)) return n.toLocaleString();
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function formatValue(prefix, suffix, value) {
    return (prefix || "") + fmtNum(value) + (suffix || "");
  }

  function formatBarDataLabel(model, value) {
    var prefix = model.valuePrefix || "";
    var suffix = model.valueSuffix || "";
    if (suffix) return formatValue(prefix, suffix, value);
    if (prefix && prefix.length <= 2) return prefix + fmtNum(value);
    return fmtNum(value);
  }

  function currentPeriodLabel(dateGroup) {
    var now = new Date();
    var y = now.getFullYear();
    var m = String(now.getMonth() + 1).padStart(2, "0");
    var d = String(now.getDate()).padStart(2, "0");
    if (dateGroup === "day") return y + "-" + m + "-" + d;
    if (dateGroup === "week") {
      var jan1 = new Date(y, 0, 1);
      var dayOfYear = Math.floor((now - jan1) / 86400000);
      var week = Math.floor((dayOfYear + jan1.getDay()) / 7);
      return y + "-W" + String(week).padStart(2, "0");
    }
    if (dateGroup === "year") return String(y);
    return y + "-" + m;
  }

  function clientNameSuffix(label) {
    var s = String(label || "").trim();
    var idx = s.lastIndexOf("-");
    if (idx < 0 || idx >= s.length - 1) return "";
    var suffix = s.slice(idx + 1).trim();
    if (/^[A-Za-z][A-Za-z0-9]*$/.test(suffix)) return suffix.toUpperCase();
    return "";
  }

  function shortAxisLabel(label, labelAxisMode) {
    if (labelAxisMode === "client_suffix") {
      var code = clientNameSuffix(label);
      if (code) return code;
    }
    var s = String(label || "");
    var monthMatch = /^(\d{4})-(\d{2})$/.exec(s);
    if (monthMatch) {
      var mi = parseInt(monthMatch[2], 10) - 1;
      if (mi >= 0 && mi < 12) return MONTH_SHORT[mi];
    }
    var dayMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (dayMatch) return dayMatch[2] + "/" + dayMatch[3];
    if (s.length > 8) return s.slice(0, 8);
    return s;
  }

  function resolveHighlightItem(cfg) {
    var item = cfg && cfg.highlight_item;
    if (item === "max" || item === "latest") return item;
    return "latest";
  }

  function resolveActiveIndex(points, cfg) {
    if (!points.length) return -1;
    var mode = resolveHighlightItem(cfg);
    if (mode === "max") {
      var maxIdx = 0;
      var i;
      for (i = 1; i < points.length; i++) {
        if (points[i].value > points[maxIdx].value) maxIdx = i;
      }
      return maxIdx;
    }
    var current = currentPeriodLabel(cfg.date_group || "month");
    for (i = 0; i < points.length; i++) {
      if (points[i].label === current) return i;
    }
    return points.length - 1;
  }

  function normalizeFeaturedBarData(widget, apiData) {
    var cfg = (widget && widget.config) || {};
    var prefix = cfg.prefix != null && cfg.prefix !== "" ? cfg.prefix : ((apiData && apiData.prefix) || "");
    var suffix = cfg.suffix != null && cfg.suffix !== "" ? cfg.suffix : ((apiData && apiData.suffix) || "");
    var avgLabelBase = cfg.average_label || "Avg";
    var showAverageLine = cfg.show_average_line !== false;
    var showTooltip = cfg.show_tooltip !== false;
    var showSummaryLegend = cfg.show_summary_legend !== false;
    var emptyBase = {
      empty: true,
      unsupported: false,
      points: [],
      activeIndex: -1,
      averageValue: 0,
      averageLabel: avgLabelBase,
      valuePrefix: prefix,
      valueSuffix: suffix,
      showAverageLine: showAverageLine,
      showTooltip: showTooltip,
      showSummaryLegend: showSummaryLegend,
    };

    if (!apiData || apiData.status !== "ok" || apiData.kind !== "series") {
      return emptyBase;
    }

    var labels = apiData.labels || [];
    var values = apiData.values || [];
    var points = [];
    var i;
    for (i = 0; i < labels.length && points.length < MAX_POINTS; i++) {
      var val = Number(values[i]);
      if (!Number.isFinite(val)) continue;
      points.push({ label: String(labels[i]), value: val });
    }

    if (!points.length) {
      return emptyBase;
    }

    var hasNegative = points.some(function (p) { return p.value < 0; });
    if (hasNegative) {
      return {
        empty: false,
        unsupported: true,
        points: points,
        activeIndex: -1,
        averageValue: 0,
        averageLabel: avgLabelBase,
        valuePrefix: prefix,
        valueSuffix: suffix,
        showAverageLine: showAverageLine,
        showTooltip: showTooltip,
        showSummaryLegend: showSummaryLegend,
      };
    }

    var sum = 0;
    points.forEach(function (p) { sum += p.value; });
    var averageValue = points.length ? sum / points.length : 0;
    var activeIndex = resolveActiveIndex(points, cfg);

    return {
      empty: false,
      unsupported: false,
      points: points,
      activeIndex: activeIndex,
      averageValue: averageValue,
      averageLabel: avgLabelBase + " " + formatValue(prefix, suffix, averageValue),
      valuePrefix: prefix,
      valueSuffix: suffix,
      showAverageLine: showAverageLine,
      showTooltip: showTooltip,
      showSummaryLegend: showSummaryLegend,
      valueScaleMin: cfg.value_scale_min,
      valueScaleMax: cfg.value_scale_max,
      showDataLabels: cfg.show_data_labels === true,
      labelFontBoost: Number(cfg.label_font_boost) || 0,
      labelAxisMode: cfg.label_axis_mode || "auto",
      compactAvgLabel: cfg.compact_avg_label === true,
    };
  }

  function destroyFeaturedBarChart(mountEl) {
    if (!mountEl) return;
    if (typeof mountEl._featuredBarCleanup === "function") {
      mountEl._featuredBarCleanup();
      mountEl._featuredBarCleanup = null;
    }
    mountEl.innerHTML = "";
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isPercentSuffix(suffix) {
    return String(suffix || "").trim() === "%";
  }

  function legendRightText(value, total, prefix, suffix) {
    if (isPercentSuffix(suffix)) {
      return formatValue(prefix, suffix, value);
    }
    return sharePercent(value, total);
  }

  function sharePercent(value, total) {
    if (!total || total <= 0) return "0.0%";
    return ((value / total) * 100).toFixed(1) + "%";
  }

  function escapeSvgText(text) {
    return escapeHtml(text);
  }

  function axisDisplayLabel(label, slotW, fontSize, labelAxisMode) {
    var s = shortAxisLabel(label, labelAxisMode);
    fontSize = fontSize || AXIS_LABEL_FONT_SIZE;
    var maxChars = Math.max(2, Math.floor((slotW - 6) / (fontSize * 0.62)));
    if (s.length > maxChars) return s.slice(0, Math.max(1, maxChars - 1)) + "…";
    return s;
  }

  function resolveLabelFontSizes(n, boost) {
    boost = Number(boost) || 0;
    return {
      axis: (n > 8 ? AXIS_LABEL_FONT_SIZE : AXIS_LABEL_FONT_SIZE_FEW) + boost,
      barValue: BAR_VALUE_LABEL_FONT_SIZE + boost,
    };
  }

  function appendSvgAxisLabels(svg, points, activeIdx, n, padL, slotW, padT, chartH, axisFontSize, labelAxisMode) {
    var labelCY = padT + chartH + 20;
    var fontSize = axisFontSize || (n > 8 ? AXIS_LABEL_FONT_SIZE : AXIS_LABEL_FONT_SIZE_FEW);
    var pillH = Math.max(34, Math.round(fontSize * 1.45));
    var i;
    for (i = 0; i < n; i++) {
      var cx = padL + i * slotW + slotW / 2;
      var fullLabel = points[i].label;
      var displayLabel = axisDisplayLabel(fullLabel, slotW, fontSize, labelAxisMode);
      var isActive = i === activeIdx && activeIdx >= 0;
      svg.push('<g class="bms-featured-bar-axis-g">');
      svg.push("<title>" + escapeHtml(fullLabel) + "</title>");
      if (isActive) {
        var tw = Math.min(slotW - 2, Math.max(displayLabel.length * fontSize * 0.62 + 12, 28));
        svg.push(
          '<rect class="bms-featured-bar-axis-pill-bg" x="' + (cx - tw / 2).toFixed(2)
          + '" y="' + (labelCY - pillH / 2).toFixed(2) + '" width="' + tw.toFixed(2)
          + '" height="' + pillH + '" rx="9" fill="#eaf5ff"/>'
        );
        svg.push(
          '<text class="bms-featured-bar-axis-pill-text" x="' + cx.toFixed(2) + '" y="' + labelCY
          + '" text-anchor="middle" dominant-baseline="middle" fill="#1e96e8" font-size="' + fontSize
          + '" font-weight="600" font-family="system-ui,-apple-system,sans-serif">'
          + escapeSvgText(displayLabel) + "</text>"
        );
      } else {
        svg.push(
          '<text class="bms-featured-bar-axis-label" x="' + cx.toFixed(2) + '" y="' + labelCY
          + '" text-anchor="middle" dominant-baseline="middle" fill="#9ca3af" font-size="' + fontSize
          + '" font-family="system-ui,-apple-system,sans-serif">'
          + escapeSvgText(displayLabel) + "</text>"
        );
      }
      svg.push("</g>");
    }
  }

  function buildBarSvg(model) {
    var points = model.points;
    var n = points.length;
    var w = 760;
    var h = 360;
    var padL = 48;
    var padR = 24;
    var padT = 52;
    var labelSizes = resolveLabelFontSizes(n, model.labelFontBoost);
    var padB = 48 + Math.round((Number(model.labelFontBoost) || 0) * 0.8);
    var chartW = w - padL - padR;
    var chartH = h - padT - padB;
    var dataMax = Math.max.apply(null, points.map(function (p) { return p.value; }).concat([model.averageValue, 1]));
    var scaleMin = model.valueScaleMin != null && Number.isFinite(Number(model.valueScaleMin))
      ? Number(model.valueScaleMin) : 0;
    var scaleMax = model.valueScaleMax != null && Number.isFinite(Number(model.valueScaleMax))
      ? Number(model.valueScaleMax) : dataMax;
    var scaleSpan = scaleMax - scaleMin || 1;
    var slotW = chartW / n;
    var barW = Math.max(44, Math.min(60, slotW * 0.62));
    var activeIdx = model.activeIndex;

    function barHeight(v) {
      return Math.max(4, ((v - scaleMin) / scaleSpan) * chartH);
    }
    function barX(i) {
      return padL + i * slotW + (slotW - barW) / 2;
    }
    function barTop(v) {
      return padT + chartH - barHeight(v);
    }

    var svg = [];
    svg.push('<svg class="bms-featured-bar-svg" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="xMidYMid meet">');
    svg.push('<defs>');
    svg.push('<linearGradient id="fb-inactive-grad" x1="0" y1="0" x2="0" y2="1">');
    svg.push('<stop offset="0%" stop-color="var(--featured-bar-muted, #f3f6f9)"/>');
    svg.push('<stop offset="100%" stop-color="var(--featured-bar-grid, #edf2f7)"/>');
    svg.push('</linearGradient>');
    svg.push('<linearGradient id="fb-active-grad" x1="0" y1="0" x2="0" y2="1">');
    svg.push('<stop offset="0%" stop-color="var(--featured-bar-blue, #1e96e8)"/>');
    svg.push('<stop offset="100%" stop-color="var(--featured-bar-blue-dark, #1570b8)"/>');
    svg.push('</linearGradient>');
    svg.push('<pattern id="fb-stripe-inactive" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">');
    svg.push('<rect width="7" height="7" fill="transparent"/>');
    svg.push('<line x1="0" y1="0" x2="0" y2="7" stroke="#cbd5e1" stroke-width="2.2" stroke-linecap="round"/>');
    svg.push('</pattern>');
    svg.push('<pattern id="fb-stripe-active" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">');
    svg.push('<rect width="7" height="7" fill="transparent"/>');
    svg.push('<line x1="0" y1="0" x2="0" y2="7" stroke="rgba(255,255,255,0.28)" stroke-width="2.2" stroke-linecap="round"/>');
    svg.push('</pattern>');
    svg.push('<filter id="fb-bar-shadow" x="-20%" y="-20%" width="140%" height="140%">');
    svg.push('<feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="rgba(30,150,232,0.18)"/>');
    svg.push('</filter>');
    svg.push('</defs>');

    var barMetas = [];
    var activeMeta = null;
    var avgLineYPct = null;
    if (model.showAverageLine) {
      var avgY = padT + chartH - ((model.averageValue - scaleMin) / scaleSpan) * chartH;
      avgLineYPct = (avgY / h) * 100;
      svg.push('<line class="bms-featured-bar-avg" x1="' + padL + '" y1="' + avgY.toFixed(2) + '" x2="' + (w - padR) + '" y2="' + avgY.toFixed(2) + '" stroke="#9ca3af" stroke-width="2" stroke-dasharray="6 6"/>');
    }
    for (var i = 0; i < n; i++) {
      var isActive = i === activeIdx && activeIdx >= 0;
      var barVal = points[i].value;
      var bh = barHeight(barVal);
      var bx = barX(i);
      var by = padT + chartH - bh;
      var brx = Math.min(18, bh / 2);
      var centerX = bx + barW / 2;
      var hasValue = barVal > 0;

      if (!isActive) {
        svg.push('<rect class="bms-featured-bar-rect bms-featured-bar-rect--inactive" x="' + bx.toFixed(2) + '" y="' + by.toFixed(2) + '" width="' + barW.toFixed(2) + '" height="' + bh.toFixed(2) + '" rx="' + brx.toFixed(2) + '" fill="url(#fb-inactive-grad)" stroke="#e5e7eb" stroke-width="1"/>');
        if (hasValue) {
          svg.push('<rect x="' + bx.toFixed(2) + '" y="' + by.toFixed(2) + '" width="' + barW.toFixed(2) + '" height="' + bh.toFixed(2) + '" rx="' + brx.toFixed(2) + '" fill="url(#fb-stripe-inactive)" opacity="0.72"/>');
        }
      } else {
        svg.push('<rect class="bms-featured-bar-rect bms-featured-bar-rect--active" x="' + bx.toFixed(2) + '" y="' + by.toFixed(2) + '" width="' + barW.toFixed(2) + '" height="' + bh.toFixed(2) + '" rx="' + brx.toFixed(2) + '" fill="url(#fb-active-grad)" filter="url(#fb-bar-shadow)"/>');
        if (hasValue) {
          svg.push('<rect x="' + bx.toFixed(2) + '" y="' + by.toFixed(2) + '" width="' + barW.toFixed(2) + '" height="' + bh.toFixed(2) + '" rx="' + brx.toFixed(2) + '" fill="url(#fb-stripe-active)" opacity="0.55"/>');
          svg.push('<circle class="bms-featured-bar-dot" cx="' + centerX.toFixed(2) + '" cy="' + by.toFixed(2) + '" r="7" fill="var(--featured-bar-blue, #1e96e8)" stroke="#fff" stroke-width="3"/>');
        }
        activeMeta = {
          index: i,
          xPct: (centerX / w) * 100,
          yPct: (by / h) * 100,
          svgX: centerX,
          svgY: by,
          value: points[i].value,
          label: points[i].label,
          isActive: true,
        };
      }

      barMetas.push({
        index: i,
        label: points[i].label,
        value: points[i].value,
        xPct: (centerX / w) * 100,
        yPct: (by / h) * 100,
        svgX: centerX,
        svgY: by,
        isActive: isActive,
      });

      if (model.showDataLabels && hasValue) {
        var labelText = formatBarDataLabel(model, barVal);
        svg.push(
          '<text class="bms-featured-bar-value-label' + (isActive ? " bms-featured-bar-value-label--active" : "")
          + '" x="' + centerX.toFixed(2) + '" y="' + (by - 12).toFixed(2)
          + '" text-anchor="middle" fill="' + (isActive ? "#1570b8" : "#6b7280")
          + '" font-size="' + labelSizes.barValue + '" font-weight="600">' + escapeHtml(labelText) + "</text>"
        );
      }

      var hitY = padT;
      var hitH = chartH;
      svg.push(
        '<rect class="bms-featured-bar-hit" data-index="' + i + '" x="' + (padL + i * slotW).toFixed(2)
        + '" y="' + hitY + '" width="' + slotW.toFixed(2) + '" height="' + hitH
        + '" fill="transparent" pointer-events="all"/>'
      );
    }

    appendSvgAxisLabels(svg, points, activeIdx, n, padL, slotW, padT, chartH, labelSizes.axis, model.labelAxisMode);

    svg.push('</svg>');
    return {
      html: svg.join(""),
      activeMeta: activeMeta,
      barMetas: barMetas,
      avgLineYPct: avgLineYPct,
      geometry: {
        w: w,
        h: h,
        padL: padL,
        chartW: chartW,
        n: n,
        slotW: slotW,
      },
    };
  }

  function barIndexAtClientX(clientX, svgEl, geo) {
    if (!svgEl || !geo || !geo.n) return 0;
    var rect = svgEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return 0;
    var scale = Math.min(rect.width / geo.w, rect.height / geo.h);
    var renderedW = geo.w * scale;
    var offsetX = rect.left + (rect.width - renderedW) / 2;
    var svgX = (clientX - offsetX) / scale;
    var raw = (svgX - geo.padL) / geo.slotW;
    return Math.max(0, Math.min(geo.n - 1, Math.floor(raw)));
  }

  function barTipPosition(meta, svgEl, geo, chartWrap) {
    if (!meta || !svgEl || !geo || !chartWrap) {
      return { left: (meta && meta.xPct != null ? meta.xPct : 0) + "%", top: (meta && meta.yPct != null ? meta.yPct : 0) + "%" };
    }
    var svgRect = svgEl.getBoundingClientRect();
    var wrapRect = chartWrap.getBoundingClientRect();
    if (!svgRect.width || !wrapRect.width) {
      return { left: meta.xPct + "%", top: meta.yPct + "%" };
    }
    var scale = Math.min(svgRect.width / geo.w, svgRect.height / geo.h);
    var renderedW = geo.w * scale;
    var renderedH = geo.h * scale;
    var offsetX = svgRect.left + (svgRect.width - renderedW) / 2;
    var offsetY = svgRect.top + (svgRect.height - renderedH) / 2;
    var px = offsetX + meta.svgX * scale - wrapRect.left;
    var py = offsetY + meta.svgY * scale - wrapRect.top;
    return {
      left: ((px / wrapRect.width) * 100) + "%",
      top: ((py / wrapRect.height) * 100) + "%",
    };
  }

  function bindBarHoverTips(chartWrap, model, barMetas, geometry) {
    if (!model.showTooltip || !barMetas.length) return function () {};

    var total = 0;
    model.points.forEach(function (p) { total += p.value; });

    var hoverTip = document.createElement("div");
    hoverTip.className = "bms-featured-bar-hover-tip";
    var tipTitle = document.createElement("div");
    tipTitle.className = "bms-featured-bar-hover-tip-title";
    var tipRow = document.createElement("div");
    tipRow.className = "bms-featured-bar-hover-tip-row";
    var tipSwatch = document.createElement("span");
    tipSwatch.setAttribute("aria-hidden", "true");
    var tipValue = document.createElement("span");
    tipValue.className = "bms-featured-bar-hover-tip-value";
    tipRow.appendChild(tipSwatch);
    tipRow.appendChild(tipValue);
    hoverTip.appendChild(tipTitle);
    hoverTip.appendChild(tipRow);
    chartWrap.appendChild(hoverTip);

    var hoverLive = false;
    var activeIdx = -1;

    function renderTipContent(meta) {
      tipTitle.textContent = meta.label;
      tipSwatch.className = meta.isActive
        ? "bms-featured-bar-hover-tip-swatch bms-featured-bar-hover-tip-swatch--active"
        : "bms-featured-bar-hover-tip-swatch bms-featured-bar-hover-tip-swatch--inactive";
      var valueText = formatValue(model.valuePrefix, model.valueSuffix, meta.value);
      var rightText = legendRightText(meta.value, total, model.valuePrefix, model.valueSuffix);
      if (isPercentSuffix(model.valueSuffix)) {
        tipValue.textContent = valueText;
      } else {
        tipValue.innerHTML = escapeHtml(valueText)
          + ' <span class="bms-featured-bar-hover-tip-pct">(' + escapeHtml(rightText) + ")</span>";
      }
    }

    function showTip(meta) {
      if (!meta) return;
      var idx = meta.index;
      if (hoverLive && idx === activeIdx) return;
      activeIdx = idx;

      var firstFrame = !hoverLive;
      if (firstFrame) hoverTip.classList.add("is-instant");

      renderTipContent(meta);
      var pos = barTipPosition(meta, svgEl, geometry, chartWrap);
      hoverTip.style.left = pos.left;
      hoverTip.style.top = pos.top;
      hoverTip.classList.add("is-visible");
      hoverLive = true;

      if (firstFrame) {
        void hoverTip.offsetWidth;
        hoverTip.classList.remove("is-instant");
      }
    }

    function hideTip() {
      hoverLive = false;
      activeIdx = -1;
      hoverTip.classList.remove("is-instant");
      hoverTip.classList.remove("is-visible");
    }

    var svgEl = chartWrap.querySelector ? chartWrap.querySelector(".bms-featured-bar-svg") : null;

    function onMove(e) {
      var idx = barIndexAtClientX(e.clientX, svgEl, geometry);
      showTip(barMetas[idx]);
    }
    function onLeave() {
      hideTip();
    }

    chartWrap.addEventListener("mousemove", onMove);
    chartWrap.addEventListener("mouseleave", onLeave);

    return function () {
      chartWrap.removeEventListener("mousemove", onMove);
      chartWrap.removeEventListener("mouseleave", onLeave);
      if (hoverTip.parentNode) hoverTip.parentNode.removeChild(hoverTip);
    };
  }

  function buildLegendSummary(model) {
    if (!model.showSummaryLegend) return null;
    var points = model.points;
    if (!points.length || points.length > 5) return null;

    var total = 0;
    points.forEach(function (p) { total += p.value; });

    var legend = document.createElement("div");
    legend.className = "bms-featured-legend";

    points.forEach(function (p, idx) {
      var isActive = idx === model.activeIndex && model.activeIndex >= 0;
      var row = document.createElement("div");
      row.className = "bms-featured-legend-row";

      var swatch = document.createElement("span");
      swatch.className = "bms-featured-legend-swatch" + (isActive ? " is-active" : "");
      if (typeof swatch.setAttribute === "function") {
        swatch.setAttribute("aria-hidden", "true");
      }

      var label = document.createElement("span");
      label.className = "bms-featured-legend-label";
      label.textContent = p.label;
      label.title = p.label;

      var valueEl = document.createElement("span");
      valueEl.className = "bms-featured-legend-value";
      valueEl.textContent = legendRightText(p.value, total, model.valuePrefix, model.valueSuffix);

      row.appendChild(swatch);
      row.appendChild(label);
      row.appendChild(valueEl);
      legend.appendChild(row);
    });

    return legend;
  }

  function renderFeaturedBarChart(mountEl, widget, apiData) {
    if (!mountEl) return;
    destroyFeaturedBarChart(mountEl);

    var model = normalizeFeaturedBarData(widget, apiData);
    if (model.unsupported) {
      mountEl.innerHTML = '<p class="state-msg">重点柱状暂不支持负值</p>';
      return;
    }
    if (model.empty) {
      mountEl.innerHTML = '<p class="state-msg">暂无数据</p>';
      return;
    }

    var card = document.createElement("div");
    card.className = "bms-featured-bar-card";

    var chartWrap = document.createElement("div");
    chartWrap.className = "bms-featured-bar-chart";
    var built = buildBarSvg(model);
    chartWrap.innerHTML = built.html;

    if (model.showAverageLine && built.avgLineYPct != null) {
      var avgLabel = document.createElement("div");
      avgLabel.className = "bms-featured-bar-average-label";
      if (model.compactAvgLabel) {
        avgLabel.className += " bms-featured-bar-average-label--compact";
      }
      avgLabel.textContent = model.averageLabel;
      avgLabel.style.top = built.avgLineYPct + "%";
      chartWrap.appendChild(avgLabel);
    }

    var unbindHover = bindBarHoverTips(chartWrap, model, built.barMetas || [], built.geometry);
    card.appendChild(chartWrap);

    var legendEl = buildLegendSummary(model);
    if (legendEl) card.appendChild(legendEl);

    mountEl.appendChild(card);

    var ro = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(function () { /* responsive via CSS */ });
      ro.observe(mountEl);
    }
    mountEl._featuredBarCleanup = function () {
      if (typeof unbindHover === "function") unbindHover();
      if (ro) ro.disconnect();
    };
  }

  global.CrmFeaturedBarChartKit = {
    normalizeFeaturedBarData: normalizeFeaturedBarData,
    renderFeaturedBarChart: renderFeaturedBarChart,
    destroyFeaturedBarChart: destroyFeaturedBarChart,
  };
})(typeof window !== "undefined" ? window : globalThis);
