// Ambient motion that costs almost nothing while nobody is looking.
//
// With glass panels (backdrop-filter) on the page, any moving pixel makes the browser
// redraw and re-blur every panel: the cost of a frame is the same for a 48 s nebula drift
// as for a 7 px pulse. Measured on a 5K screen, one idle page kept Chrome's GPU process at
// 85 %. Two opt-ins, both keep the CSS animations exactly as written:
//
//   data-ambient          slow drifts (the nebula, wallpaper blobs): paused and moved
//                         forward AMBIENT_FPS times a second, all in one frame. For a drift
//                         of 30 s or more it looks the same and costs ~2 frames a second.
//   data-ambient="live"   small living details (a pulsing mark, a live dot): run at full
//                         rate while the window is focused.
//
// Both stand still while the tab is hidden or the window is not focused (a tool left open
// on a second screen), and resume from the same point. The attribute covers the element
// and its subtree. Never put feedback the user waits for (a spinner, a toast) under it.
// Load with defer. Without JavaScript the CSS animations simply run as before.
(() => {
  const AMBIENT_FPS = 2;
  const anims = (sel) => [...document.querySelectorAll(sel)].flatMap((el) => el.getAnimations({ subtree: true }));
  const active = () => !document.hidden && document.hasFocus();
  let elapsed = 0;
  let last = performance.now();

  function step() {
    const now = performance.now();
    if (active()) elapsed += now - last;
    last = now;
    for (const a of anims('[data-ambient]:not([data-ambient="live"])')) {
      if (a.playState !== "paused") a.pause();
      if (a.currentTime !== elapsed) a.currentTime = elapsed;
    }
  }

  function live() {
    const on = active();
    for (const a of anims('[data-ambient="live"]')) {
      if (on && a.playState === "paused") a.play();
      else if (!on && a.playState === "running") a.pause();
    }
  }

  function wake() { last = performance.now(); live(); }

  function start() {
    step(); live();
    // A live detail created later (a class toggled on) picks up the state on the next tick.
    setInterval(() => { if (active()) step(); else last = performance.now(); live(); }, 1000 / AMBIENT_FPS);
    addEventListener("blur", wake);
    addEventListener("focus", wake);
    document.addEventListener("visibilitychange", wake);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
