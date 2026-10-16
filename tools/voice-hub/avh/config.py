"""Where the hub keeps its data and how it is reached.

Everything has a default that works with no config file at all. The optional file
~/.config/agent-skeleton/voice-hub.env (KEY=VALUE, same dialect as the kit's other env
files) overrides the defaults, and real environment variables override the file.
"""

import os
import re

HOME = os.path.expanduser("~")
# tools/voice-hub/avh/config.py -> tools/voice-hub -> the agent-skeleton checkout.
HUB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT_ROOT = os.path.dirname(os.path.dirname(HUB_ROOT))
CONFIG_FILE = os.environ.get(
    "AVH_CONFIG", os.path.join(HOME, ".config", "agent-skeleton", "voice-hub.env"))

DEFAULTS = {
    # Data: the SQLite database plus one audio file per note. Outside the repo on
    # purpose: the notes are work content and must never end up in git. Created 0700.
    "AVH_HOME": os.path.join(HOME, ".local", "share", "agent-skeleton", "voice-hub"),
    # Loopback only. Nothing listens on the LAN. A phone can reach the hub through
    # Tailscale Serve, which is opt-in (`avh service install --tailnet`).
    "AVH_HOST": "127.0.0.1",
    "AVH_PORT": "7473",
    # Public (tailnet) base URL, filled in by `avh service install --tailnet`, which
    # reads the machine's MagicDNS name from `tailscale status`.
    "AVH_PUBLIC_URL": "",
    # HTTPS port Tailscale Serve exposes the hub on (only with --tailnet).
    "AVH_TAILNET_PORT": "8443",
    # Speaking rate notes are synthesised at when the caller does not say. The
    # player converts between "effective speed" (what you hear) and playbackRate, and
    # never plays a note slower than it was recorded (that is what sounds metallic).
    "AVH_DEFAULT_SPEECH_RATE": "1.0",
    # The kit's voice-note.py, used to re-synthesise a note at the natural rate.
    "AVH_VOICE_NOTE": os.path.join(KIT_ROOT, "kit", "bundles", "voice", "scripts",
                                   "voice-note.py"),
    # Logins allowed through Tailscale Serve (comma list). Empty = any tailnet user,
    # which on a single-person tailnet is the same thing.
    "AVH_ALLOWED_LOGINS": "",
    # Optional ticket links per key prefix, comma separated:
    # "PROJ=https://your-org.atlassian.net/browse/,OPS=https://tracker.example.com/t/"
    "AVH_TICKET_LINKS": "",
    # launchd label of the login service (macOS).
    "AVH_LAUNCHD_LABEL": "com.agent-skeleton.voice-hub",
}


def _load_env(path):
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                if key.startswith("export "):
                    key = key[7:].strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                else:
                    val = re.split(r"\s+#", val, maxsplit=1)[0].strip()
                out[key] = val
    except OSError:
        pass
    return out


def load():
    cfg = dict(DEFAULTS)
    cfg.update(_load_env(CONFIG_FILE))
    for key in DEFAULTS:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    cfg["AVH_HOME"] = os.path.expanduser(cfg["AVH_HOME"])
    return cfg


def save_value(key, value):
    """Set one KEY=VALUE line in the config file, keeping every other line as it is."""
    directory = os.path.dirname(CONFIG_FILE)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    lines = []
    try:
        with open(CONFIG_FILE, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        pass
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == key:
            out.append("%s=%s" % (key, value))
            done = True
        else:
            out.append(line)
    if not done:
        out.append("%s=%s" % (key, value))
    fd = os.open(CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def local_url(cfg):
    return "http://%s:%s" % (cfg["AVH_HOST"], cfg["AVH_PORT"])


def public_url(cfg):
    return (cfg.get("AVH_PUBLIC_URL") or "").rstrip("/")


def note_urls(cfg, note_id):
    """Every URL a note is reachable at: this machine (local) and, if set up, the tailnet."""
    out = {"local": "%s/n/%s" % (local_url(cfg), note_id)}
    if public_url(cfg):
        out["public"] = "%s/n/%s" % (public_url(cfg), note_id)
    return out


def ticket_links(cfg):
    out = {}
    for pair in (cfg.get("AVH_TICKET_LINKS") or "").split(","):
        if "=" in pair:
            key, _, url = pair.partition("=")
            out[key.strip()] = url.strip()
    return out
