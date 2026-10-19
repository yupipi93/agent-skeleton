#!/usr/bin/env python3
"""notifylib: configuration, channels and text notifications for the voice bundle.

Channels: `hub` (the local voice hub in tools/voice-hub, the default), and two external
ones that stay off until the user lists them: `telegram` and `chat` (Google Chat).

One module, three users, so the config is parsed one way and every channel is sent one way:

  * kit/bundles/voice/scripts/voice-note.py imports it (spoken summaries);
  * kit/bundles/voice/scripts/voice-note-hook.py imports it (the Stop hook);
  * kit/bundles/voice/scripts/notify.sh runs `python3 notifylib.py notify ...` (text).

Config: ~/.config/agent-skeleton/notify.env (KEY=VALUE, mode 0600, read with the core
envfile parser, never sourced). Every key can be overridden by an environment variable
of the same name; NOTIFY_CONFIG points at another file (tests use it).

Secrets (the Telegram bot token, the Chat webhook URL, the TTS API key) never reach a
command line or a log: HTTP happens in this process with urllib, and every error message
is scrubbed of them before it is printed.

Python 3.9+, standard library only.
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))           # kit/bundles/voice/scripts/lib
SCRIPTS = os.path.dirname(HERE)                               # kit/bundles/voice/scripts
KIT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(SCRIPTS))))
CORE_LIB = os.path.join(KIT_ROOT, "kit", "bundles", "core", "scripts", "lib")

sys.path.insert(0, CORE_LIB)
try:
    import envfile  # noqa: E402
except ImportError:                                           # pragma: no cover
    envfile = None

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, ".config", "agent-skeleton")
STATE_DIR = os.environ.get("AGENT_SKELETON_STATE") or os.path.join(
    HOME, ".local", "state", "agent-skeleton")


def config_file():
    return os.path.expanduser(os.environ.get("NOTIFY_CONFIG")
                              or os.path.join(CONFIG_DIR, "notify.env"))


def voice_log():
    return os.path.expanduser(os.environ.get("VOICE_LOG") or os.path.join(STATE_DIR, "voice.log"))


def notify_log():
    return os.path.expanduser(os.environ.get("NOTIFY_LOG")
                              or os.path.join(STATE_DIR, "notify.log"))


GCHAT_PY = os.environ.get("GCHAT_PY") or os.path.join(
    KIT_ROOT, "kit", "bundles", "google", "scripts", "gchat.py")
HUB_CLI_DEFAULT = os.path.join(KIT_ROOT, "tools", "voice-hub", "bin", "avh")

DEFAULTS = {
    # Channels: a comma list of hub, telegram and chat, or none. The default is the local
    # voice hub only; `auto` means the same. Telegram and Google Chat are used only when
    # listed here (or with --to), and only once their credentials are filled in.
    "NOTIFY_CHANNELS": "hub",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    # Google Chat: an incoming webhook posts text and cards (no OAuth); a space plus the
    # google bundle's gchat.py login also uploads the audio.
    "GCHAT_WEBHOOK_URL": "",
    "GCHAT_SPACE": "",
    "GCHAT_PING_USER": "",
    # Text to speech: auto picks google when a key or a gcloud account is set, else the
    # macOS `say` voice, else none (the summary goes out as text).
    "TTS_ENGINE": "auto",
    "TTS_API_KEY": "",
    "TTS_GCLOUD_ACCOUNT": "",
    "TTS_QUOTA_PROJECT": "",
    "TTS_LANG": "",
    "TTS_VOICE": "",
    "TTS_SPEED": "1.0",
    "VOICE_GREETING": "",
    "VOICE_USER_NAME": "",
    "VOICE_SPEAKERS_FILE": os.path.join(CONFIG_DIR, "speakers.json"),
    # The hub channel's kill switch (off removes `hub` from every list), its CLI, and what
    # happens after a note is stored: auto plays it in an open hub tab, else opens the
    # player in the browser; always opens the browser; never only prints the link.
    "VOICE_HUB": "on",
    "VOICE_HUB_CLI": "",
    "VOICE_HUB_OPEN": "auto",
    "VOICE_HUB_OPENER": "",
    "NOTIFY_TZ": "",
    # Stop hook thresholds and the phrase that skips it for one turn.
    "VOICE_HOOK_LONG_SECONDS": "240",
    "VOICE_HOOK_TOOL_CALLS": "15",
    "VOICE_HOOK_REPLY_CHARS": "1200",
    "VOICE_HOOK_OPTOUT": "no audio",
}
SECRET_KEYS = ("TELEGRAM_BOT_TOKEN", "GCHAT_WEBHOOK_URL", "TTS_API_KEY")
CHANNELS = ("hub", "telegram", "chat")
EXTERNAL = ("telegram", "chat")
HTTP_TIMEOUT = 30
TELEGRAM_TIMEOUT = 20


class NotifyError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- config
def _parse_env(path):
    if envfile is not None:
        return envfile.load(path)
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$", line)
                if m and not line.lstrip().startswith("#"):
                    v = m.group(2).strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    elif " #" in v:
                        v = v.split(" #", 1)[0].rstrip()
                    out[m.group(1)] = v
    except OSError:
        pass
    return out


def skeleton_root():
    """The checkout whose skeleton.toml / skeleton.local.toml give [user]: this kit, or
    AGENT_SKELETON_ROOT when set (tests point it at an empty temp dir)."""
    return os.path.expanduser(os.environ.get("AGENT_SKELETON_ROOT") or KIT_ROOT)


def _skeleton_user():
    """[user] name and language from skeleton.local.toml / skeleton.toml, when readable."""
    try:
        import tomllib                                        # Python 3.11+
    except ImportError:
        return {}
    out = {}
    root = skeleton_root()
    for name in ("skeleton.toml", "skeleton.local.toml"):
        try:
            with open(os.path.join(root, name), "rb") as fh:
                user = tomllib.load(fh).get("user") or {}
        except (OSError, ValueError):
            continue
        for key in ("name", "language"):
            if isinstance(user.get(key), str) and user[key].strip():
                out[key] = user[key].strip()
    return out


_WARNED = set()


def warn_mode(path):
    """One stderr line when a config file is readable by group or others."""
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        return
    if mode & 0o077 and path not in _WARNED:
        _WARNED.add(path)
        sys.stderr.write("notify: %s is mode %s; it holds secrets, run: chmod 600 %s\n"
                         % (path, oct(mode), path))


def load_config(path=None, warn=True):
    """DEFAULTS < skeleton [user] < the config file < environment variables."""
    path = path or config_file()
    cfg = dict(DEFAULTS)
    user = _skeleton_user()
    if user.get("name"):
        cfg["VOICE_USER_NAME"] = user["name"]
    if user.get("language"):
        cfg["TTS_LANG"] = user["language"]
    data = _parse_env(path)
    for key, value in data.items():
        cfg[key] = value
    for key in DEFAULTS:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    if warn and data:
        warn_mode(path)
    lang = (cfg.get("TTS_LANG") or "en").strip().lower()[:2]
    cfg["TTS_LANG"] = lang if lang in ("en", "es") else "en"
    return cfg


def is_on(value):
    return str(value or "").strip().lower() in ("1", "on", "yes", "true")


def telegram_ready(cfg):
    return bool(cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID"))


def chat_ready(cfg):
    return bool(cfg.get("GCHAT_WEBHOOK_URL") or cfg.get("GCHAT_SPACE"))


def resolve_channels(cfg, override=None, warn=True, ready_only=True):
    """The channels to use, in a stable order.

    `hub` (default, also what `auto` means) is the local voice hub; VOICE_HUB=off removes
    it. `telegram` and `chat` are opt-in: used only when listed, and with ready_only only
    once their credentials are set. `all` lists the hub plus every configured external
    channel, an explicit opt-in. `none` is nothing."""
    raw = (override or cfg.get("NOTIFY_CHANNELS") or "hub").strip().lower()
    if raw == "none":
        return []
    ready = {"hub": is_on(cfg.get("VOICE_HUB", "on")), "telegram": telegram_ready(cfg),
             "chat": chat_ready(cfg)}
    if raw == "auto":
        raw = "hub"
    if raw in ("all", "both"):
        return [c for c in CHANNELS if ready[c]]
    wanted = [c.strip() for c in raw.replace("+", ",").split(",") if c.strip()]
    out = []
    for name in wanted:
        if name == "auto":
            name = "hub"
        if name not in CHANNELS:
            if warn:
                sys.stderr.write("notify: unknown channel %r ignored (hub, telegram, chat, "
                                 "none)\n" % name)
            continue
        if name == "hub" and not ready["hub"]:
            continue                 # VOICE_HUB=off: the user turned the hub off on purpose
        if ready_only and not ready[name]:
            if warn:
                sys.stderr.write("notify: channel %s is not configured in %s, skipped\n"
                                 % (name, config_file()))
            continue
        if name not in out:
            out.append(name)
    return out


def hub_cli(cfg):
    return os.path.expanduser(cfg.get("VOICE_HUB_CLI") or HUB_CLI_DEFAULT)


def hub_on(cfg):
    return is_on(cfg.get("VOICE_HUB")) and os.path.exists(hub_cli(cfg))


def hub_command(cfg):
    """The hub CLI as the user would type it: repo-relative for the bundled one."""
    path = hub_cli(cfg)
    if os.path.realpath(path) == os.path.realpath(HUB_CLI_DEFAULT):
        return "tools/voice-hub/bin/avh"
    return path


def hub_start_hint(cfg):
    """The one command that starts the hub server on this platform."""
    if sys.platform == "darwin":
        return hub_command(cfg) + " service install"
    return hub_command(cfg) + " serve"


def hub_status(cfg, timeout=15):
    """{"running": bool, "url", "players", "error"} from `avh ping --json`; never raises."""
    if not os.path.exists(hub_cli(cfg)):
        return {"running": False, "url": "", "players": 0,
                "error": "the voice hub was not found at %s (set VOICE_HUB_CLI)" % hub_cli(cfg)}
    try:
        proc = subprocess.run([sys.executable, hub_cli(cfg), "ping", "--json"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        out = json.loads(proc.stdout.decode("utf-8") or "{}")
    except Exception as exc:                                  # noqa: BLE001
        return {"running": False, "url": "", "players": 0,
                "error": "the voice hub CLI failed: %s" % str(exc)[:200]}
    out.setdefault("players", 0)
    if not out.get("running"):
        out["error"] = "the voice hub is not running (%s); start it with: %s" % (
            out.get("url") or "http://127.0.0.1:7473", hub_start_hint(cfg))
    return out


def configured(cfg):
    """True once the bundle is set up (notify.env exists) and a note has somewhere to go.

    A fresh install has no notify.env, so the Stop hook stays inert until
    `bin/skeleton setup voice` writes one, even though the hub is the default channel."""
    return os.path.exists(config_file()) and bool(resolve_channels(cfg, warn=False))


def scrub(text, cfg):
    """Remove every secret value from a message before it is shown or logged."""
    text = str(text)
    for key in SECRET_KEYS:
        value = cfg.get(key) or ""
        if len(value) >= 6:
            text = text.replace(value, "***")
    token = cfg.get("TELEGRAM_BOT_TOKEN") or ""
    if token:
        text = text.replace(urllib.parse.quote(token, safe=""), "***")
    return re.sub(r"(key|token)=[A-Za-z0-9_%.-]{8,}", r"\1=***", text)


# ------------------------------------------------------------------------------- logs
def append_log(path, line):
    """Append one timestamped line; the file is created 0600 in a 0700 directory."""
    try:
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory, mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except OSError:
        pass


# ------------------------------------------------------------------------------- http
def _request(url, data=None, headers=None, timeout=HTTP_TIMEOUT, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body.decode("utf-8")) if body.strip() else {}


def multipart(fields, files):
    """multipart/form-data body. fields: {name: str}; files: {name: (filename, bytes, ctype)}."""
    boundary = "----agentskeleton%d" % int(time.time() * 1000)
    body = b""
    for name, value in fields.items():
        if value is None:
            continue
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, name, value)).encode("utf-8")
    for name, (filename, content, ctype) in files.items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                 "Content-Type: %s\r\n\r\n" % (boundary, name, filename, ctype)).encode("utf-8")
        body += content + b"\r\n"
    body += ("--%s--\r\n" % boundary).encode("utf-8")
    return body, "multipart/form-data; boundary=%s" % boundary


def telegram_call(cfg, method, fields, files=None, timeout=TELEGRAM_TIMEOUT):
    """POST to the Bot API. The token lives in the URL, inside this process only."""
    # TELEGRAM_API_BASE (environment only) lets tests point at a local fake server.
    base = os.environ.get("TELEGRAM_API_BASE") or "https://api.telegram.org"
    url = "%s/bot%s/%s" % (base.rstrip("/"), cfg["TELEGRAM_BOT_TOKEN"], method)
    fields = dict(fields)
    fields["chat_id"] = cfg["TELEGRAM_CHAT_ID"]
    if files:
        data, ctype = multipart(fields, files)
    else:
        data = urllib.parse.urlencode(fields).encode("utf-8")
        ctype = "application/x-www-form-urlencoded"
    try:
        out = _request(url, data=data, headers={"Content-Type": ctype}, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise NotifyError(scrub("Telegram %s: %s" % (exc.code, detail), cfg))
    except Exception as exc:                                  # noqa: BLE001
        raise NotifyError(scrub("Telegram unreachable: %s" % exc, cfg))
    if not out.get("ok"):
        # 200 with {"ok": false} happens: the status code alone is not proof of delivery.
        raise NotifyError(scrub("Telegram refused: %s" % out.get("description"), cfg))
    return out


def chat_webhook_post(cfg, payload, timeout=HTTP_TIMEOUT):
    """Post through the space's incoming webhook (the URL is the credential)."""
    url = (cfg.get("GCHAT_WEBHOOK_URL") or "").replace("\\", "")   # shell paste damage
    data = json.dumps(payload).encode("utf-8")
    try:
        return _request(url, data=data, method="POST", timeout=timeout,
                        headers={"Content-Type": "application/json; charset=UTF-8"})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise NotifyError(scrub("Chat webhook %s: %s" % (exc.code, detail), cfg))
    except Exception as exc:                                  # noqa: BLE001
        raise NotifyError(scrub("Chat webhook unreachable: %s" % exc, cfg))


def chat_token():
    """A user bearer token from the google bundle's gchat.py (its own refresh token)."""
    if not os.path.exists(GCHAT_PY):
        raise NotifyError("gchat.py not found at %s" % GCHAT_PY)
    try:
        out = subprocess.run([sys.executable, GCHAT_PY, "token"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=60)
    except Exception as exc:                                  # noqa: BLE001
        raise NotifyError("no Chat token: %s" % exc)
    token = out.stdout.decode().strip()
    if out.returncode != 0 or not token:
        detail = out.stderr.decode("utf-8", "replace").strip().splitlines()
        raise NotifyError("no Chat token (run: kit/bundles/google/scripts/gchat.py login): %s"
                          % (detail[-1][:200] if detail else "empty token"))
    return token


def _chat_api(url, data, token, ctype, timeout=120):
    try:
        return _request(url, data=data, method="POST", timeout=timeout,
                        headers={"Authorization": "Bearer " + token, "Content-Type": ctype})
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        try:
            msg = json.loads(payload)["error"]["message"]
        except Exception:                                     # noqa: BLE001
            msg = payload[:300]
        raise NotifyError("Chat API %s: %s" % (exc.code, msg))
    except Exception as exc:                                  # noqa: BLE001
        raise NotifyError("Chat API unreachable: %s" % exc)


CHAT_MESSAGES = "https://chat.googleapis.com/v1/%s/messages"
CHAT_UPLOAD = "https://chat.googleapis.com/upload/v1/%s/attachments:upload?uploadType=multipart"


def chat_user_post(space, text, token):
    """A message as the user. markupSyntax MARKDOWN: without it, markup is never parsed."""
    body = json.dumps({"text": text, "markupSyntax": "MARKUP_SYNTAX_MARKDOWN"}).encode("utf-8")
    return _chat_api(CHAT_MESSAGES % space, body, token, "application/json").get("name", "")


def chat_upload(space, filename, content, ctype, token):
    """Upload a file and post it alone (no text: the player renders best that way)."""
    boundary = "----agentskeletonchat%d" % int(time.time() * 1000)
    meta = json.dumps({"filename": filename})
    body = ("--%s\r\nContent-Disposition: form-data; name=\"metadata\"\r\n"
            "Content-Type: application/json\r\n\r\n%s\r\n" % (boundary, meta)).encode("utf-8")
    body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
             "Content-Type: %s\r\n\r\n" % (boundary, filename, ctype)).encode("utf-8")
    body += content + b"\r\n" + ("--%s--\r\n" % boundary).encode("utf-8")
    up = _chat_api(CHAT_UPLOAD % space, body, token, "multipart/form-data; boundary=" + boundary)
    ref = (up.get("attachmentDataRef") or {}).get("attachmentUploadToken")
    if not ref:
        raise NotifyError("Chat upload returned no attachmentUploadToken")
    message = {"attachment": [{"contentName": filename, "contentType": ctype,
                               "attachmentDataRef": {"attachmentUploadToken": ref}}]}
    return _chat_api(CHAT_MESSAGES % space, json.dumps(message).encode("utf-8"), token,
                     "application/json").get("name", "")


# -------------------------------------------------------------------------- rendering
SOURCE_ICON = {
    "TERRAFORM": "🏗️", "TF": "🏗️", "IAC": "🏗️",
    "DEPLOY": "🚀", "BUILD": "🚀", "RELEASE": "🚀",
    "GCP": "☁️", "CLOUD": "☁️", "IAM": "☁️",
    "DB": "🗄️", "SQL": "🗄️", "DATABASE": "🗄️",
    "SECURITY": "🛡️", "CVE": "🛡️",
    "BILLING": "💰", "COST": "💰",
    "DNS": "🌐", "NET": "🌐",
    "JIRA": "🎫", "TICKET": "🎫",
    "ACTION": "👷", "APPROVAL": "👷", "DECISION": "👷",
    "AGENT": "🤖", "NOTIFY": "🔔",
}
LEVEL_ICON = {"ok": "✅", "warn": "⚠️", "crit": "🚨", "info": "ℹ️"}
LOUD_LEVELS = ("warn", "crit")
INLINE_TAGS = ("b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code")
TAG_RE = re.compile(r"</?(?:" + "|".join(INLINE_TAGS) + r")>")
BODY_MAX = 3400


def icon_for(source):
    return SOURCE_ICON.get((source or "").upper(), "📋")


def html_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def sanitize_html(text):
    """Keep balanced inline tags, escape everything else (Telegram rejects bad HTML)."""
    out, stack, pos = [], [], 0
    for m in TAG_RE.finditer(text):
        out.append(html_escape(text[pos:m.start()]))
        tok = m.group(0)
        name = tok.strip("</>")
        if tok.startswith("</"):
            if stack and stack[-1] == name:
                stack.pop()
                out.append(tok)
            else:
                out.append(html_escape(tok))
        else:
            stack.append(name)
            out.append(tok)
        pos = m.end()
    out.append(html_escape(text[pos:]))
    out.extend("</%s>" % n for n in reversed(stack))
    return "".join(out)


def truncate_lines(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    nl = cut.rfind("\n")
    return (cut[:nl] if nl > 0 else cut) + "\n... (truncated)"


def html_to_markdown(text):
    """Caller inline HTML to Chat Markdown (user-token messages)."""
    marks = {"b": "**", "strong": "**", "i": "*", "em": "*", "u": "*", "ins": "*",
             "s": "~~", "strike": "~~", "del": "~~", "code": "`"}
    return TAG_RE.sub(lambda m: marks[m.group(0).strip("</>")], text)


def markdown_to_classic(text):
    """Chat Markdown to the classic markup incoming webhooks parse (*bold*, _it_, ~s~)."""
    def classic(t):
        t = re.sub(r"\*\*(.+?)\*\*", "\x00\\1\x00", t, flags=re.S)
        t = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"_\1_", t)
        t = re.sub(r"~~(.+?)~~", r"~\1~", t)
        return t.replace("\x00", "*")
    # Code spans and blocks are left alone: `rm *.log` must survive intact.
    parts = re.split(r"(```.*?```|`[^`\n]*`)", text, flags=re.S)
    return "".join(p if i % 2 else classic(p) for i, p in enumerate(parts))


def footer_stamp(cfg):
    tz = cfg.get("NOTIFY_TZ") or ""
    saved = os.environ.get("TZ")
    try:
        if tz:
            os.environ["TZ"] = tz
            if hasattr(time, "tzset"):
                time.tzset()
        return time.strftime("%d %b %H:%M")
    finally:
        if tz:
            if saved is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = saved
            if hasattr(time, "tzset"):
                time.tzset()


def render_telegram(level, source, title, body, code, cfg):
    e_body = sanitize_html(truncate_lines(body, BODY_MAX))
    quote = "<blockquote expandable>" if (len(e_body) > 300 or e_body.count("\n") > 5) \
        else "<blockquote>"
    text = "%s %s <b>%s</b> · %s\n%s%s</blockquote>" % (
        LEVEL_ICON.get(level, "ℹ️"), icon_for(source), html_escape(source.upper()),
        sanitize_html(title), quote, e_body)
    if code:
        text += '\n<pre><code class="language-bash">%s</code></pre>' % html_escape(code)
    text += "\n<i>%s · %s · %s</i>" % (html_escape(socket.gethostname()),
                                        html_escape(source), footer_stamp(cfg))
    return text


def render_chat(level, source, title, body, code, cfg):
    """Chat Markdown (the user-token flavour); the webhook path maps it to classic."""
    text = "%s %s **%s** · %s\n\n%s" % (
        LEVEL_ICON.get(level, "ℹ️"), icon_for(source), source.upper(),
        html_to_markdown(title), html_to_markdown(truncate_lines(body, BODY_MAX)))
    if code:
        text += "\n\n```bash\n%s\n```" % code
    text += "\n\n_%s · %s · %s_" % (socket.gethostname(), source, footer_stamp(cfg))
    return text


def render_local(level, source, title, body, code):
    """The plain-text copy printed on this machine (the hub channel's text half)."""
    text = "%s %s %s · %s" % (LEVEL_ICON.get(level, "ℹ️"), icon_for(source), source.upper(),
                              TAG_RE.sub("", title))
    if body:
        text += "\n" + TAG_RE.sub("", truncate_lines(body, BODY_MAX))
    if code:
        text += "\n$ " + code
    return text


def print_paste_block(code):
    """A command sent to a channel also belongs in the agent's chat reply: say so."""
    sys.stderr.write("\n--- ALSO PASTE THIS IN THE CHAT REPLY (a command goes to both places) ---\n")
    sys.stderr.write("```bash\n%s\n```\n" % code)


# ---------------------------------------------------------------------------- sending
def send_text(cfg, channels, telegram_html, chat_md, loud=False, mention=False):
    """Send one message to each channel. Returns (delivered, failures)."""
    delivered, failures = [], []
    for channel in channels:
        try:
            if channel == "telegram":
                fields = {"text": telegram_html, "parse_mode": "HTML",
                          "disable_notification": "false" if loud else "true"}
                try:
                    telegram_call(cfg, "sendMessage", fields)
                except NotifyError:
                    # Never lose an alert to a formatting problem: retry unstyled.
                    plain = re.sub(r"<[^>]+>", "", telegram_html)
                    plain = plain.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                    telegram_call(cfg, "sendMessage", {"text": plain,
                                                       "disable_notification": fields[
                                                           "disable_notification"]})
            else:
                text = chat_md
                if cfg.get("GCHAT_WEBHOOK_URL"):
                    ping = cfg.get("GCHAT_PING_USER") if mention else ""
                    classic = markdown_to_classic(text)
                    chat_webhook_post(cfg, {"text": ("<%s> " % ping if ping else "") + classic})
                else:
                    chat_user_post(cfg["GCHAT_SPACE"], text, chat_token())
            delivered.append(channel)
        except NotifyError as exc:
            failures.append("%s: %s" % (channel, scrub(exc, cfg)))
    return delivered, failures


def hub_attach_command(cfg, code, label="", explanation=""):
    """Best effort: the hub shows the command first in this session's voice note."""
    if not hub_on(cfg):
        return
    try:
        subprocess.run([sys.executable, hub_cli(cfg), "command", "add", "--code", code,
                        "--label", label, "--explanation", explanation[:300]],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except Exception:                                         # noqa: BLE001
        pass


TEST_BODY = ("Formatting check: <b>bold</b>, <i>italic</i>, <s>strike</s>, <code>inline code</code>.\n"
             "If those render styled (no literal angle brackets), the channel is healthy.")


def notify_main(argv):
    p = argparse.ArgumentParser(
        prog="notify.sh",
        description="Send a text notification: printed locally with commands attached to the "
                    "voice hub (default), plus Telegram or Google Chat when opted in.")
    p.add_argument("level", nargs="?", choices=("info", "ok", "warn", "crit"))
    p.add_argument("title", nargs="?")
    p.add_argument("message", nargs="*")
    p.add_argument("--source", default="AGENT",
                   help="subsystem tag: AGENT TERRAFORM DEPLOY GCP DB SECURITY BILLING DNS JIRA ACTION")
    p.add_argument("--code", help="a command, inside this message as a copyable block")
    p.add_argument("--code-only", dest="code_only",
                   help="a command, as its own message right after this one")
    p.add_argument("--to", help="channels for this call: hub, telegram, chat, a comma list "
                                 "or none")
    p.add_argument("--dry-run", action="store_true", help="render and print, send nothing")
    p.add_argument("--test", action="store_true", help="send a formatting showcase")
    p.add_argument("--quiet", action="store_true", help="no local echo")
    p.add_argument("--client", help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    cfg = load_config()
    if args.test:
        args.level, args.title, args.message, args.source = "info", "Channel test", [TEST_BODY], "NOTIFY"
    code_only = args.code_only or ""
    if code_only and not args.level:
        level, title, body = "", "", ""
    else:
        if not (args.level and args.title):
            p.error("need <level> <title> <message>, or --code-only CMD, or --test")
        level, title, body = args.level, args.title, " ".join(args.message)
    code = args.code or ""

    channels = resolve_channels(cfg, args.to, warn=not args.dry_run)
    for cmd in (code, code_only):
        if cmd:
            print_paste_block(cmd)
    if args.dry_run:
        # Show every channel the call names, configured or not: that is what a preview is for.
        channels = resolve_channels(cfg, args.to, warn=False, ready_only=False)
    if not channels:
        return 0                     # NOTIFY_CHANNELS=none: an emitter never breaks

    messages = []
    if level:
        messages.append((render_telegram(level, args.source, title, body, code, cfg),
                         render_chat(level, args.source, title, body, code, cfg),
                         level in LOUD_LEVELS))
    if code_only:
        messages.append(('<pre><code class="language-bash">%s</code></pre>' % html_escape(code_only),
                         "```bash\n%s\n```" % code_only, False))
    local = render_local(level, args.source, title, body, code) if level else ""
    if code_only:
        local = (local + "\n" if local else "") + "$ " + code_only

    if args.dry_run:
        if "hub" in channels:
            sys.stderr.write("DRY-RUN hub (printed here; a command attaches to this session's "
                             "voice note)\n%s\n\n" % local)
        for tg, chat, loud in messages:
            if "telegram" in channels:
                sys.stderr.write("DRY-RUN telegram (parse_mode=HTML, notify=%s)\n%s\n\n"
                                 % ("loud" if loud else "silent", tg))
            if "chat" in channels:
                via = "webhook" if cfg.get("GCHAT_WEBHOOK_URL") else "user token"
                shown = markdown_to_classic(chat) if cfg.get("GCHAT_WEBHOOK_URL") else chat
                sys.stderr.write("DRY-RUN chat (%s)\n%s\n\n" % (via, shown))
        return 0

    delivered, failures = set(), []
    if "hub" in channels:
        # The hub keeps voice notes, not text: the text is shown here, and a command is
        # attached to this agent session's voice note (first, with a copy button).
        if not args.quiet:
            print(local)
        delivered.add("local")
        for cmd in (code, code_only):
            if cmd and hub_on(cfg):
                hub_attach_command(cfg, cmd, title, body)
                delivered.add("hub")
    external = [c for c in channels if c in EXTERNAL]
    for i, (tg, chat, loud) in enumerate(messages):
        if not external:
            break
        ok, bad = send_text(cfg, external, tg, chat, loud=loud, mention=(i == 0))
        delivered.update(ok)
        failures.extend(bad)
    append_log(notify_log(), "[%s] %s | %s | to=%s%s" % (
        level or "code", args.source, title[:80], ",".join(sorted(delivered)) or "-",
        (" failed=" + "; ".join(failures)) if failures else ""))
    for problem in failures:
        sys.stderr.write("notify: %s\n" % problem)
    if not delivered:
        sys.stderr.write("notify: FAILED, nothing delivered (log %s)\n" % notify_log())
        return 1
    if external and not args.quiet:
        print("notification sent to %s: [%s] %s / %s" % (
            "+".join(sorted(delivered)), level or "code", args.source, title))
    return 3 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "notify":
        sys.exit(notify_main(sys.argv[2:]))
    sys.stderr.write("usage: notifylib.py notify [notify.sh arguments]\n")
    sys.exit(64)
