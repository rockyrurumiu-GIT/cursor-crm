/**
 * BMS Dashboard — featured_line (重点折线) SVG card renderer.
 */
(function (global) {
  "use strict";
  var FEATURED_BLUE = "#1e96e8";
  var LINE_COLOR = FEATURED_BLUE;
  var FEATURED_VALUE_MODES = ["auto", "sum", "latest", "average"];
  function fmtNum(v) {
    if (v == null || Number.isNaN(Number(v))) return "0";
    var n = Number(v);
    if (Number.isInteger(n)) return n.toLocaleString();
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  function formatValue(prefix, suffix, value) {
    return (prefix || "") + fmtNum(value) + (suffix || "");
  }
  function isPercentSuffix(suffix) {
    return String(suffix || "").trim() === "%";
  }
  function mainValueModeLabel(mode) {
    if (mode === "latest") return "最新值";
    if (mode === "average") return "平均值";
    if (mode === "sum") return "总和";
    return "";
  }
  function buildInfoTitle(mainValueMode, lifecyclePassRate) {
    var mainPart;
    if (mainValueMode === "sum") {
      mainPart = "主指标：所有点数值求和";
    } else if (mainValueMode === "average") {
      mainPart = "主指标：所有点数值的算术平均";
    } else {
      mainPart = "主指标：当前序列最后一个点";
      if (lifecyclePassRate) {
        mainPart += "；五率图按招聘流程原始顺序取末点";
      }
    }
    return mainPart + "；平均线：当前所有阶段数值的算术平均；对比：最后一个点相对前一个点变化";
  }
  function resolveFeaturedMainValue(points, apiData, cfg, suffix) {
    var mode = cfg.featured_value_mode || "auto";
    var isPercent = isPercentSuffix(suffix);
    var finalMode = mode === "auto" ? (isPercent ? "latest" : "sum") : mode;
    if (FEATURED_VALUE_MODES.indexOf(finalMode) < 0) finalMode = "auto";
    if (finalMode === "auto") finalMode = isPercent ? "latest" : "sum";
    if (!points.length) return { value: 0, mode: finalMode };
    if (finalMode === "latest") {
      return { value: points[points.length - 1].value, mode: "latest" };
    }
    if (finalMode === "average") {
      var avg = points.reduce(function (s, p) { return s + p.value; }, 0) / points.length;
      return { value: avg, mode: "average" };
    }
    var sumVal = apiData && apiData.total != null
      ? Number(apiData.total)
      : points.reduce(function (s, p) { return s + p.value; }, 0);
    if (!Number.isFinite(sumVal)) sumVal = 0;
    return { value: sumVal, mode: "sum" };
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
  function resolveValueScaleDomain(cfg, values) {
    if (cfg && cfg.value_scale_max != null && Number.isFinite(Number(cfg.value_scale_max))) {
      var fixedMin = cfg.value_scale_min != null && Number.isFinite(Number(cfg.value_scale_min))
        ? Number(cfg.value_scale_min) : 0;
      return { min: fixedMin, max: Number(cfg.value_scale_max) };
    }
    return computeYDomain(values);
  }
  function emptyFeaturedLineModel(widget, cfg, apiData) {
    return {
      title: (widget && widget.title) || "统计趋势",
      empty: true,
      points: [],
      total: 0,
      mainValue: 0,
      mainValueMode: "sum",
      mainValueModeLabel: "",
      infoTitle: buildInfoTitle("sum", cfg.lifecycle_pass_rate),
      valuePrefix: cfg.prefix || (apiData && apiData.prefix) || "",
      valueSuffix: cfg.suffix || (apiData && apiData.suffix) || "",
      comparisonLabel: cfg.comparison_label || "较上期",
      averageLabel: cfg.average_label || "Avg",
      showAverageLine: cfg.show_average_line !== false,
      showComparison: cfg.show_comparison !== false,
      showPointValues: cfg.show_point_values === true,
      activeIndex: 0,
      deltaPercent: null,
      deltaDirection: null,
      averageValue: 0,
      lineColor: LINE_COLOR,
    };
  }
  function normalizeFeaturedLineData(widget, apiData) {
    var cfg = (widget && widget.config) || {};
    if (!apiData || apiData.status !== "ok" || apiData.kind !== "series") {
      return emptyFeaturedLineModel(widget, cfg, apiData);
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
    var isPercent = isPercentSuffix(suffix);
    var highlightLatest = cfg.highlight_latest !== false;
    var showComparison = cfg.show_comparison !== false;
    var activeIndex = highlightLatest && points.length ? points.length - 1 : 0;
    var mainResolved = resolveFeaturedMainValue(points, apiData, cfg, suffix);
    var total = mainResolved.value;
    var sum = 0;
    points.forEach(function (p) { sum += p.value; });
    var averageValue = points.length ? sum / points.length : 0;
    var deltaPercent = null;
    var deltaDirection = null;
    if (showComparison && points.length >= 2) {
      var last = points[points.length - 1].value;
      var prev = points[points.length - 2].value;
      if (prev !== 0) {
        deltaPercent = Math.round(Math.abs((last - prev) / prev) * 100);
        deltaDirection = last >= prev ? "up" : "down";
      } else if (last !== 0) {
        deltaPercent = 100;
        deltaDirection = last > 0 ? "up" : "down";
      }
    }
    var avgLabelBase = cfg.average_label;
    if (!avgLabelBase) avgLabelBase = isPercent ? "平均" : "Avg";
    var averageLabel = avgLabelBase + " " + formatValue(prefix, suffix, averageValue);
    var lifecyclePassRate = cfg.lifecycle_pass_rate === true;
    var modeLabel = mainValueModeLabel(mainResolved.mode);
    return {
      title: (widget && widget.title) || "统计趋势",
      empty: points.length === 0,
      points: points,
      total: total,
      mainValue: mainResolved.value,
      mainValueMode: mainResolved.mode,
      mainValueModeLabel: modeLabel,
      infoTitle: buildInfoTitle(mainResolved.mode, lifecyclePassRate),
      valuePrefix: prefix,
      valueSuffix: suffix,
      comparisonLabel: cfg.comparison_label || "较上期",
      averageLabel: averageLabel,
      showAverageLine: cfg.show_average_line !== false,
      showComparison: showComparison,
      showPointValues: cfg.show_point_values === true,
      activeIndex: activeIndex,
      deltaPercent: deltaPercent,
      deltaDirection: deltaDirection,
      averageValue: averageValue,
      lineColor: LINE_COLOR,
      valueScaleMin: cfg.value_scale_min,
      valueScaleMax: cfg.value_scale_max,
      compactAvgLabel: cfg.compact_avg_label === true,
    };
  }
  function destroyFeaturedLine(mountEl) {
    if (!mountEl) return;
    if (typeof mountEl._featuredLineCleanup === "function") {
      mountEl._featuredLineCleanup();
      mountEl._featuredLineCleanup = null;
    }
    mountEl.innerHTML = "";
  }
  function shouldShowPointLabel(index, n, activeIndex) {
    if (n <= 8) return true;
    return index === 0 || index === n - 1 || index === activeIndex;
  }
  function buildChartSvg(model, accent) {
    var points = model.points;
    var w = 1000;
    var h = 360;
    var padL = 8;
    var padR = 8;
    var padT = 40;
    var padB = 8;
    var chartW = w - padL - padR;
    var chartH = h - padT - padB;
    var values = points.map(function (p) { return p.value; });
    var domain = resolveValueScaleDomain({
      value_scale_min: model.valueScaleMin,
      value_scale_max: model.valueScaleMax,
    }, values);
    var n = points.length;
    var activeIdx = n >= 1 ? Math.min(Math.max(model.activeIndex, 0), n - 1) : 0;
    function xAt(i) {
      if (n <= 1) return padL + chartW / 2;
      return padL + (i / (n - 1)) * chartW;
    }
    function yAt(v) {
      var t = (v - domain.min) / (domain.max - domain.min || 1);
      return padT + chartH - t * chartH;
    }
    var svgParts = [];
    svgParts.push('<svg class="bms-featured-line-svg" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" aria-hidden="true">');
    svgParts.push('<defs><linearGradient id="fl-area-grad" x1="0" y1="0" x2="0" y2="1">');
    svgParts.push('<stop offset="0%" stop-color="' + accent + '" stop-opacity="0.22"/>');
    svgParts.push('<stop offset="100%" stop-color="' + accent + '" stop-opacity="0"/>');
    svgParts.push("</linearGradient></defs>");
    if (n >= 2) {
      var linePts = [];
      var areaPts = [];
      for (var i = 0; i < n; i++) {
        var x = xAt(i);
        var y = yAt(points[i].value);
        linePts.push(x.toFixed(2) + "," + y.toFixed(2));
        areaPts.push(x.toFixed(2) + "," + y.toFixed(2));
      }
      var baseY = (padT + chartH).toFixed(2);
      var areaPath = "M" + areaPts[0] + " L" + areaPts.slice(1).join(" L") + " L" + xAt(n - 1).toFixed(2) + "," + baseY + " L" + xAt(0).toFixed(2) + "," + baseY + " Z";
      svgParts.push('<path class="bms-featured-line-area" d="' + areaPath + '" fill="url(#fl-area-grad)"/>');
      svgParts.push('<polyline class="bms-featured-line-path" fill="none" stroke="' + accent + '" stroke-opacity="1" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round" points="' + linePts.join(" ") + '"/>');
    }
    var avgLineYPct = null;
    if (model.showAverageLine && n >= 1) {
      var ay = yAt(model.averageValue);
      avgLineYPct = (ay / h) * 100;
      svgParts.push('<line class="bms-featured-line-avg" x1="' + padL + '" y1="' + ay.toFixed(2) + '" x2="' + (w - padR) + '" y2="' + ay.toFixed(2) + '" stroke="#9ca3af" stroke-width="2" stroke-dasharray="6 6"/>');
    }
    var pointPositions = [];
    for (var pi = 0; pi < n; pi++) {
      var px = xAt(pi);
      var py = yAt(points[pi].value);
      var isActive = pi === activeIdx;
      if (isActive) {
        svgParts.push('<circle class="bms-featured-line-dot" cx="' + px.toFixed(2) + '" cy="' + py.toFixed(2) + '" r="6" fill="' + accent + '" stroke="#fff" stroke-width="2.5"/>');
      } else if (model.showPointValues) {
        svgParts.push('<circle class="bms-featured-line-point" cx="' + px.toFixed(2) + '" cy="' + py.toFixed(2) + '" r="3" fill="' + accent + '" stroke="#fff" stroke-width="1.5"/>');
      }
      pointPositions.push({
        index: pi,
        xPct: (px / w) * 100,
        yPct: (py / h) * 100,
        value: points[pi].value,
        showLabel: model.showPointValues && shouldShowPointLabel(pi, n, activeIdx),
      });
    }
    svgParts.push("</svg>");
    var activePoint = pointPositions.length ? pointPositions[activeIdx] : null;
    return {
      html: svgParts.join(""),
      pointPositions: pointPositions,
      activePoint: activePoint,
      avgLineYPct: avgLineYPct,
    };
  }

  function tooltipTopPct(yPct) {
    var offset = yPct < 18 ? 12 : 10;
    return Math.max(12, yPct - offset) + "%";
  }
  function renderFeaturedLine(mountEl, widget, apiData, opts) {
    opts = opts || {};
    if (!mountEl) return;
    destroyFeaturedLine(mountEl);
    var model = normalizeFeaturedLineData(widget, apiData);
    var accent = opts.lineColor || model.lineColor || LINE_COLOR;
    var card = document.createElement("div");
    card.className = "bms-featured-line-card";
    var valueRow = document.createElement("div");
    valueRow.className = "bms-featured-kpi-row";
    if (model.empty) {
      var emptyVal = document.createElement("div");
      emptyVal.className = "bms-featured-main-value bms-featured-line-value--empty";
      emptyVal.textContent = "暂无数据";
      valueRow.appendChild(emptyVal);
    } else {
      var mainVal = document.createElement("span");
      mainVal.className = "bms-featured-main-value";
      mainVal.textContent = formatValue(model.valuePrefix, model.valueSuffix, model.mainValue);
      valueRow.appendChild(mainVal);
      if (model.mainValueModeLabel) {
        var modeNote = document.createElement("span");
        modeNote.className = "bms-featured-main-caption";
        modeNote.textContent = model.mainValueModeLabel;
        valueRow.appendChild(modeNote);
      }
      if (model.deltaPercent != null && model.deltaDirection) {
        var delta = document.createElement("span");
        delta.className = "bms-featured-delta-chip bms-featured-delta-chip--" + model.deltaDirection;
        delta.textContent = (model.deltaDirection === "up" ? "↗ " : "↘ ") + model.deltaPercent + "%";
        valueRow.appendChild(delta);
        var cmp = document.createElement("span");
        cmp.className = "bms-featured-delta-label";
        cmp.textContent = model.comparisonLabel;
        valueRow.appendChild(cmp);
      }
    }
    card.appendChild(valueRow);
    var chartWrap = document.createElement("div");
    chartWrap.className = "bms-featured-line-chart";
    var chartBuilt = null;
    if (!model.empty) {
      chartBuilt = buildChartSvg(model, accent);
      chartWrap.innerHTML = chartBuilt.html;
      if (model.showAverageLine) {
        var avgLabel = document.createElement("div");
        avgLabel.className = "bms-featured-line-average-label";
        if (model.compactAvgLabel) {
          avgLabel.className += " bms-featured-line-average-label--compact";
        }
        avgLabel.textContent = model.averageLabel;
        if (chartBuilt.avgLineYPct != null) {
          avgLabel.style.top = chartBuilt.avgLineYPct + "%";
        }
        chartWrap.appendChild(avgLabel);
      }
      if (chartBuilt.activePoint) {
        var tip = document.createElement("div");
        tip.className = "bms-featured-line-tooltip";
        tip.textContent = formatValue(model.valuePrefix, model.valueSuffix, chartBuilt.activePoint.value);
        tip.style.left = chartBuilt.activePoint.xPct + "%";
        tip.style.top = tooltipTopPct(chartBuilt.activePoint.yPct);
        chartWrap.appendChild(tip);
      }
      (chartBuilt.pointPositions || []).forEach(function (pt) {
        if (!pt.showLabel) return;
        var lbl = document.createElement("span");
        lbl.className = "bms-featured-line-point-label";
        lbl.textContent = formatValue(model.valuePrefix, model.valueSuffix, pt.value);
        lbl.style.left = pt.xPct + "%";
        lbl.style.top = Math.max(2, pt.yPct - 10) + "%";
        chartWrap.appendChild(lbl);
      });
    } else {
      chartWrap.innerHTML = '<div class="bms-featured-line-chart-empty"></div>';
    }
    card.appendChild(chartWrap);
    if (!model.empty && model.points.length && chartBuilt) {
      var axis = document.createElement("div");
      axis.className = "bms-featured-line-axis";
      var slotPct = 100 / model.points.length;
      var pillMaxWidth = "calc(" + slotPct + "% - 4px)";
      model.points.forEach(function (p, idx) {
        var pill = document.createElement("span");
        pill.className = "bms-featured-line-axis-pill" + (idx === model.activeIndex ? " is-active" : "");
        pill.textContent = p.label;
        pill.title = p.label;
        pill.style.maxWidth = pillMaxWidth;
        var pos = chartBuilt.pointPositions[idx];
        if (pos) pill.style.left = pos.xPct + "%";
        axis.appendChild(pill);
      });
      card.appendChild(axis);
    }
    mountEl.appendChild(card);
    var ro = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(function () {
        /* structure is responsive via CSS; no full redraw needed for v1 */
      });
      ro.observe(mountEl);
    }
    mountEl._featuredLineCleanup = function () {
      if (ro) ro.disconnect();
    };
  }
  global.CrmFeaturedLineChartKit = {
    normalizeFeaturedLineData: normalizeFeaturedLineData,
    renderFeaturedLine: renderFeaturedLine,
    destroyFeaturedLine: destroyFeaturedLine,
    isPercentSuffix: isPercentSuffix,
    resolveFeaturedMainValue: resolveFeaturedMainValue,
  };
})(typeof window !== "undefined" ? window : globalThis);
