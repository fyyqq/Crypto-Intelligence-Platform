// /profile sidebar (components/profile_page.py::_sidebar): the chevron button shrinks the sidebar to an icon strip and
// back by flipping `profile-collapsed` on .profile-layout; the choice is remembered in this browser. With no saved
// choice it starts open on tablets/desktop and minimized on phones (where it stacks above the page).
(function () {
  if (window.__profileSidebar) return;
  window.__profileSidebar = true;
  var KEY = "profileSidebarCollapsed";

  function saved() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function apply() {
    var layout = document.querySelector(".profile-layout");
    if (!layout || layout.dataset.sidebarInit) return;
    layout.dataset.sidebarInit = "1";
    var s = saved();
    var collapsed = s === null ? window.innerWidth < 768 : s === "1";
    layout.classList.toggle("profile-collapsed", collapsed);
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".profile-sidebar-toggle");
    if (!btn) return;
    var layout = btn.closest(".profile-layout");
    if (!layout) return;
    var collapsed = layout.classList.toggle("profile-collapsed");
    try { localStorage.setItem(KEY, collapsed ? "1" : "0"); } catch (err) {}
  });

  // The sidebar links swap the view in place (content + address bar) so the sidebar never reloads. Each path is also
  // a real route, so a refresh or a shared link opens the same view; Back/Forward re-apply the view from the path.
  function viewForPath() {
    return /^\/profile\/edit-profile\/?$/.test(location.pathname) ? "edit" : "portfolio";
  }

  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest(".profile-side-link");
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    var layout = link.closest(".profile-layout");
    if (!layout) return;
    e.preventDefault();
    e.stopPropagation();
    layout.setAttribute("data-view", link.getAttribute("data-view"));
    var href = link.getAttribute("href");
    if (location.pathname.replace(/\/$/, "") !== href) history.pushState({ profileView: link.getAttribute("data-view") }, "", href);
    window.scrollTo(0, 0);
  }, true);

  window.addEventListener("popstate", function () {
    var layout = document.querySelector(".profile-layout");
    if (layout) layout.setAttribute("data-view", viewForPath());
  });

  // The sidebar panel is exactly as tall as the visible part of the screen (below the header while it is on screen,
  // or the sticky tablet header), so the account row at its bottom is always in view.
  var queued = false;
  function fit() {
    queued = false;
    var inner = document.querySelector(".profile-sidebar-inner");
    if (!inner) return;
    if (window.innerWidth < 768) { inner.style.top = ""; inner.style.height = ""; return; }
    var header = document.querySelector(".site-header");
    var top = header ? Math.max(0, header.getBoundingClientRect().bottom) : 0;
    inner.style.top = top + "px";
    inner.style.height = Math.max(160, window.innerHeight - top) + "px";
  }
  function queueFit() { if (!queued) { queued = true; requestAnimationFrame(fit); } }
  window.addEventListener("scroll", queueFit, { passive: true });
  window.addEventListener("resize", queueFit);

  // The page is client-rendered: wait for the layout to appear (and re-apply after route changes).
  new MutationObserver(function () { apply(); queueFit(); }).observe(document.documentElement, { childList: true, subtree: true });
  apply();
  queueFit();
})();
