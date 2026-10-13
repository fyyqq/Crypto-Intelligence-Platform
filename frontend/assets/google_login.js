// Google sign-in on /login and /signup (components/login_page.py::_google_button).
// Renders Google's own button with the official Google Identity Services
// library (https://accounts.google.com/gsi/client, loaded by the page) and
// sends the ID token Google returns to our server, which verifies it
// (/api/auth/google) and sets the session cookie; then the site loads
// logged in. Only the public client ID is ever in the browser.
(function () {
  if (window.__googleLoginInit) return;
  window.__googleLoginInit = true;

  var clientId = null;
  var initialised = false;

  function showError(msg) {
    var el = document.getElementById("google-signin-error");
    if (!el) return;
    el.textContent = msg || "";
    el.style.display = msg ? "block" : "none";
  }

  function onCredential(response) {
    showError("");
    fetch("/api/auth/google", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: response.credential }),
    })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) { return [r.ok, d]; });
      })
      .then(function (res) {
        if (res[0] && res[1].ok) window.location.assign("/");
        else showError(res[1].error || "Google sign-in failed. Please try again.");
      })
      .catch(function () { showError("Could not reach the server. Please try again."); });
  }

  function render() {
    var el = document.getElementById("google-signin-btn");
    if (!el || !clientId || !(window.google && google.accounts && google.accounts.id)) return;
    if (el.childElementCount > 0) return; // already rendered
    if (!initialised) {
      google.accounts.id.initialize({
        client_id: clientId,
        callback: onCredential,
        ux_mode: "popup",
        auto_select: false,
        cancel_on_tap_outside: true,
      });
      initialised = true;
    }
    google.accounts.id.renderButton(el, {
      type: "standard",
      theme: "outline",
      size: "large",
      text: "continue_with",
      shape: "rectangular",
      logo_alignment: "left",
      width: Math.max(200, Math.min(380, el.clientWidth || 380)),
    });
  }

  fetch("/api/auth/google/config", { credentials: "same-origin" })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      clientId = d.client_id || null;
      if (!clientId) showError("Google sign-in isn't set up on this site.");
      render();
    })
    .catch(function () {});

  // The library and the page render asynchronously (and a page change can
  // replace the container), so keep (re)rendering until it's in place.
  setInterval(render, 400);
})();
