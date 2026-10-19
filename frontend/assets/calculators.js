// /tools/profit-calculator and /tools/currency-converter (components/calculator_pages.py): the arithmetic runs here, in the
// browser, so every key press answers at once. The live USD -> MYR rate arrives as `data-rate` on the page's .calc-root
// (kept fresh by CalcState every 30 s); a new rate recalculates by itself. Only USD and MYR. The pure functions are
// exported on window.__calc (and module.exports for the tests).
(function () {
  var SYM = { USD: "$", MYR: "RM" };
  var QUICK = [1, 5, 10, 25, 50, 100, 500, 1000, 5000, 10000];

  // ---- pure maths ------------------------------------------------------------------------------------------------
  function num(text) {
    var t = String(text == null ? "" : text).replace(/[\s,]/g, "");
    if (!/^\d*\.?\d*$/.test(t) || t === "" || t === ".") return null;
    var v = parseFloat(t);
    return isFinite(v) ? v : null;
  }

  function money(v, cur) {
    var s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return (v < 0 ? "-" : "") + SYM[cur] + s;
  }

  function signed(v, cur) {
    return (v > 0 ? "+" : v < 0 ? "-" : "") + SYM[cur] + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // capital 1000, pct 50, sign +1 -> { change: 500, result: 1500 }; a loss of more than 100% is capped at 100%.
  function profit(capital, pct, sign) {
    var clamped = sign < 0 && pct > 100;
    var p = clamped ? 100 : pct;
    var change = (capital * p / 100) * (sign < 0 ? -1 : 1);
    return { change: change, result: capital + change, pct: p, clamped: clamped };
  }

  // rate = MYR per 1 USD
  function convert(amount, from, rate) {
    return from === "USD" ? amount * rate : amount / rate;
  }

  function other(cur) {
    return cur === "USD" ? "MYR" : "USD";
  }

  function rateText(v) {
    return v.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  }

  // Equal split of 100% into n parts that add up to exactly 100: 3 -> [33.33, 33.33, 33.34].
  function equalPcts(n) {
    var each = Math.floor(10000 / n) / 100, out = [];
    for (var i = 0; i < n; i++) out.push(each);
    out[n - 1] = Math.round((100 - each * (n - 1)) * 100) / 100;
    return out;
  }

  // Amounts for each percentage of `capital`, in whole cents, adding up to exactly capital x sum(pcts)% (largest remainder),
  // so 1000 split in 3 is 333.34 + 333.33 + 333.33, never 999.99. Returns the amounts in currency units.
  function splitAmounts(capital, pcts) {
    var sum = 0, i;
    for (i = 0; i < pcts.length; i++) sum += pcts[i];
    var target = Math.round(capital * sum / 100 * 100);
    var exact = pcts.map(function (p) { return capital * p / 100 * 100; });
    var cents = exact.map(Math.floor);
    var left = target - cents.reduce(function (a, b) { return a + b; }, 0);
    var order = exact.map(function (x, k) { return k; }).sort(function (a, b) { return (exact[b] - cents[b]) - (exact[a] - cents[a]) || a - b; });
    for (i = 0; left > 0 && i < order.length; i++, left--) cents[order[i]] += 1;
    return cents.map(function (c) { return c / 100; });
  }

  var api = { num: num, money: money, signed: signed, profit: profit, convert: convert, other: other, equalPcts: equalPcts, splitAmounts: splitAmounts };
  if (typeof window !== "undefined") window.__calc = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined") return;

  // ---- the page ----------------------------------------------------------------------------------------------------
  function q(root, sel) { return root.querySelector(sel); }
  function out(root, name, text) { var el = q(root, '[data-o="' + name + '"]'); if (el) el.textContent = text; return el; }
  function rateOf(root) {
    var r = parseFloat(root.getAttribute("data-rate"));
    return r > 0 ? r : 0;
  }

  function mark(root, attr, value) {
    var buttons = root.querySelectorAll("[" + attr + "]");
    for (var i = 0; i < buttons.length; i++) buttons[i].classList.toggle("calc-seg-active", buttons[i].getAttribute(attr) === String(value));
  }

  function setTone(el, v) {
    if (!el) return;
    el.classList.toggle("calc-up", v > 0);
    el.classList.toggle("calc-down", v < 0);
  }

  function renderProfit(root) {
    var cur = root.dataset.cur || "USD";
    var sign = parseInt(root.dataset.sign || "1", 10);
    var rate = rateOf(root);
    mark(root, "data-cur", cur);
    mark(root, "data-sign", sign);
    out(root, "prefix", SYM[cur]);
    var capital = num(q(root, '[data-f="capital"]').value);
    var pctIn = num(q(root, '[data-f="pct"]').value);
    var result = q(root, '[data-o="result"]'), change = q(root, '[data-o="change"]');
    if (capital == null || pctIn == null) {
      out(root, "result", "—"); out(root, "change", ""); out(root, "formula", "Enter your capital and a percentage.");
      out(root, "other", ""); out(root, "warn", ""); setTone(result, 0); setTone(change, 0);
      return;
    }
    var r = profit(capital, pctIn, sign);
    out(root, "result", money(r.result, cur));
    out(root, "change", (sign < 0 ? "Loss " : "Profit ") + signed(r.change, cur) + " (" + (sign < 0 ? "-" : "+") + r.pct.toLocaleString("en-US", { maximumFractionDigits: 4 }) + "%)");
    out(root, "formula", money(capital, cur) + (sign < 0 ? " - " : " + ") + r.pct.toLocaleString("en-US", { maximumFractionDigits: 4 }) + "% = " + money(r.result, cur));
    out(root, "warn", r.clamped ? "A loss can't be more than 100%, so it is counted as 100%." : "");
    setTone(result, r.change); setTone(change, r.change);
    var o = other(cur);
    if (rate) {
      var f = function (v) { return convert(v, cur, rate); };
      out(root, "other", money(f(r.result), o) + "  (" + (r.change ? signed(f(r.change), o) : money(0, o)) + ")  ·  1 USD = " + rateText(rate) + " MYR");
    } else {
      out(root, "other", "Waiting for the live rate…");
    }
  }

  function renderConvert(root) {
    var cur = root.dataset.cur || "USD";
    var o = other(cur);
    var rate = rateOf(root);
    mark(root, "data-cur", cur);
    out(root, "prefix", SYM[cur]);
    out(root, "to-label", o === "USD" ? "USD · US dollar" : "MYR · Malaysian ringgit");
    var amount = num(q(root, '[data-f="amount"]').value);
    var body = q(root, '[data-o="table"]');
    out(root, "th-from", cur);
    out(root, "th-to", o);
    if (!rate) {
      out(root, "result", "—"); out(root, "formula", "Waiting for the live rate…"); out(root, "rates", "");
      if (body) body.innerHTML = "";
      return;
    }
    out(root, "result", amount == null ? "—" : money(convert(amount, cur, rate), o));
    out(root, "formula", amount == null ? "Enter an amount." : money(amount, cur) + " = " + money(convert(amount, cur, rate), o));
    out(root, "rates", "1 USD = " + rateText(rate) + " MYR   ·   1 MYR = " + rateText(1 / rate) + " USD");
    if (body) {
      var rows = "";
      for (var i = 0; i < QUICK.length; i++) rows += "<tr><td>" + money(QUICK[i], cur) + "</td><td>" + money(convert(QUICK[i], cur, rate), o) + "</td></tr>";
      body.innerHTML = rows;
    }
  }

  // ---- capital splitter ----------------------------------------------------------------------------------------
  var MIN_PARTS = 2, MAX_PARTS = 12;

  function splitCount(root) {
    var n = parseInt(root.dataset.count || "3", 10);
    return Math.min(MAX_PARTS, Math.max(MIN_PARTS, isNaN(n) ? 3 : n));
  }

  function fmtPct(v) { return v.toLocaleString("en-US", { maximumFractionDigits: 4 }); }

  // The percentage of every part: equal mode = the equal split, custom mode = what is typed (kept in root.__pcts).
  function splitPcts(root) {
    var n = splitCount(root);
    if (root.dataset.mode !== "custom") { var each = []; for (var k = 0; k < n; k++) each.push(100 / n); return each; } // exact, so the cents are shared out evenly
    var raw = root.__pcts || [], out = [];
    for (var i = 0; i < n; i++) { var v = num(raw[i]); out.push(v == null ? 0 : v); }
    return out;
  }

  // Rebuilds the rows (when the number of parts, the mode or a preset changes), never while a percentage is being typed.
  function buildRows(root) {
    var n = splitCount(root), body = q(root, '[data-o="parts"]');
    if (!body) return;
    var custom = root.dataset.mode === "custom";
    var raw = root.__pcts = (root.__pcts || []).slice(0, n);
    while (raw.length < n) raw.push(custom ? "" : "");
    var html = "";
    for (var i = 0; i < n; i++) {
      var pctCell = custom
        ? '<div class="calc-input-wrap calc-pct-wrap"><input type="text" inputmode="decimal" autocomplete="off" class="calc-input" data-pct="' + i + '" aria-label="Part ' + (i + 1) + ' percentage" value="' + (raw[i] == null ? "" : String(raw[i]).replace(/"/g, "")) + '"><span class="calc-affix">%</span></div>'
        : fmtPct(100 / n) + "%";
      html += "<tr><td>Part " + (i + 1) + "</td><td>" + pctCell + '</td><td class="calc-amt"></td><td class="calc-oth"></td></tr>';
    }
    body.innerHTML = html;
  }

  function renderSplit(root, rebuild) {
    var cur = root.dataset.cur || "USD", o = other(cur), rate = rateOf(root);
    var custom = root.dataset.mode === "custom";
    mark(root, "data-cur", cur);
    mark(root, "data-mode", custom ? "custom" : "equal");
    out(root, "prefix", SYM[cur]);
    out(root, "count", String(splitCount(root)));
    out(root, "th-oth", "In " + o);
    var eqBtn = q(root, "[data-equalize]");
    if (eqBtn) eqBtn.style.display = custom ? "" : "none";
    if (rebuild) buildRows(root);
    var pcts = splitPcts(root), capital = num(q(root, '[data-f="capital"]').value);
    var sum = 0, i;
    for (i = 0; i < pcts.length; i++) sum += pcts[i];
    sum = Math.round(sum * 10000) / 10000;
    var amounts = capital == null ? null : splitAmounts(capital, pcts);
    var rows = root.querySelectorAll('[data-o="parts"] tr');
    for (i = 0; i < rows.length; i++) {
      var amt = rows[i].querySelector(".calc-amt"), oth = rows[i].querySelector(".calc-oth");
      if (amt) amt.textContent = amounts ? money(amounts[i], cur) : "—";
      if (oth) oth.textContent = amounts && rate ? money(convert(amounts[i], cur, rate), o) : "—";
    }
    var status = q(root, '[data-o="status"]'), total = q(root, '[data-o="total"]');
    var allocated = amounts ? amounts.reduce(function (a, b) { return a + b; }, 0) : null;
    if (total) total.textContent = amounts ? money(allocated, cur) : "—";
    out(root, "total-pct", fmtPct(sum) + "%");
    var msg = "", tone = 0;
    if (Math.abs(sum - 100) < 0.005) { msg = "Total 100% ✓"; tone = 1; }
    else if (sum < 100) { msg = "Total " + fmtPct(sum) + "% · " + fmtPct(Math.round((100 - sum) * 10000) / 10000) + "% left to assign" + (capital != null ? " (" + money(capital - allocated, cur) + ")" : ""); tone = 0; }
    else { msg = "Total " + fmtPct(sum) + "% · over by " + fmtPct(Math.round((sum - 100) * 10000) / 10000) + "%"; tone = -1; }
    if (status) { status.textContent = msg; status.classList.toggle("calc-up", tone > 0); status.classList.toggle("calc-down", tone < 0); status.classList.toggle("calc-amber", tone === 0); }
  }

  function render(root) {
    if (root.dataset.calc === "profit") renderProfit(root);
    else if (root.dataset.calc === "convert") renderConvert(root);
    else if (root.dataset.calc === "split") renderSplit(root, !root.__built && (root.__built = true));
  }

  function init(root) {
    if (root.__calcReady) return;
    root.__calcReady = true;
    root.dataset.cur = root.dataset.cur || "USD"; // USD is the default currency
    root.dataset.sign = root.dataset.sign || "1";
    root.dataset.mode = root.dataset.mode || "equal";
    root.dataset.count = root.dataset.count || "3";
    render(root);
  }

  function scan() {
    var roots = document.querySelectorAll(".calc-root");
    for (var i = 0; i < roots.length; i++) init(roots[i]);
  }

  document.addEventListener("input", function (e) {
    var root = e.target.closest && e.target.closest(".calc-root");
    if (!root || !e.target.matches("input")) return;
    if (root.dataset.calc === "split") {
      if (e.target.hasAttribute("data-pct")) (root.__pcts = root.__pcts || [])[parseInt(e.target.getAttribute("data-pct"), 10)] = e.target.value;
      renderSplit(root, false); // the row being typed in is never rebuilt
      return;
    }
    render(root);
  }, true);

  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest(".calc-root [data-cur], .calc-root [data-sign], .calc-root [data-swap], .calc-root [data-mode], .calc-root [data-step], .calc-root [data-preset], .calc-root [data-equalize]");
    if (!t) return;
    var root = t.closest(".calc-root");
    if (root.dataset.calc === "split" && !t.hasAttribute("data-cur")) {
      var n = splitCount(root);
      if (t.hasAttribute("data-mode")) {
        var toCustom = t.getAttribute("data-mode") === "custom";
        if (toCustom && root.dataset.mode !== "custom") root.__pcts = equalPcts(n).map(String); // start from the equal split
        root.dataset.mode = toCustom ? "custom" : "equal";
      } else if (t.hasAttribute("data-step")) {
        root.dataset.count = String(Math.min(MAX_PARTS, Math.max(MIN_PARTS, n + parseInt(t.getAttribute("data-step"), 10))));
      } else if (t.hasAttribute("data-preset")) {
        var list = t.getAttribute("data-preset").split(",");
        root.__pcts = list;
        root.dataset.count = String(list.length);
        root.dataset.mode = "custom";
      } else if (t.hasAttribute("data-equalize")) {
        root.dataset.mode = "equal"; // the exact equal split (the cents are shared out evenly)
      }
      renderSplit(root, true);
      return;
    }
    if (t.hasAttribute("data-cur")) root.dataset.cur = t.getAttribute("data-cur");
    else if (t.hasAttribute("data-sign")) root.dataset.sign = t.getAttribute("data-sign");
    else root.dataset.cur = other(root.dataset.cur || "USD"); // swap (the amount stays)
    render(root);
  }, true);

  // A new rate (the root's data-rate attribute) recalculates; the page is client-rendered, so roots appear later.
  new MutationObserver(function (muts) {
    for (var i = 0; i < muts.length; i++) {
      var m = muts[i];
      if (m.type === "attributes") {
        var root = m.target.closest && m.target.closest(".calc-root");
        if (root && root.__calcReady) render(root);
      }
    }
    scan();
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-rate"] });
  scan();
})();
