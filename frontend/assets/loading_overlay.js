// Full-page loading screen on every page load / reload: the Repace 3D logo GIF on the app's dark background, kept
// for at least 5 seconds counted from the start of the navigation (and until the browser's own "load" has
// finished, so it never uncovers a half-built page), then faded out. Added to <html> straight away, outside the
// React root, so it shows before the app starts and is never touched by a re-render. Loaded first in
// frontend.py's head_components.
(function () {
  if (window.__repaceLoadingOverlay) return;
  window.__repaceLoadingOverlay = true;
  var MIN_MS = 5000;
  var MAX_MS = 20000; // never leave the screen covered for good

  var style = document.createElement("style");
  style.textContent =
    "#repace-loading-overlay{position:fixed;top:0;right:0;bottom:0;left:0;z-index:2147483647;display:flex;" +
    "align-items:center;justify-content:center;background:#111013;opacity:1;transition:opacity .35s ease}" +
    "#repace-loading-overlay.repace-fade{opacity:0;pointer-events:none}" +
    "#repace-loading-overlay img{width:min(360px,70vw);height:auto;display:block}";
  (document.head || document.documentElement).appendChild(style);

  var overlay = document.createElement("div");
  overlay.id = "repace-loading-overlay";
  overlay.setAttribute("role", "status");
  overlay.setAttribute("aria-label", "Loading");
  var img = document.createElement("img");
  img.src = "/loading-logo.gif";
  img.alt = "";
  overlay.appendChild(img);
  document.documentElement.appendChild(overlay);

  var timerDone = false;
  var loaded = document.readyState === "complete";
  var closed = false;
  function close() {
    if (closed) return;
    closed = true;
    overlay.classList.add("repace-fade");
    setTimeout(function () {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }, 450);
  }
  function check() {
    if (timerDone && loaded) close();
  }
  // performance.now() counts from the start of this navigation, so a slow load does not add 5 more seconds.
  setTimeout(function () {
    timerDone = true;
    check();
  }, Math.max(0, MIN_MS - performance.now()));
  if (!loaded) {
    window.addEventListener("load", function () {
      loaded = true;
      check();
    });
  }
  setTimeout(close, MAX_MS);
})();
