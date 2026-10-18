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

  var api = { num: num, money: money, signed: signed, profit: profit, convert: convert, other: other };
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

  function render(root) {
    if (root.dataset.calc === "profit") renderProfit(root);
    else if (root.dataset.calc === "convert") renderConvert(root);
  }

  function init(root) {
    if (root.__calcReady) return;
    root.__calcReady = true;
    root.dataset.cur = root.dataset.cur || "USD"; // USD is the default currency
    root.dataset.sign = root.dataset.sign || "1";
    render(root);
  }

  function scan() {
    var roots = document.querySelectorAll(".calc-root");
    for (var i = 0; i < roots.length; i++) init(roots[i]);
  }

  document.addEventListener("input", function (e) {
    var root = e.target.closest && e.target.closest(".calc-root");
    if (root && e.target.matches("input")) render(root);
  }, true);

  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest(".calc-root [data-cur], .calc-root [data-sign], .calc-root [data-swap]");
    if (!t) return;
    var root = t.closest(".calc-root");
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
