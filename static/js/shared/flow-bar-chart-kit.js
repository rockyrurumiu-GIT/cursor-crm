/**
 * RMS Dashboard — pipeline dialysis distribution bars.
 * Renders chart_pipeline_dialysis as a refined rounded distribution chart.
 */
(function (global) {
  "use strict";

  var uid = 0;

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(v) {
    var n = Number(v);
    if (!Number.isFinite(n)) return "0";
    if (Number.isInteger(n)) return n.toLocaleString();
    return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }

  function totalForRow(row, keys) {
    return (keys || []).reduce(function (sum, key) {
      return sum + (Number(row && row[key]) || 0);
    }, 0);
  }

  function shortLabel(label, maxLen) {
    var s = String(label == null ? "" : label);
    maxLen = maxLen || 8;
    if (s.length <= maxLen) return s;
    return s.slice(0, maxLen - 1) + "…";
  }

  function destroy(mountEl) {
    if (mountEl) mountEl.innerHTML = "";
  }

  function render(mountEl, opts) {
    if (!mountEl) return;
    destroy(mountEl);
    opts = opts || {};
    var keys = opts.keys || [];
    var rows = opts.rows || [];
    var prefix = opts.prefix || "";
    var suffix = opts.suffix || "";

    if (!rows.length || !keys.length) {
      mountEl.innerHTML = '<p class="state-msg">暂无数据</p>';
      return;
    }

    var cols = rows.map(function (row) {
      return {
        label: String(row.label == null ? "" : row.label),
        total: totalForRow(row, keys),
      };
    }).filter(function (col) {
      return col.total > 0;
    });

    if (!cols.length) {
      mountEl.innerHTML = '<p class="state-msg">暂无数据</p>';
      return;
    }

    var maxTotal = Math.max.apply(null, cols.map(function (col) { return col.total; }).concat([1]));
    var highlightIdx = 0;
    cols.forEach(function (col, i) {
      if (col.total > cols[highlightIdx].total) highlightIdx = i;
    });

    uid += 1;
    var gid = "flowdist-" + uid;
    var W = 960;
    var H = 360;
    var padX = 28;
    var padTop = 42;
    var padBottom = 70;
    var chartBottom = H - padBottom;
    var chartH = chartBottom - padTop;
    var slot = (W - padX * 2) / cols.length;
    var barW = Math.max(76, Math.min(132, slot * 0.72));
    var minBarH = 38;
    var svg = [];

    function xCenter(i) {
      return padX + slot * i + slot / 2;
    }

    svg.push('<svg class="bms-flow-bar-svg" viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="xMidYMid meet" role="img" aria-hidden="true">');
    svg.push("<defs>");
    svg.push('<linearGradient id="' + gid + '-active" x1="0" y1="0" x2="1" y2="1">');
    svg.push('<stop offset="0%" stop-color="#d8b7ff"/>');
    svg.push('<stop offset="42%" stop-color="#a16cf1"/>');
    svg.push('<stop offset="100%" stop-color="#6f35dc"/>');
    svg.push("</linearGradient>");
    svg.push('<linearGradient id="' + gid + '-active-sheen" x1="0" y1="0" x2="1" y2="0">');
    svg.push('<stop offset="0%" stop-color="#ffffff" stop-opacity="0.26"/>');
    svg.push('<stop offset="55%" stop-color="#ffffff" stop-opacity="0"/>');
    svg.push("</linearGradient>");
    svg.push('<linearGradient id="' + gid + '-muted" x1="0" y1="0" x2="0" y2="1">');
    svg.push('<stop offset="0%" stop-color="#f2e9ff"/>');
    svg.push('<stop offset="100%" stop-color="#ddd0f4"/>');
    svg.push("</linearGradient>");
    svg.push('<linearGradient id="' + gid + '-muted-sheen" x1="0" y1="0" x2="1" y2="0">');
    svg.push('<stop offset="0%" stop-color="#ffffff" stop-opacity="0.36"/>');
    svg.push('<stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>');
    svg.push("</linearGradient>");
    svg.push('<filter id="' + gid + '-active-shadow" x="-24%" y="-20%" width="148%" height="150%">');
    svg.push('<feDropShadow dx="0" dy="14" stdDeviation="13" flood-color="#7c3aed" flood-opacity="0.2"/>');
    svg.push("</filter>");
    svg.push('<filter id="' + gid + '-soft-shadow" x="-20%" y="-15%" width="140%" height="140%">');
    svg.push('<feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#8b5cf6" flood-opacity="0.08"/>');
    svg.push("</filter>");
    svg.push("</defs>");

    cols.forEach(function (col, i) {
      var cx = xCenter(i);
      var rawH = (col.total / maxTotal) * chartH;
      var h = Math.max(minBarH, rawH);
      var x = cx - barW / 2;
      var y = chartBottom - h;
      var isActive = i === highlightIdx;
      var valueText = prefix + fmtNum(col.total) + suffix;
      var rx = 13;
      var fillId = gid + (isActive ? "-active" : "-muted");
      var sheenId = gid + (isActive ? "-active-sheen" : "-muted-sheen");

      svg.push('<g class="bms-flow-bar-item' + (isActive ? " is-active" : "") + '" data-index="' + i + '">');
      svg.push('<text class="bms-flow-bar-value" x="' + cx.toFixed(1) + '" y="' + (y - 17).toFixed(1) + '" text-anchor="middle">' + escapeHtml(valueText) + "</text>");
      svg.push('<rect class="bms-flow-bar-rect' + (isActive ? " is-active" : "") + '" x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + barW.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="' + rx + '" fill="url(#' + fillId + ')" filter="url(#' + gid + (isActive ? "-active-shadow" : "-soft-shadow") + ')">');
      svg.push("<title>" + escapeHtml(col.label) + "：" + escapeHtml(valueText) + "</title></rect>");
      svg.push('<rect class="bms-flow-bar-sheen" x="' + (x + 1).toFixed(1) + '" y="' + (y + 1).toFixed(1) + '" width="' + (barW - 2).toFixed(1) + '" height="' + Math.max(0, h - 2).toFixed(1) + '" rx="' + rx + '" fill="url(#' + sheenId + ')"/>');
      if (isActive) {
        var label = shortLabel(col.label, 7);
        var pillW = Math.max(66, Math.min(108, label.length * 14 + 26));
        svg.push('<rect class="bms-flow-bar-pill-bg" x="' + (cx - pillW / 2).toFixed(1) + '" y="' + (chartBottom + 12).toFixed(1) + '" width="' + pillW.toFixed(1) + '" height="34" rx="9"/>');
        svg.push('<text class="bms-flow-bar-label is-active" x="' + cx.toFixed(1) + '" y="' + (chartBottom + 35).toFixed(1) + '" text-anchor="middle">' + escapeHtml(label) + "</text>");
      } else {
        svg.push('<text class="bms-flow-bar-label" x="' + cx.toFixed(1) + '" y="' + (chartBottom + 34).toFixed(1) + '" text-anchor="middle">' + escapeHtml(shortLabel(col.label, 8)) + "</text>");
      }
      svg.push("</g>");
    });

    svg.push("</svg>");

    var card = document.createElement("div");
    card.className = "bms-flow-bar-card";
    var chartWrap = document.createElement("div");
    chartWrap.className = "bms-flow-bar-chart";
    chartWrap.innerHTML = svg.join("");
    card.appendChild(chartWrap);
    mountEl.appendChild(card);
  }

  global.CrmFlowBarChartKit = {
    render: render,
    destroy: destroy,
  };
})(typeof window !== "undefined" ? window : this);
