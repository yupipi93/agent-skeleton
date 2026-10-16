/* Service worker: app shell offline, last API answers offline, and audio cached on the
 * phone so a note still plays when the Mac is asleep or Tailscale has dropped.
 *
 * Audio is the tricky part. A media element always asks with a Range header, and the
 * Cache API stores whole 200 responses (it refuses to store a 206). So audio is cached
 * by fetching the full file without Range, and every Range request is answered by
 * slicing the cached blob into a hand-built 206.
 */
const VERSION = 'avh-v2';
const SHELL = `${VERSION}-shell`;
const API = `${VERSION}-api`;
const AUDIO = 'avh-audio';          // not versioned: audio never changes for an id
const AUDIO_MAX = 40;
const SHELL_FILES = ['/', '/static/app.css', '/static/app.js', '/static/theme.js', '/manifest.webmanifest',
  '/static/icons/icon-192.png', '/static/icons/icon-512.png', '/static/icons/favicon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith('avh-v') && !k.startsWith(VERSION)) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener('message', e => {
  if (e.data && e.data.type === 'prefetch') e.waitUntil(prefetch(e.data.urls || []));
});

async function prefetch(urls) {
  const cache = await caches.open(AUDIO);
  for (const url of urls) {
    if (await cache.match(url)) continue;
    try { await cache.add(url); } catch { /* offline or gone: try next time */ }
  }
  const keys = await cache.keys();
  for (const req of keys.slice(0, Math.max(0, keys.length - AUDIO_MAX))) await cache.delete(req);
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname === '/api/events') return;                      // live stream: never touch
  if (url.pathname.startsWith('/media/')) { e.respondWith(audio(req)); return; }
  if (url.pathname.startsWith('/api/')) { e.respondWith(networkFirst(req, API, true)); return; }
  if (req.mode === 'navigate') { e.respondWith(navigate(req)); return; }
  e.respondWith(networkFirst(req, SHELL, false));
});

async function networkFirst(req, cacheName, flag) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req);
    if (!hit) throw err;
    if (!flag) return hit;
    const headers = new Headers(hit.headers);
    headers.set('X-AVH-Offline', '1');
    return new Response(await hit.blob(), { status: 200, headers });
  }
}

async function navigate(req) {
  try {
    const res = await fetch(req);
    // A ?play=1 link may come back as the small "playing in your other tab" page: that
    // one must never become the offline app shell.
    if (res.ok && !new URL(req.url).searchParams.has('play')) (await caches.open(SHELL)).put('/', res.clone());
    return res;
  } catch {
    return (await caches.match('/')) || Response.error();
  }
}

async function audio(req) {
  const cache = await caches.open(AUDIO);
  const u = new URL(req.url);
  const key = u.pathname + u.search;            // ?v= changes when a note is re-recorded
  let hit = await cache.match(key);
  if (!hit) {
    try {
      const res = await fetch(req);
      // Played once, keep it: fetch the whole file in the background for next time.
      if (res.ok || res.status === 206) cache.add(key).catch(() => {});
      return res;
    } catch (err) {
      return new Response(null, { status: 504, statusText: 'offline, not cached' });
    }
  }
  const range = req.headers.get('range');
  if (!range) return hit;
  const blob = await hit.blob();
  const size = blob.size;
  const m = /^bytes=(\d*)-(\d*)$/.exec(range.split(',')[0].trim());
  if (!m || (!m[1] && !m[2])) return new Response(blob, { status: 200, headers: hit.headers });
  let start, end;
  if (!m[1]) { start = Math.max(0, size - Number(m[2])); end = size - 1; }
  else { start = Number(m[1]); end = m[2] ? Math.min(Number(m[2]), size - 1) : size - 1; }
  if (start >= size || end < start) {
    return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
  }
  const headers = new Headers(hit.headers);
  headers.set('Content-Range', `bytes ${start}-${end}/${size}`);
  headers.set('Content-Length', String(end - start + 1));
  headers.set('Accept-Ranges', 'bytes');
  return new Response(blob.slice(start, end + 1), { status: 206, statusText: 'Partial Content', headers });
}
