// /profile sidebar (components/profile_page.py::_sidebar): the toggle button shrinks the sidebar to an icon strip and
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

  // The page is client-rendered: wait for the layout to appear (and re-apply after route changes).
  new MutationObserver(apply).observe(document.documentElement, { childList: true, subtree: true });
  apply();
})();
