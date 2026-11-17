// Screenshots of a web tool through the Chrome DevTools Protocol, with real device emulation:
// desktop and phone, light and dark, and a horizontal-overflow check. Headless Chrome will
// not shrink a window below ~500 px on its own, and plain --screenshot never finishes on a
// page with an open event stream or long poll.
// Usage: node shoot.mjs <outdir> <url>   (Node 22+ for the global WebSocket)
// Point it at an instance on its own port with test or copied data, not the live one.
// Env: SHOTS=a,b  HASH=#x  WAIT=4500 (ms per shot)  SHOOT_TIMEOUT=120 (s, whole run)
//      EVAL='js' runs in the page after WAIT, then EVAL_WAIT ms (700; open a menu, say)
//
// Chrome never outlives this script: it runs detached in its own process group, and the
// group is killed and the temp profile removed on success, error, timeout and signals.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const out = process.argv[2];
const url = process.argv[3];
if (!out || !url) {
  console.error("usage: node shoot.mjs <outdir> <url>");
  process.exit(2);
}
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const SEND_TIMEOUT_MS = 30000;
const HARD_TIMEOUT_MS = Number(process.env.SHOOT_TIMEOUT || 120) * 1000;
mkdirSync(out, { recursive: true });
const profile = mkdtempSync(path.join(os.tmpdir(), "house-shoot-"));
const port = 9300 + Math.floor(Math.random() * 400);
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--hide-scrollbars", "about:blank"], { stdio: "ignore", detached: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const alive = () => chrome.exitCode === null && chrome.signalCode === null;
const killGroup = (sig) => {
  if (!chrome.pid) return;
  try { process.kill(-chrome.pid, sig); } catch { try { chrome.kill(sig); } catch { /* gone */ } }
};
const exited = new Promise((r) => chrome.once("exit", r));
let cleaned = false;
const removeProfile = () => { try { rmSync(profile, { recursive: true, force: true }); } catch { /* best effort */ } };
// Graceful: TERM the group, give Chrome 2 s, then KILL whatever is left (helpers may
// outlive the leader) and delete the profile.
async function cleanup() {
  if (cleaned) return;
  cleaned = true;
  killGroup("SIGTERM");
  if (alive()) await Promise.race([exited, sleep(2000)]);
  killGroup("SIGKILL");
  removeProfile();
}
// Last resort, synchronous: runs on any process.exit() that skipped cleanup().
process.on("exit", () => {
  if (cleaned) return;
  cleaned = true;
  killGroup("SIGKILL");
  removeProfile();
});
const bail = async (code, why) => { console.error(`shoot: ${why}, stopping Chrome`); await cleanup(); process.exit(code); };
for (const [sig, n] of [["SIGINT", 2], ["SIGTERM", 15], ["SIGHUP", 1]]) process.on(sig, () => bail(128 + n, sig));
setTimeout(() => bail(3, `no result after ${HARD_TIMEOUT_MS / 1000}s (SHOOT_TIMEOUT)`), HARD_TIMEOUT_MS).unref();

async function target() {
  for (let i = 0; i < 50; i++) {
    if (!alive()) throw new Error("chrome exited before it was ready");
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json`, { signal: AbortSignal.timeout(2000) })).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("chrome did not start");
}

let ws;
try {
  ws = new WebSocket(await target());
  await new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("DevTools websocket did not open")), 10000);
    ws.addEventListener("open", () => { clearTimeout(t); resolve(); }, { once: true });
    ws.addEventListener("error", () => { clearTimeout(t); reject(new Error("DevTools websocket error")); }, { once: true });
  });
  let id = 0;
  const pending = new Map();
  const logs = [];
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === "Runtime.exceptionThrown") logs.push("EXC " + JSON.stringify(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type)) logs.push(m.params.type + " " + m.params.args.map((a) => a.value ?? a.description).join(" "));
    if (m.method === "Log.entryAdded" && m.params.entry.level === "error") logs.push("LOG " + m.params.entry.text);
  });
  ws.addEventListener("close", () => {
    for (const [, r] of pending) r({ error: { message: "DevTools websocket closed" } });
    pending.clear();
  });
  // Every CDP call times out: a hung Chrome must not hang the script.
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const i = ++id;
    const t = setTimeout(() => { pending.delete(i); reject(new Error(`${method} timed out`)); }, SEND_TIMEOUT_MS);
    pending.set(i, (m) => { clearTimeout(t); m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m); });
    ws.send(JSON.stringify({ id: i, method, params }));
  });

  await send("Runtime.enable"); await send("Log.enable"); await send("Page.enable");
  const shots = [
    { name: "desktop-dark", w: 1440, h: 900, mobile: false, scheme: "dark" },
    { name: "desktop-light", w: 1440, h: 900, mobile: false, scheme: "light" },
    { name: "phone-dark", w: 390, h: 844, mobile: true, scheme: "dark", full: true },
    { name: "phone-light", w: 360, h: 780, mobile: true, scheme: "light", full: true },
  ];
  const only = process.env.SHOTS ? process.env.SHOTS.split(",") : null;
  for (const s of shots) {
    if (only && !only.includes(s.name)) continue;
    await send("Emulation.setDeviceMetricsOverride", { width: s.w, height: s.h, deviceScaleFactor: 2, mobile: s.mobile });
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: s.scheme }] });
    await send("Page.navigate", { url: url + (process.env.HASH || "") });
    await sleep(Number(process.env.WAIT || 4500));
    if (process.env.EVAL) {
      const r = await send("Runtime.evaluate", { expression: process.env.EVAL, returnByValue: true });
      if (r.result.exceptionDetails) logs.push("EVAL " + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text));
      await sleep(Number(process.env.EVAL_WAIT || 700));
    }
    const m = await send("Runtime.evaluate", { expression: "JSON.stringify({sw: document.documentElement.scrollWidth, iw: innerWidth, sh: document.documentElement.scrollHeight})", returnByValue: true });
    const dims = JSON.parse(m.result.result.value);
    let clip;
    if (s.full) clip = { x: 0, y: 0, width: s.w, height: Math.min(dims.sh, 4000), scale: 1 };
    const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: !!s.full, ...(clip ? { clip } : {}) });
    writeFileSync(path.join(out, s.name + ".png"), Buffer.from(shot.result.data, "base64"));
    console.log(s.name, JSON.stringify(dims), dims.sw > dims.iw ? "HORIZONTAL OVERFLOW" : "");
  }
  console.log(logs.length ? logs.join("\n") : "no console errors");
} catch (e) {
  console.error("shoot:", e.message);
  process.exitCode = 1;
} finally {
  try { ws?.close(); } catch { /* already closed */ }
  await cleanup();
}
process.exit();
