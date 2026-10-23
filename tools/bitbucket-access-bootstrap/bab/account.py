"""Which Atlassian account the tool's browser is signed in as, and which one it should be.

A token is created by whoever holds the session, and Bitbucket records that
account as its creator. People with several Atlassian accounts (an employer's
and a client's, or an alias that cannot sign in) can easily sign in with the
wrong one, so `create` refuses to act unless the session matches the expected
account.

Expected account, first found: `BAB_EXPECTED_ACCOUNT`, then `BITBUCKET_EMAIL`,
then `JIRA_EMAIL`, each from the environment or from
~/.config/agent-skeleton/atlassian.env (the file `pr-bitbucket.sh` already uses).
An email or an Atlassian account id both work.
"""

from __future__ import annotations

import os
import sys

from . import config

ATLASSIAN_ENV = "~/.config/agent-skeleton/atlassian.env"
KEYS = ("BAB_EXPECTED_ACCOUNT", "BITBUCKET_EMAIL", "JIRA_EMAIL")
ME_URLS = (
    "https://id.atlassian.com/gateway/api/me",
    f"{config.BITBUCKET}/!api/2.0/user",
)


def expected() -> str | None:
    sys.path.insert(0, str(config.REPO_ROOT / "kit" / "bundles" / "core" / "scripts" / "lib"))
    try:
        import envfile
    except ImportError:
        envfile = None
    path = os.path.expanduser(ATLASSIAN_ENV)
    for key in KEYS:
        value = os.environ.get(key)
        if not value and envfile is not None and os.path.exists(path):
            value = envfile.get(path, key)
        if value:
            return value.strip()
    return None


def signed_in(page) -> dict:
    """Email and account id of the session, read with the browser's own cookies."""
    found: dict = {}
    for url in ME_URLS:
        try:
            resp = page.context.request.get(url, timeout=15000)
            if resp.ok:
                data = resp.json()
                found.setdefault("email", data.get("email"))
                found.setdefault("account_id", data.get("account_id"))
        except Exception:
            continue
        if found.get("email") and found.get("account_id"):
            break
    return {k: v for k, v in found.items() if v}


def matches(session: dict, want: str) -> bool:
    want = want.strip().lower()
    return want in {str(v).strip().lower() for v in session.values()}


def describe(session: dict) -> str:
    if not session:
        return "unknown"
    return " / ".join(str(session[k]) for k in ("email", "account_id") if k in session)
