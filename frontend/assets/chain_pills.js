// Delegated (document-level) handlers for every draggable/arrow-scrollable
// pill slider on the page: the narrative filter bar (see
// components/filters.py::_narrative_pill_slider) and the chain filter bar
// (see components/filters.py::_chain_filter_slider). Both use the same
// mechanics, just different class names, and delegation means this works
// for content that doesn't exist yet at page-load time — no per-element
// binding/rebinding needed.
(function () {
  if (window.__chainPillsInit) return;
  window.__chainPillsInit = true;

  const WRAP_SELECTOR =
    ".narrative-pills-wrap, .chain-filter-pills-wrap, .alerts-slider-wrap, .news-slider-wrap, .x-posts-slider-wrap";
  const TRACK_SELECTOR =
    ".narrative-pills-track, .chain-filter-pills-track, .alerts-slider-track, .news-slider-track, .x-posts-slider-track";
  const LEFT_BTN_SELECTOR =
    ".narrative-scroll-left, .chain-filter-scroll-left, .alerts-scroll-left, .news-scroll-left, .x-posts-scroll-left";
  const RIGHT_BTN_SELECTOR =
    ".narrative-scroll-right, .chain-filter-scroll-right, .alerts-scroll-right, .news-scroll-right, .x-posts-scroll-right";

  // Hides an arrow once its end of the track is reached (nothing left to
  // scroll that direction), instead of always showing both.
  function updateArrowVisibility(track) {
    const wrap = track.closest(WRAP_SELECTOR);
    if (!wrap) return;
    const leftBtn = wrap.querySelector(LEFT_BTN_SELECTOR);
    const rightBtn = wrap.querySelector(RIGHT_BTN_SELECTOR);
    const atStart = track.scrollLeft <= 1;
    const atEnd = track.scrollLeft + track.clientWidth >= track.scrollWidth - 1;
    if (leftBtn) leftBtn.style.display = atStart ? "none" : "flex";
    if (rightBtn) rightBtn.style.display = atEnd ? "none" : "flex";
  }

  function scanTracks(root) {
    root.querySelectorAll(TRACK_SELECTOR).forEach(updateArrowVisibility);
  }

  document.addEventListener("click", function (e) {
    const leftBtn = e.target.closest(LEFT_BTN_SELECTOR);
    const rightBtn = e.target.closest(RIGHT_BTN_SELECTOR);
    if (!leftBtn && !rightBtn) return;
    const wrap = (leftBtn || rightBtn).closest(WRAP_SELECTOR);
    const track = wrap && wrap.querySelector(TRACK_SELECTOR);
    if (track) {
      // Scroll by one card/pill's width (plus its gap) instead of a fixed
      // pixel amount, since news cards are much wider than filter pills.
      const first = track.firstElementChild;
      const step = first ? first.getBoundingClientRect().width + 12 : 160;
      track.scrollBy({ left: leftBtn ? -step : step, behavior: "smooth" });
    }
  });

  // capture:true — scroll events don't bubble, but capturing still reaches
  // document for scroll on any descendant, including drag-scroll and the
  // arrow buttons' scrollBy above (which fires scroll events throughout its
  // smooth animation).
  document.addEventListener(
    "scroll",
    function (e) {
      const track = e.target.closest && e.target.closest(TRACK_SELECTOR);
      if (track) updateArrowVisibility(track);
    },
    true
  );

  // Catches tracks added after page load and sets their initial arrow
  // visibility (e.g. hides both when content doesn't overflow at all).
  new MutationObserver(() => scanTracks(document)).observe(document.body, {
    childList: true,
    subtree: true,
  });
  scanTracks(document);

  // A real click always has *some* mousedown-to-mouseup movement (mouse
  // jitter, or the browser auto-scrolling the target into view first), so
  // treating any movement as a drag would swallow ordinary pill clicks.
  // DRAG_THRESHOLD tells the two apart: below it, do nothing and let the
  // native click fire; at or past it, scroll instead and suppress the click
  // that would otherwise also fire on mouseup (which would end up
  // filtering/toggling whatever pill happens to be under the cursor when a
  // drag ends).
  const DRAG_THRESHOLD = 4;
  let isDown = false;
  let hasDragged = false;
  let suppressNextClick = false;
  let startX = 0;
  let startScrollLeft = 0;
  let activeTrack = null;

  document.addEventListener("mousedown", function (e) {
    const track = e.target.closest(TRACK_SELECTOR);
    if (!track) return;
    isDown = true;
    hasDragged = false;
    activeTrack = track;
    startX = e.pageX;
    startScrollLeft = track.scrollLeft;
  });

  document.addEventListener("mousemove", function (e) {
    if (!isDown || !activeTrack) return;
    const dx = e.pageX - startX;
    if (!hasDragged && Math.abs(dx) < DRAG_THRESHOLD) return;
    hasDragged = true;
    activeTrack.classList.add("grabbing");
    e.preventDefault();
    activeTrack.scrollLeft = startScrollLeft - dx;
  });

  function releaseDrag() {
    if (hasDragged) suppressNextClick = true;
    if (activeTrack) activeTrack.classList.remove("grabbing");
    isDown = false;
    hasDragged = false;
    activeTrack = null;
  }

  document.addEventListener("mouseup", releaseDrag);
  document.addEventListener("mouseleave", releaseDrag);

  // Capture phase so this runs before React's own (bubbling-phase) click
  // handlers, e.g. a pill's on_click filtering by narrative.
  document.addEventListener(
    "click",
    function (e) {
      if (!suppressNextClick) return;
      suppressNextClick = false;
      e.preventDefault();
      e.stopPropagation();
    },
    true
  );
})();

// Equalizes every card in a horizontal slider track to the tallest card's
// natural height — percentage height (height: 100%) can't do this reliably
// since the track's own height is intrinsic (sized by its tallest child),
// not a definite value flex percentage children can resolve against. Covers
// both the "Targeted Narrative + Coin" alerts and the news slider (same
// mechanics, different card content — see narrative_alerts.py / news_feed.py).
(function () {
  if (window.__cardHeightSyncInit) return;
  window.__cardHeightSyncInit = true;

  const EQUALIZE_TRACK_SELECTOR = ".alerts-slider-track, .news-slider-track";

  function equalizeTrack(track) {
    const cards = Array.from(track.children);
    if (!cards.length) return;
    cards.forEach(function (c) {
      c.style.height = "auto";
    });
    const maxHeight = Math.max.apply(
      null,
      cards.map(function (c) {
        return c.getBoundingClientRect().height;
      })
    );
    cards.forEach(function (c) {
      c.style.height = maxHeight + "px";
    });
  }

  function equalizeHeights() {
    document.querySelectorAll(EQUALIZE_TRACK_SELECTOR).forEach(equalizeTrack);
  }

  let resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(equalizeHeights, 150);
  });
  document.addEventListener("DOMContentLoaded", equalizeHeights);
  window.addEventListener("load", equalizeHeights);
  new MutationObserver(equalizeHeights).observe(document.body, {
    childList: true,
    subtree: true,
  });
  equalizeHeights();
})();

// Pagination: instant visual flip on click, before the backend sleep resolves.
// The state will also update (active_page_str), but this handler ensures the
// visual highlight appears synchronously with the click, not after the 250ms
// skeleton delay and re-render.
(function () {
  if (window.__paginationClickInit) return;
  window.__paginationClickInit = true;

  document.addEventListener("click", (e) => {
    const pageNumber = e.target.closest(".page-number:not(.page-number-active)");
    if (pageNumber) {
      document
        .querySelectorAll(".page-number-active")
        .forEach((el) => el.classList.remove("page-number-active"));
      pageNumber.classList.add("page-number-active");
    }
  });
})();

// "/" focuses the header's global search field (components/global_search.py)
// — the field itself shows a "/" badge advertising this, same shortcut
// convention as GitHub/Linear/etc. Ignored while already typing in any
// input/textarea/contenteditable so it doesn't hijack a "/" the user meant
// to type as a character.
(function () {
  if (window.__globalSearchShortcutInit) return;
  window.__globalSearchShortcutInit = true;

  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
    const active = document.activeElement;
    const isTyping =
      active &&
      (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable);
    if (isTyping) return;
    const input = document.getElementById("global-search-input-field");
    if (!input) return;
    e.preventDefault();
    input.focus();
  });
})();

// Closes the header search's autocomplete dropdown on a real click outside
// it. Skips the DOM query on every click when the dropdown isn't even open
// (the common case) — only reaches for .global-search-close-trigger once a
// dropdown element is actually present.
(function () {
  if (window.__globalSearchOutsideClickInit) return;
  window.__globalSearchOutsideClickInit = true;

  document.addEventListener("click", function (e) {
    if (!document.querySelector(".global-search-dropdown")) return;
    if (e.target.closest(".global-search-container")) return;
    const trigger = document.getElementById("global-search-close-trigger");
    if (trigger) trigger.click();
  });
})();

