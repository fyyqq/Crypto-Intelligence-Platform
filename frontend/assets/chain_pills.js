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

  document.addEventListener("click", function (e) {
    const leftBtn = e.target.closest(".chain-scroll-left, .narrative-scroll-left");
    const rightBtn = e.target.closest(".chain-scroll-right, .narrative-scroll-right");
    if (!leftBtn && !rightBtn) return;
    const wrap = (leftBtn || rightBtn).closest(WRAP_SELECTOR);
    const track = wrap && wrap.querySelector(TRACK_SELECTOR);
    if (track) {
      track.scrollBy({ left: leftBtn ? -160 : 160, behavior: "smooth" });
    }
  });

  let isDown = false;
  let startX = 0;
  let startScrollLeft = 0;
  let activeTrack = null;

  document.addEventListener("mousedown", function (e) {
    const track = e.target.closest(TRACK_SELECTOR);
    if (!track) return;
    isDown = true;
    activeTrack = track;
    track.classList.add("grabbing");
    startX = e.pageX;
    startScrollLeft = track.scrollLeft;
  });

  document.addEventListener("mousemove", function (e) {
    if (!isDown || !activeTrack) return;
    e.preventDefault();
    activeTrack.scrollLeft = startScrollLeft - (e.pageX - startX);
  });

  function releaseDrag() {
    if (activeTrack) activeTrack.classList.remove("grabbing");
    isDown = false;
    activeTrack = null;
  }

  document.addEventListener("mouseup", releaseDrag);
  document.addEventListener("mouseleave", releaseDrag);
})();
