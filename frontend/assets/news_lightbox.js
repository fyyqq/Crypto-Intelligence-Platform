// News reader (components/news_detail.py): click a photo (img.news-photo) to see it full size in a popup in the middle of the
// page, with left / right arrows (and the arrow keys / a swipe) to step through the article's other photos. Esc, the x button
// or a click outside the picture closes it. Built on demand, delegated on the document because Reflex renders client-side.
(function () {
  var box = null, imgEl, counter, prevBtn, nextBtn, list = [], index = 0, lastFocus = null, startX = null;

  var ARROW = function (d) {
    return '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + d + '"></path></svg>';
  };

  // The generic category image and a group's profile picture stand in when a post has no photo; they are not worth enlarging.
  function real(i) {
    var src = i.currentSrc || i.src || "";
    return src !== "" && !/fallback-image|_avatar_/.test(src);
  }

  function photos() {
    return Array.prototype.slice.call(document.querySelectorAll("img.news-photo")).filter(real);
  }

  function build() {
    box = document.createElement("div");
    box.className = "news-lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", "Photo viewer");
    box.innerHTML =
      '<button type="button" class="nlb-btn nlb-close" aria-label="Close" data-nlb="close">' + ARROW("M18 6 6 18M6 6l12 12") + "</button>" +
      '<button type="button" class="nlb-btn nlb-prev" aria-label="Previous photo" data-nlb="prev">' + ARROW("m15 18-6-6 6-6") + "</button>" +
      '<img class="nlb-img" alt="">' +
      '<button type="button" class="nlb-btn nlb-next" aria-label="Next photo" data-nlb="next">' + ARROW("m9 18 6-6-6-6") + "</button>" +
      '<div class="nlb-count"></div>';
    document.body.appendChild(box);
    imgEl = box.querySelector(".nlb-img");
    counter = box.querySelector(".nlb-count");
    prevBtn = box.querySelector(".nlb-prev");
    nextBtn = box.querySelector(".nlb-next");
    box.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-nlb]");
      if (b) { var a = b.getAttribute("data-nlb"); if (a === "close") close(); else step(a === "next" ? 1 : -1); return; }
      if (e.target !== imgEl) close(); // a click outside the picture
    });
    box.addEventListener("touchstart", function (e) { startX = e.touches.length === 1 ? e.touches[0].clientX : null; }, { passive: true });
    box.addEventListener("touchend", function (e) {
      if (startX == null) return;
      var dx = e.changedTouches[0].clientX - startX; startX = null;
      if (Math.abs(dx) > 50) step(dx < 0 ? 1 : -1);
    }, { passive: true });
  }

  function show() {
    var el = list[index];
    imgEl.src = el.currentSrc || el.src;
    imgEl.alt = el.alt || "";
    var many = list.length > 1;
    prevBtn.style.display = nextBtn.style.display = counter.style.display = many ? "" : "none";
    counter.textContent = (index + 1) + " / " + list.length;
  }

  function step(d) {
    if (list.length < 2) return;
    index = (index + d + list.length) % list.length; // after the last photo comes the first
    show();
  }

  function open(el) {
    list = photos();
    if (!list.length) return;
    index = Math.max(0, list.indexOf(el));
    if (!box) build();
    lastFocus = document.activeElement;
    show();
    box.classList.add("nlb-open");
    document.documentElement.classList.add("nlb-lock");
    box.querySelector(".nlb-close").focus();
  }

  function close() {
    if (!box) return;
    box.classList.remove("nlb-open");
    document.documentElement.classList.remove("nlb-lock");
    imgEl.removeAttribute("src");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("img.news-photo");
    if (el && real(el)) { e.preventDefault(); open(el); }
  });

  document.addEventListener("keydown", function (e) {
    if (!box || !box.classList.contains("nlb-open")) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowRight") step(1);
    else if (e.key === "ArrowLeft") step(-1);
  });
})();
