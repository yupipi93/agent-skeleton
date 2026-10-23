"""Token shapes, and how to keep them out of anything written or printed.

Atlassian prefixes every secret it issues: `ATCTT` for Bitbucket repository,
project and workspace access tokens, `ATATT` for Atlassian API tokens, `ATBB`
for the retired app passwords. The suffix is base64url-ish, sometimes with `=`.
"""

from __future__ import annotations

import re

TOKEN = re.compile(r"\b(ATCTT|ATATT|ATBB)[A-Za-z0-9_\-=]{20,}")


def find(text: str) -> str | None:
    match = TOKEN.search(text or "")
    return match.group(0) if match else None


def scrub(text: str) -> str:
    return TOKEN.sub(lambda m: f"{m.group(1)}<redacted>", text or "")


def contains(text: str) -> bool:
    return TOKEN.search(text or "") is not None
