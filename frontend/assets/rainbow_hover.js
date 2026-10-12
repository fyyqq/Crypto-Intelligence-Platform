// Hover/touch tooltip for the /tools rainbow chart (components/tools_page.py
// .rainbow-chart). Everything is computed here from the chart model the
// server sends once in data-rainbow (market_tools_service._build_rainbow's
// "hover"): chart geometry, the band model and the daily closes. No library,
// no external service. Shows a vertical guide, a dot on the price line, and
// a card with the date, the price that day + its band, and every band's
// price level at that date (future dates show the levels only).
(function () {
  if (window.__rainbowHoverInit) return;
  window.__rainbowHoverInit = true;

  let cacheKey = "";
  let model = null;

  function getModel(chart) {
    const raw = chart.getAttribute("data-rainbow") || "";
    if (!raw) return null;
    const key = raw.length + ":" + raw.slice(0, 40);
    if (key !== cacheKey) {
      try {
        model = JSON.parse(raw);
        cacheKey = key;
      } catch (e) {
        return null;
      }
    }
    return model;
  }

  // Mirrors the Python _fmt_usd (coin_state.py): 2 decimals from $1, never
  // rounds a small price to $0.00.
  function fmtUsd(v) {
    if (v >= 1 || v === 0) return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    let d = 8;
    let s = v.toFixed(d);
    while (d < 20 && /^0\.0+$/.test(s)) {
      d += 4;
      s = v.toFixed(d);
    }
    s = s.replace(/0+$/, "");
    if (s.endsWith(".")) s += "00";
    return "$" + s;
  }

  // Band levels: compact, like the chart's own axis labels.
  function fmtLevel(v) {
    if (v >= 1e6) return "$" + (v / 1e6).toFixed(v >= 1e7 ? 1 : 2) + "M";
    if (v >= 1e3) return "$" + (v / 1e3).toFixed(v >= 1e4 ? 1 : 2) + "K";
    return fmtUsd(v);
  }

  function fmtDate(t) {
    return new Date(t * 1000).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
  }

  function priceAt(m, day) {
    const p = m.pts;
    if (!p.length || day < p[0][0] || day > p[p.length - 1][0]) return null;
    let lo = 0, hi = p.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (p[mid][0] < day) lo = mid + 1;
      else hi = mid;
    }
    if (lo > 0 && Math.abs(p[lo - 1][0] - day) < Math.abs(p[lo][0] - day)) lo -= 1;
    return p[lo];
  }

  function ensureParts(chart) {
    let tip = chart.querySelector(".rainbow-tip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "rainbow-tip";
      const guide = document.createElement("div");
      guide.className = "rainbow-guide";
      const dot = document.createElement("div");
      dot.className = "rainbow-hover-dot";
      chart.appendChild(guide);
      chart.appendChild(dot);
      chart.appendChild(tip);
    }
    return [tip, chart.querySelector(".rainbow-guide"), chart.querySelector(".rainbow-hover-dot")];
  }

  function hide(chart) {
    chart.querySelectorAll(".rainbow-tip, .rainbow-guide, .rainbow-hover-dot").forEach(function (el) {
      el.style.display = "none";
    });
  }

  function show(chart, clientX) {
    const m = getModel(chart);
    const svg = chart.querySelector("svg");
    if (!m || !svg) return;
    const rect = svg.getBoundingClientRect();
    const scale = rect.width / m.W;
    const vx = (clientX - rect.left) / scale;
    const pw = m.W - m.L - m.R, ph = m.H - m.T - m.B;
    if (vx < m.L || vx > m.W - m.R) return hide(chart);
    const t = m.t0 + ((vx - m.L) / pw) * (m.t1 - m.t0);
    const day = Math.round((t - m.t0) / 86400);
    const days = (t - m.g) / 86400;
    if (days <= 1) return hide(chart);
    const center = m.slope * Math.log(days) + m.icpt;
    const py = function (v) { return m.T + ((m.ymax - v) / (m.ymax - m.ymin)) * ph; };
    const hit = priceAt(m, day);
    const exact = hit && Math.abs(hit[0] - day) <= 3 ? hit : null;
    const tDisp = exact ? m.t0 + exact[0] * 86400 : t;

    let bandIdx = -1;
    if (exact) {
      const pos = (Math.log10(exact[1]) - (center + m.lo)) / m.step;
      bandIdx = Math.max(0, Math.min(m.bands.length - 1, Math.floor(pos)));
    }
    const parts = ensureParts(chart);
    const tip = parts[0], guide = parts[1], dot = parts[2];
    // SVG elements have no offsetLeft/offsetTop: measure against the chart box.
    const crect = chart.getBoundingClientRect();
    const offX = rect.left - crect.left, offY = rect.top - crect.top;
    const xPx = offX + (exact ? m.L + ((exact[0] * 86400) / (m.t1 - m.t0)) * pw : vx) * scale;

    guide.style.display = "block";
    guide.style.left = xPx + "px";
    guide.style.top = offY + m.T * scale + "px";
    guide.style.height = ph * scale + "px";
    if (exact) {
      dot.style.display = "block";
      dot.style.left = xPx + "px";
      dot.style.top = offY + py(Math.log10(exact[1])) * scale + "px";
    } else {
      dot.style.display = "none";
    }

    let rows = "";
    for (let k = m.bands.length - 1; k >= 0; k--) {
      const level = Math.pow(10, center + m.lo + k * m.step);
      const cur = k === bandIdx ? " rainbow-tip-row-current" : "";
      rows += '<div class="rainbow-tip-row' + cur + '"><span class="rainbow-tip-swatch" style="background:' + m.bands[k][1] +
        '"></span><span class="rainbow-tip-label">' + m.bands[k][0] + '</span><span class="rainbow-tip-level">' + fmtLevel(level) + "</span></div>";
    }
    tip.innerHTML =
      '<div class="rainbow-tip-date">' + fmtDate(tDisp) + "</div>" +
      (exact
        ? '<div class="rainbow-tip-price">' + m.asset + " " + fmtUsd(exact[1]) + "</div>"
        : '<div class="rainbow-tip-price rainbow-tip-muted">' + (day > m.pts[m.pts.length - 1][0] ? "Projected bands" : "No price data") + "</div>") +
      rows;
    tip.style.display = "block";
    const w = tip.offsetWidth, cw = chart.clientWidth;
    let left = xPx + 14;
    if (left + w > cw) left = Math.max(0, xPx - 14 - w);
    tip.style.left = left + "px";
    tip.style.top = offY + 8 + "px";
  }

  function onMove(e) {
    const chart = e.target.closest && e.target.closest(".rainbow-chart");
    if (!chart) {
      document.querySelectorAll(".rainbow-chart").forEach(hide);
      return;
    }
    show(chart, e.clientX);
  }

  document.addEventListener("pointermove", onMove, { passive: true });
  document.addEventListener("pointerdown", onMove, { passive: true });
  // A mouse leaving the window hides it; a finger lifting off (touch fires
  // pointerleave right after the tap) keeps it until the next tap elsewhere.
  document.addEventListener("pointerleave", function (e) {
    if (e.pointerType === "touch") return;
    document.querySelectorAll(".rainbow-chart").forEach(hide);
  });
})();
