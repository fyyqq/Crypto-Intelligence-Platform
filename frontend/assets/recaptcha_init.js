// reCAPTCHA v3 (invisible): keeps the hidden "g-recaptcha-response" field of each form
// filled with a fresh token for its action. Tokens are single-use and expire after 2 min,
// so refresh on load, every 90 s, and again shortly after every submit.
(function () {
  if (window.__recaptchaInit) return;
  window.__recaptchaInit = true;
  function refresh() {
    if (!window.grecaptcha || !window.grecaptcha.execute) return;
    document.querySelectorAll('input[name="g-recaptcha-response"][data-sitekey]').forEach(function (el) {
      var key = el.getAttribute("data-sitekey");
      if (!key) return;
      window.grecaptcha.ready(function () {
        window.grecaptcha.execute(key, { action: el.getAttribute("data-action") || "submit" }).then(function (t) {
          el.value = t;
        }).catch(function () {});
      });
    });
  }
  var t = setInterval(function () {
    if (window.grecaptcha && window.grecaptcha.execute && document.querySelector('input[name="g-recaptcha-response"]')) {
      clearInterval(t);
      refresh();
      setInterval(refresh, 90000);
    }
  }, 300);
  document.addEventListener("submit", function () { setTimeout(refresh, 2500); }, true);
})();
