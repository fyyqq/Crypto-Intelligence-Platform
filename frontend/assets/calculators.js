// /tools/pnl-calculator and /tools/currency-converter (components/calculator_pages.py): the arithmetic runs here, in the
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

  // terms = [{amount, op}] in one currency; op ("+" or "-") joins a term to the one before it (the first term's op is ignored):
  // 1000 + 1000 - 250 = 1750, worked left to right. Returns the total.
  function sumTerms(terms) {
    var total = 0;
    for (var i = 0; i < terms.length; i++) total += i > 0 && terms[i].op === "-" ? -terms[i].amount : terms[i].amount;
    return total;
  }

  // The rise (+) or drop (-) of the total against the main value (the first amount), in percent; null when the main value is 0.
  function pctChange(base, total) {
    return base > 0 ? (total - base) / base * 100 : null;
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

  // DCA plan against an all-time high. tiers = [{drop, pct}]: a drop of 75 means the price is 75% below the ATH, pct is the
  // share of the budget bought there. Per tier: the price (ath x (1 - drop)), the money spent (budget x pct), the tokens
  // bought, and the real % move from the previous tier's price (the first tier is measured from the ATH). Tiers whose drop
  // is not between 0 and 100 (or pct below 0) are invalid and skipped in the totals.
  function dca(budget, ath, tiers) {
    var rows = [], invested = 0, tokens = 0, prev = ath, pctSum = 0;
    for (var i = 0; i < tiers.length; i++) {
      var t = tiers[i], ok = t.drop != null && t.pct != null && t.drop >= 0 && t.drop < 100 && t.pct >= 0;
      if (!ok) { rows.push({ valid: false }); continue; }
      var price = ath * (1 - t.drop / 100), spent = budget * t.pct / 100, got = spent / price;
      var loss = budget * t.drop / 100; // what a fall of `drop`% takes from the capital put in
      rows.push({ valid: true, drop: t.drop, pct: t.pct, price: price, spent: spent, tokens: got, vsPrev: (price / prev - 1) * 100, fromAth: i === 0 || prev === ath, loss: loss, balance: budget - loss });
      invested += spent; tokens += got; prev = price; pctSum += t.pct;
    }
    var avg = tokens > 0 ? invested / tokens : null;
    return { rows: rows, invested: invested, tokens: tokens, avg: avg, avgDrop: avg == null ? null : (avg / ath - 1) * 100, pctSum: pctSum };
  }

  var api = { num: num, money: money, signed: signed, profit: profit, convert: convert, sumTerms: sumTerms, pctChange: pctChange, other: other, equalPcts: equalPcts, splitAmounts: splitAmounts, dca: dca };
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

  // ---- add / subtract amounts (Currency Converter page, second card) ----------------------------------------------
  var MAX_TERMS = 10;

  function buildSumRows(root) {
    var body = q(root, '[data-o="terms"]'), terms = root.__terms || [];
    if (!body) return;
    var html = "";
    for (var i = 0; i < terms.length; i++) {
      html += '<div class="calc-term' + (i > 0 ? " calc-term-op" : "") + '">' +
        (i > 0 ? '<div class="calc-segs calc-ops"><button type="button" class="calc-seg" data-op="+" data-ti="' + i + '" aria-label="Add amount ' + (i + 1) + '">+</button><button type="button" class="calc-seg" data-op="-" data-ti="' + i + '" aria-label="Subtract amount ' + (i + 1) + '">−</button></div>' : "") +
        '<div class="calc-input-wrap"><span class="calc-affix" data-term-prefix="' + i + '"></span><input type="text" inputmode="decimal" autocomplete="off" spellcheck="false" class="calc-input" data-term="' + i + '" placeholder="0" aria-label="Amount ' + (i + 1) + '" value="' + String(terms[i].amt == null ? "" : terms[i].amt).replace(/"/g, "") + '"></div>' +
        (terms.length > 2 ? '<button type="button" class="calc-del" aria-label="Remove amount ' + (i + 1) + '" data-del-term="' + i + '">×</button>' : "") + "</div>";
    }
    body.innerHTML = html;
  }

  function renderSum(root, rebuild) {
    var cur = root.dataset.cur || "USD";
    var o = other(cur);
    var rate = rateOf(root);
    mark(root, "data-cur", cur);
    if (rebuild) buildSumRows(root);
    var terms = root.__terms || [];
    var addButtons = root.querySelectorAll("[data-add-term]");
    for (var b = 0; b < addButtons.length; b++) addButtons[b].style.display = terms.length >= MAX_TERMS ? "none" : "";
    for (var i = 0; i < terms.length; i++) { // the currency symbol in front of every box and each row's pressed + / - button
      var pre = q(root, '[data-term-prefix="' + i + '"]');
      if (pre) pre.textContent = SYM[cur];
      var btns = root.querySelectorAll('[data-op][data-ti="' + i + '"]');
      for (var k = 0; k < btns.length; k++) btns[k].classList.toggle("calc-seg-active", btns[k].getAttribute("data-op") === (terms[i].op === "-" ? "-" : "+"));
    }
    // A row left empty is skipped (with its operator); a row with text that is not a number makes the total "check".
    var used = [], bad = false;
    for (var j = 0; j < terms.length; j++) {
      var raw = String(terms[j].amt || "").trim();
      if (raw === "") continue;
      var v = num(raw);
      if (v == null) { bad = true; continue; }
      used.push({ amount: v, op: terms[j].op === "-" ? "-" : "+" });
    }
    var clear = function (msg) { out(root, "result", "—"); out(root, "pct", ""); out(root, "formula", msg); out(root, "other", ""); out(root, "rates", ""); };
    if (bad) return clear("Check the amounts: numbers only.");
    if (!used.length) return clear("Enter at least one amount.");
    var total = sumTerms(used);
    var formula = "";
    for (var n = 0; n < used.length; n++) formula += (n > 0 ? (used[n].op === "-" ? " - " : " + ") : "") + money(used[n].amount, cur);
    out(root, "result", money(total, cur));
    var ch = pctChange(used[0].amount, total), pctEl = out(root, "pct", "");
    if (ch != null && pctEl) {
      var rounded = Math.round(ch * 100) / 100;
      pctEl.textContent = (rounded > 0 ? "+" : "") + fmtPct(rounded) + "%";
      pctEl.title = (rounded > 0 ? "Up " : rounded < 0 ? "Down " : "No change ") + (rounded ? fmtPct(Math.abs(rounded)) + "% " : "") + "from the main value " + money(used[0].amount, cur);
      setTone(pctEl, rounded);
    }
    out(root, "formula", formula + " = " + money(total, cur));
    out(root, "other", rate ? "≈ " + money(convert(total, cur, rate), o) : "Waiting for the live rate…");
    out(root, "rates", rate ? "1 USD = " + rateText(rate) + " MYR   ·   1 MYR = " + rateText(1 / rate) + " USD" : "");
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

  // ---- DCA against the ATH -------------------------------------------------------------------------------------
  var MAX_TIERS = 20;

  function pos(text) { return num(String(text == null ? "" : text).replace(/^\s*[-−–]/, "")); } // "-75" and "75" are the same drop

  // Prices: never rounded to nothing (0.0000123 stays readable).
  function price(v, cur) {
    var digits = v >= 1 ? 4 : v >= 0.01 ? 6 : 10;
    return SYM[cur] + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: digits });
  }

  function buildDcaRows(root) {
    var body = q(root, '[data-o="tiers"]'), tiers = root.__tiers || [];
    if (!body) return;
    var html = "";
    for (var i = 0; i < tiers.length; i++) {
      var inp = function (k, v, label) {
        return '<div class="calc-input-wrap calc-pct-wrap"><input type="text" inputmode="decimal" autocomplete="off" class="calc-input" data-t="' + i + '" data-k="' + k + '" aria-label="Tier ' + (i + 1) + " " + label + '" value="' + String(v == null ? "" : v).replace(/"/g, "") + '"><span class="calc-affix">%</span></div>';
      };
      html += "<tr><td>" + (i + 1) + "</td><td>" + inp("drop", tiers[i].drop, "drop from the ATH") + "</td><td>" + inp("pct", tiers[i].pct, "share of the budget") + '</td><td class="dca-spent"></td><td class="dca-price"></td><td class="dca-vs"></td><td class="dca-loss"></td><td class="dca-bal"></td><td>' +
        (tiers.length > 1 ? '<button type="button" class="calc-del" aria-label="Remove tier ' + (i + 1) + '" data-del-tier="' + i + '">×</button>' : "") + "</td></tr>";
    }
    body.innerHTML = html;
  }

  function renderDca(root, rebuild) {
    var cur = root.dataset.cur || "USD";
    mark(root, "data-cur", cur);
    out(root, "prefix", SYM[cur]);
    out(root, "prefix2", SYM[cur]);
    if (rebuild) buildDcaRows(root);
    var addButtons = root.querySelectorAll("[data-add-tier]");
    for (var b = 0; b < addButtons.length; b++) addButtons[b].style.display = (root.__tiers || []).length >= MAX_TIERS ? "none" : "";
    var budget = num(q(root, '[data-f="budget"]').value), ath = num(q(root, '[data-f="ath"]').value);
    var tiers = (root.__tiers || []).map(function (t) { var d = pos(t.drop), p = num(t.pct); return { drop: d, pct: p }; });
    var ready = budget != null && ath != null && ath > 0;
    // A row with both boxes still empty (just added) is not an error: it shows dashes and is left out.
    var blank = (root.__tiers || []).map(function (t) { return String(t.drop || "").trim() === "" && String(t.pct || "").trim() === ""; });
    var r = ready ? dca(budget, ath, tiers) : null;
    var trs = root.querySelectorAll('[data-o="tiers"] tr');
    for (var i = 0; i < trs.length; i++) {
      var row = r && r.rows[i], cell = function (c, text) { var el = trs[i].querySelector(c); if (el) el.textContent = text; };
      if (!row || !row.valid) { cell(".dca-spent", "—"); cell(".dca-price", "—"); cell(".dca-vs", row && !blank[i] ? "check" : "—"); cell(".dca-loss", "—"); cell(".dca-bal", "—"); continue; }
      cell(".dca-spent", money(row.spent, cur));
      cell(".dca-price", price(row.price, cur));
      // Loss %: the drop from the ATH (-75%, -80%, -85%), the same value as the Drop from ATH column; the hover says how far
      // the price falls from the previous tier.
      var vs = trs[i].querySelector(".dca-vs");
      if (vs) {
        vs.textContent = row.drop > 0 ? "-" + fmtPct(Math.round(row.drop * 100) / 100) + "%" : "0%";
        vs.title = "From the previous tier the price moves " + (row.vsPrev > 0 ? "+" : "") + fmtPct(Math.round(row.vsPrev * 100) / 100) + "%" + (row.fromAth ? " (measured from the ATH)" : "");
        vs.classList.toggle("calc-down", row.drop > 0);
      }
      cell(".dca-loss", row.loss > 0 ? "-" + money(row.loss, cur) : money(0, cur));
      var bal = trs[i].querySelector(".dca-bal");
      if (bal) { bal.textContent = money(row.balance, cur); bal.classList.toggle("calc-down", row.balance < 0); }
    }
    var allValid = r && r.rows.length > 0 && r.rows.every(function (x, i) { return x.valid || blank[i]; });
    var status = q(root, '[data-o="status"]'), sum = r ? Math.round(r.pctSum * 10000) / 10000 : 0, msg = "", tone = 0;
    if (!ready) msg = "Enter your budget and the ATH price.";
    else if (!allValid) { msg = "Each tier needs a drop between 0% and 99.99% and a budget share of 0% or more."; tone = -1; }
    else if (Math.abs(sum - 100) < 0.005) { msg = "Budget used: 100% ✓"; tone = 1; }
    else if (sum < 100) msg = "Budget used: " + fmtPct(sum) + "% · " + fmtPct(Math.round((100 - sum) * 10000) / 10000) + "% not assigned (" + money(budget - r.invested, cur) + ")";
    else { msg = "Budget used: " + fmtPct(sum) + "% · over by " + fmtPct(Math.round((sum - 100) * 10000) / 10000) + "%"; tone = -1; }
    if (status) { status.textContent = msg; status.classList.toggle("calc-up", tone > 0); status.classList.toggle("calc-down", tone < 0); status.classList.toggle("calc-amber", tone === 0); }
  }

  function render(root) {
    if (root.dataset.calc === "dca") renderDca(root, !root.__built && (root.__built = true));
    else if (root.dataset.calc === "profit") renderProfit(root);
    else if (root.dataset.calc === "convert") renderConvert(root);
    else if (root.dataset.calc === "sum") renderSum(root, !root.__built && (root.__built = true));
    else if (root.dataset.calc === "split") renderSplit(root, !root.__built && (root.__built = true));
  }

  function init(root) {
    if (root.__calcReady) return;
    root.__calcReady = true;
    root.dataset.cur = root.dataset.cur || "USD"; // USD is the default currency
    root.dataset.sign = root.dataset.sign || "1";
    root.dataset.mode = root.dataset.mode || "equal";
    root.dataset.count = root.dataset.count || "3";
    if (root.dataset.calc === "sum" && !root.__terms) root.__terms = [{ amt: "1000", op: "+" }, { amt: "1000", op: "+" }]; // $1000 + $1000
    if (root.dataset.calc === "dca" && !root.__tiers) root.__tiers = [{ drop: "75", pct: "30" }, { drop: "80", pct: "30" }, { drop: "85", pct: "40" }]; // the example
    render(root);
  }

  function scan() {
    var roots = document.querySelectorAll(".calc-root");
    for (var i = 0; i < roots.length; i++) init(roots[i]);
  }

  document.addEventListener("input", function (e) {
    var root = e.target.closest && e.target.closest(".calc-root");
    if (!root || !e.target.matches("input")) return;
    if (root.dataset.calc === "dca") {
      if (e.target.hasAttribute("data-t")) root.__tiers[parseInt(e.target.getAttribute("data-t"), 10)][e.target.getAttribute("data-k")] = e.target.value;
      renderDca(root, false); // the box being typed in is never rebuilt
      return;
    }
    if (root.dataset.calc === "sum") {
      if (e.target.hasAttribute("data-term")) root.__terms[parseInt(e.target.getAttribute("data-term"), 10)].amt = e.target.value;
      renderSum(root, false); // the box being typed in is never rebuilt
      return;
    }
    if (root.dataset.calc === "split") {
      if (e.target.hasAttribute("data-pct")) (root.__pcts = root.__pcts || [])[parseInt(e.target.getAttribute("data-pct"), 10)] = e.target.value;
      renderSplit(root, false); // the row being typed in is never rebuilt
      return;
    }
    render(root);
  }, true);

  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest(".calc-root [data-cur], .calc-root [data-sign], .calc-root [data-swap], .calc-root [data-mode], .calc-root [data-step], .calc-root [data-preset], .calc-root [data-equalize], .calc-root [data-add-tier], .calc-root [data-del-tier], .calc-root [data-op], .calc-root [data-add-term], .calc-root [data-del-term]");
    if (!t) return;
    var root = t.closest(".calc-root");
    if (root.dataset.calc === "dca") {
      if (t.hasAttribute("data-cur")) root.dataset.cur = t.getAttribute("data-cur");
      else if (t.hasAttribute("data-add-tier")) { if (root.__tiers.length < MAX_TIERS) root.__tiers.push({ drop: "", pct: "" }); }
      else if (t.hasAttribute("data-del-tier")) { if (root.__tiers.length > 1) root.__tiers.splice(parseInt(t.getAttribute("data-del-tier"), 10), 1); }
      renderDca(root, true);
      return;
    }
    if (root.dataset.calc === "sum") {
      if (t.hasAttribute("data-op")) root.__terms[parseInt(t.getAttribute("data-ti"), 10)].op = t.getAttribute("data-op");
      else if (t.hasAttribute("data-cur")) root.dataset.cur = t.getAttribute("data-cur");
      else if (t.hasAttribute("data-add-term")) { if (root.__terms.length < MAX_TERMS) root.__terms.push({ amt: "", op: "+" }); }
      else if (t.hasAttribute("data-del-term")) { if (root.__terms.length > 2) root.__terms.splice(parseInt(t.getAttribute("data-del-term"), 10), 1); }
      renderSum(root, t.hasAttribute("data-add-term") || t.hasAttribute("data-del-term"));
      return;
    }
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
