#!/usr/bin/env python3
"""voice-note.py: speak a summary and deliver it as a voice note.

    kit/bundles/voice/scripts/voice-note.py --source TERRAFORM --title "Plan ready" "The plan is clean..."
    printf '%s' "$summary" | kit/bundles/voice/scripts/voice-note.py --title "Release" --file -
    kit/bundles/voice/scripts/voice-note.py --dry-run --title "Try" "Hello."    # audio file, nothing sent

Engines (TTS_ENGINE, default auto):
  google  Google Cloud Text-to-Speech, Chirp 3 HD voices. Auth: TTS_API_KEY (sent in the
          X-Goog-Api-Key header) or a gcloud user token for TTS_GCLOUD_ACCOUNT, billed to
          TTS_QUOTA_PROJECT (x-goog-user-project). Text over one request is synthesised
          in chunks as PCM, joined, and encoded once, so a long note is still one clip.
  say     the macOS built-in `say` voice, converted with ffmpeg. Free, offline.
  none    no audio: the summary is delivered as text.
  auto    google when a key or a gcloud account is configured, else say, else none.

Channels (NOTIFY_CHANNELS, a comma list; default hub, and auto means hub too):
  hub       the default. The note is stored in the local voice hub (tools/voice-hub:
            history, a player with a speed control, transcript), the player link is
            printed for the reply, and the note is played: VOICE_HUB_OPEN=auto (default)
            hands it to an open hub tab, else opens the link in the default browser;
            always opens the browser; never only prints the link. The hub server must be
            running: if it is not, the script says how to start it and exits 1.
  telegram  opt-in. sendVoice (an Opus voice bubble with a speed control).
  chat      opt-in. Google Chat. With GCHAT_SPACE and the google bundle's gchat.py login,
            the audio is uploaded (an MP4 with a waveform, which Chat plays inline). With
            only GCHAT_WEBHOOK_URL, the caption and the summary text are posted.
Telegram and Google Chat are never used unless listed (NOTIFY_CHANNELS=hub,telegram, or
--to telegram for one call) and configured.

The opening sentence is built here, not by the caller: "Hi, Ana. This is the payments
agent, about Terraform." It names the repository the agent is working in, so several
agents speaking with the same voice can be told apart. Commands, URLs and code blocks are
never read aloud; a fenced block becomes "The command is in the chat."

Exit codes: 0 delivered everywhere; 3 partial (delivered somewhere, a channel failed, or
audio failed and the text went out instead: do not send it again); 1 nothing delivered
or nothing configured; 2 usage. --dry-run synthesises locally and sends nothing;
--plan prints the spoken text only; --self-test runs offline checks.

Config: ~/.config/agent-skeleton/notify.env (see lib/notifylib.py). Python 3.9+, stdlib.
"""

import argparse
import base64
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import wave

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
import notifylib as nl  # noqa: E402

TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
VOICES_URL = "https://texttospeech.googleapis.com/v1/voices"
# The API takes 5000 bytes per request; 4200 leaves room for an unlucky accented paragraph.
MAX_CHUNK_BYTES = 4200
TTS_TIMEOUT = 180
GAP_MS = 300
SAY_WPM = 175

LANG_CODES = {"en": "en-US", "es": "es-ES"}
GOOGLE_VOICE = {"en": "en-US-Chirp3-HD-Charon", "es": "es-ES-Chirp3-HD-Charon"}
SAY_LOCALES = {"en": ("en_US", "en_GB", "en_"), "es": ("es_ES", "es_MX", "es_")}
SAY_PREFERRED = {"en": ("Samantha", "Alex", "Daniel", "Karen", "Moira", "Tessa"),
                 "es": ("Mónica", "Monica", "Paulina", "Marisol")}
# Novelty voices `say` also ships: never picked automatically.
SAY_NOVELTY = {"Albert", "Bad News", "Bahh", "Bells", "Boing", "Bubbles", "Cellos", "Good News",
               "Jester", "Organ", "Superstar", "Trinoids", "Whisper", "Wobble", "Zarvox"}

TEXT = {
    "en": {"greeting": "Hi", "intro": "This is %s", "about": ", about %s",
           "agent": "the %s agent", "code": "The command is in the chat.", "link": "a link",
           "summary": "Summary"},
    "es": {"greeting": "Hola", "intro": "Soy %s", "about": ", sobre %s",
           "agent": "el agente de %s", "code": "El comando está en el chat.", "link": "un enlace",
           "summary": "Resumen"},
}

# --source tag -> (english topic, spanish topic). AGENT and unknown tags add nothing.
TOPICS = {
    "TERRAFORM": ("Terraform", "Terraform"), "TF": ("Terraform", "Terraform"),
    "IAC": ("the infrastructure", "la infraestructura"),
    "DEPLOY": ("a deployment", "un despliegue"), "BUILD": ("a build", "una compilación"),
    "RELEASE": ("a release", "una versión"),
    "GCP": ("Google Cloud", "Google Cloud"), "CLOUD": ("the cloud", "la nube"),
    "IAM": ("permissions", "los permisos"),
    "DB": ("the database", "la base de datos"), "SQL": ("the database", "la base de datos"),
    "DATABASE": ("the database", "la base de datos"),
    "SECURITY": ("security", "la seguridad"), "CVE": ("vulnerabilities", "vulnerabilidades"),
    "BILLING": ("the spend", "el gasto"), "COST": ("the spend", "el gasto"),
    "DNS": ("DNS", "el DNS"), "NET": ("the network", "la red"),
    "JIRA": ("the ticket", "el ticket"), "TICKET": ("the ticket", "el ticket"),
    "ACTION": ("something I need from you", "algo que necesito de ti"),
    "APPROVAL": ("an approval I need", "una aprobación que necesito"),
    "DECISION": ("a decision", "una decisión"),
}


# --------------------------------------------------------------------------- identity
def repo_name():
    try:
        top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                      stderr=subprocess.DEVNULL, timeout=10)
        name = os.path.basename(top.decode().strip())
        if name:
            return name
    except Exception:                                         # noqa: BLE001
        pass
    try:
        return os.path.basename(os.getcwd())
    except OSError:
        return ""


def load_speakers(cfg):
    path = os.path.expanduser(cfg.get("VOICE_SPEAKERS_FILE") or "")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def speaker(lang, cfg, who=None, repo=None):
    """How the note names itself out loud. --who > speakers file > 'the <repo> agent'."""
    if who and who.strip():
        return who.strip().rstrip(".")
    repo = repo if repo is not None else repo_name()
    entry = load_speakers(cfg).get(repo)
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    if isinstance(entry, dict) and str(entry.get(lang) or "").strip():
        return str(entry[lang]).strip()
    spoken = (repo or "workspace").replace("-", " ").replace("_", " ").strip()
    return TEXT[lang]["agent"] % spoken


def caption_tag(cfg, tag=None, repo=None):
    if tag is not None:
        return tag
    repo = repo if repo is not None else repo_name()
    entry = load_speakers(cfg).get(repo)
    if isinstance(entry, dict) and entry.get("tag"):
        return str(entry["tag"])
    return (repo or "")[:24]


def opener(lang, who, source="", greeting=None, name=None):
    """The first sentence: greeting, who is speaking, and about what."""
    t = TEXT[lang]
    hello = (greeting or t["greeting"]).strip().rstrip(".!")
    if name and name.strip():
        hello = "%s, %s" % (hello, name.strip())
    topic = TOPICS.get((source or "").upper())
    tail = t["about"] % topic[0 if lang == "en" else 1] if topic else ""
    return "%s. %s%s." % (hello, t["intro"] % who, tail)


GREET_OPEN = re.compile(r"^\s*(hi|hello|hey|hola|buenas)\b[^.!?\n]{0,90}[.!?\n]", re.I)
SELF_OPEN = re.compile(r"^\s*(this is|here is|i am|i'm|soy|aqu[ií])\b[^.!?\n]{0,50}"
                       r"\bagen(t|te)\b[^.!?\n]{0,60}[.!?\n]", re.I)


def drop_leading_intro(text):
    """Remove a greeting or self-introduction the caller wrote: the tool already said it."""
    out = text.lstrip()
    for _ in range(2):
        for pattern in (GREET_OPEN, SELF_OPEN):
            m = pattern.match(out)
            if m:
                out = out[m.end():].lstrip()
                break
        else:
            break
    return out or text


# ---------------------------------------------------------------------- text for the ear
CODE_FENCE = re.compile(r"```.*?```", re.S)
URL_RE = re.compile(r"https?://\S+")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
EMOJI_RANGES = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0xFE00, 0xFE0F), (0x2B00, 0x2BFF),
                (0x200D, 0x200D))


def _is_emoji(ch):
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in EMOJI_RANGES)


def speakable(text, lang="en"):
    """Agent prose (markdown, links, emoji, code) into something worth hearing."""
    t = TEXT.get(lang, TEXT["en"])
    s = CODE_FENCE.sub(" " + t["code"] + " ", text)
    s = LINK_RE.sub(r"\1", s)
    s = URL_RE.sub(t["link"], s)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"^\s{0,3}#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.M)
    s = re.sub(r"^\s*\d+[.)]\s+", "", s, flags=re.M)
    s = re.sub(r"^\s*>\s?", "", s, flags=re.M)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"^\s*\|", "", s, flags=re.M)
    s = s.replace("|", ", ")
    s = re.sub(r"^\s*[-=_:]{3,}[-=_:, ]*$", "", s, flags=re.M)
    s = "".join(ch for ch in s if not _is_emoji(ch))
    s = unicodedata.normalize("NFC", s)
    lines = []
    for raw in s.split("\n"):
        line = raw.strip()
        if line and line[-1] not in ".,:;!?…":
            line += "."
        lines.append(line)
    s = "\n".join(lines)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def _hard_split(s, limit):
    out, buf = [], ""
    for ch in s:
        if len((buf + ch).encode("utf-8")) > limit:
            out.append(buf)
            buf = ch
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


def chunk(text, limit=MAX_CHUNK_BYTES):
    """Request-sized pieces, cut at paragraphs, then sentences, then words."""
    def size(s):
        return len(s.encode("utf-8"))

    if size(text) <= limit:
        return [text] if text else []
    units = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if size(para) <= limit:
            units.append(para)
            continue
        for sentence in re.split(r"(?<=[.!?…])\s+", para):
            if size(sentence) <= limit:
                units.append(sentence)
                continue
            buf = ""
            for word in sentence.split(" "):
                if size(word) > limit:
                    if buf:
                        units.append(buf)
                        buf = ""
                    units.extend(_hard_split(word, limit))
                    continue
                cand = (buf + " " + word).strip()
                if size(cand) > limit and buf:
                    units.append(buf)
                    buf = word
                else:
                    buf = cand
            if buf:
                units.append(buf)
    out, cur = [], ""
    for unit in units:
        cand = (cur + "\n\n" + unit) if cur else unit
        if size(cand) > limit and cur:
            out.append(cur)
            cur = unit
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------------------ audio
def which(cmd):
    return shutil.which(cmd)


_FFMPEG_CACHE = {}


def ffmpeg_has(kind, name):
    """True when this ffmpeg build ships the encoder (kind 'encoders') or filter."""
    key = (kind, name)
    if key not in _FFMPEG_CACHE:
        ok = False
        if which("ffmpeg"):
            try:
                out = subprocess.check_output(["ffmpeg", "-hide_banner", "-" + kind],
                                              stderr=subprocess.DEVNULL, timeout=30)
                ok = (" %s " % name).encode() in out
            except Exception:                                 # noqa: BLE001
                ok = False
        _FFMPEG_CACHE[key] = ok
    return _FFMPEG_CACHE[key]


def have_opus():
    return ffmpeg_has("encoders", "libopus")


def ffmpeg(args, src_bytes, src_suffix, dst_suffix, label):
    """Run ffmpeg from a temp input to a temp output and return the output bytes."""
    tmp = tempfile.mkdtemp(prefix="voice-note-")
    src = os.path.join(tmp, "in" + src_suffix)
    dst = os.path.join(tmp, "out" + dst_suffix)
    try:
        with open(src, "wb") as fh:
            fh.write(src_bytes)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src] + args + [dst]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if proc.returncode != 0:
            raise RuntimeError("%s failed: %s" % (
                label, proc.stderr.decode("utf-8", "replace").strip()[-200:]))
        with open(dst, "rb") as fh:
            data = fh.read()
        if not data:
            raise RuntimeError("%s produced nothing" % label)
        return data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def encode_opus(src_bytes, suffix=".wav", tempo=1.0):
    args = []
    if abs(tempo - 1.0) > 0.01:
        args += ["-filter:a", "atempo=%.4f" % tempo]
    args += ["-c:a", "libopus", "-b:a", "32k", "-ac", "1", "-f", "ogg"]
    return ffmpeg(args, src_bytes, suffix, ".ogg", "opus encode")


def mp4_waveform(ogg):
    """Chat plays an MP4 with a waveform video inline; it has no voice bubble for agents."""
    return ffmpeg(["-filter_complex",
                   "[0:a]showwaves=s=720x240:mode=cline:rate=25:colors=0x8AB4F8[v]",
                   "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "64k",
                   "-ac", "1", "-ar", "48000", "-shortest", "-movflags", "+faststart"],
                  ogg, ".ogg", ".mp4", "mp4 waveform encode")


def mp4_audio(ogg):
    return ffmpeg(["-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "48000", "-vn",
                   "-movflags", "+faststart"], ogg, ".ogg", ".mp4", "mp4 audio encode")


def pcm_from_wav(data):
    with wave.open(io.BytesIO(data)) as w:
        if w.getnchannels() != 1:
            raise RuntimeError("expected mono audio, got %d channels" % w.getnchannels())
        return w.readframes(w.getnframes()), w.getframerate(), w.getsampwidth()


def wav_from_pcm(pcm, rate, width):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def probe_seconds(data, suffix):
    """Duration of an audio blob with ffprobe, or None."""
    if not which("ffprobe"):
        return None
    tmp = tempfile.mkdtemp(prefix="voice-note-")
    path = os.path.join(tmp, "a" + suffix)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
        out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                       "format=duration", "-of", "csv=p=0", path],
                                      stderr=subprocess.DEVNULL, timeout=30)
        return int(round(float(out.decode().strip())))
    except Exception:                                         # noqa: BLE001
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------- engines
def resolve_engine(cfg, override=None):
    raw = (override or cfg.get("TTS_ENGINE") or "auto").strip().lower()
    if raw in ("google", "say", "none"):
        return raw
    if cfg.get("TTS_API_KEY") or cfg.get("TTS_GCLOUD_ACCOUNT"):
        return "google"
    if which("say") and have_opus():
        return "say"
    return "none"


def access_token(cfg):
    """A user token from gcloud, pinned to TTS_GCLOUD_ACCOUNT when set."""
    account = cfg.get("TTS_GCLOUD_ACCOUNT", "")
    cmd = ["gcloud", "auth", "print-access-token"]
    if account:
        cmd.append("--account=" + account)
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    except Exception as exc:                                  # noqa: BLE001
        raise RuntimeError("no Google token: %s" % exc)
    token = out.stdout.decode().strip()
    if out.returncode != 0 or not token:
        detail = out.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("no Google token for %s (try: gcloud auth login): %s" % (
            account or "the active gcloud account", detail[-1][:200] if detail else ""))
    return token


def _tts_request(url, payload, cfg, method="POST"):
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if cfg.get("TTS_API_KEY"):
        headers["X-Goog-Api-Key"] = cfg["TTS_API_KEY"]        # a header, never ?key=
    else:
        headers["Authorization"] = "Bearer " + access_token(cfg)
        if cfg.get("TTS_QUOTA_PROJECT"):
            # User credentials need an explicit quota project or the API answers 403.
            headers["x-goog-user-project"] = cfg["TTS_QUOTA_PROJECT"]
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TTS_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body)["error"]["message"]
        except Exception:                                     # noqa: BLE001
            msg = body[:300]
        raise RuntimeError(nl.scrub("TTS API %s: %s" % (exc.code, msg), cfg))
    except Exception as exc:                                  # noqa: BLE001
        raise RuntimeError(nl.scrub("TTS API unreachable: %s" % exc, cfg))


def google_synthesize(text, voice, lang_code, speed, encoding, cfg):
    payload = {"input": {"text": text},
               "voice": {"languageCode": lang_code, "name": voice},
               "audioConfig": {"audioEncoding": encoding, "speakingRate": float(speed)}}
    audio = _tts_request(TTS_URL, payload, cfg).get("audioContent")
    if not audio:
        raise RuntimeError("TTS returned no audio")
    return base64.b64decode(audio)


def google_voices(lang_code, cfg):
    url = VOICES_URL + "?" + urllib.parse.urlencode({"languageCode": lang_code})
    return _tts_request(url, None, cfg, method="GET").get("voices", [])


def say_voices():
    """[(name, locale)] from `say -v ?`."""
    try:
        out = subprocess.check_output(["say", "-v", "?"], stderr=subprocess.DEVNULL, timeout=30)
    except Exception:                                         # noqa: BLE001
        return []
    voices = []
    for line in out.decode("utf-8", "replace").splitlines():
        m = re.match(r"^(.+?)\s+([a-z]{2}_[A-Z0-9]{2,3})\s+#", line)
        if m:
            voices.append((m.group(1).strip(), m.group(2)))
    return voices


def pick_say_voice(lang, cfg):
    if cfg.get("TTS_VOICE") and "Chirp" not in cfg["TTS_VOICE"]:
        return cfg["TTS_VOICE"]
    voices = say_voices()
    names = {n for n, _ in voices}
    for preferred in SAY_PREFERRED.get(lang, ()):
        if preferred in names:
            return preferred
    for prefix in SAY_LOCALES.get(lang, ("en_",)):
        for name, locale in voices:
            if locale.startswith(prefix) and name not in SAY_NOVELTY:
                return name
    return ""                                                 # the system voice


def say_synthesize(text, voice, speed):
    """`say` to AIFF (text through a file, not argv), then Opus with ffmpeg."""
    tmp = tempfile.mkdtemp(prefix="voice-note-say-")
    src, aiff = os.path.join(tmp, "text.txt"), os.path.join(tmp, "out.aiff")
    try:
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(text)
        cmd = ["say", "-r", str(int(SAY_WPM * float(speed))), "-o", aiff, "-f", src]
        if voice:
            cmd[1:1] = ["-v", voice]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if proc.returncode != 0 or not os.path.exists(aiff):
            raise RuntimeError("say failed: %s" % proc.stderr.decode("utf-8", "replace")[-200:])
        with open(aiff, "rb") as fh:
            data = fh.read()
        return encode_opus(data, ".aiff")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def resolve_voice(engine, lang, cfg, explicit=None):
    """(voice, language code) for the engine."""
    voice = explicit or ""
    if engine == "google":
        if not voice:
            configured_voice = cfg.get("TTS_VOICE") or ""
            voice = configured_voice if "-" in configured_voice else GOOGLE_VOICE[lang]
        parts = voice.split("-")
        return voice, "-".join(parts[:2]) if len(parts) >= 2 else LANG_CODES[lang]
    if engine == "say":
        return voice or pick_say_voice(lang, cfg), LANG_CODES[lang]
    return "", LANG_CODES[lang]


def synthesize(engine, spoken, voice, lang_code, speed, cfg, max_bytes):
    """Return (clips, seconds, mode). One clip unless no Opus encoder is available."""
    if engine == "say":
        if not have_opus():
            raise RuntimeError("the say engine needs ffmpeg with libopus (brew install ffmpeg)")
        clip = say_synthesize(spoken, voice, speed)
        return [clip], probe_seconds(clip, ".ogg"), "say"
    parts = chunk(spoken, max_bytes)
    if len(parts) == 1:
        clip = google_synthesize(parts[0], voice, lang_code, speed, "OGG_OPUS", cfg)
        return [clip], probe_seconds(clip, ".ogg"), "single"
    if have_opus():
        pcm, rate, width = b"", 24000, 2
        for i, part in enumerate(parts):
            piece, rate, width = pcm_from_wav(
                google_synthesize(part, voice, lang_code, speed, "LINEAR16", cfg))
            if i:
                pcm += b"\x00" * (int(rate * GAP_MS / 1000) * width)
            pcm += piece
        seconds = int(len(pcm) / float(rate * width))
        return [encode_opus(wav_from_pcm(pcm, rate, width))], seconds, "merged"
    clips = [google_synthesize(p, voice, lang_code, speed, "OGG_OPUS", cfg) for p in parts]
    return clips, None, "split"


# ---------------------------------------------------------------------------- captions
def caption_html(source, title, tag, part=1, total=1):
    head = "%s <b>%s</b>" % (nl.icon_for(source), nl.html_escape((source or "AGENT").upper()))
    if tag:
        head += " · " + nl.html_escape(tag)
    if title:
        head += " · " + nl.html_escape(title)
    if total > 1:
        head += " (%d/%d)" % (part, total)
    return head[:1000]


def caption_md(source, title, tag, part=1, total=1):
    head = "%s **%s**" % (nl.icon_for(source), (source or "AGENT").upper())
    if tag:
        head += " · " + tag
    if title:
        head += " · " + title
    if total > 1:
        head += " (%d/%d)" % (part, total)
    return head


def chat_media(ogg):
    """(bytes, filename, content type) Chat can play: waveform MP4, audio MP4, else Ogg."""
    stamp = time.strftime("%Y-%m-%dT%H%MZ", time.gmtime())
    if ffmpeg_has("encoders", "libx264") and ffmpeg_has("filters", "showwaves"):
        return mp4_waveform(ogg), "voice_message_%s.mp4" % stamp, "video/mp4"
    if ffmpeg_has("encoders", "aac"):
        return mp4_audio(ogg), "voice_message_%s.mp4" % stamp, "video/mp4"
    return ogg, "voice_message_%s.ogg" % stamp, "audio/ogg"


def webhook_card(text, player, title, source, subtitle, summary, lang):
    """Caption plus a card with a button to the hub player (webhooks may post cardsV2)."""
    label = "▶ Listen with speed control" if lang == "en" else "▶ Escuchar con velocidad"
    widgets = []
    if summary:
        widgets.append({"textParagraph": {"text": summary[:400]}})
    widgets.append({"buttonList": {"buttons": [{"text": label,
                                                "onClick": {"openLink": {"url": player}}}]}})
    return {"text": text, "cardsV2": [{"cardId": "voice-note", "card": {
        "header": {"title": (title or source.upper())[:120], "subtitle": subtitle[:120]},
        "sections": [{"widgets": widgets}]}}]}


# --------------------------------------------------------------------------------- hub
def hub_register(cfg, audio, meta):
    """Store the note in the voice hub. Returns {id, local, public, ...} or {}; never raises."""
    if not nl.hub_on(cfg):
        return {}
    tmp = tempfile.mkdtemp(prefix="voice-note-hub-")
    path = os.path.join(tmp, "note.ogg")
    try:
        with open(path, "wb") as fh:
            fh.write(audio)
        proc = subprocess.run([sys.executable, nl.hub_cli(cfg), "add", "--audio", path,
                               "--meta-json", "-", "--json"],
                              input=json.dumps(meta).encode("utf-8"), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=180)
        if proc.returncode != 0:
            sys.stderr.write("voice-note: hub not updated: %s\n"
                             % proc.stderr.decode("utf-8", "replace").strip()[-200:])
            return {}
        out = json.loads(proc.stdout.decode("utf-8"))
        urls = out.get("urls") or {}

        def play(u):
            return (u + "?play=1") if u else ""
        return {"id": out.get("id", ""), "local": play(urls.get("local", "")),
                "public": play(urls.get("public", "")), "summary": out.get("summary", ""),
                "agent": out.get("agent_label", "")}
    except Exception as exc:                                  # noqa: BLE001
        sys.stderr.write("voice-note: hub not updated: %s\n" % exc)
        return {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


OPEN_MODES = ("auto", "always", "never")


def open_mode(cfg, override=None):
    raw = (override or cfg.get("VOICE_HUB_OPEN") or "auto").strip().lower()
    return raw if raw in OPEN_MODES else "auto"


def browser_opener(cfg):
    """The command that opens a URL: VOICE_HUB_OPENER, else open (macOS) or xdg-open."""
    custom = (cfg.get("VOICE_HUB_OPENER") or "").strip()
    if custom:
        return shlex.split(custom)
    if sys.platform == "darwin" and which("open"):
        return ["open"]
    if which("xdg-open"):
        return ["xdg-open"]
    return []


def open_in_browser(cfg, url):
    """True when the opener accepted the URL. The URL is one argv item, never a shell."""
    cmd = browser_opener(cfg)
    if not cmd:
        return False
    try:
        proc = subprocess.run(cmd + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=20)
        return proc.returncode == 0
    except Exception:                                         # noqa: BLE001
        return False


def hub_play(cfg, hub, mode):
    """Make the stored note heard. Returns how: tab, browser, link (printed only)."""
    url = hub.get("local") or ""
    if mode == "never" or not url:
        return "link"
    if mode == "auto":
        try:
            proc = subprocess.run([sys.executable, nl.hub_cli(cfg), "play", hub["id"], "--json",
                                   "--wait", "3"], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=20)
            if json.loads(proc.stdout.decode("utf-8") or "{}").get("played"):
                return "tab"
        except Exception:                                     # noqa: BLE001
            pass
    # `always`, or no hub tab took it. The ?play=1 link still hands the note to an open
    # tab server-side, so a second tab never plays over the first.
    return "browser" if open_in_browser(cfg, url) else "link"


def hub_record(cfg, hub, channels):
    if not hub.get("id"):
        return
    try:
        subprocess.run([sys.executable, nl.hub_cli(cfg), "update", hub["id"], "--channels-json",
                        json.dumps(channels)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60)
    except Exception:                                         # noqa: BLE001
        pass


# ------------------------------------------------------------------------------ deliver
def deliver_telegram(cfg, clips, seconds, source, title, tag):
    for i, clip in enumerate(clips, 1):
        fields = {"caption": caption_html(source, title, tag, i, len(clips)), "parse_mode": "HTML"}
        if seconds and len(clips) == 1:
            fields["duration"] = str(seconds)
        nl.telegram_call(cfg, "sendVoice", fields,
                         {"voice": ("voice-note.ogg", clip, "audio/ogg")}, timeout=60)


def deliver_chat(cfg, clips, spoken, source, title, tag, hub, seconds, lang):
    """Audio through the user token when a space is set; the caption through the webhook."""
    space = cfg.get("GCHAT_SPACE") or ""
    hook = cfg.get("GCHAT_WEBHOOK_URL") or ""
    player = hub.get("public") or hub.get("local") or ""
    ping = cfg.get("GCHAT_PING_USER") or ""
    kind = "audio" if space else "text"
    token = nl.chat_token() if space else ""
    for i, clip in enumerate(clips, 1):
        cap = caption_md(source, title, tag, i, len(clips))
        if not space:
            # Webhook only: no upload possible, so the summary travels as text.
            cap = cap + "\n\n" + spoken[:3500]
        if hook:
            text = ("<%s> " % ping if ping and i == 1 else "") + nl.markdown_to_classic(cap)
            if player and i == 1:
                mins = "%d:%02d" % (seconds // 60, seconds % 60) if seconds else ""
                sub = " · ".join(x for x in (hub.get("agent", ""), tag, mins) if x)
                try:
                    nl.chat_webhook_post(cfg, webhook_card(text, player, title, source, sub,
                                                           hub.get("summary", ""), lang))
                except nl.NotifyError:
                    nl.chat_webhook_post(cfg, {"text": text + "\n" + player})
            else:
                nl.chat_webhook_post(cfg, {"text": text})
        elif space:
            nl.chat_user_post(space, cap + ("\n▶ " + player if player and i == 1 else ""), token)
        if space:
            media, name, ctype = chat_media(clip)
            nl.chat_upload(space, name, media, ctype, token)
    return kind


def text_fallback(cfg, channels, source, title, raw, lang):
    """Audio failed or the engine is none: the summary still has to arrive, as text.

    Only the external channels carry text; the hub stores voice notes."""
    channels = [c for c in channels if c in nl.EXTERNAL]
    if not channels:
        return [], []
    body = raw if len(raw) < 3000 else raw[:2990] + "…"
    tg = nl.render_telegram("info", source, title or TEXT[lang]["summary"],
                            nl.html_escape(body), "", cfg)
    md = nl.render_chat("info", source, title or TEXT[lang]["summary"], body, "", cfg)
    return nl.send_text(cfg, channels, tg, md, mention=True)


# --------------------------------------------------------------------------------- main
def read_text(args):
    if args.file == "-":
        return sys.stdin.read()
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            return fh.read()
    return " ".join(args.text)


def dry_run_path():
    directory = os.path.join(nl.STATE_DIR, "dry-run")
    os.makedirs(directory, mode=0o700, exist_ok=True)
    return os.path.join(directory, "voice-note-%s.ogg" % time.strftime("%Y%m%d-%H%M%S"))


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def build_parser():
    p = argparse.ArgumentParser(prog="voice-note.py",
                                description="Speak a summary and deliver it as a voice note.")
    p.add_argument("text", nargs="*", help="the text to speak")
    p.add_argument("--file", help="read the text from a file, or - for stdin")
    p.add_argument("--title", default="", help="caption shown with the audio")
    p.add_argument("--source", default="AGENT",
                   help="AGENT TERRAFORM DEPLOY GCP DB SECURITY BILLING DNS JIRA ACTION")
    p.add_argument("--lang", help="en or es (default: TTS_LANG, then [user] language, then en)")
    p.add_argument("--engine", help="google, say or none (default: TTS_ENGINE, auto)")
    p.add_argument("--voice", help="voice name (Chirp voice for google, `say -v` name for say)")
    p.add_argument("--speed", help="speaking rate for the channel copies (default: TTS_SPEED)")
    p.add_argument("--to", help="channels for this call: hub, telegram, chat, a comma list, "
                                "or none (default: NOTIFY_CHANNELS, hub)")
    p.add_argument("--open", choices=OPEN_MODES, dest="open_mode",
                   help="after storing in the hub: auto (an open hub tab, else the browser), "
                        "always (the browser), never (default: VOICE_HUB_OPEN, auto)")
    p.add_argument("--who", help="how the note introduces itself (default: from the repo)")
    p.add_argument("--tag", help="short label for the caption (default: the repo)")
    p.add_argument("--greeting", help="say this instead of the greeting")
    p.add_argument("--no-opener", action="store_true", help="do not prepend the introduction")
    p.add_argument("--summary", help="one line for the hub and the Chat card")
    p.add_argument("--link", action="append", default=[], help="URL shown in the hub (repeatable)")
    p.add_argument("--command", action="append", default=[], dest="commands",
                   help="a command for the user, shown first in the hub with a copy button; "
                        "never spoken (repeatable)")
    p.add_argument("--brief", help="one or two written sentences shown first in the hub")
    p.add_argument("--no-hub", action="store_true", help="do not store this note in the hub")
    p.add_argument("--out", help="also write the audio (natural rate) to this path")
    p.add_argument("--no-send", action="store_true", help="synthesise only, deliver nothing")
    p.add_argument("--dry-run", action="store_true",
                   help="synthesise locally and print the plan; nothing is sent")
    p.add_argument("--plan", action="store_true", help="print the spoken text only, no audio")
    p.add_argument("--list-voices", action="store_true", help="voices for the language and engine")
    p.add_argument("--max-bytes", type=int, default=MAX_CHUNK_BYTES, help=argparse.SUPPRESS)
    p.add_argument("--self-test", action="store_true", help="offline checks")
    p.add_argument("--client", help=argparse.SUPPRESS)
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
    if args.self_test:
        return self_test()

    cfg = nl.load_config()
    lang = (args.lang or cfg["TTS_LANG"]).lower()[:2]
    lang = lang if lang in TEXT else "en"
    engine = resolve_engine(cfg, args.engine)
    voice, lang_code = resolve_voice(engine, lang, cfg, args.voice)

    if args.list_voices:
        if engine == "google":
            for v in google_voices(lang_code, cfg):
                print("%-34s %-8s %s" % (v.get("name"), v.get("ssmlGender"),
                                          ",".join(v.get("languageCodes", []))))
        elif engine == "say":
            for name, locale in say_voices():
                if locale.startswith(lang):
                    print("%-24s %s" % (name, locale))
        else:
            print("engine none: no voices (set TTS_ENGINE=say or google)")
        return 0

    raw = read_text(args)
    if not raw.strip():
        p.error("nothing to say: pass text, --file or pipe into stdin")

    repo = repo_name()
    who = speaker(lang, cfg, args.who, repo)
    tag = caption_tag(cfg, args.tag, repo)
    spoken = speakable(raw, lang)
    head = ""
    if not args.no_opener:
        head = opener(lang, who, args.source, args.greeting or cfg.get("VOICE_GREETING"),
                      cfg.get("VOICE_USER_NAME"))
        spoken = head + "\n\n" + drop_leading_intro(spoken)

    try:
        speed = float(args.speed or cfg.get("TTS_SPEED") or 1.0)
    except ValueError:
        p.error("--speed must be a number")
    speed = min(2.0, max(0.5, speed))
    resolved = nl.resolve_channels(cfg, args.to, warn=not (args.dry_run or args.plan))
    hub_wanted = "hub" in resolved and not args.no_hub
    channels = [c for c in resolved if c in nl.EXTERNAL]      # opt-in external channels
    # The hub keeps the natural-rate recording and its player speeds it up cleanly; the
    # channels without a speed control get a copy at TTS_SPEED.
    synth_speed = 1.0 if (hub_wanted and not args.speed) else speed
    tempo = speed / synth_speed

    if args.plan or args.dry_run:
        sys.stderr.write("PLAN engine=%s voice=%s lang=%s speed=%s (synth %s) channels=%s "
                         "open=%s chars=%d\n" % (
                             engine, voice or "(default)", lang_code, speed, synth_speed,
                             ",".join((["hub"] if hub_wanted else []) + channels) or "-",
                             open_mode(cfg, args.open_mode) if hub_wanted else "-",
                             len(spoken)))
        sys.stderr.write("caption: %s\n--- spoken ---\n%s\n" % (
            caption_md(args.source, args.title, tag), spoken))
        if args.plan or engine == "none":
            return 0

    sending = not (args.no_send or args.dry_run)
    if sending and not channels and not hub_wanted:
        sys.stderr.write("voice-note: no channel (NOTIFY_CHANNELS=%s, VOICE_HUB=%s in %s); "
                         "nothing sent. The default is the local hub: NOTIFY_CHANNELS=hub\n"
                         % (args.to or cfg.get("NOTIFY_CHANNELS") or "hub",
                            cfg.get("VOICE_HUB") or "on", nl.config_file()))
        return 1

    pre_failures = []
    if sending and hub_wanted:
        status = nl.hub_status(cfg)
        if not status.get("running"):
            # Never a silent fallback: the external channels are used only when the user
            # listed them, and then the missing hub still makes the result partial.
            hub_wanted = False
            pre_failures.append("hub: %s" % status.get("error", "not running"))
            if not channels:
                sys.stderr.write("voice-note: %s\n" % status.get("error", "hub not running"))
                nl.append_log(nl.voice_log(), "failed | hub down | source=%s" % args.source)
                return 1

    if engine == "none":
        if args.no_send:
            sys.stderr.write("voice-note: engine none, no audio to write\n")
            return 1
        if not channels:
            sys.stderr.write("voice-note: no speech engine (TTS_ENGINE=none, or no `say` and "
                             "no Google key), and the hub stores audio only. Install ffmpeg "
                             "(brew install ffmpeg) or run: kit/bundles/voice/scripts/"
                             "tts-set-api-key.sh\n")
            return 1
        delivered, failures = text_fallback(cfg, channels, args.source, args.title, raw, lang)
        return finish(cfg, delivered, pre_failures + failures + (
            ["hub: no audio to store (engine none)"] if hub_wanted else []),
            "text", engine, args, tag, len(spoken), None, {})

    try:
        clips, seconds, mode = synthesize(engine, spoken, voice, lang_code, synth_speed, cfg,
                                          args.max_bytes)
    except RuntimeError as exc:
        reason = nl.scrub(exc, cfg)
        if args.no_send or args.dry_run:
            sys.stderr.write("voice-note: synthesis failed: %s\n" % reason)
            return 1
        if channels:
            sys.stderr.write("voice-note: synthesis failed (%s); sending the text instead\n"
                             % reason)
        nl.append_log(nl.voice_log(), "fallback text | %s" % reason[:200])
        delivered, failures = text_fallback(cfg, channels, args.source, args.title, raw, lang)
        return finish(cfg, delivered, pre_failures + failures + ["audio: %s" % reason],
                      "text-fallback", engine, args, tag, len(spoken), None, {})

    native = clips[0]
    if args.out:
        write_private(os.path.expanduser(args.out), native)
    if args.dry_run:
        path = os.path.expanduser(args.out) if args.out else dry_run_path()
        if not args.out:
            write_private(path, native)
        sys.stderr.write("DRY-RUN wrote %d bytes of Ogg/Opus (%s, %s s) to %s; nothing sent\n"
                         % (len(native), mode, seconds if seconds else "?", path))
        print(path)
        return 0
    if args.no_send:
        sys.stderr.write("voice-note: %d bytes of Ogg/Opus in %d clip(s), not sent\n"
                         % (sum(len(c) for c in clips), len(clips)))
        return 0

    if abs(tempo - 1.0) > 0.01 and have_opus():
        try:
            clips = [encode_opus(c, ".ogg", tempo=tempo) for c in clips]
            seconds = int(seconds / tempo) if seconds else seconds
        except RuntimeError as exc:
            sys.stderr.write("voice-note: speed-up failed (%s); sending at 1x\n" % exc)

    hub = {}
    if hub_wanted:
        hub = hub_register(cfg, native, {
            "title": args.title, "source": args.source, "tag": tag, "lang": lang,
            "speaker": who if not args.no_opener else "", "voice": voice,
            "speech_rate": synth_speed, "text": raw, "spoken": spoken,
            "summary": args.summary or "", "links": args.link, "brief": args.brief or "",
            "commands": [{"code": c, "label": "", "explanation": ""} for c in args.commands]})

    delivered, failures, record = [], list(pre_failures), {}
    for channel in channels:
        try:
            if channel == "telegram":
                deliver_telegram(cfg, clips, seconds, args.source, args.title, tag)
                record["telegram"] = {"status": "ok"}
            else:
                kind = deliver_chat(cfg, clips, spoken, args.source, args.title, tag, hub,
                                    seconds, lang)
                record["chat"] = {"status": "ok", "kind": kind}
            delivered.append(channel)
        except (nl.NotifyError, RuntimeError) as exc:
            failures.append("%s: %s" % (channel, nl.scrub(exc, cfg)))
            record[channel] = {"status": "failed", "error": nl.scrub(exc, cfg)[:200]}
    if hub.get("id"):
        delivered.insert(0, "hub")
        played = hub_play(cfg, hub, open_mode(cfg, args.open_mode))
        record["hub"] = {"status": "ok", "played": played}
        hub_record(cfg, hub, record)
        sys.stderr.write("voice-note: %s\n" % {
            "tab": "playing in the open hub tab",
            "browser": "opened the player in the browser",
            "link": "stored in the hub; open the link below to listen"}[played])
        print("🎧 Voice hub: %s" % hub["local"])
        if hub.get("public"):
            print("📱 Phone: %s" % hub["public"])
        label = "Listen" if lang == "en" else "Escuchar"
        print("Markdown: [🎧 %s: %s](%s)" % (label, (args.title or TEXT[lang]["summary"])
                                             .replace("]", ")"), hub["local"]))
    elif hub_wanted:
        failures.append("hub: not stored (see the error above)")
    return finish(cfg, delivered, failures, "audio", engine, args, tag, len(spoken), seconds,
                  {"mode": mode})


def finish(cfg, delivered, failures, kind, engine, args, tag, chars, seconds, extra):
    for problem in failures:
        sys.stderr.write("voice-note: %s\n" % problem)
    if not delivered:
        nl.append_log(nl.voice_log(), "failed | kind=%s source=%s %s" % (
            kind, args.source, "; ".join(failures)[:300]))
        sys.stderr.write("voice-note: FAILED, nothing was delivered (log %s)\n" % nl.voice_log())
        return 1
    nl.append_log(nl.voice_log(), "sent note | kind=%s to=%s engine=%s source=%s tag=%s chars=%d "
                  "dur=%ss%s%s" % (kind, ",".join(delivered), engine, args.source, tag, chars,
                                   seconds if seconds else "?",
                                   (" mode=%s" % extra["mode"]) if extra.get("mode") else "",
                                   (" failed=" + ";".join(failures)[:300]) if failures else ""))
    sys.stderr.write("voice-note: delivered (%s) to %s\n" % (kind, "+".join(delivered)))
    if failures or kind == "text-fallback":
        sys.stderr.write("voice-note: PARTIAL (exit 3): the summary reached %s, so do NOT send "
                         "it again; fix the failed part instead.\n" % "+".join(delivered))
        return 3
    return 0


# -------------------------------------------------------------------------- self-test
def self_test():
    """Offline checks: no network, no config, no audio engine needed."""
    results = {"pass": 0, "fail": 0}

    def ok(name, cond):
        if cond:
            results["pass"] += 1
        else:
            results["fail"] += 1
            sys.stderr.write("FAIL %s\n" % name)

    s = speakable("## Title\n\n- **done** the `terraform plan`\n\n```bash\nterraform apply\n```\n")
    ok("headings lose their hashes", "#" not in s)
    ok("bold loses its asterisks", "*" not in s)
    ok("inline code survives as words", "terraform plan" in s)
    ok("a fenced command is never read aloud", "terraform apply" not in s)
    ok("a fenced command points at the chat", "The command is in the chat." in s)
    ok("spanish points at the chat in spanish", "en el chat" in speakable("```x```", "es"))
    s = speakable("See [the dashboard](https://example.com/d) and https://example.com/x now")
    ok("link text survives", "the dashboard" in s)
    ok("urls are not spoken", "example.com" not in s and "a link" in s)
    ok("emoji are dropped", "\U0001F680" not in speakable("Done \U0001F680 here"))
    ok("lines get end punctuation", speakable("one line\nanother line").count(".") >= 2)

    long_text = ("Sentence number one with enough words in it. " * 400).strip()
    parts = chunk(long_text)
    ok("long text is split", len(parts) > 1)
    ok("every chunk fits", all(len(c.encode("utf-8")) <= MAX_CHUNK_BYTES for c in parts))
    ok("nothing is dropped", sum(len(c.split()) for c in parts) == len(long_text.split()))
    ok("short text is one chunk", len(chunk("Hello.")) == 1)
    ok("empty text is no chunk", chunk("") == [])
    blob = "a" * (MAX_CHUNK_BYTES * 2)
    ok("an unbreakable blob still splits",
       all(len(c.encode("utf-8")) <= MAX_CHUNK_BYTES for c in chunk(blob + " " + blob)))
    ok("multibyte text is measured in bytes",
       all(len(c.encode("utf-8")) <= MAX_CHUNK_BYTES for c in chunk("ñáé" * 3000)))

    o = opener("en", "the payments agent", "TERRAFORM", name="Ana")
    ok("english opener", o == "Hi, Ana. This is the payments agent, about Terraform.")
    o = opener("es", "el agente de pagos", "JIRA")
    ok("spanish opener", o == "Hola. Soy el agente de pagos, sobre el ticket.")
    ok("AGENT names no subject", opener("en", "x", "AGENT") == "Hi. This is x.")
    ok("a custom greeting wins", opener("en", "x", "", greeting="Morning").startswith("Morning."))
    ok("a caller's own hello is not said twice",
       drop_leading_intro("Hi Ana, this is the api agent. The deploy is done.")
       == "The deploy is done.")
    ok("a spanish intro is dropped",
       drop_leading_intro("Hola Ana. Soy el agente de pagos. Listo.") == "Listo.")
    ok("ordinary prose is untouched",
       drop_leading_intro("The apply finished at three.") == "The apply finished at three.")
    ok("this is without agent survives",
       drop_leading_intro("This is fine. More.").startswith("This is fine"))

    cfg = dict(nl.DEFAULTS, VOICE_SPEAKERS_FILE="/nonexistent/speakers.json")
    ok("unmapped repos introduce themselves", speaker("en", cfg, repo="billing-api")
       == "the billing api agent")
    ok("spanish default speaker", speaker("es", cfg, repo="pagos") == "el agente de pagos")
    ok("--who wins", speaker("en", cfg, who=" the release bot. ", repo="x") == "the release bot")
    tmpdir = tempfile.mkdtemp(prefix="voice-selftest-")
    try:
        spk = os.path.join(tmpdir, "speakers.json")
        with open(spk, "w", encoding="utf-8") as fh:
            json.dump({"svc-a": {"en": "the checkout agent", "es": "el agente de pagos",
                                 "tag": "checkout"}, "svc-b": "the B team agent"}, fh)
        cfg2 = dict(cfg, VOICE_SPEAKERS_FILE=spk)
        ok("speakers file, per language", speaker("es", cfg2, repo="svc-a") == "el agente de pagos")
        ok("speakers file, plain string", speaker("en", cfg2, repo="svc-b") == "the B team agent")
        ok("speakers file tag", caption_tag(cfg2, None, "svc-a") == "checkout")
        env_path = os.path.join(tmpdir, "notify.env")
        with open(env_path, "w", encoding="utf-8") as fh:
            fh.write("NOTIFY_CHANNELS=chat  # inline comment\nGCHAT_WEBHOOK_URL='https://chat."
                     "example.com/v1/x?key=a&token=b'\nTTS_ENGINE=none\nTTS_LANG=es\n")
        os.chmod(env_path, 0o600)
        saved = {k: os.environ.pop(k, None) for k in nl.DEFAULTS}
        try:
            c = nl.load_config(env_path, warn=False)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        ok("inline comments are dropped", c["NOTIFY_CHANNELS"] == "chat")
        ok("a quoted url with & survives", c["GCHAT_WEBHOOK_URL"].endswith("&token=b"))
        ok("chat is ready with a webhook", nl.resolve_channels(c, warn=False) == ["chat"])
        ok("spanish config", c["TTS_LANG"] == "es")
        ok("secrets are scrubbed", "token=b" not in nl.scrub("x " + c["GCHAT_WEBHOOK_URL"], c))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    base = dict(nl.DEFAULTS)
    ok("the default channel is the hub", nl.resolve_channels(base, warn=False) == ["hub"])
    tg = dict(base, TELEGRAM_BOT_TOKEN="123:fake", TELEGRAM_CHAT_ID="42")
    ok("credentials alone never turn telegram on", nl.resolve_channels(tg, warn=False) == ["hub"])
    ok("auto means the hub only",
       nl.resolve_channels(dict(tg, NOTIFY_CHANNELS="auto"), warn=False) == ["hub"])
    ok("telegram is an explicit opt-in",
       nl.resolve_channels(dict(tg, NOTIFY_CHANNELS="hub,telegram"), warn=False)
       == ["hub", "telegram"])
    ok("--to opts in for one call", nl.resolve_channels(tg, "telegram", warn=False) == ["telegram"])
    ok("VOICE_HUB=off removes the hub",
       nl.resolve_channels(dict(tg, VOICE_HUB="off", NOTIFY_CHANNELS="hub,telegram"), warn=False)
       == ["telegram"])
    ok("none means none", nl.resolve_channels(dict(tg, NOTIFY_CHANNELS="none"), warn=False) == [])
    ok("an unconfigured channel is skipped",
       nl.resolve_channels(dict(tg, NOTIFY_CHANNELS="chat,telegram"), warn=False) == ["telegram"])
    ok("open mode defaults to auto", open_mode(base) == "auto")
    ok("an unknown open mode is auto", open_mode(dict(base, VOICE_HUB_OPEN="sometimes")) == "auto")
    ok("a custom opener is split, not shelled",
       browser_opener(dict(base, VOICE_HUB_OPENER="my-open --new-tab")) == ["my-open", "--new-tab"])
    ok("the bot token is scrubbed", "123:fake" not in nl.scrub("url bot123:fake/x", tg))
    ok("engine auto without credentials is not google", resolve_engine(base) in ("say", "none"))
    ok("engine auto with a key is google", resolve_engine(dict(base, TTS_API_KEY="k")) == "google")
    ok("google voice per language", resolve_voice("google", "es", base)[0] == GOOGLE_VOICE["es"])
    ok("an explicit voice sets its locale",
       resolve_voice("google", "en", base, "en-GB-Chirp3-HD-Kore")[1] == "en-GB")

    cap = caption_html("terraform", "<b>x", "api", 2, 3)
    ok("caption escapes html", "&lt;b&gt;x" in cap and "(2/3)" in cap)
    ok("caption carries the icon", nl.icon_for("TERRAFORM") in cap)
    ok("chat caption is markdown", caption_md("deploy", "T", "api").startswith("🚀 **DEPLOY**"))
    body, ctype = nl.multipart({"chat_id": "1"}, {"voice": ("a.ogg", b"\x00", "audio/ogg")})
    ok("multipart declares its boundary", ctype.startswith("multipart/form-data; boundary="))
    ok("multipart carries the file", b'filename="a.ogg"' in body)
    ok("html is sanitized", nl.sanitize_html("<b>open & <script>") == "<b>open &amp; &lt;script&gt;</b>")
    ok("webhook markup is classic", nl.markdown_to_classic("**b** *i* `*x*`") == "*b* _i_ `*x*`")
    card = webhook_card("t", "http://127.0.0.1:7473/n/x", "T", "AGENT", "s", "", "en")
    ok("the card links the player",
       card["cardsV2"][0]["card"]["sections"][0]["widgets"][0]["buttonList"]["buttons"][0]
       ["onClick"]["openLink"]["url"].endswith("/n/x"))

    pcm = b"".join(bytes([i % 256, (i * 7) % 256]) for i in range(2400))
    back, rate, width = pcm_from_wav(wav_from_pcm(pcm, 24000, 2))
    ok("wav round-trips", back == pcm and rate == 24000 and width == 2)
    if have_opus():
        ogg = encode_opus(wav_from_pcm(pcm * 40, 24000, 2))
        ok("opus encode yields Ogg", ogg[:4] == b"OggS")
        ok("the speed-up keeps Ogg", encode_opus(ogg, ".ogg", tempo=1.5)[:4] == b"OggS")
    print("voice-note self-test: %d PASS, %d FAIL" % (results["pass"], results["fail"]))
    return 0 if results["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
