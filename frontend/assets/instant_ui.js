// Instant feedback in the browser for clicks that otherwise wait a full
// round trip to the server before anything visibly changes (~0.35s+ from
// Malaysia to the live server, more when it is busy). The server event still
// runs as before and its result replaces/confirms what is shown here; this
// only makes the first visible reaction immediate. Loaded on every page
// (frontend.py head_components).
//
//  1. Table: page numbers / arrows, narrative + chain pills, sortable
//     headers, rows-per-page and the table's own search show the skeleton at
//     once (.coin-table-wrap.table-loading, the hidden tbody.skel-rows) until
//     the new rows arrive, for at least MIN_SKELETON_MS like before.
//  2. Watchlist stars flip filled/empty on the click.
//  3. Popups (watchlist, notification bell) open/close on the click and on a
//     click outside.
//  4. Header search: suggestions from a coin list loaded once from
//     /api/coin-index, shown as you type; replaced by the server's live
//     results as soon as those match what is in the box.
(function () {
  if (window.__instantUiInit) return;
  window.__instantUiInit = true;

  var MIN_SKELETON_MS = 300;
  var MAX_SKELETON_MS = 8000;
  var rowsSelectOpen = false;

  // ---- 1. table skeleton ---------------------------------------------------
  function tableWrap() {
    return document.querySelector(".coin-table-wrap");
  }

  function startTableLoading() {
    var wrap = tableWrap();
    if (!wrap) return;
    wrap.classList.add("table-loading");
    wrap.__loadingSince = Date.now();
    if (!wrap.__observer) {
      wrap.__observer = new MutationObserver(function () {
        if (wrap.classList.contains("table-loading") && Date.now() - wrap.__loadingSince > 30) stopTableLoading(wrap);
      });
      wrap.__observer.observe(wrap, { childList: true, subtree: true, characterData: true });
    }
    clearTimeout(wrap.__maxTimer);
    wrap.__maxTimer = setTimeout(function () { wrap.classList.remove("table-loading"); }, MAX_SKELETON_MS);
  }

  function stopTableLoading(wrap) {
    var wait = Math.max(0, MIN_SKELETON_MS - (Date.now() - wrap.__loadingSince));
    clearTimeout(wrap.__stopTimer);
    wrap.__stopTimer = setTimeout(function () { wrap.classList.remove("table-loading"); }, wait);
  }

  function markActive(el, activeClass) {
    var parent = el.parentElement && el.parentElement.closest("div");
    if (parent) parent.querySelectorAll("." + activeClass).forEach(function (n) { n.classList.remove(activeClass); });
    el.classList.add(activeClass);
  }

  document.addEventListener(
    "click",
    function (e) {
      var t = e.target;
      if (!t.closest) return;
      var pill = t.closest(".narrative-pill, .chain-filter-pill, .page-number, .page-arrow-btn, .sortable-th");
      if (pill && tableWrap()) {
        if (pill.classList.contains("narrative-pill")) markActive(pill, "narrative-pill-active");
        else if (pill.classList.contains("chain-filter-pill")) markActive(pill, "chain-filter-pill-active");
        else if (pill.classList.contains("page-number")) markActive(pill, "page-number-active");
        startTableLoading();
      }
      if (t.closest(".rows-per-page-select")) rowsSelectOpen = true;
      else if (t.closest("[role=option]") && rowsSelectOpen && tableWrap()) {
        rowsSelectOpen = false;
        startTableLoading(); // rows-per-page choice
      }
    },
    true
  );

  document.addEventListener(
    "input",
    function (e) {
      if (e.target && e.target.id === "coin-search-input-field") startTableLoading();
    },
    true
  );

  // ---- 2. watchlist stars ----------------------------------------------------
  document.addEventListener(
    "click",
    function (e) {
      var star = e.target.closest && e.target.closest(".wl-star");
      if (!star) return;
      var svg = star.tagName.toLowerCase() === "svg" ? star : star.querySelector("svg");
      if (!svg) return;
      var on = svg.classList.contains("wl-star-force-on") ||
        (!svg.classList.contains("wl-star-force-off") && (svg.getAttribute("fill") || "none") !== "none");
      svg.classList.remove("wl-star-force-on", "wl-star-force-off");
      svg.classList.add(on ? "wl-star-force-off" : "wl-star-force-on");
      // Drop the override once the server's own render changes the star.
      var obs = new MutationObserver(function () {
        svg.classList.remove("wl-star-force-on", "wl-star-force-off");
        obs.disconnect();
      });
      obs.observe(svg, { attributes: true, attributeFilter: ["fill"] });
      setTimeout(function () { svg.classList.remove("wl-star-force-on", "wl-star-force-off"); obs.disconnect(); }, 5000);
    },
    true
  );

  // ---- 3. popups ---------------------------------------------------------------
  var POPUPS = [
    // The watchlist popup only closes from its own X (no click-outside on the server side either).
    { trigger: ".watchlist-fab", popup: ".watchlist-popup", boundary: null },
    { trigger: ".notification-bell", popup: ".notification-popup", boundary: ".notification-bell-wrap" },
  ];

  document.addEventListener(
    "click",
    function (e) {
      var t = e.target;
      if (!t.closest) return;
      POPUPS.forEach(function (p) {
        var el = document.querySelector(p.popup);
        if (!el) return;
        var isOpen = getComputedStyle(el).display !== "none";
        if (t.closest(p.trigger)) {
          el.style.display = isOpen ? "none" : "flex";
        } else if (isOpen && p.boundary && !t.closest(p.boundary)) {
          el.style.display = "none"; // click outside (the server is told by the existing listeners)
        } else if (isOpen && t.closest(p.popup) && t.closest(".lucide-x")) {
          el.style.display = "none"; // the popup's own close button
        }
      });
    },
    true
  );

  // ---- 3b. price alert popup --------------------------------------------------
  // The add / edit alert popup (coin_detail.py::_alert_dialog) is always in the page; a click on any .alert-open-btn
  // shows it at once, prefilled (the coin's price text, or the edited alert's price), while the click's own server
  // event (which alert is edited, alert_dialog_open) is still on its way. Cancel / backdrop / Escape hide it at once
  // too. The server stays the authority: it keeps the popup open on an error and closes it after a save.
  function setNative(input, value) {
    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true })); // lets the app's own input state follow
  }

  document.addEventListener(
    "click",
    function (e) {
      var t = e.target;
      if (!t.closest) return;
      var ov = document.querySelector(".alert-overlay");
      if (!ov) return;
      var btn = t.closest(".alert-open-btn");
      if (btn) {
        var edit = btn.getAttribute("data-alert-mode") === "edit";
        ov.classList.remove("js-closed");
        ov.classList.add("js-open");
        var title = ov.querySelector(".alert-title");
        if (title) title.textContent = edit ? "Edit price alert" : "New price alert";
        var input = ov.querySelector("input");
        if (input) {
          var price = edit ? btn.getAttribute("data-alert-price") || "" : String(ov.getAttribute("data-now") || "").replace(/[$,\s]/g, "");
          setNative(input, price);
          setTimeout(function () { input.focus(); input.select(); }, 0);
        }
      } else if (t.closest(".alert-close")) {
        ov.classList.remove("js-open");
        ov.classList.add("js-closed");
      }
    },
    true
  );

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var ov = document.querySelector(".alert-overlay");
    if (ov && getComputedStyle(ov).display !== "none") {
      var cancel = ov.querySelector(".alert-cancel");
      if (cancel) cancel.click(); // hides it now and tells the server
    }
  });

  // When the server closes the popup (after a save) drop the instant-open flag, so the next open starts clean.
  new MutationObserver(function (records) {
    records.forEach(function (r) {
      var ov = r.target;
      if (ov.getAttribute("data-open") === "false") ov.classList.remove("js-open");
    });
  }).observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ["data-open"] });

  // ---- 3c. phone header: the search icon shows / hides the search bar below the header --------------------
  document.addEventListener(
    "click",
    function (e) {
      var t = e.target;
      if (!t.closest || !t.closest(".header-search-toggle")) return;
      var header = document.querySelector(".site-header");
      if (!header) return;
      var open = header.classList.toggle("mobile-search-open");
      if (open) {
        var input = header.querySelector(".global-search-input");
        if (input) setTimeout(function () { input.focus(); }, 0);
      }
    },
    true
  );

  // ---- 4. header search suggestions -------------------------------------------
  var index = null;
  var loading = null;

  function loadIndex() {
    if (index || loading) return loading;
    loading = fetch("/api/coin-index", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (rows) { index = rows; return rows; })
      .catch(function () { index = []; return []; });
    return loading;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function instantBox(container) {
    var box = container.querySelector(".gs-instant");
    if (!box) {
      box = document.createElement("div");
      box.className = "global-search-dropdown gs-instant";
      container.appendChild(box);
    }
    return box;
  }

  function hideInstant(container) {
    if (!container) return;
    container.classList.remove("gs-pending");
    var box = container.querySelector(".gs-instant");
    if (box) box.style.display = "none";
  }

  function renderInstant(input) {
    var container = input.closest(".global-search-container");
    if (!container) return;
    var q = input.value.trim().toLowerCase();
    if (!q || !index) {
      hideInstant(container);
      return;
    }
    var matches = [];
    for (var i = 0; i < index.length && matches.length < 5; i++) {
      var r = index[i];
      if (String(r[2]).toLowerCase().indexOf(q) !== -1 || String(r[1]).toLowerCase().indexOf(q) !== -1) matches.push(r);
    }
    var html = matches.length
      ? matches.map(function (r) {
          return '<a class="global-search-result-row gs-row" data-cmc-id="' + esc(r[0]) + '" href="/coins/' + esc(String(r[6] || String(r[1]).toLowerCase())) + '">' +
            '<img src="https://s2.coinmarketcap.com/static/img/coins/64x64/' + esc(r[0]) + '.png" alt="">' +
            '<span class="gs-names"><span class="gs-name">' + esc(r[2]) + '</span><span class="gs-sym">' + esc(r[1]) + "</span></span>" +
            '<span class="gs-price"><span>' + esc(r[3]) + '</span><span class="gs-chg" style="color:' + esc(r[5]) + '">' + esc(r[4]) + "</span></span></a>";
        }).join("")
      : '<p class="global-search-empty gs-empty">No coins found for "' + esc(input.value.trim()) + '"</p>';
    var box = instantBox(container);
    box.innerHTML = html;
    box.style.display = "block";
    container.classList.add("gs-pending");
    watchServer(container, input);
  }

  function watchServer(container, input) {
    if (container.__gsObserver) return;
    container.__gsObserver = new MutationObserver(function () {
      if (!container.classList.contains("gs-pending")) return;
      var server = container.querySelector(".global-search-dropdown:not(.gs-instant)");
      if (server && server.getAttribute("data-q") === input.value) hideInstant(container);
    });
    container.__gsObserver.observe(container, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-q"] });
  }

  document.addEventListener(
    "focusin",
    function (e) {
      if (e.target && e.target.id === "global-search-input-field") loadIndex();
    },
    true
  );

  document.addEventListener(
    "input",
    function (e) {
      var input = e.target;
      if (!input || input.id !== "global-search-input-field") return;
      if (index) renderInstant(input);
      else (loadIndex() || Promise.resolve()).then(function () { renderInstant(input); });
    },
    true
  );

  document.addEventListener(
    "click",
    function (e) {
      var t = e.target;
      if (!t.closest) return;
      var container = document.querySelector(".global-search-container");
      if (!container) return;
      if (t.closest(".global-search-clear-icon") || !t.closest(".global-search-container")) hideInstant(container);
    },
    true
  );
})();
