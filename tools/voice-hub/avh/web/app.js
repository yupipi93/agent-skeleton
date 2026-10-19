/* Voice Hub front end. No framework and no build step: one file, served as is. */
'use strict';

const SPEEDS = [1, 1.25, 1.5, 1.75, 2, 2.5];
const PAGE = 60;
const $ = (sel, root = document) => root.querySelector(sel);
const audio = $('#audio');

const S = {
  cfg: null,
  notes: [],
  byId: new Map(),
  hasMore: false,
  filters: { q: '', status: '', agent: '', tag: '' },
  current: null,          // note loaded in the audio element
  detailId: null,
  speed: 1,               // effective speed: what he hears, independent of synthesis rate
  queue: false,           // continue with the next unheard note when one ends
  heardSent: new Set(),
  lastSaved: 0,
  knownIds: new Set(),
  offline: false,
  playerTab: false,       // holds the 'avh-player' lock: plays notes opened elsewhere
  acks: new Map(),        // play request -> tab that answered it
  remoteReq: 0,           // request this tab is playing on behalf of another
  remote: null,           // {tab, id}: another hub tab of this browser is playing that note
};
const TAB = Math.random().toString(36).slice(2, 10);

/* ------------------------------------------------------------------ storage */
const store = {
  get(k, d) { try { const v = localStorage.getItem('avh.' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('avh.' + k, JSON.stringify(v)); } catch { /* private mode */ } },
};

/* ---------------------------------------------------------------------- api */
async function api(path, opts = {}) {
  const init = { headers: { 'Accept': 'application/json' }, ...opts };
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.headers['X-AVH'] = '1';
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  if (!res.ok) throw new Error(path + ' -> ' + res.status);
  S.offline = res.headers.get('X-AVH-Offline') === '1';
  return res.json();
}
const patch = (id, body) => api('/api/notes/' + id, { method: 'PATCH', body, keepalive: true });

/* ------------------------------------------------------------------ helpers */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function el(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; }
function fmtTime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0');
}
function fmtSpeed(x) { return (Math.round(x * 100) / 100).toString() + '×'; }
const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'short' });
const timeFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });
const fullFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'full', timeStyle: 'short' });
function dayLabel(d) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const that = new Date(d); that.setHours(0, 0, 0, 0);
  const diff = Math.round((today - that) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  return dayFmt.format(d);
}
function agentOf(n) {
  const a = (S.cfg && S.cfg.agents[n.agent]) || { name: 'Agent', badge: 'AI', color: '#8a8f98' };
  return { name: n.agent_label || a.name, badge: n.agent_badge || a.badge, color: n.agent_color || a.color };
}
function avatar(n) {
  const a = agentOf(n);
  return `<span class="avatar" style="background:${esc(a.color)}" title="${esc(a.name)}">${esc(a.badge)}</span>`;
}
// Never slower than the recording: slowing synthetic speech down is what sounds metallic.
function effFor(note, eff) { return Math.max(eff, (note && note.speech_rate) || 1); }
function rateFor(note, eff) {
  const base = note && note.speech_rate > 0 ? note.speech_rate : 1;
  return Math.min(4, Math.max(1, effFor(note, eff) / base));
}
function toast(msg, onClick) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  t.onclick = () => { t.hidden = true; if (onClick) onClick(); };
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, onClick ? 8000 : 3500);
}

/* --------------------------------------------------------------------- wave */
function waveHTML(peaks, cls = '') {
  const p = peaks && peaks.length ? peaks : new Array(80).fill(18);
  const w = p.length * 3;
  const bars = p.map((v, i) => {
    const h = Math.max(6, v);
    return `<rect x="${i * 3}" y="${(100 - h) / 2}" width="2" height="${h}" rx="1"/>`;
  }).join('');
  return `<div class="wave ${cls}">
    <svg viewBox="0 0 ${w} 100" preserveAspectRatio="none" aria-hidden="true"><g class="bars">${bars}</g></svg>
    <svg viewBox="0 0 ${w} 100" preserveAspectRatio="none" aria-hidden="true" class="done-layer" style="clip-path: inset(0 100% 0 0)"><g class="done">${bars}</g></svg>
  </div>`;
}
function setWave(container, frac) {
  if (!container) return;
  const layer = container.querySelector('.done-layer');
  if (layer) layer.style.clipPath = `inset(0 ${(100 - Math.min(1, Math.max(0, frac)) * 100).toFixed(2)}% 0 0)`;
}

/* ------------------------------------------------------------------ markdown */
function md(src) {
  const blocks = [];
  let s = String(src || '').replace(/```[^\n]*\n?([\s\S]*?)```/g, (_, code) => {
    blocks.push(`<pre><code>${esc(code.trimEnd())}</code></pre>`);
    return `\u0000${blocks.length - 1}\u0000`;
  });
  const inline = t => esc(t)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  const out = [];
  for (const para of s.split(/\n\s*\n/)) {
    const lines = para.split('\n').filter(l => l.trim() !== '');
    if (!lines.length) continue;
    if (/^\u0000\d+\u0000$/.test(para.trim())) { out.push(blocks[+para.trim().slice(1, -1)]); continue; }
    if (lines.every(l => /^\s*[-*+]\s+/.test(l))) {
      out.push('<ul>' + lines.map(l => '<li>' + inline(l.replace(/^\s*[-*+]\s+/, '')) + '</li>').join('') + '</ul>');
    } else if (lines.every(l => /^\s*\d+[.)]\s+/.test(l))) {
      out.push('<ol>' + lines.map(l => '<li>' + inline(l.replace(/^\s*\d+[.)]\s+/, '')) + '</li>').join('') + '</ol>');
    } else if (/^#{1,6}\s/.test(lines[0])) {
      out.push('<h4>' + inline(lines[0].replace(/^#+\s*/, '')) + '</h4>' + (lines.length > 1 ? '<p>' + lines.slice(1).map(inline).join('<br>') + '</p>' : ''));
    } else {
      out.push('<p>' + lines.map(inline).join('<br>') + '</p>');
    }
  }
  return out.join('').replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[+i]);
}

/* -------------------------------------------------------------------- list */
function qs() {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(S.filters)) if (v) p.set(k, v);
  p.set('limit', PAGE);
  return p;
}

async function loadList({ append = false } = {}) {
  const list = $('#list');
  if (!append && !S.notes.length) list.innerHTML = '<div class="skeleton"></div>'.repeat(4);
  const p = qs();
  if (append && S.notes.length) p.set('before', S.notes[S.notes.length - 1].created_at);
  try {
    const data = await api('/api/notes?' + p);
    S.notes = append ? S.notes.concat(data.notes) : data.notes;
    S.hasMore = data.has_more;
    for (const n of data.notes) { S.byId.set(n.id, Object.assign(S.byId.get(n.id) || {}, n)); S.knownIds.add(n.id); }
    renderList();
    prefetchAudio();
  } catch (e) {
    list.innerHTML = `<div class="empty"><b>Cannot reach the hub</b>Check that the computer running it is on and, on a phone, that Tailscale is connected.</div>`;
  }
}

function renderList() {
  const list = $('#list');
  if (!S.notes.length) {
    const filtered = Object.values(S.filters).some(Boolean);
    list.innerHTML = filtered
      ? '<div class="empty"><b>Nothing matches these filters</b>Try removing one.</div>'
      : '<div class="empty"><b>No notes yet</b>When an agent sends you a spoken summary it shows up here right away.</div>';
    return;
  }
  const frag = document.createDocumentFragment();
  if (S.offline) frag.appendChild(el('<div class="offline-banner">Offline. Showing what this device saved last.</div>'));
  let lastDay = '';
  for (const n of S.notes) {
    const d = new Date(n.created_at);
    const label = dayLabel(d);
    if (label !== lastDay) { frag.appendChild(el(`<div class="day">${esc(label)}</div>`)); lastDay = label; }
    frag.appendChild(cardEl(n, d));
  }
  if (S.hasMore) {
    const more = el('<button class="btn more" type="button">Load more</button>');
    more.onclick = () => loadList({ append: true });
    frag.appendChild(more);
  }
  list.replaceChildren(frag);
  syncPlayingUI();
}

function cardEl(n, d) {
  const a = agentOf(n);
  const title = n.title || n.summary || 'Voice note';
  const card = el(`<article class="card${n.heard_at ? '' : ' unheard'}${S.detailId === n.id ? ' active' : ''}" data-id="${esc(n.id)}" tabindex="0">
    ${avatar(n)}
    <div class="card-main">
      <div class="card-title">${n.starred ? '<span class="star-on">★</span> ' : ''}${esc(title)}</div>
      <div class="meta"><span>${esc(timeFmt.format(d))}</span><span class="sep"></span><span>${esc(a.name)}</span>${n.tag ? `<span class="sep"></span><span>${esc(n.tag)}</span>` : ''}<span class="sep"></span><span>${fmtTime(n.duration)}</span>${(n.commands || []).some(c => c.code) ? '<span class="sep"></span><span title="Has a command to copy">⌨️ command</span>' : ''}</div>
    </div>
    <div class="card-ctl">
      <button class="heard-mini" type="button" aria-pressed="${!!n.heard_at}" title="${n.heard_at ? 'Heard · tap to mark as unheard' : 'Mark as heard'}" aria-label="${n.heard_at ? 'Mark as unheard' : 'Mark as heard'}"><svg viewBox="0 0 24 24"><path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg></button>
      <button class="play-mini" type="button" aria-label="Play ${esc(title)}"><svg viewBox="0 0 24 24" class="i-play"><path d="M8 5v14l11-7z"/></svg><svg viewBox="0 0 24 24" class="i-pause"><path d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg></button>
    </div>
    ${n.title && n.summary ? `<div class="card-summary">${esc(n.summary)}</div>` : ''}
    <div class="card-wave">${waveHTML(n.peaks)}</div>
  </article>`);
  card.addEventListener('click', e => {
    if (e.target.closest('.play-mini')) { e.stopPropagation(); togglePlay(n); return; }
    if (e.target.closest('.heard-mini')) { e.stopPropagation(); update(n.id, { heard: !n.heard_at }); return; }
    const wave = e.target.closest('.card-wave');
    if (wave && seekCard(n, wave, e)) return;
    nav('/n/' + n.id);
  });
  card.addEventListener('keydown', e => { if (e.key === 'Enter') nav('/n/' + n.id); });
  if (n.position && n.duration) setWave(card.querySelector('.card-wave'), n.position / n.duration);
  return card;
}

// The note in the player: a tap on its wave in the list seeks, as on the player's own wave.
function seekCard(n, wave, e) {
  if (!S.current || S.current.id !== n.id) return false;
  const dur = isFinite(audio.duration) ? audio.duration : n.duration;
  const r = wave.getBoundingClientRect();
  if (!dur || !r.width) return false;
  const frac = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
  audio.currentTime = frac * dur;
  setWave(wave, frac);
  return true;
}

/* ------------------------------------------------------------------ facets */
async function loadFacets() {
  try {
    const f = await api('/api/facets');
    const chips = $('#agentChips');
    chips.replaceChildren(...f.agents.map(({ agent, c }) => {
      const a = (S.cfg.agents[agent]) || S.cfg.agents.unknown;
      const b = el(`<button class="chip" type="button" aria-pressed="${S.filters.agent === agent}" data-agent="${esc(agent)}"><span class="dot" style="background:${esc(a.color)}"></span>${esc(a.name)} <small>${c}</small></button>`);
      b.onclick = () => { S.filters.agent = S.filters.agent === agent ? '' : agent; refreshFilters(); };
      return b;
    }));
    const sel = $('#tagSel');
    const cur = S.filters.tag;
    sel.replaceChildren(el('<option value="">All projects</option>'),
      ...f.tags.map(({ tag, c }) => el(`<option value="${esc(tag)}">${esc(tag)} (${c})</option>`)));
    sel.value = cur;
    const unheard = f.totals.unheard || 0;
    $('#unheardCount').textContent = unheard ? unheard : '';
    $('#markAllBtn').hidden = !unheard;
    S.unheard = unheard;
    document.title = (unheard ? `(${unheard}) ` : '') + 'Voice Hub';
    if ('setAppBadge' in navigator) { (unheard ? navigator.setAppBadge(unheard) : navigator.clearAppBadge()).catch(() => {}); }
  } catch { /* offline: keep what is on screen */ }
}

function refreshFilters() {
  for (const b of document.querySelectorAll('#statusChips .chip')) b.setAttribute('aria-pressed', String(b.dataset.status === S.filters.status));
  for (const b of document.querySelectorAll('#agentChips .chip')) b.setAttribute('aria-pressed', String(b.dataset.agent === S.filters.agent));
  S.notes = [];
  loadList();
}

/* ------------------------------------------------------------------ detail */
async function openDetail(id) {
  S.detailId = id;
  document.body.classList.add('route-note');
  for (const c of document.querySelectorAll('.card')) c.classList.toggle('active', c.dataset.id === id);
  const box = $('#detail');
  let note = S.byId.get(id);
  if (!note || note.spoken === undefined) {
    if (!note) box.innerHTML = '<div class="empty">Loading…</div>';
    try { note = await api('/api/notes/' + id); S.byId.set(id, note); }
    catch { box.innerHTML = '<div class="empty"><b>Note not found</b>It may have been archived.</div>'; return; }
  }
  if (S.detailId !== id) return;
  const switched = box.dataset.id !== id;
  box.dataset.id = id;
  renderDetail(note);
  if (switched) box.scrollTop = 0;
  if (window.matchMedia('(max-width: 959px)').matches) window.scrollTo(0, 0);
  // Deep link from a chat: get it ready so one tap plays it.
  if (!S.current) loadNote(note, { autoplay: false });
}

function closeDetail() {
  S.detailId = null;
  document.body.classList.remove('route-note');
  $('#detail').replaceChildren();
  delete $('#detail').dataset.id;
  for (const c of document.querySelectorAll('.card.active')) c.classList.remove('active');
}

function renderDetail(n) {
  const a = agentOf(n);
  const d = new Date(n.created_at);
  const isCur = S.current && S.current.id === n.id;
  const ch = n.channels || {};
  const chatSpace = ch.chat && ch.chat.space ? ch.chat.space.replace('spaces/', '') : '';
  const links = (S.cfg && S.cfg.ticket_links) || {};
  const ticketHTML = (n.tickets || []).map(t => {
    const base = links[t.split('-')[0]];
    return base ? `<a class="ticket" href="${esc(base + t)}" target="_blank" rel="noopener">${esc(t)}</a>`
      : `<button class="ticket" type="button" data-copy="${esc(t)}" title="Copy">${esc(t)}</button>`;
  }).join('');
  const segs = n.segments || [];
  let lastP = -1, tr = '';
  segs.forEach((s, i) => {
    if (s.p !== lastP) { tr += (lastP >= 0 ? '</p>' : '') + '<p>'; lastP = s.p; }
    tr += `<span data-i="${i}" data-t="${s.t}">${esc(s.text)}</span> `;
  });
  if (tr) tr += '</p>';
  const textDiffers = n.text && n.text.trim() && n.text.trim() !== (n.spoken || '').trim();
  const box = $('#detail');
  box.innerHTML = `
    <button class="btn back" type="button" data-back>← Notes</button>
    <div class="d-head">${avatar(n)}<h1>${esc(n.title || n.summary || 'Voice note')}</h1></div>
    <div class="d-sub">${esc(a.name)}${n.tag ? ' · ' + esc(n.tag) : ''}${n.source ? ' · ' + esc(n.source) : ''} · ${esc(fullFmt.format(d))}</div>
    ${forYouHTML(n)}
    ${n.summary && n.title ? `<div class="d-summary">${esc(n.summary)}</div>` : ''}
    <div class="d-player">
      <div class="d-wave">${waveHTML(n.peaks)}</div>
      <div class="d-times"><span id="dCur">${fmtTime(isCur ? audio.currentTime : (n.position || 0))}</span><span id="dLeft">${fmtTime(n.duration)}</span></div>
      <div class="d-controls">
        <button class="icon" type="button" data-act="back" aria-label="Back 10 seconds"><svg viewBox="0 0 24 24"><path d="M12 5V2L7 6l5 4V7a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8Z"/><text x="12" y="16.3" text-anchor="middle" font-size="6.5" font-weight="700">10</text></svg></button>
        <button class="icon big" type="button" data-act="play" aria-label="Play or pause"><svg viewBox="0 0 24 24" class="i-play"><path d="M8 5v14l11-7z"/></svg><svg viewBox="0 0 24 24" class="i-pause"><path d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg></button>
        <button class="icon" type="button" data-act="fwd" aria-label="Forward 30 seconds"><svg viewBox="0 0 24 24"><path d="M12 5V2l5 4-5 4V7a6 6 0 1 0 6 6h2a8 8 0 1 1-8-8Z"/><text x="12" y="16.3" text-anchor="middle" font-size="6.5" font-weight="700">30</text></svg></button>
      </div>
      <div class="speeds" role="radiogroup" aria-label="Speed">${SPEEDS.map(x => {
        const below = x < (n.speech_rate || 1) - 0.01;
        return `<button type="button" data-speed="${x}" aria-pressed="${x === S.speed}"${below ? ` class="below" title="Recorded at ${fmtSpeed(n.speech_rate)}: slower would sound metallic. Use Re-record at natural speed."` : ''}>${fmtSpeed(x)}</button>`;
      }).join('')}</div>
      ${n.speech_rate > 1.01 ? `<div class="rate-note">Recorded at ${fmtSpeed(n.speech_rate)}: it plays from that speed up${n.can_resynth ? '. Re-record it to hear it cleanly at 1×.' : '.'}</div>` : ''}
    </div>
    <div class="actions">
      <button class="btn" type="button" data-act="star" aria-pressed="${!!n.starred}">${n.starred ? '🌟 Starred' : '⭐ Star'}</button>
      <button class="btn" type="button" data-act="heard">${n.heard_at ? '🔁 Mark as unheard' : '✅ Mark as heard'}</button>
      <button class="btn" type="button" data-act="share">🔗 Copy link</button>
      <a class="btn" href="${esc(n.audio_url)}" download="${esc((n.title || n.id).replace(/[^\w\- ]+/g, '').trim() || n.id)}.mp3">⬇️ Download</a>
      ${chatSpace ? `<a class="btn" href="https://chat.google.com/room/${esc(chatSpace)}" target="_blank" rel="noopener">💬 Open in Google Chat</a>` : ''}
      ${n.can_resynth ? `<button class="btn" type="button" data-act="resynth" title="Synthesise the text again at the natural rate (costs about ${Math.round((n.spoken || n.text || '').length / 100) / 10} thousand TTS characters)">🎙️ Re-record at natural speed</button>` : ''}
      <button class="btn" type="button" data-act="archive">${n.archived ? '♻️ Restore' : '🗄️ Archive'}</button>
    </div>
    ${tr ? `<div class="section"><h2>Transcript <small>approximate timing · tap a sentence to jump</small></h2><div class="transcript">${tr}</div></div>` : ''}
    ${textDiffers ? `<div class="section"><h2>Text the agent wrote</h2><div class="md">${md(n.text)}</div></div>` : ''}
    ${ticketHTML ? `<div class="section"><h2>Tickets</h2><div class="tickets">${ticketHTML}</div></div>` : ''}
    ${(n.links || []).length ? `<div class="section links"><h2>Links</h2>${n.links.map(u => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>`).join('')}</div>` : ''}
    <div class="section"><h2>Details</h2><dl class="facts">
      <dt>Agent</dt><dd>${esc(a.name)}</dd>
      ${n.speaker ? `<dt>Introduces itself as</dt><dd>${esc(n.speaker)}</dd>` : ''}
      ${n.repo ? `<dt>Repository</dt><dd>${esc(n.repo)}${n.branch && n.branch !== 'HEAD' ? ' · <code>' + esc(n.branch) + '</code>' : ''}</dd>` : ''}
      ${n.cwd ? `<dt>Folder</dt><dd><code>${esc(n.cwd)}</code></dd>` : ''}
      ${n.session_id ? `<dt>Session</dt><dd><button class="ticket" type="button" data-copy="${esc(n.session_id)}" title="Copy">${esc(n.session_id)}</button></dd>` : ''}
      <dt>Duration</dt><dd>${fmtTime(n.duration)} recorded at ${fmtSpeed(n.speech_rate)}</dd>
      ${n.voice ? `<dt>Voice</dt><dd>${esc(n.voice)}</dd>` : ''}
      <dt>Delivery</dt><dd>${Object.keys(ch).length ? Object.entries(ch).map(([k, v]) => esc(k) + ': ' + esc(typeof v === 'object' ? (v.status || 'ok') : v)).join(' · ') : 'hub only'}</dd>
      <dt>Origin</dt><dd>${n.origin === 'live' ? 'live' : 'imported (' + esc(n.origin) + ')'}</dd>
      <dt>Id</dt><dd><code>${esc(n.id)}</code></dd>
    </dl></div>`;
  wireDetail(box, n);
  syncPlayingUI();
}

// What the agent left for him to act on: the command it sent and the short written
// explanation. First thing in the note, each command with its own copy button.
function forYouHTML(n) {
  const cmds = (n.commands || []).filter(c => c.code || c.explanation);
  if (!n.brief && !cmds.length) return '';
  return `<div class="foryou"><h2>📌 For you</h2>
    ${n.brief ? `<div class="md brief">${md(n.brief)}</div>` : ''}
    ${cmds.map(c => `<div class="cmd">
      ${c.label || c.explanation ? `<div class="cmd-label">${c.label ? `<b>${esc(c.label)}</b>` : ''}${c.label && c.explanation ? ' · ' : ''}${c.explanation ? esc(c.explanation) : ''}</div>` : ''}
      ${c.code ? `<div class="cmd-code"><pre><code>${esc(c.code)}</code></pre>
        <button class="btn copy" type="button" data-copy="${esc(c.code)}" data-copy-msg="Command copied ✅">📋 Copy</button></div>` : ''}
    </div>`).join('')}
  </div>`;
}

function wireDetail(box, n) {
  box.querySelector('[data-back]').onclick = () => nav('/');
  const wave = box.querySelector('.d-wave');
  const range = el('<input type="range" min="0" max="1000" value="0" aria-label="Position">');
  wave.querySelector('.wave').appendChild(range);
  range.addEventListener('input', () => {
    const frac = range.value / 1000;
    if (S.current && S.current.id === n.id && isFinite(audio.duration)) { audio.currentTime = frac * audio.duration; }
    else { loadNote(n, { autoplay: true, at: frac * n.duration }); }
  });
  if (!(S.current && S.current.id === n.id) && n.position && n.duration) setWave(wave, n.position / n.duration);
  // onclick, not addEventListener: #detail survives re-renders, and stacked listeners
  // with stale notes made "mark as heard" toggle twice and undo itself.
  box.onclick = async e => {
    const b = e.target.closest('button, [data-copy]');
    if (!b) return;
    if (b.dataset.copy) { copy(b.dataset.copy, b.dataset.copyMsg || 'Copied'); return; }
    if (b.dataset.speed) { setSpeed(+b.dataset.speed); return; }
    const act = b.dataset.act;
    if (act === 'play') togglePlay(n);
    else if (act === 'back') { ensureLoaded(n); audio.currentTime = Math.max(0, audio.currentTime - 10); }
    else if (act === 'fwd') { ensureLoaded(n); audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 30); }
    else if (act === 'star') { await update(n.id, { starred: !n.starred }); }
    else if (act === 'heard') { await update(n.id, { heard: !n.heard_at }); }
    else if (act === 'archive') { await update(n.id, { archived: !n.archived }); toast(n.archived ? 'Restored' : 'Archived'); }
    else if (act === 'share') {
      const url = (n.urls && (n.urls.public || n.urls.local)) || location.href;
      copy(url, 'Link copied');
    }
    else if (act === 'resynth') { resynthNote(n, b); }
  };
  box.querySelector('.transcript')?.addEventListener('click', e => {
    const s = e.target.closest('span[data-t]');
    if (!s) return;
    const t = +s.dataset.t;
    if (S.current && S.current.id === n.id) { audio.currentTime = t; if (audio.paused) audio.play().catch(() => {}); }
    else loadNote(n, { autoplay: true, at: t });
  });
}

async function update(id, body) {
  if (body.heard === false) S.heardSent.delete(id);
  try {
    const note = await patch(id, body);
    S.byId.set(id, Object.assign(S.byId.get(id) || {}, note));
    const i = S.notes.findIndex(x => x.id === id);
    if (i >= 0) S.notes[i] = Object.assign(S.notes[i], note);
    if (S.current && S.current.id === id) Object.assign(S.current, note);
    renderList();
    if (S.detailId === id) renderDetail(S.byId.get(id));
    loadFacets();
  } catch { toast('Could not save: the hub is offline'); }
}

function copy(text, msg = 'Copied') {
  (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
    .then(() => toast(msg), () => toast(text));
}

async function resynthNote(n, button) {
  button.disabled = true;
  button.textContent = '🎙️ Re-recording…';
  try {
    const note = await api('/api/notes/' + n.id + '/resynth', { method: 'POST', body: {} });
    S.byId.set(n.id, note);
    const i = S.notes.findIndex(x => x.id === n.id);
    if (i >= 0) S.notes[i] = Object.assign(S.notes[i], note);
    if (S.current && S.current.id === n.id) {
      const wasPlaying = !audio.paused;
      loadNote(note, { autoplay: wasPlaying, at: 0 });
    }
    renderList();
    if (S.detailId === n.id) renderDetail(note);
    toast('Re-recorded at natural speed ✨');
  } catch {
    button.disabled = false;
    button.textContent = '🎙️ Re-record at natural speed';
    toast('Could not re-record (TTS credentials?)');
  }
}

/* ------------------------------------------------------------------- theme */
const TAP_TO_CHANGE = ' · tap to change it';
const THEMES = [['auto', '🌓', 'Theme: automatic, follows the system'], ['light', '☀️', 'Theme: light'], ['dark', '🌙', 'Theme: dark']];
function applyTheme(t) {
  const root = document.documentElement;
  if (t === 'light' || t === 'dark') root.dataset.theme = t; else delete root.dataset.theme;
  const [, icon, label] = THEMES.find(x => x[0] === t) || THEMES[0];
  const b = $('#themeBtn');
  if (b) { b.textContent = icon; b.title = label + TAP_TO_CHANGE; b.setAttribute('aria-label', label); }
  const dark = t === 'dark' || (t !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
  for (const m of document.querySelectorAll('meta[name="theme-color"]')) m.content = dark ? '#121316' : '#f6f5f2';
}
function cycleTheme() {
  const cur = store.get('theme', 'auto');
  const next = THEMES[(THEMES.findIndex(x => x[0] === cur) + 1) % THEMES.length][0];
  store.set('theme', next);
  applyTheme(next);
  toast(THEMES.find(x => x[0] === next)[2]);
}

/* ---------------------------------------------------------------- tooltips */
/* What each control does, shown when the pointer rests on it or it gets keyboard focus.
 * Keyed by selector so the templates stay readable; a function gets the element and
 * answers for its current state, since the title is set at hover time. */
const noteInDetail = () => S.byId.get(S.detailId) || {};
const TIPS = [
  ['#topBack, [data-back]', 'Back to the list of notes (Esc)'],
  ['#q', 'Search titles, text, tickets and projects (shortcut: /)'],
  ['#statusChips [data-status=""]', 'Show every note'],
  ['#statusChips [data-status="unheard"]', 'Show only the notes you have not heard yet'],
  ['#statusChips [data-status="starred"]', 'Show only starred notes'],
  ['#agentChips .chip', b => b.getAttribute('aria-pressed') === 'true' ? 'Clear the agent filter'
    : 'Show only notes from ' + b.textContent.replace(/\s*\d+\s*$/, '').trim()],
  ['#markAllBtn', b => b.dataset.armed ? 'Tap again to confirm'
    : 'Mark every unheard note as heard (asks for a second tap to confirm)'],
  ['#tagSel', 'Filter by project'],
  ['.card .play-mini', b => b.closest('.card').classList.contains('is-playing') ? 'Pause' : 'Play without opening the note'],
  ['.card .heard-mini', b => b.getAttribute('aria-pressed') === 'true'
    ? 'Heard. Tap to mark it as unheard again' : 'Unheard. Tap to mark it as heard without opening it'],
  ['.card.current .card-wave', 'Tap to jump to that point of the audio'],
  ['[data-act="back"], #pBack', 'Back 10 seconds (← or J)'],
  ['[data-act="play"], #pPlay', 'Play or pause (space or K)'],
  ['[data-act="fwd"], #pFwd', 'Forward 30 seconds (→ or L)'],
  ['.speeds button:not(.below)', b => 'Listen at ' + b.textContent + ' (shortcuts: < and >)'],
  ['#pSpeed', 'Change the speed, one step per tap (shortcuts: < and >)'],
  ['#pNext', 'Skip to the next unheard note (N)'],
  ['#playerMeta', 'Open the note that is playing'],
  ['.wave input[type=range]', 'Tap or drag to jump to another point'],
  ['[data-act="star"]', () => noteInDetail().starred ? 'Remove from starred' : 'Star it: you will find it under the Starred filter'],
  ['[data-act="heard"]', () => noteInDetail().heard_at ? 'Mark it as unheard again' : 'Mark it as heard'],
  ['[data-act="share"]', 'Copy the link to this note, to open it on another device or share it in a chat'],
  ['.actions a[download]', 'Download the audio as MP3'],
  ['.actions a[href^="https://chat.google.com/"]', 'Open the original message in Google Chat'],
  ['[data-act="archive"]', () => noteInDetail().archived ? 'Put it back in the list' : 'Archive: it leaves the list but is not deleted'],
  ['.transcript span', 'Tap to jump to this sentence'],
  ['a.ticket', a => 'Open ' + a.textContent + ' in a new tab'],
  ['button.ticket, .cmd .copy', 'Copy to the clipboard'],
];
function tipFor(node) {
  for (const [sel, tip] of TIPS) if (node.matches(sel)) return typeof tip === 'function' ? tip(node) : tip;
  return null;
}
// Walk up from what is under the pointer to the first control with something to say;
// a control with no entry and no title falls back to its aria-label.
function showTip(e) {
  for (let node = e.target; node instanceof Element; node = node.parentElement) {
    const tip = tipFor(node) || (!node.title && node.matches('button, a, input, select') ? node.getAttribute('aria-label') : null);
    if (tip) { node.title = tip; return; }
    if (node.title) return;
  }
}

/* -------------------------------------------------------- play from a link */
/* A link ending in ?play=1 (the one agents put in their replies and the Chat card
 * opens) starts the note. If a Voice Hub tab is already open and has been used, that
 * tab plays it, because browsers let a tab that was clicked before make sound; the new
 * tab then says so and closes itself where the browser allows. Otherwise the new tab
 * plays it, and if the browser blocks sound without a click, one tap does it. */
function claimPlayerRole() {
  if (!navigator.locks) { S.playerTab = true; return; }
  navigator.locks.request('avh-player', () => {
    S.playerTab = true;
    // Tell the server this tab can take links: reopen the event stream flagged as player.
    if (es && !es.player) { disconnectEvents(); connectEvents(); }
    return new Promise(() => {});
  }).catch(() => {});
}

async function onRemotePlay(d, ack) {
  if (d.from === TAB || !S.playerTab || (d.host && d.host !== location.host.toLowerCase())) return;
  let note = S.byId.get(d.id);
  try { if (!note || note.spoken === undefined) { note = await api('/api/notes/' + d.id); S.byId.set(d.id, note); } }
  catch { return; }
  const prev = S.current;
  loadNote(note, { autoplay: false, at: 0 });
  // Answer on the `play` event, not when play() resolves: in a background tab the promise
  // waits for the audio to buffer, and the link must not wait for that. play() rejects
  // at once (without `play`) when the tab may not make sound.
  const playing = audio.play();
  const ok = await Promise.race([
    new Promise(resolve => audio.addEventListener('play', () => resolve(true), { once: true })),
    playing.then(() => true, () => false),
  ]);
  playing.catch(() => {});
  if (!ok) {
    if (prev && prev.id !== note.id) loadNote(prev, { autoplay: false });
    return;                                  // no permission to make sound: let the new tab try
  }
  S.remoteReq = d.req;
  if (ack) ack();
  else fetch('/api/play-ack', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-AVH': '1' },
    body: JSON.stringify({ req: d.req, tab: TAB }) }).catch(() => {});
  if (S.detailId !== note.id) nav('/n/' + note.id);
  toast('🔊 Playing: ' + (note.title || note.summary || 'voice note'));
}

function onRemoteAck(d) {
  S.acks.set(d.req, d.tab);
  // Two browsers both had a player tab: the first to answer keeps playing.
  if (S.remoteReq === d.req && d.tab !== TAB && !audio.paused) audio.pause();
}

function waitFor(cond, ms) {
  return new Promise(resolve => {
    const t0 = Date.now();
    (function tick() { if (cond()) resolve(true); else if (Date.now() - t0 > ms) resolve(false); else setTimeout(tick, 50); })();
  });
}

async function playFromLink(id, { serverTried = false } = {}) {
  // Same browser first: straight to the player tab, no network, works in the background.
  const localReq = 'l' + TAB + Date.now();
  tabs.post({ type: 'play-req', id, req: localReq });
  if (await waitFor(() => S.acks.has(localReq), 1200)) {
    showOverlay('🔊', 'Playing in your Voice Hub tab', 'You can close this one. It can also pause it.', null);
    setTimeout(() => { try { window.close(); } catch { /* not closable */ } }, 1200);
    return;
  }
  // Another browser (say the hub is open in Chrome and the link opened in Cursor). The
  // server already asks open hub tabs before serving a ?play=1 link (`tried=1`), so this
  // only runs for links that skipped it.
  if (!serverTried) await waitFor(() => S.sseReady, 2500);
  let req = 0;
  if (S.sseReady && !serverTried) {
    try {
      req = (await api('/api/play', { method: 'POST', body: { id, from: TAB } })).req;
    } catch { req = 0; }
  }
  if (req && await waitFor(() => S.acks.has(req) && S.acks.get(req) !== TAB, 1500)) {
    showOverlay('🔊', 'Playing in your Voice Hub tab', 'You can close this one. It can also pause it.', null);
    setTimeout(() => { try { window.close(); } catch { /* not closable */ } }, 1200);
    return;
  }
  let note = S.byId.get(id);
  try { if (!note || note.spoken === undefined) { note = await api('/api/notes/' + id); S.byId.set(id, note); } }
  catch { return; }
  loadNote(note, { autoplay: false, at: 0 });
  audio.play().catch(() => {
    showOverlay('▶', note.title || note.summary || 'Voice note', 'Tap to listen', () => audio.play().catch(() => {}));
  });
}

function showOverlay(icon, title, sub, onTap) {
  const o = el(`<div class="overlay" role="dialog" aria-label="${esc(title)}"><button type="button" class="overlay-btn">
    <span class="overlay-icon">${esc(icon)}</span><b>${esc(title)}</b><small>${esc(sub)}</small></button></div>`);
  o.onclick = () => { o.remove(); if (onTap) onTap(); };
  document.body.appendChild(o);
}

/* ------------------------------------------------------------------ player */
function loadNote(note, { autoplay = true, at = null } = {}) {
  S.current = note;
  audio.src = note.audio_url;
  const resumeAt = at !== null ? at
    : (!note.heard_at && note.position > 5 && note.position < (note.duration || 0) - 10 ? note.position - 2 : 0);
  audio.addEventListener('loadedmetadata', () => {
    applySpeed();
    if (resumeAt) audio.currentTime = resumeAt;
  }, { once: true });
  applySpeed();
  $('#player').hidden = false;
  const a = agentOf(note);
  $('#playerAvatar').outerHTML = `<span class="avatar" id="playerAvatar" style="background:${esc(a.color)}">${esc(a.badge)}</span>`;
  $('#playerTitle').textContent = note.title || note.summary || 'Voice note';
  $('#playerWave').innerHTML = waveHTML(note.peaks);
  const pr = el('<input type="range" min="0" max="1000" value="0" aria-label="Position in the current note">');
  $('#playerWave .wave').appendChild(pr);
  pr.addEventListener('input', () => { if (isFinite(audio.duration)) audio.currentTime = pr.value / 1000 * audio.duration; });
  updateSub();
  setMediaSession(note);
  if (autoplay) audio.play().catch(() => toast('Tap ▶ to start'));
  syncPlayingUI();
}

function ensureLoaded(note) { if (!S.current || S.current.id !== note.id) loadNote(note, { autoplay: false }); }

function togglePlay(note) {
  // The note is playing in another hub tab (a link was opened and that tab took it):
  // this button is a remote control for it, never a second copy of the audio.
  if (audio.paused && S.remote && S.remote.id === note.id) {
    tabs.post({ type: 'cmd', to: S.remote.tab, action: 'pause' });
    S.remote = null;
    syncPlayingUI();
    return;
  }
  if (!S.current || S.current.id !== note.id) { loadNote(note, { autoplay: true }); return; }
  if (audio.paused) audio.play().catch(() => {}); else audio.pause();
}

/* One player per browser. Every hub tab announces when it starts or stops playing; the
 * others pause their own audio and show the remote one as playing, so pause in any tab
 * pauses the note that is actually sounding. */
const tabs = (() => {
  let ch = null;
  try { ch = new BroadcastChannel('avh-player'); } catch { /* old browser */ }
  return {
    post(msg) { if (ch) try { ch.postMessage(Object.assign({ tab: TAB }, msg)); } catch { /* closed */ } },
    on(fn) { if (ch) ch.onmessage = e => fn(e.data || {}); },
  };
})();

function announce(playing) {
  if (S.current) tabs.post({ type: 'state', id: S.current.id, playing });
}

tabs.on(msg => {
  if (msg.tab === TAB) return;
  if (msg.type === 'state') {
    if (msg.playing) {
      if (!audio.paused) audio.pause();                  // only one tab sounds at a time
      S.remote = { tab: msg.tab, id: msg.id };
    } else if (S.remote && S.remote.tab === msg.tab) {
      S.remote = null;
    }
    syncPlayingUI();
  } else if (msg.type === 'play-req') {
    onRemotePlay({ id: msg.id, req: msg.req, from: msg.tab },
      () => tabs.post({ type: 'play-ack', req: msg.req }));
  } else if (msg.type === 'play-ack') {
    onRemoteAck({ req: msg.req, tab: msg.tab });
  } else if (msg.type === 'hello') {
    if (!audio.paused) announce(true);                 // tell a new tab who is sounding
  } else if (msg.type === 'cmd' && msg.to === TAB) {
    if (msg.action === 'pause') audio.pause();
    else if (msg.action === 'play') audio.play().catch(() => {});
  }
});

function applySpeed() {
  if (!S.current) return;
  const r = rateFor(S.current, S.speed);
  audio.defaultPlaybackRate = r;
  audio.playbackRate = r;
  audio.preservesPitch = true;
}

function setSpeed(eff) {
  S.speed = eff;
  store.set('speed', eff);
  applySpeed();
  $('#pSpeed').textContent = fmtSpeed(eff);
  for (const b of document.querySelectorAll('.speeds button')) b.setAttribute('aria-pressed', String(+b.dataset.speed === eff));
  updateSub();
}

function updateSub() {
  if (!S.current) return;
  const dur = audio.duration && isFinite(audio.duration) ? audio.duration : S.current.duration;
  const left = Math.max(0, dur - audio.currentTime) / rateFor(S.current, S.speed);
  $('#playerSub').textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(dur)} · ${fmtTime(left)} left at ${fmtSpeed(effFor(S.current, S.speed))}`;
}

function syncPlayingUI() {
  const playing = !audio.paused && S.current;
  const remoteId = audio.paused && S.remote ? S.remote.id : null;
  document.body.classList.toggle('has-player', !!S.current);
  $('#player').classList.toggle('is-playing', !!playing);
  for (const c of document.querySelectorAll('.card')) {
    const mine = S.current && c.dataset.id === S.current.id;
    c.classList.toggle('current', !!mine);
    c.classList.toggle('playing', !!(mine && playing));
    c.classList.toggle('is-playing', !!(mine && playing));
  }
  const d = $('#detail');
  const mineDetail = S.current && S.detailId === S.current.id;
  d.querySelector('.d-controls')?.classList.toggle('is-playing',
    !!(mineDetail && playing) || (!!remoteId && S.detailId === remoteId));
  for (const c of document.querySelectorAll('.card')) {
    if (remoteId && c.dataset.id === remoteId) c.classList.add('playing', 'is-playing');
  }
}

let lastSeg = -1;
function onTime() {
  if (!S.current) return;
  const dur = audio.duration && isFinite(audio.duration) ? audio.duration : S.current.duration;
  const frac = dur ? audio.currentTime / dur : 0;
  setWave($('#playerWave'), frac);
  const range = $('#playerWave input'); if (range) range.value = Math.round(frac * 1000);
  const card = document.querySelector(`.card[data-id="${CSS.escape(S.current.id)}"] .card-wave`);
  setWave(card, frac);
  if (S.detailId === S.current.id) {
    const box = $('#detail');
    setWave(box.querySelector('.d-wave'), frac);
    const r = box.querySelector('.d-wave input'); if (r) r.value = Math.round(frac * 1000);
    const cur = $('#dCur'); if (cur) cur.textContent = fmtTime(audio.currentTime);
    const left = $('#dLeft'); if (left) left.textContent = '-' + fmtTime((dur - audio.currentTime) / rateFor(S.current, S.speed));
    const segs = S.current.segments || (S.byId.get(S.current.id) || {}).segments || [];
    let idx = -1;
    for (let i = 0; i < segs.length; i++) { if (segs[i].t <= audio.currentTime + 0.15) idx = i; else break; }
    if (idx !== lastSeg) {
      box.querySelector('.transcript .now')?.classList.remove('now');
      const sp = box.querySelector(`.transcript span[data-i="${idx}"]`);
      if (sp) { sp.classList.add('now'); if (!audio.paused && isOutOfView(sp)) sp.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
      lastSeg = idx;
    }
  }
  updateSub();
  if (dur && frac >= 0.95) markHeard(S.current);
  const now = Date.now();
  if (now - S.lastSaved > 10000 && !audio.paused) { S.lastSaved = now; savePosition(); }
}

function isOutOfView(node) {
  const r = node.getBoundingClientRect();
  const bottom = window.innerHeight - $('#player').offsetHeight;
  return r.top < 80 || r.bottom > bottom;
}

function savePosition() {
  if (!S.current || !isFinite(audio.currentTime)) return;
  const pos = Math.round(audio.currentTime * 10) / 10;
  S.current.position = pos;
  patch(S.current.id, { position: pos }).catch(() => {});
}

function markHeard(note) {
  if (note.heard_at || S.heardSent.has(note.id)) return;
  S.heardSent.add(note.id);
  note.heard_at = new Date().toISOString();
  patch(note.id, { heard: true }).then(n => {
    S.byId.set(n.id, Object.assign(S.byId.get(n.id) || {}, n));
    document.querySelector(`.card[data-id="${CSS.escape(n.id)}"]`)?.classList.remove('unheard');
    loadFacets();
  }).catch(() => S.heardSent.delete(note.id));
}

/* Two taps, no dialog: the first arms the button for a few seconds, the second marks. */
async function markAllHeard() {
  const b = $('#markAllBtn');
  if (!b.dataset.armed) {
    b.dataset.armed = '1';
    b.textContent = `Mark ${S.unheard || 'all'} as heard? Tap again`;
    clearTimeout(markAllHeard._t);
    markAllHeard._t = setTimeout(resetMarkAll, 4000);
    return;
  }
  resetMarkAll();
  b.disabled = true;
  try {
    const { marked } = await api('/api/notes/mark-all-heard', { method: 'POST', body: {} });
    const now = new Date().toISOString();
    for (const n of [...S.notes, ...S.byId.values()]) if (!n.heard_at && !n.archived) n.heard_at = now;
    if (S.current && !S.current.heard_at) S.current.heard_at = now;
    if (S.filters.status === 'unheard') refreshFilters(); else renderList();
    if (S.detailId && S.byId.get(S.detailId)) renderDetail(S.byId.get(S.detailId));
    loadFacets();
    toast(marked ? `✅ ${marked} ${marked === 1 ? 'note' : 'notes'} marked as heard` : 'Nothing was left unheard');
  } catch { toast('Could not save: the hub is offline'); }
  finally { b.disabled = false; }
}
function resetMarkAll() {
  const b = $('#markAllBtn');
  clearTimeout(markAllHeard._t);
  delete b.dataset.armed;
  b.textContent = '✓ Mark all as heard';
}

async function nextUnheard(afterId) {
  try {
    const data = await api('/api/notes?status=unheard&limit=200');
    const pending = data.notes.filter(n => n.id !== afterId).reverse();   // oldest first
    return pending[0] || null;
  } catch { return null; }
}

async function playQueue() {
  S.queue = true;
  const n = await nextUnheard(null);
  if (!n) { toast('Nothing unheard 🎉'); S.queue = false; return; }
  loadNote(n, { autoplay: true });
  toast('Playing everything unheard, oldest first');
}

async function playNext() {
  const n = await nextUnheard(S.current && S.current.id);
  if (n) loadNote(n, { autoplay: true });
  else { S.queue = false; toast('Nothing unheard left'); }
}

/* ----------------------------------------------------------- media session */
function setMediaSession(note) {
  const ms = navigator.mediaSession;
  if (!ms) return;
  const a = agentOf(note);
  try {
    ms.metadata = new MediaMetadata({
      title: note.title || note.summary || 'Voice note',
      artist: a.name,
      album: note.tag ? 'Voice Hub · ' + note.tag : 'Voice Hub',
      artwork: [{ src: '/static/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
                { src: '/static/icons/icon-512.png', sizes: '512x512', type: 'image/png' }],
    });
  } catch { /* old browser */ }
  const H = {
    play: () => audio.play(),
    pause: () => audio.pause(),
    seekbackward: d => { audio.currentTime = Math.max(0, audio.currentTime - (d.seekOffset || 10)); },
    seekforward: d => { audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + (d.seekOffset || 30)); },
    seekto: d => { audio.currentTime = d.seekTime; },
    nexttrack: () => playNext(),
  };
  for (const [k, h] of Object.entries(H)) { try { ms.setActionHandler(k, h); } catch { /* unsupported */ } }
}
function syncPosition() {
  const ms = navigator.mediaSession, d = audio.duration;
  if (!ms || !ms.setPositionState || !isFinite(d) || d <= 0 || !(audio.playbackRate > 0)) return;
  try { ms.setPositionState({ duration: d, playbackRate: audio.playbackRate, position: Math.min(audio.currentTime, d) }); } catch { /* ignore */ }
}

/* ------------------------------------------------------------- live events */
let es = null;
function connectEvents() {
  if (es || (document.hidden && matchMedia('(pointer: coarse)').matches)) return;
  es = new EventSource('/api/events' + (S.playerTab ? '?player=1' : ''));
  es.player = S.playerTab;
  es.addEventListener('hello', () => { S.sseReady = true; });
  es.addEventListener('notes', onRemoteChange);
  es.addEventListener('play', e => { try { onRemotePlay(JSON.parse(e.data)); } catch { /* bad event */ } });
  es.addEventListener('play-ack', e => { try { onRemoteAck(JSON.parse(e.data)); } catch { /* bad event */ } });
  es.onerror = () => { /* EventSource retries by itself */ };
}
function disconnectEvents() { if (es) { es.close(); es = null; S.sseReady = false; } }
let changeTimer = null;
function onRemoteChange() {
  clearTimeout(changeTimer);
  changeTimer = setTimeout(async () => {
    const before = new Set(S.knownIds);
    await Promise.all([loadList(), loadFacets()]);
    const fresh = S.notes.filter(n => !before.has(n.id));
    if (fresh.length && before.size) {
      const n = fresh[0];
      toast(`🎧 New note from ${agentOf(n).name}: ${n.title || n.summary}`, () => nav('/n/' + n.id));
    }
  }, 250);
}

/* ------------------------------------------------------------ offline cache */
function prefetchAudio() {
  if (!navigator.serviceWorker || !navigator.serviceWorker.controller) return;
  const urls = S.notes.filter(n => !n.heard_at).slice(0, 15).map(n => n.audio_url);
  if (S.current) urls.unshift(S.current.audio_url);
  navigator.serviceWorker.controller.postMessage({ type: 'prefetch', urls });
}

/* ------------------------------------------------------------------ router */
function nav(path) {
  if (location.pathname + location.search !== path) history.pushState({}, '', path);
  route();
}
function route() {
  const m = location.pathname.match(/^\/n\/([A-Za-z0-9]+)/);
  if (m) openDetail(m[1]); else closeDetail();
}

/* --------------------------------------------------------------- keyboard */
function onKey(e) {
  if (e.target.matches('input, select, textarea') || e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (k === ' ' || k === 'k') { if (S.current) { e.preventDefault(); audio.paused ? audio.play() : audio.pause(); } }
  else if (k === 'ArrowLeft' || k === 'j') { audio.currentTime = Math.max(0, audio.currentTime - 10); }
  else if (k === 'ArrowRight' || k === 'l') { audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 30); }
  else if (k === '>' || k === ']') { const i = SPEEDS.indexOf(S.speed); setSpeed(SPEEDS[Math.min(SPEEDS.length - 1, i + 1)]); }
  else if (k === '<' || k === '[') { const i = SPEEDS.indexOf(S.speed); setSpeed(SPEEDS[Math.max(0, i - 1)]); }
  else if (k === 'n') playNext();
  else if (k === '/') { e.preventDefault(); $('#q').focus(); }
  else if (k === 'Escape' && S.detailId) nav('/');
}

/* --------------------------------------------------------------------- boot */
async function boot() {
  applyTheme(store.get('theme', 'auto'));
  claimPlayerRole();
  tabs.post({ type: 'hello' });
  const params = new URLSearchParams(location.search);
  const urlSpeed = parseFloat(params.get('speed'));
  const playId = params.get('play') === '1' ? (location.pathname.match(/^\/n\/([A-Za-z0-9]+)/) || [])[1] : null;
  const serverTried = params.get('tried') === '1';
  if (playId) history.replaceState({}, '', location.pathname);   // a reload must not replay it
  if (['unheard', 'starred'].includes(params.get('status'))) {
    S.filters.status = params.get('status');
    for (const b of document.querySelectorAll('#statusChips .chip')) b.setAttribute('aria-pressed', String(b.dataset.status === S.filters.status));
  }
  S.speed = SPEEDS.includes(urlSpeed) ? urlSpeed : store.get('speed', null);
  try { S.cfg = await api('/api/config'); }
  catch { S.cfg = { agents: { unknown: { name: 'Agent', badge: 'AI', color: '#8a8f98' } }, ticket_links: {}, default_speech_rate: 1 }; }
  if (!SPEEDS.includes(S.speed)) S.speed = 1;
  $('#pSpeed').textContent = fmtSpeed(S.speed);

  audio.addEventListener('timeupdate', onTime);
  audio.addEventListener('play', () => { S.remote = null; announce(true); syncPlayingUI(); syncPosition(); });
  audio.addEventListener('pause', () => { announce(false); syncPlayingUI(); syncPosition(); savePosition(); });
  window.addEventListener('pagehide', () => announce(false));
  audio.addEventListener('ratechange', syncPosition);
  audio.addEventListener('seeked', () => { syncPosition(); onTime(); });
  audio.addEventListener('loadedmetadata', syncPosition);
  audio.addEventListener('ended', () => {
    if (S.current) { markHeard(S.current); S.current.position = 0; patch(S.current.id, { position: 0 }).catch(() => {}); }
    syncPlayingUI();
    if (S.queue) setTimeout(playNext, 700);
  });
  audio.addEventListener('error', () => { if (S.current) toast('Could not load the audio. Is the hub running?'); });

  $('#pPlay').onclick = () => { if (S.current) togglePlay(S.current); };
  $('#pBack').onclick = () => { audio.currentTime = Math.max(0, audio.currentTime - 10); };
  $('#pFwd').onclick = () => { audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 30); };
  $('#pSpeed').onclick = () => { const i = SPEEDS.indexOf(S.speed); setSpeed(SPEEDS[(i + 1) % SPEEDS.length]); };
  $('#pNext').onclick = () => { S.queue = true; playNext(); };
  $('#playerMeta').onclick = () => { if (S.current) nav('/n/' + S.current.id); };
  $('#topBack').onclick = () => nav('/');
  $('#queueBtn').onclick = playQueue;
  $('#markAllBtn').onclick = markAllHeard;
  $('#themeBtn').onclick = cycleTheme;
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => applyTheme(store.get('theme', 'auto')));
  for (const b of document.querySelectorAll('#statusChips .chip')) b.onclick = () => { S.filters.status = b.dataset.status; refreshFilters(); };
  $('#tagSel').onchange = e => { S.filters.tag = e.target.value; refreshFilters(); };
  let qt = null;
  $('#q').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { S.filters.q = e.target.value.trim(); refreshFilters(); }, 220); });
  document.addEventListener('click', e => {
    const a = e.target.closest('a[data-nav]');
    if (a) { e.preventDefault(); nav(a.getAttribute('href')); }
  });
  document.addEventListener('keydown', onKey);
  document.addEventListener('pointerover', showTip);
  document.addEventListener('focusin', showTip);
  window.addEventListener('popstate', route);
  window.addEventListener('pagehide', savePosition);
  document.addEventListener('visibilitychange', () => {
    // Phones: drop the stream in the background (frozen tabs keep dead sockets). Desktop:
    // keep it, a background hub tab must still hear "play this note".
    if (document.hidden) { if (matchMedia('(pointer: coarse)').matches) disconnectEvents(); savePosition(); }
    else { connectEvents(); loadList(); loadFacets(); }
  });

  connectEvents();
  await Promise.all([loadList(), loadFacets()]);
  route();
  if (playId) playFromLink(playId, { serverTried });

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(() => {
      navigator.serviceWorker.ready.then(() => setTimeout(prefetchAudio, 1500));
    }).catch(() => {});
  }
}

boot();
