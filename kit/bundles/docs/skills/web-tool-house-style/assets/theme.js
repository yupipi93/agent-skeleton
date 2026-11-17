/* Theme before first paint, so a manual choice never flashes the other one.
 * Load in <head>, before the stylesheet: <script src="/theme.js"></script>.
 * Rename KEY per tool. The page cycles system -> light -> dark with house.cycleTheme()
 * (chip ◐ ☀ ☾, key T); "system" removes the attribute and the CSS follows the OS. */
(function () {
  var KEY = 'tool.theme';
  var GLYPH = { system: '◐', light: '☀', dark: '☾' };
  function stored() {
    try { var t = localStorage.getItem(KEY); return t === 'light' || t === 'dark' ? t : 'system'; } catch (e) { return 'system'; }
  }
  function apply(t) {
    var root = document.documentElement;
    if (t === 'light' || t === 'dark') root.dataset.theme = t; else delete root.dataset.theme;
    var dark = t === 'dark' || (t === 'system' && window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < metas.length; i++) metas[i].content = dark ? '#07080c' : '#f4f1ea';
    var chip = document.getElementById('themeBtn');
    if (chip) { chip.textContent = GLYPH[t]; chip.setAttribute('aria-label', 'Theme: ' + t + ' (T)'); chip.title = 'Theme: ' + t + ' (T)'; }
    // Canvases and JS-coloured views listen to this to repaint with the new tokens.
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: t, dark: dark } }));
  }
  function cycle() {
    var order = ['system', 'light', 'dark'];
    var next = order[(order.indexOf(stored()) + 1) % order.length];
    try { if (next === 'system') localStorage.removeItem(KEY); else localStorage.setItem(KEY, next); } catch (e) { /* blocked */ }
    apply(next);
    return next;
  }
  apply(stored());
  if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () { apply(stored()); });
  document.addEventListener('DOMContentLoaded', function () { apply(stored()); });
  window.house = window.house || {};
  window.house.cycleTheme = cycle;
  window.house.theme = stored;
})();
