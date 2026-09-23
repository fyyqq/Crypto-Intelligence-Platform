// Delegated (document-level) handlers for every draggable/arrow-scrollable
// pill slider on the page: the chain dropdown's carousel (see
// components/coin_table.py::_chain_carousel) and the narrative filter bar
// (see components/filters.py::_narrative_pill_slider). Both use the same
// mechanics, just different class names, and delegation means this works
// for content that doesn't exist yet at page-load time (a coin's popover
// only mounts once opened) — no per-element binding/rebinding needed.
(function () {
  if (window.__chainPillsInit) return;
  window.__chainPillsInit = true;

  const WRAP_SELECTOR = ".chain-pills-wrap, .narrative-pills-wrap";
  const TRACK_SELECTOR = ".chain-pills-track, .narrative-pills-track";
  const LEFT_BTN_SELECTOR = ".chain-scroll-left, .narrative-scroll-left";
  const RIGHT_BTN_SELECTOR = ".chain-scroll-right, .narrative-scroll-right";

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
      track.scrollBy({ left: leftBtn ? -160 : 160, behavior: "smooth" });
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

  // Catches tracks that don't exist yet at page load (a coin's popover) and
  // sets their initial arrow visibility (e.g. hides both when content
  // doesn't overflow at all).
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
