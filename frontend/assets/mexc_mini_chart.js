// Coin page "Your MEXC" mini chart (components/portfolio_page.py::coin_mexc_section): TradingView Lightweight
// Charts (Apache-2.0, self-hosted in /vendor, loaded only when a chart is on the page) drawing the coin's MEXC
// candles with horizontal price lines: the average buy price (blue) and every open limit / stop order (red,
// dashed for a stop's trigger). The server puts the data on the element (data-candles, data-lines, JSON) and
// refreshes it; this script redraws whenever those attributes change and follows the light/dark theme.
(function () {
  if (window.__pfMiniChart) return;
  window.__pfMiniChart = true;
  var LIB = "/vendor/lightweight-charts-4.2.3.standalone.production.js";
  var loading = null;

  function lib() {
    if (window.LightweightCharts) return Promise.resolve(window.LightweightCharts);
    if (!loading) {
      loading = new Promise(function (resolve, reject) {
        var s = document.createElement("script");
        s.src = LIB;
        s.onload = function () { resolve(window.LightweightCharts); };
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
    return loading;
  }

  function dark() { return document.documentElement.classList.contains("dark"); }

  function themeOptions() {
    var d = dark();
    return {
      layout: { background: { color: "transparent" }, textColor: d ? "#b4b4b4" : "#60646c", fontSize: 11, attributionLogo: true },
      grid: { vertLines: { visible: false }, horzLines: { color: d ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)" } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
      crosshair: { horzLine: { labelBackgroundColor: d ? "#3a3a3a" : "#60646c" }, vertLine: { labelBackgroundColor: d ? "#3a3a3a" : "#60646c" } },
    };
  }

  function parse(el, name) {
    try { return JSON.parse(el.getAttribute(name) || "[]"); } catch (e) { return []; }
  }

  function precision(price) {
    if (!(price > 0)) return 2;
    if (price >= 1) return price >= 1000 ? 2 : 4;
    return Math.min(12, Math.ceil(-Math.log10(price)) + 3);
  }

  function render(el) {
    var candles = parse(el, "data-candles");
    var lines = parse(el, "data-lines");
    var empty = el.querySelector(".pf-mini-empty");
    if (!candles.length) {
      if (empty) empty.style.display = "";
      return;
    }
    if (empty) empty.style.display = "none";
    lib().then(function (LWC) {
      var host = el.querySelector(".pf-mini-canvas");
      if (!host) return;
      if (!el.__chart) {
        el.__chart = LWC.createChart(host, Object.assign({ autoSize: true, handleScale: false, handleScroll: false }, themeOptions()));
        el.__series = el.__chart.addCandlestickSeries({ upColor: "#26a69a", downColor: "#ef5350", borderVisible: false, wickUpColor: "#26a69a", wickDownColor: "#ef5350" });
        el.__lines = [];
      }
      var series = el.__series;
      var last = candles[candles.length - 1][4];
      var p = precision(last);
      series.applyOptions({
        priceFormat: { type: "price", precision: p, minMove: Math.pow(10, -p) },
        // keep every line in view, even an order far from the current price
        autoscaleInfoProvider: function (original) {
          var r = original();
          if (!r || !r.priceRange) return r;
          var lo = r.priceRange.minValue, hi = r.priceRange.maxValue;
          lines.forEach(function (l) { lo = Math.min(lo, l.p); hi = Math.max(hi, l.p); });
          return { priceRange: { minValue: lo, maxValue: hi }, margins: r.margins };
        },
      });
      series.setData(candles.map(function (c) { return { time: c[0], open: c[1], high: c[2], low: c[3], close: c[4] }; }));
      el.__lines.forEach(function (l) { series.removePriceLine(l); });
      el.__lines = lines.map(function (l) {
        return series.createPriceLine({ price: l.p, color: l.c, lineWidth: 2, lineStyle: l.s, axisLabelVisible: true, title: l.t });
      });
      if (el.dataset.fitted !== el.getAttribute("data-symbol")) {
        el.__chart.timeScale().fitContent();
        el.dataset.fitted = el.getAttribute("data-symbol");
      }
    }).catch(function () { if (empty) { empty.textContent = "Chart could not load."; empty.style.display = ""; } });
  }

  var pending = new Set();
  var timer = null;
  function schedule(el) {
    pending.add(el);
    if (timer) return;
    timer = setTimeout(function () {
      timer = null;
      pending.forEach(function (x) { if (document.contains(x)) render(x); });
      pending.clear();
    }, 50);
  }

  function scan() { document.querySelectorAll(".pf-mini-chart").forEach(schedule); }

  new MutationObserver(function (records) {
    records.forEach(function (r) {
      if (r.type === "attributes" && r.target.classList && r.target.classList.contains("pf-mini-chart")) schedule(r.target);
      else if (r.type === "childList") r.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        if (n.classList.contains("pf-mini-chart")) schedule(n);
        else if (n.querySelectorAll) n.querySelectorAll(".pf-mini-chart").forEach(schedule);
      });
    });
  }).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-candles", "data-lines"] });

  // light/dark switch: restyle every chart
  new MutationObserver(function () {
    document.querySelectorAll(".pf-mini-chart").forEach(function (el) { if (el.__chart) el.__chart.applyOptions(themeOptions()); });
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan);
  else scan();
})();
