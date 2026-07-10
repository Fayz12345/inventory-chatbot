// Global navigation loading overlay. Shows a spinner during full-page
// navigations (link clicks / form submits) so the user never sees an idle
// page. Deliberately skips AJAX actions (which call e.preventDefault and run
// their own spinners), downloads, new-tab/modified clicks, and cross-origin
// links. A short delay avoids flashing on fast navigations; a backstop timer
// guarantees the overlay never sticks.
(function () {
  var DELAY = 140;       // ms — don't flash on snappy navigations
  var BACKSTOP = 20000;  // ms — never let the overlay stick
  var overlay, showTimer, backstopTimer;

  function build() {
    overlay = document.createElement('div');
    overlay.className = 'route-loader';
    overlay.innerHTML =
      '<div class="route-loader__box" role="status" aria-live="polite">' +
      '<div class="route-loader__spinner"></div>' +
      '<div class="route-loader__label">Loading&hellip;</div>' +
      '</div>';
    document.body.appendChild(overlay);
  }

  function show() {
    if (!overlay) return;
    overlay.classList.add('active');
    clearTimeout(backstopTimer);
    backstopTimer = setTimeout(hide, BACKSTOP);
  }
  function scheduleShow() {
    clearTimeout(showTimer);
    showTimer = setTimeout(show, DELAY);
  }
  function hide() {
    clearTimeout(showTimer);
    clearTimeout(backstopTimer);
    if (overlay) overlay.classList.remove('active');
  }

  function isInternalNav(a) {
    if (!a) return false;
    if (a.hasAttribute('download') || a.hasAttribute('data-no-loading')) return false;
    var t = a.getAttribute('target');
    if (t && t !== '_self') return false;
    var href = a.getAttribute('href') || '';
    if (!href || href.charAt(0) === '#') return false;
    if (/^(javascript:|mailto:|tel:|blob:|data:)/i.test(href)) return false;
    var url;
    try { url = new URL(a.href, window.location.href); } catch (e) { return false; }
    if (url.origin !== window.location.origin) return false;
    // pure in-page hash jump (same path+query, only hash differs)
    if (url.pathname === window.location.pathname &&
        url.search === window.location.search && url.hash) return false;
    return true;
  }

  document.addEventListener('click', function (e) {
    if (e.defaultPrevented) return;                 // handled by a JS action
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target && e.target.closest && e.target.closest('a');
    if (isInternalNav(a)) scheduleShow();
  }, false);

  document.addEventListener('submit', function (e) {
    if (e.defaultPrevented) return;                 // AJAX form, no navigation
    var f = e.target;
    if (f && (f.hasAttribute('data-no-loading') ||
              (f.getAttribute('target') && f.getAttribute('target') !== '_self'))) return;
    scheduleShow();
  }, false);

  // Clear on arrival and on back/forward (bfcache) restore.
  window.addEventListener('pageshow', hide);
  window.addEventListener('pagehide', function () { clearTimeout(showTimer); });

  if (document.body) build();
  else document.addEventListener('DOMContentLoaded', build);
})();
