// Delegated (document-level) handlers for the chain-pills carousel inside
// each coin's chain dropdown (see components/coin_table.py::_chain_carousel).
// Delegation means these work for every popover, including ones that don't
// exist yet at page-load time (each row's popover content only mounts once
// opened) — no per-row binding/rebinding needed.
(function () {
  if (window.__chainPillsInit) return;
  window.__chainPillsInit = true;

  document.addEventListener("click", function (e) {
    const leftBtn = e.target.closest(".chain-scroll-left");
    const rightBtn = e.target.closest(".chain-scroll-right");
    if (!leftBtn && !rightBtn) return;
    const wrap = (leftBtn || rightBtn).closest(".chain-pills-wrap");
    const track = wrap && wrap.querySelector(".chain-pills-track");
    if (track) {
      track.scrollBy({ left: leftBtn ? -160 : 160, behavior: "smooth" });
    }
  });

  let isDown = false;
  let startX = 0;
  let startScrollLeft = 0;
  let activeTrack = null;

  document.addEventListener("mousedown", function (e) {
    const track = e.target.closest(".chain-pills-track");
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
