"""Which build is serving, for the page footer and /healthz.

    from build import info
    info()  # {"version": "0.1.0", "release": 7, "commit": "abc1234",
            #  "committed_at": "2026-01-01T10:00:00+01:00", "dirty": False}

RELEASE is bumped with every numbered release of the backlog; the commit says exactly
which code runs (a screenshot then tells whether it is the latest build). Read it once at
startup: a deployed checkout only changes with a restart.
"""

import os
import subprocess

VERSION = "0.1.0"
RELEASE = 1
ROOT = os.path.dirname(os.path.abspath(__file__))


def _git(*args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        r = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True,
                           timeout=5, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def info():
    out = {"version": VERSION, "release": RELEASE, "commit": "", "committed_at": "", "dirty": False}
    head = _git("log", "-1", "--format=%h %cI")
    if head:
        out["commit"], _, out["committed_at"] = head.partition(" ")
        out["dirty"] = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return out


# Page side (JS):
#   footer.textContent = [name, 'release ' + b.release, b.commit, fmtDate(b.committed_at),
#                         b.dirty ? 'uncommitted changes' : ''].filter(Boolean).join(' · ');
