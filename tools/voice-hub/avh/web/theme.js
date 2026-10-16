/* Applied before the stylesheet renders, so a manual theme never flashes the other one. */
(function () {
  try {
    var t = JSON.parse(localStorage.getItem('avh.theme') || '"auto"');
    if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t;
  } catch (e) { /* storage blocked: follow the system */ }
})();
