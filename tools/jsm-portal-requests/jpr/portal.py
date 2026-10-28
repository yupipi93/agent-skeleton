"""The signed-in portal session: REST calls made from inside the page.

Every call runs `fetch` in the tool's tab, on the site's own origin, so it carries the
browser's Atlassian session cookies: the request is made as the person signed in to
the tool's Chrome, never as an API token. Writes send `X-Atlassian-Token: no-check`,
the header Jira wants on cookie-authenticated POSTs.
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlencode

from . import config

FETCH_JS = """
async ([url, method, body]) => {
  const headers = {
    'Accept': 'application/json',
    'X-ExperimentalApi': 'opt-in',
    'X-Atlassian-Token': 'no-check',
  };
  const opts = {method, headers, credentials: 'same-origin'};
  if (body !== null) { headers['Content-Type'] = 'application/json'; opts.body = body; }
  const r = await fetch(url, opts);
  return {status: r.status, url: r.url, text: await r.text()};
}
"""


class NotSignedIn(RuntimeError):
    """The site sent the browser to the Atlassian sign-in page.

    The tool never types a password: a person signs in with `jpr login` and the
    command is run again.
    """


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, text: str):
        self.status = status
        self.text = text
        super().__init__(f"{method} {path}: HTTP {status}: {error_summary(text)}")


def error_summary(text: str) -> str:
    try:
        data = json.loads(text)
    except ValueError:
        return (text or "").strip()[:300]
    parts = []
    if isinstance(data, dict):
        if data.get("errorMessage"):
            parts.append(str(data["errorMessage"]))
        for key in ("errorMessages", "errors"):
            value = data.get(key)
            if isinstance(value, list):
                parts += [str(v.get("title") or v.get("detail") or v) if isinstance(v, dict) else str(v) for v in value]
            elif isinstance(value, dict):
                parts += [f"{k}: {v}" for k, v in value.items()]
        if data.get("message"):
            parts.append(str(data["message"]))
    return "; ".join(parts)[:500] or (text or "").strip()[:300]


def is_login_page(url: str) -> bool:
    return url.startswith(("https://id.atlassian.com/login", "https://id.atlassian.com/step-up")) or (
        "/servicedesk/customer/user/login" in url or "/login.jsp" in url
    )


def wait_idle(page, settle_ms: int = 1500) -> None:
    """Wait for spinners to go away, then a fixed settle."""
    deadline = time.monotonic() + 30
    spinner = page.locator("[role=progressbar], [data-testid*=spinner], [aria-busy=true]")
    while time.monotonic() < deadline:
        try:
            if not any(spinner.nth(i).is_visible() for i in range(spinner.count())):
                break
        except Exception:
            break
        time.sleep(0.4)
    page.wait_for_timeout(settle_ms)


def goto(page, url: str, settle_ms: int = 1500) -> None:
    page.goto(url, wait_until="domcontentloaded")
    wait_idle(page, settle_ms)
    if is_login_page(page.url):
        raise NotSignedIn(
            f"the site asks to sign in before {url}: run `jpr stop`, then `jpr login`, "
            "sign in, close the window and run again"
        )


class Session:
    def __init__(self, page):
        self.page = page
        self.base = config.base_url()
        if not page.url.startswith(self.base):
            goto(page, f"{self.base}/servicedesk/customer/portals")

    def call(self, method: str, path: str, body: dict | None = None, ok=(200, 201, 204)):
        url = path if path.startswith("http") else f"{self.base}{path}"
        payload = json.dumps(body) if body is not None else None
        result = self.page.evaluate(FETCH_JS, [url, method, payload])
        if is_login_page(result.get("url", "")) or result["status"] == 401:
            raise NotSignedIn("the portal session is not signed in: run `jpr stop`, then `jpr login`")
        if result["status"] not in ok:
            raise ApiError(method, path, result["status"], result["text"])
        text = result["text"]
        return json.loads(text) if text.strip() else {}

    def get(self, path: str, **params):
        if params:
            path = f"{path}{'&' if '?' in path else '?'}{urlencode(params)}"
        return self.call("GET", path)

    def paged(self, path: str, limit: int = 100) -> list[dict]:
        """All `values` of a servicedeskapi page set (start / limit / isLastPage)."""
        out: list[dict] = []
        start = 0
        while True:
            data = self.get(path, start=start, limit=limit)
            values = data.get("values", [])
            out += values
            if data.get("isLastPage", True) or not values:
                return out
            start += len(values)

    def myself(self) -> dict:
        try:
            return self.get("/rest/api/3/myself")
        except ApiError:
            # Portal-only customers have no Jira user profile.
            return self.get("/rest/servicedesk/1/customer/profile") or {}
