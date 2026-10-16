"""Run the hub as a login service (launchd, macOS) and, optionally, publish it on a tailnet.

    avh service install [--tailnet]   LaunchAgent (+ Tailscale Serve with --tailnet), idempotent
    avh service status                is it up, locally and on the tailnet
    avh service restart               restart the server (after pulling a new kit version)
    avh service uninstall             undo both
    avh doctor                        everything the hub depends on, one line each

The server binds 127.0.0.1 only. With --tailnet, Tailscale Serve terminates HTTPS on a
tailnet-only port (AVH_TAILNET_PORT, default 8443) and proxies to it, so a phone on the
same tailnet reaches the hub; nothing is exposed to the LAN or the internet. Without it
the hub is local to this machine.
"""

import json
import os
import plistlib
import shutil
import subprocess
import sys
import urllib.request

from . import config as config_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "bin", "avh")


def label(cfg):
    return cfg.get("AVH_LAUNCHD_LABEL") or config_mod.DEFAULTS["AVH_LAUNCHD_LABEL"]


def plist_path(cfg):
    return os.path.expanduser("~/Library/LaunchAgents/%s.plist" % label(cfg))


def log_path(cfg):
    return os.path.expanduser("~/Library/Logs/%s.log" % label(cfg))


def _run(cmd, check=False):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if check and proc.returncode != 0:
        raise RuntimeError("%s: %s" % (" ".join(cmd), proc.stderr.decode().strip()[-300:]))
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def _python():
    for cand in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3"):
        if os.path.exists(cand):
            return cand
    return sys.executable


def _uid():
    return str(os.getuid())


def _get(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as exc:                                # noqa: BLE001
        return 0, str(exc)


def _macos(action):
    if sys.platform != "darwin":
        print("avh service %s: the login service is launchd (macOS) only. Elsewhere run "
              "`bin/avh serve` under your own supervisor (systemd user unit, tmux...)." % action)
        return False
    return True


def tailnet_name():
    if not shutil.which("tailscale"):
        return ""
    code, out, _ = _run(["tailscale", "status", "--json"])
    if code != 0:
        return ""
    try:
        return (json.loads(out).get("Self") or {}).get("DNSName", "").rstrip(".")
    except ValueError:
        return ""


def write_plist(cfg):
    plist, log = plist_path(cfg), log_path(cfg)
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    path = ":".join(["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
                     "/usr/sbin", "/sbin"])
    data = {
        "Label": label(cfg),
        "ProgramArguments": [_python(), ENTRY, "serve"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ProcessType": "Background",
        "WorkingDirectory": ROOT,
        "EnvironmentVariables": {"PATH": path, "PYTHONUNBUFFERED": "1"},
        "StandardOutPath": log,
        "StandardErrorPath": log,
        # The server sets umask 077 itself; this covers anything launchd creates.
        "Umask": 0o077,
    }
    with open(plist, "wb") as fh:
        plistlib.dump(data, fh)


def install(cfg, tailnet=False):
    if not _macos("install"):
        return 1
    write_plist(cfg)
    _run(["launchctl", "bootout", "gui/%s/%s" % (_uid(), label(cfg))])
    _run(["launchctl", "bootstrap", "gui/%s" % _uid(), plist_path(cfg)], check=True)
    print("launchd: %s loaded (log %s)" % (label(cfg), log_path(cfg)))
    if tailnet:
        name = tailnet_name()
        if name:
            port = cfg["AVH_TAILNET_PORT"]
            code, out, err = _run(["tailscale", "serve", "--bg", "--yes", "--https=%s" % port,
                                   "http://127.0.0.1:%s" % cfg["AVH_PORT"]])
            if code == 0:
                url = "https://%s%s" % (name, "" if port == "443" else ":" + port)
                config_mod.save_value("AVH_PUBLIC_URL", url)
                print("tailnet: %s" % url)
            else:
                print("tailscale serve failed: %s" % (err.strip() or out.strip())[-300:])
        else:
            print("tailscale not available: the hub stays local (%s)"
                  % config_mod.local_url(cfg))
    print("local: %s" % config_mod.local_url(cfg))
    return 0


def uninstall(cfg):
    if not _macos("uninstall"):
        return 1
    _run(["launchctl", "bootout", "gui/%s/%s" % (_uid(), label(cfg))])
    if os.path.exists(plist_path(cfg)):
        os.remove(plist_path(cfg))
    if config_mod.public_url(cfg) and shutil.which("tailscale"):
        _run(["tailscale", "serve", "--https=%s" % cfg["AVH_TAILNET_PORT"], "off"])
    print("removed the launchd job%s (data kept in %s)"
          % (" and the tailnet port" if config_mod.public_url(cfg) else "", cfg["AVH_HOME"]))
    return 0


def restart(cfg):
    if not _macos("restart"):
        return 1
    code, _, err = _run(["launchctl", "kickstart", "-k", "gui/%s/%s" % (_uid(), label(cfg))])
    print("restarted" if code == 0 else "restart failed: %s" % err.strip())
    return code


def status(cfg):
    state = "not loaded"
    if sys.platform == "darwin":
        code, out, _ = _run(["launchctl", "print", "gui/%s/%s" % (_uid(), label(cfg))])
        if code == 0:
            for line in out.splitlines():
                if line.strip().startswith("state ="):
                    state = line.split("=", 1)[1].strip()
    print("launchd: %s" % state)
    st, _ = _get(config_mod.local_url(cfg) + "/healthz")
    print("local:   %s %s" % (config_mod.local_url(cfg), "OK" if st == 200 else "DOWN"))
    pub = config_mod.public_url(cfg)
    if pub:
        st, _ = _get(pub + "/healthz", timeout=8)
        print("tailnet: %s %s" % (pub, "OK" if st == 200 else "unreachable from here"))
    return 0


def run(action, cfg, tailnet=False):
    if action == "install":
        return install(cfg, tailnet=tailnet)
    return {"uninstall": uninstall, "restart": restart, "status": status}[action](cfg)


def doctor(cfg):
    from .store import Store
    ok = True

    def line(good, name, detail=""):
        nonlocal ok
        ok = ok and good
        print("%s %-22s %s" % ("✅" if good else "❌", name, detail))

    line(sys.version_info >= (3, 9), "python", sys.version.split()[0])
    line(bool(shutil.which("ffmpeg")), "ffmpeg", shutil.which("ffmpeg") or "brew install ffmpeg")
    try:
        store = Store(cfg["AVH_HOME"])
        total = store.facets()["totals"]
        mode = oct(os.stat(cfg["AVH_HOME"]).st_mode & 0o777)
        line(True, "data", "%s (%s, %d notes, %d unheard)" % (
            cfg["AVH_HOME"], mode, total["total"] or 0, total["unheard"] or 0))
    except Exception as exc:                                # noqa: BLE001
        line(False, "data", str(exc))
    if sys.platform == "darwin":
        plist = plist_path(cfg)
        line(os.path.exists(plist), "launchd job",
             plist if os.path.exists(plist) else "optional: bin/avh service install")
    st, _ = _get(config_mod.local_url(cfg) + "/healthz")
    line(st == 200, "server", config_mod.local_url(cfg) if st == 200
         else "%s down: bin/avh serve (or service install)" % config_mod.local_url(cfg))
    pub = config_mod.public_url(cfg)
    if pub:
        st, _ = _get(pub + "/healthz", timeout=8)
        line(st == 200, "tailnet", pub)
    voice = cfg.get("AVH_VOICE_NOTE") or ""
    line(os.path.exists(voice), "voice-note.py", voice or "AVH_VOICE_NOTE not set")
    return 0 if ok else 1
