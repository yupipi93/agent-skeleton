"""The note store: one SQLite database plus one audio file per note.

Writers (the CLI that voice-note.py calls) and the reader (the web
server) are separate processes, so the database runs in WAL mode with a busy timeout,
and nobody keeps a connection open longer than one operation. The server notices
writes from other processes through PRAGMA data_version, which is exactly what that
pragma exists for.

Every note's audio is normalised to constant-bitrate MP3 (64 kbps mono). Not AAC and not
Opus, on purpose: the Chromium inside VS Code and Cursor ships without AAC and Opus
decoders (microsoft/vscode#310736), so an .m4a is silent in Cursor's built-in browser
and in an MCP App player inside Cursor's chat. MP3 plays in all of them, in Chrome on
Android and in Safari, and CBR seeks accurately with plain byte ranges.
"""

import array
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timezone

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    summary       TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'AGENT',
    tag           TEXT NOT NULL DEFAULT '',
    speaker       TEXT NOT NULL DEFAULT '',
    agent         TEXT NOT NULL DEFAULT 'unknown',
    agent_surface TEXT NOT NULL DEFAULT '',
    agent_label   TEXT NOT NULL DEFAULT '',
    session_id    TEXT NOT NULL DEFAULT '',
    cwd           TEXT NOT NULL DEFAULT '',
    repo          TEXT NOT NULL DEFAULT '',
    branch        TEXT NOT NULL DEFAULT '',
    lang          TEXT NOT NULL DEFAULT 'en',
    voice         TEXT NOT NULL DEFAULT '',
    speech_rate   REAL NOT NULL DEFAULT 1.0,
    duration      REAL NOT NULL DEFAULT 0,
    audio_file    TEXT NOT NULL DEFAULT '',
    audio_bytes   INTEGER NOT NULL DEFAULT 0,
    peaks         TEXT NOT NULL DEFAULT '[]',
    text          TEXT NOT NULL DEFAULT '',
    spoken        TEXT NOT NULL DEFAULT '',
    segments      TEXT NOT NULL DEFAULT '[]',
    tickets       TEXT NOT NULL DEFAULT '[]',
    links         TEXT NOT NULL DEFAULT '[]',
    channels      TEXT NOT NULL DEFAULT '{}',
    origin        TEXT NOT NULL DEFAULT 'live',
    origin_ref    TEXT NOT NULL DEFAULT '',
    heard_at      TEXT,
    position      REAL NOT NULL DEFAULT 0,
    starred       INTEGER NOT NULL DEFAULT 0,
    archived      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS notes_created ON notes(created_at DESC);
CREATE INDEX IF NOT EXISTS notes_origin_ref ON notes(origin_ref);
CREATE TABLE IF NOT EXISTS pending_commands (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    item        TEXT NOT NULL
);
"""

# Columns added after v1; created on open when missing, so old databases upgrade in place.
MIGRATIONS = [
    ("commands", "TEXT NOT NULL DEFAULT '[]'"),
    ("brief", "TEXT NOT NULL DEFAULT ''"),
]
# A command sent by the same agent session this long before or after its voice note
# belongs to that note.
COMMAND_WINDOW_MIN = 30

JSON_FIELDS = ("peaks", "segments", "tickets", "links", "channels", "commands")
EDITABLE = {"title", "summary", "source", "tag", "speaker", "agent", "agent_surface",
            "agent_label", "session_id", "cwd", "repo", "branch", "lang", "voice",
            "speech_rate", "text", "spoken", "segments", "tickets", "links", "channels",
            "origin", "origin_ref", "heard_at", "position", "starred", "archived",
            "created_at", "commands", "brief"}

TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,15}-[0-9]{1,6}\b")
URL_RE = re.compile(r"https?://[^\s)>\]\"'`]+")
PEAK_BUCKETS = 160


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _b36(n):
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = chars[r] + out
    return out or "0"


def new_id():
    """Short, URL-safe and sortable by creation time: base36 millis + 3 random chars."""
    rnd = "".join(random.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(3))
    return "%s%s" % (_b36(int(time.time() * 1000)), rnd)


class Store:
    def __init__(self, home):
        self.home = home
        self.db_path = os.path.join(home, "hub.db")
        self.audio_dir = os.path.join(home, "audio")
        # Private from the first byte: transcripts and audio of work sessions.
        old = os.umask(0o077)
        try:
            os.makedirs(self.audio_dir, mode=0o700, exist_ok=True)
        finally:
            os.umask(old)
        for path in (home, self.audio_dir):
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass
        with self.connect() as db:
            db.executescript(SCHEMA)
            have = {r[1] for r in db.execute("PRAGMA table_info(notes)")}
            for col, decl in MIGRATIONS:
                if col not in have:
                    db.execute("ALTER TABLE notes ADD COLUMN %s %s" % (col, decl))
            db.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    # --------------------------------------------------------------- connection
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA foreign_keys=ON")
        return _Closing(db)

    # ------------------------------------------------------------------ reading
    def get(self, note_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return _row(row) if row else None

    def find_by_ref(self, origin_ref):
        with self.connect() as db:
            row = db.execute("SELECT * FROM notes WHERE origin_ref = ? LIMIT 1",
                             (origin_ref,)).fetchone()
        return _row(row) if row else None

    def list(self, q="", agent="", tag="", source="", status="", limit=60, before="",
             light=True, include_archived=False):
        where, args = [], []
        if not include_archived:
            where.append("archived = 0")
        if q:
            like = "%" + q.lower() + "%"
            where.append("(lower(title) LIKE ? OR lower(summary) LIKE ? OR lower(text) "
                         "LIKE ? OR lower(spoken) LIKE ? OR lower(tag) LIKE ? OR "
                         "lower(tickets) LIKE ?)")
            args += [like] * 6
        if agent:
            where.append("agent = ?")
            args.append(agent)
        if tag:
            where.append("tag = ?")
            args.append(tag)
        if source:
            where.append("source = ?")
            args.append(source.upper())
        if status == "unheard":
            where.append("heard_at IS NULL")
        elif status == "starred":
            where.append("starred = 1")
        elif status == "archived":
            where[:] = [w for w in where if w != "archived = 0"]
            where.append("archived = 1")
        if before:
            where.append("created_at < ?")
            args.append(before)
        sql = "SELECT * FROM notes"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(int(limit))
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
        out = [_row(r) for r in rows]
        if light:
            for n in out:
                n.pop("text", None)
                n.pop("spoken", None)
                n.pop("segments", None)
        return out

    def facets(self):
        with self.connect() as db:
            agents = db.execute("SELECT agent, count(*) c FROM notes WHERE archived = 0 "
                                "GROUP BY agent ORDER BY c DESC").fetchall()
            tags = db.execute("SELECT tag, count(*) c FROM notes WHERE archived = 0 AND "
                              "tag != '' GROUP BY tag ORDER BY c DESC").fetchall()
            sources = db.execute("SELECT source, count(*) c FROM notes WHERE archived = 0 "
                                 "GROUP BY source ORDER BY c DESC").fetchall()
            totals = db.execute(
                "SELECT count(*) total, sum(heard_at IS NULL) unheard, "
                "sum(starred) starred, sum(duration) seconds FROM notes "
                "WHERE archived = 0").fetchone()
        return {"agents": [dict(r) for r in agents], "tags": [dict(r) for r in tags],
                "sources": [dict(r) for r in sources],
                "totals": {k: (totals[k] or 0) for k in totals.keys()}}

    def data_version(self):
        """Changes whenever ANOTHER connection commits. Cheap, so it can be polled."""
        with self.connect() as db:
            return db.execute("PRAGMA data_version").fetchone()[0], \
                db.execute("SELECT max(updated_at) FROM notes").fetchone()[0] or ""

    def audio_path(self, note):
        return os.path.join(self.audio_dir, note["audio_file"]) if note.get(
            "audio_file") else ""

    # ------------------------------------------------------------------ writing
    def add(self, audio_path, meta):
        """Ingest one note. `audio_path` is any format ffmpeg reads; it is copied, never
        moved, so the caller keeps its file. Returns the stored note."""
        note_id = meta.get("id") or new_id()
        created = meta.get("created_at") or now_iso()
        month_dir = os.path.join(self.audio_dir, created[:4], created[5:7])
        os.makedirs(month_dir, exist_ok=True)
        rel = os.path.join(created[:4], created[5:7], note_id + ".mp3")
        dst = os.path.join(self.audio_dir, rel)
        normalise_audio(audio_path, dst)
        duration = probe_duration(dst)
        peaks = compute_peaks(dst)
        text = meta.get("text") or ""
        spoken = meta.get("spoken") or text
        commands = merge_commands(meta.get("commands") or [], extract_code_blocks(text))
        if meta.get("session_id"):
            commands = merge_commands(commands, self._take_pending(meta["session_id"]))
        record = {
            "id": note_id, "created_at": created, "updated_at": now_iso(),
            "title": meta.get("title") or "", "source": (meta.get("source") or "AGENT").upper(),
            "tag": meta.get("tag") or "", "speaker": meta.get("speaker") or "",
            "agent": meta.get("agent") or "unknown",
            "agent_surface": meta.get("agent_surface") or "",
            "agent_label": meta.get("agent_label") or "",
            "session_id": meta.get("session_id") or "", "cwd": meta.get("cwd") or "",
            "repo": meta.get("repo") or "", "branch": meta.get("branch") or "",
            "lang": meta.get("lang") or "en", "voice": meta.get("voice") or "",
            "speech_rate": float(meta.get("speech_rate") or 1.0),
            "duration": duration, "audio_file": rel,
            "audio_bytes": os.path.getsize(dst), "peaks": peaks,
            "text": text, "spoken": spoken,
            "summary": meta.get("summary") or derive_summary(text or spoken, meta.get("speaker")),
            "segments": segment_timeline(spoken, duration),
            "tickets": meta.get("tickets") or extract_tickets(
                " ".join([meta.get("title") or "", text])),
            "links": meta.get("links") or extract_links(text),
            "channels": meta.get("channels") or {},
            "commands": commands, "brief": (meta.get("brief") or "").strip(),
            "origin": meta.get("origin") or "live", "origin_ref": meta.get("origin_ref") or "",
            "heard_at": meta.get("heard_at"), "position": 0,
            "starred": 1 if meta.get("starred") else 0, "archived": 0,
        }
        cols = list(record)
        vals = [json.dumps(record[c], ensure_ascii=False) if c in JSON_FIELDS else record[c]
                for c in cols]
        with self.connect() as db:
            db.execute("INSERT INTO notes (%s) VALUES (%s)"
                       % (",".join(cols), ",".join("?" * len(cols))), vals)
        return self.get(note_id)

    def update(self, note_id, fields):
        fields = {k: v for k, v in fields.items() if k in EDITABLE}
        if not fields:
            return self.get(note_id)
        if "segments" not in fields and ("spoken" in fields):
            note = self.get(note_id)
            if note:
                fields["segments"] = segment_timeline(fields["spoken"], note["duration"])
        if "source" in fields and fields["source"]:
            fields["source"] = str(fields["source"]).upper()
        fields["updated_at"] = now_iso()
        sets = ", ".join("%s = ?" % k for k in fields)
        vals = [json.dumps(v, ensure_ascii=False) if k in JSON_FIELDS else v
                for k, v in fields.items()]
        with self.connect() as db:
            db.execute("UPDATE notes SET %s WHERE id = ?" % sets, vals + [note_id])
        return self.get(note_id)

    def mark_all_heard(self):
        """Mark every unheard, unarchived note as heard in one statement; returns the count."""
        stamp = now_iso()
        with self.connect() as db:
            cur = db.execute("UPDATE notes SET heard_at = ?, updated_at = ? "
                             "WHERE heard_at IS NULL AND archived = 0", (stamp, stamp))
            return cur.rowcount

    def replace_audio(self, note_id, src, speech_rate=None, spoken=None):
        """Swap a note's recording (re-synthesis). New file name, so no cache serves
        the old bytes; timeline, waveform and duration follow the new audio."""
        note = self.get(note_id)
        if not note:
            return None
        old = self.audio_path(note)
        stem = note["audio_file"].rsplit(".", 1)[0].split("~")[0]
        rel = "%s~%s.mp3" % (stem, new_id()[-5:])
        dst = os.path.join(self.audio_dir, rel)
        normalise_audio(src, dst)
        duration = probe_duration(dst)
        spoken = spoken if spoken is not None else note["spoken"]
        fields = {"audio_file": rel, "audio_bytes": os.path.getsize(dst),
                  "duration": duration, "peaks": compute_peaks(dst), "spoken": spoken,
                  "segments": segment_timeline(spoken, duration), "position": 0}
        if speech_rate:
            fields["speech_rate"] = float(speech_rate)
        fields["updated_at"] = now_iso()
        sets = ", ".join("%s = ?" % k for k in fields)
        vals = [json.dumps(v, ensure_ascii=False) if k in JSON_FIELDS else v
                for k, v in fields.items()]
        with self.connect() as db:
            db.execute("UPDATE notes SET %s WHERE id = ?" % sets, vals + [note_id])
        if old and old != dst and os.path.exists(old):
            os.unlink(old)
        return self.get(note_id)

    def attach_command(self, item, session_id=""):
        """A command (or a short written explanation) the agent sent alongside a note.

        Attached to that session's newest note when it is recent; otherwise parked, and
        the session's next note picks it up. Returns the note id, or "" when parked.
        """
        item = {k: (item.get(k) or "").strip() for k in ("code", "label", "explanation")}
        if not item["code"] and not item["explanation"]:
            return ""
        item["at"] = now_iso()
        since = _minutes_ago(COMMAND_WINDOW_MIN)
        with self.connect() as db:
            if session_id:
                row = db.execute("SELECT id FROM notes WHERE session_id = ? AND created_at >= ?"
                                 " ORDER BY created_at DESC LIMIT 1",
                                 (session_id, since)).fetchone()
            else:
                # No session to go by: only the very latest note, and only if fresh.
                row = db.execute("SELECT id FROM notes WHERE created_at >= ? ORDER BY "
                                 "created_at DESC LIMIT 1", (_minutes_ago(5),)).fetchone()
            if not row:
                db.execute("INSERT INTO pending_commands (session_id, created_at, item) "
                           "VALUES (?, ?, ?)", (session_id, item["at"], json.dumps(item)))
                return ""
        note = self.get(row["id"])
        self.update(note["id"], {"commands": merge_commands(note["commands"], [item])})
        return note["id"]

    def _take_pending(self, session_id):
        with self.connect() as db:
            rows = db.execute("SELECT id, item FROM pending_commands WHERE session_id = ? "
                              "AND created_at >= ? ORDER BY id",
                              (session_id, _minutes_ago(COMMAND_WINDOW_MIN))).fetchall()
            db.execute("DELETE FROM pending_commands WHERE session_id = ? OR created_at < ?",
                       (session_id, _minutes_ago(24 * 60)))
        out = []
        for r in rows:
            try:
                out.append(json.loads(r["item"]))
            except ValueError:
                pass
        return out

    def merge_channels(self, note_id, channels):
        note = self.get(note_id)
        if not note:
            return None
        merged = dict(note.get("channels") or {})
        merged.update(channels or {})
        return self.update(note_id, {"channels": merged})

    def delete(self, note_id):
        """Hard delete: the row and the audio file. The UI archives instead."""
        note = self.get(note_id)
        if not note:
            return False
        path = self.audio_path(note)
        with self.connect() as db:
            db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if path and os.path.exists(path):
            os.unlink(path)
        return True


class _Closing:
    """sqlite3's own context manager commits but does not close; this one closes."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        self.db.close()
        return False


def _minutes_ago(minutes):
    from datetime import timedelta
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


CODE_BLOCK_RE = re.compile(r"```([\w+-]*)[ \t]*\n(.*?)```", re.S)


def extract_code_blocks(text):
    """Fenced blocks in the agent's text: the audio skips them ("the command is in
    the chat"), so the hub shows them first, ready to copy."""
    out = []
    for lang, code in CODE_BLOCK_RE.findall(text or ""):
        code = code.strip("\n")
        if code.strip():
            out.append({"code": code, "lang": lang, "label": "", "explanation": ""})
    return out


def merge_commands(current, extra):
    out = list(current or [])
    seen = {(c.get("code") or "", c.get("explanation") or "") for c in out}
    for c in extra or []:
        key = (c.get("code") or "", c.get("explanation") or "")
        if key not in seen and (key[0] or key[1]):
            seen.add(key)
            out.append(c)
    return out[:20]


def _row(row):
    out = dict(row)
    for key in JSON_FIELDS:
        try:
            out[key] = json.loads(out.get(key) or ("{}" if key == "channels" else "[]"))
        except ValueError:
            out[key] = {} if key == "channels" else []
    out["starred"] = bool(out.get("starred"))
    out["archived"] = bool(out.get("archived"))
    return out


# ----------------------------------------------------------------------- text helpers
GREETING_RE = re.compile(r"^\s*(hola|hi|hello)\b[^.!?]{0,40}[.!?]\s*", re.I)
INTRO_RE = re.compile(r"^\s*(soy|this is)\b[^.!?]{0,120}\b(agente|agent)\b[^.!?]{0,80}[.!?]\s*",
                      re.I)


def _plain(text):
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"[`*_#>|]", "", t)
    t = URL_RE.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def derive_summary(text, speaker=None, limit=220):
    """The first real sentence: the skill tells agents to lead with the conclusion."""
    t = _plain(text)
    for _ in range(2):
        t = GREETING_RE.sub("", t, count=1)
        t = INTRO_RE.sub("", t, count=1)
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    first = (m.group(1) if m else t).strip()
    if len(first) < 40 and m:
        rest = t[m.end():]
        m2 = re.match(r"(.+?[.!?])(\s|$)", rest)
        if m2:
            first = (first + " " + m2.group(1)).strip()
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0] + "…"
    return first


def extract_tickets(text):
    seen = []
    for key in TICKET_RE.findall(text or ""):
        # Filters out things like UTF-8, SHA-256 or ISO-8601 that share the shape.
        if key.split("-")[0] in ("UTF", "SHA", "ISO", "TLS", "HTTP", "RFC", "AES", "RSA",
                                 "MP3", "MP4", "H264", "GPT", "COVID"):
            continue
        if key not in seen:
            seen.append(key)
    return seen[:12]


def extract_links(text):
    seen = []
    for url in URL_RE.findall(text or ""):
        url = url.rstrip(".,;:")
        if url not in seen:
            seen.append(url)
    return seen[:12]


SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9\"'(])")


def segment_timeline(spoken, duration):
    """Sentence list with approximate start times, for the follow-along transcript.

    TTS speaks at a near-constant rate, so time is proportional to characters within a
    few percent, plus a fixed beat at each paragraph break. Good enough to highlight
    the sentence being read and to tap a sentence to jump to it; labelled approximate
    in the UI.
    """
    if not spoken or not duration:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", spoken) if p.strip()]
    items = []
    for pi, para in enumerate(paras):
        for s in SENTENCE_SPLIT.split(re.sub(r"\s+", " ", para)):
            s = s.strip()
            if s:
                items.append({"text": s, "para": pi})
    if not items:
        return []
    pause = 6     # characters-worth of silence at a paragraph break
    weights = []
    for i, it in enumerate(items):
        w = len(it["text"]) + 2
        if i and it["para"] != items[i - 1]["para"]:
            w += pause
        weights.append(w)
    total = float(sum(weights))
    t, out = 0.0, []
    for it, w in zip(items, weights):
        out.append({"t": round(t, 2), "text": it["text"], "p": it["para"]})
        t += duration * w / total
    return out


# ---------------------------------------------------------------------- audio helpers
def _which(name):
    return shutil.which(name)


def probe_duration(path):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path], stderr=subprocess.DEVNULL, timeout=60)
        return round(float(out.decode().strip()), 2)
    except Exception:                                       # noqa: BLE001
        return 0.0


def normalise_audio(src, dst):
    """Any input to MP3 CBR 64 kbps mono. See the module docstring for why MP3."""
    if not _which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to store audio (brew install ffmpeg)")
    tmp = dst + ".part.mp3"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vn",
           "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "64k", "-ac", "1",
           "-ar", "44100", "-write_xing", "1", "-f", "mp3", tmp]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    if proc.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise RuntimeError("ffmpeg could not convert the audio: %s"
                           % proc.stderr.decode("utf-8", "replace").strip()[-300:])
    os.replace(tmp, dst)


def compute_peaks(path, buckets=PEAK_BUCKETS):
    """A small waveform (0-100 per bucket) for the list and the scrubber."""
    try:
        proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
                               "-ac", "1", "-ar", "4000", "-f", "s16le", "-"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=300)
        samples = array.array("h")
        samples.frombytes(proc.stdout[: len(proc.stdout) // 2 * 2])
    except Exception:                                       # noqa: BLE001
        return []
    n = len(samples)
    if not n:
        return []
    step = max(1, n // buckets)
    raw = []
    for i in range(0, step * buckets, step):
        chunk = samples[i:i + step]
        if not chunk:
            break
        raw.append(max(max(chunk), -min(chunk)))
    top = float(max(raw) or 1)
    return [int(round(100 * (v / top) ** 0.7)) for v in raw]


def write_temp(data, suffix):
    fh = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    fh.write(data)
    fh.close()
    return fh.name
