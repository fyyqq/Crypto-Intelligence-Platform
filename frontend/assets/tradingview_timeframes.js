(function () {
  if (window.__tradingViewTimeframesInit) return;
  window.__tradingViewTimeframesInit = true;

  function applyInterval(chart, interval) {
    var iframe = chart.querySelector("iframe");
    if (!iframe || !interval) return;

    chart.dataset.tvInterval = interval;
    var url = new URL(iframe.src, window.location.href);
    if (url.searchParams.get("interval") !== interval) {
      url.searchParams.set("interval", interval);
      iframe.src = url.toString();
    }
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-tv-interval]");
    if (!button) return;

    var chart = button.closest("[data-tv-chart]");
    if (!chart) return;

    chart.querySelectorAll("[data-tv-interval]").forEach(function (option) {
      option.setAttribute("aria-pressed", option === button ? "true" : "false");
    });
    applyInterval(chart, button.getAttribute("data-tv-interval"));
  });

  new MutationObserver(function (records) {
    records.forEach(function (record) {
      var chart = record.target.closest && record.target.closest("[data-tv-chart]");
      if (chart && chart.dataset.tvInterval) {
        applyInterval(chart, chart.dataset.tvInterval);
      }
    });
  }).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["src"],
    subtree: true,
  });
})();