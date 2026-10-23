"""Check a token against the Bitbucket API, without printing it.

The status code tells the cases apart:

- 200: the token authenticated and may read the target.
- 403: the token authenticated but its scopes do not cover the probe (for example
  a pipelines-only token). The token itself works.
- 401: Bitbucket does not accept the token (wrong, revoked, expired, or not
  propagated yet: a new token can take a few seconds).
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request

from . import config
from .bitbucket import Target


def probe_url(target: Target) -> str:
    api = config.BITBUCKET_API
    if target.kind == "repository":
        return f"{api}/repositories/{target.workspace}/{target.repo}"
    if target.kind == "project":
        query = urllib.parse.urlencode({"q": f'project.key="{target.project_key}"', "pagelen": 1})
        return f"{api}/repositories/{target.workspace}?{query}"
    return f"{api}/repositories/{target.workspace}?pagelen=1"


def status(target: Target, value: str) -> int:
    req = urllib.request.Request(
        probe_url(target),
        headers={"Authorization": f"Bearer {value}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status
    except urllib.error.HTTPError as err:
        return err.code


def check(target: Target, value: str, attempts: int = 6, wait_s: float = 5) -> tuple[bool, str]:
    code = 0
    for attempt in range(attempts):
        code = status(target, value)
        if code != 401:
            break
        if attempt < attempts - 1:
            time.sleep(wait_s)
    if code == 200:
        return True, "200 authenticated, target readable"
    if code == 403:
        return True, "403 authenticated, scopes do not cover the read probe"
    if code == 401:
        return False, "401 Bitbucket does not accept the token"
    return False, f"unexpected HTTP {code}"
