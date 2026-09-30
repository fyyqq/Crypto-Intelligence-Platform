// Renders every .g-recaptcha element (site key in its data-sitekey) once Google's api.js
// has loaded AND React has mounted the element (auto-render would miss a late-mounted one).
(function () {
  if (window.__recaptchaInit) return;
  window.__recaptchaInit = true;
  setInterval(function () {
    if (!window.grecaptcha || !window.grecaptcha.render) return;
    document.querySelectorAll(".g-recaptcha").forEach(function (el) {
      if (el.dataset.rendered) return;
      var key = el.getAttribute("data-sitekey");
      if (!key) return;
      try {
        window.grecaptcha.render(el, { sitekey: key, theme: "dark" });
        el.dataset.rendered = "1";
      } catch (e) {}
    });
  }, 300);
})();
