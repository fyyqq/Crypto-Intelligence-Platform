// Coin page "My lines" chart (components/portfolio_page.py::coin_chart_lines_view): shown in the main chart area,
// for MEXC viewers on a coin they hold or have orders on, instead of the TradingView widget (a cross-site iframe
// a page cannot draw on). TradingView Lightweight Charts (Apache-2.0, self-hosted in /vendor, loaded only when
// such a chart is on the page) draws the coin's MEXC candles with horizontal price lines: average buy price
// (blue), limit orders (green) and stop / stop-loss orders (red, dashed, at the trigger price). The server puts
// the data on the element (data-candles, data-lines: JSON) and refreshes it; this script redraws whenever those
// attributes change, refits the time axis when the coin or timeframe changes (data-fit), and follows light/dark.
// Your own buys and sells of the coin (data-trades: [[time s, "B" | "S", price, qty], ...]) are drawn as green "B" and
// red "S" circles at the price of the fill on the candle it happened in (fills of the same side in one candle share
// one circle at their average price), by a small series primitive (Lightweight Charts plugin API).
(function () {
  if (window.__pfLinesChart) return;
  window.__pfLinesChart = true;
  var LIB = "/vendor/lightweight-charts-4.2.3.standalone.production.js";
  var SEL = ".pf-lines-chart";
  var loading = null;

  function lib() {
    if (window.LightweightCharts) return Promise.resolve(window.LightweightCharts);
    if (!loading) {
      loading = new Promise(function (resolve, reject) {
        var s = document.createElement("script");
        s.src = LIB;
        s.onload = function () { resolve(window.LightweightCharts); };
        s.onerror = function (e) { loading = null; reject(e); };
        document.head.appendChild(s);
      });
    }
    return loading;
  }

  function dark() { return document.documentElement.classList.contains("dark"); }

  function themeOptions() {
    var d = dark();
    var grid = d ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)";
    return {
      layout: { background: { color: "transparent" }, textColor: d ? "#b4b4b4" : "#60646c", fontSize: 12, attributionLogo: true },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
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

  var BUY = "#2ebd85", SELL = "#f6465d";

  // The fills snapped to the candle they fall in: [{t: candle open time, side, price, n}], fills of one side in one candle merged.
  function groupTrades(trades, candles) {
    if (!candles.length) return [];
    var first = candles[0][0], out = {}, list = [];
    trades.forEach(function (tr) {
      var when = tr[0];
      if (when < first) return; // older than the candles on the chart
      var lo = 0, hi = candles.length - 1;
      while (lo < hi) { var mid = (lo + hi + 1) >> 1; if (candles[mid][0] <= when) lo = mid; else hi = mid - 1; }
      var t = candles[lo][0], key = t + tr[1], g = out[key];
      if (!g) { g = out[key] = { t: t, side: tr[1], cost: 0, qty: 0, n: 0 }; list.push(g); }
      g.cost += tr[2] * tr[3]; g.qty += tr[3]; g.n += 1;
    });
    return list.map(function (g) { return { t: g.t, side: g.side, price: g.cost / g.qty, n: g.n }; });
  }

  // Series primitive that draws the circles; it asks the chart for coordinates on every frame, so pan / zoom just work.
  function tradeMarks() {
    var state = { chart: null, series: null, marks: [], update: null };
    var renderer = {
      draw: function (target) {
        if (!state.chart || !state.series) return;
        target.useMediaCoordinateSpace(function (scope) {
          var ctx = scope.context;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.font = "bold 11px -apple-system, Segoe UI, Roboto, sans-serif";
          state.marks.forEach(function (m) {
            var x = state.chart.timeScale().timeToCoordinate(m.t), y = state.series.priceToCoordinate(m.price);
            if (x === null || y === null || x < -10 || x > scope.mediaSize.width + 10) return;
            ctx.beginPath();
            ctx.arc(x, y, 9, 0, Math.PI * 2);
            ctx.fillStyle = m.side === "B" ? BUY : SELL;
            ctx.fill();
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = "rgba(255,255,255,0.9)";
            ctx.stroke();
            ctx.fillStyle = "#fff";
            ctx.fillText(m.side, x, y + 0.5);
          });
        });
      },
    };
    var view = { zOrder: function () { return "top"; }, renderer: function () { return renderer; } };
    return {
      attached: function (p) { state.chart = p.chart; state.series = p.series; state.update = p.requestUpdate; },
      detached: function () { state.chart = state.series = state.update = null; },
      paneViews: function () { return [view]; },
      updateAllViews: function () {},
      set: function (marks) { state.marks = marks; if (state.update) state.update(); },
    };
  }

  function render(el) {
    var candles = parse(el, "data-candles");
    var lines = parse(el, "data-lines");
    var trades = parse(el, "data-trades");
    var empty = el.querySelector(".pf-lines-empty");
    if (!candles.length) {
      if (empty) empty.style.display = "";
      return;
    }
    lib().then(function (LWC) {
      var host = el.querySelector(".pf-lines-canvas");
      if (!host) return;
      if (!el.__chart) {
        el.__chart = LWC.createChart(host, Object.assign({ autoSize: true }, themeOptions()));
        el.__series = el.__chart.addCandlestickSeries({ upColor: "#26a69a", downColor: "#ef5350", borderVisible: false, wickUpColor: "#26a69a", wickDownColor: "#ef5350" });
        el.__lines = [];
        el.__marks = tradeMarks();
        el.__series.attachPrimitive(el.__marks);
      }
      if (empty) empty.style.display = "none";
      var series = el.__series;
      var p = precision(candles[candles.length - 1][4]);
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
      el.__marks.set(groupTrades(trades, candles));
      var fit = el.getAttribute("data-fit") || "";
      if (el.__fitted !== fit) {
        el.__chart.timeScale().fitContent();
        el.__fitted = fit;
      }
    }).catch(function () { if (empty) { empty.textContent = "The chart could not load."; empty.style.display = ""; } });
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

  function scan() { document.querySelectorAll(SEL).forEach(schedule); }

  new MutationObserver(function (records) {
    records.forEach(function (r) {
      if (r.type === "attributes" && r.target.matches && r.target.matches(SEL)) schedule(r.target);
      else if (r.type === "childList") r.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        if (n.matches(SEL)) schedule(n);
        else if (n.querySelectorAll) n.querySelectorAll(SEL).forEach(schedule);
      });
    });
  }).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-candles", "data-lines", "data-trades", "data-fit"] });

  // light/dark switch: restyle every chart
  new MutationObserver(function () {
    document.querySelectorAll(SEL).forEach(function (el) { if (el.__chart) el.__chart.applyOptions(themeOptions()); });
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan);
  else scan();
})();
