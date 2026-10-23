"""A crash-safe copy of a new token until Secret Manager holds it.

Bitbucket shows a token once. If the run dies between the dialog and Secret
Manager, this file is the only copy, so it is written (mode 0600, exclusive
create, outside the repo) before anything else is attempted, and deleted as soon
as the stored version has been read back and matched.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from . import config


def write(value: str, meta: dict) -> Path:
    config.ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{meta.get('gcp_project')}--{meta.get('secret_name')}")
    path = config.STASH_DIR / f"{stamp}-{slug}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"value": value, "meta": meta}, fh)
    return path


def read(path: Path) -> tuple[str, dict]:
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise PermissionError(f"{path} has mode {oct(mode)}; expected 0600")
    data = json.loads(path.read_text())
    return data["value"], data.get("meta", {})


def remove(path: Path) -> None:
    path.unlink(missing_ok=True)
