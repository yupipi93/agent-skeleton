#!/usr/bin/env python3
"""google_oauth: the OAuth plumbing shared by gchat.py, gdocs.py and gmail.py.

Your own OAuth client, your own tokens, nothing embedded:

  * the client is the JSON you download from the Google Cloud console (Google Auth
    Platform > Clients > Desktop app > Download JSON), saved as
    ~/.config/agent-skeleton/google/client.json (GOOGLE_OAUTH_CLIENT overrides the path);
  * each tool keeps its own refresh token in ~/.config/agent-skeleton/google/<tool>-token.json,
    written 0600 from the first byte in a 0700 directory (GOOGLE_OAUTH_DIR overrides it);
  * login is the installed-app flow: PKCE (S256) plus a random state, the redirect lands on
    a one-shot server on 127.0.0.1 (a random free port for Desktop clients);
  * every HTTP request has a timeout, and no secret is ever printed or put on a command line.

A "Web application" client also works: register http://localhost:8085/callback as a
redirect URI (or set GOOGLE_OAUTH_REDIRECT_URI) and the flow uses that instead.

Python 3.9+, standard library only.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
TOKENINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
HTTP_TIMEOUT = 60
WEB_REDIRECT_DEFAULT = "http://localhost:8085/callback"


class OAuthError(RuntimeError):
    pass


def die(msg, code=1):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(code)


def config_dir():
    return os.path.expanduser(os.environ.get("GOOGLE_OAUTH_DIR")
                              or os.path.join("~", ".config", "agent-skeleton", "google"))


def client_path():
    return os.path.expanduser(os.environ.get("GOOGLE_OAUTH_CLIENT")
                              or os.path.join(config_dir(), "client.json"))


def token_path(tool):
    return os.path.join(config_dir(), "%s-token.json" % tool)


SETUP_HINT = ("create a Desktop OAuth client in your Google Cloud project (Google Auth "
              "Platform > Clients), download its JSON to %s, then run login. "
              "Guide: docs/bundles/google.md")


# --------------------------------------------------------------------------- storage
def _ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def save_json(path, data):
    """Atomic write, 0600 from the first byte (no window with the umask's mode)."""
    directory = os.path.dirname(path)
    _ensure_dir(directory)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def warn_mode(path):
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        return
    if mode & 0o077:
        sys.stderr.write("warning: %s is mode %s; run: chmod 600 %s\n" % (path, oct(mode), path))


def load_client(path=None):
    """{client_id, client_secret, kind, redirect_uris} from a console client JSON."""
    path = path or client_path()
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        raise OAuthError("no OAuth client at %s: " % path + SETUP_HINT % path)
    except (OSError, ValueError) as exc:
        raise OAuthError("cannot read the OAuth client %s: %s" % (path, exc))
    warn_mode(path)
    for kind in ("installed", "web"):
        block = doc.get(kind)
        if isinstance(block, dict) and block.get("client_id"):
            return {"client_id": block["client_id"],
                    "client_secret": block.get("client_secret", ""),
                    "kind": kind, "redirect_uris": block.get("redirect_uris") or []}
    if doc.get("client_id"):
        return {"client_id": doc["client_id"], "client_secret": doc.get("client_secret", ""),
                "kind": doc.get("kind", "installed"), "redirect_uris": []}
    raise OAuthError("%s is not an OAuth client JSON (no installed/web client_id)" % path)


def load_token(tool):
    path = token_path(tool)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise OAuthError("not logged in. Run: kit/bundles/google/scripts/%s.py login" % tool)
    except (OSError, ValueError) as exc:
        raise OAuthError("cannot read %s: %s" % (path, exc))
    warn_mode(path)
    return data


# ------------------------------------------------------------------------------ http
def post_form(url, fields, timeout=HTTP_TIMEOUT):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body.decode("utf-8")) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        try:
            err = json.loads(payload)
            detail = "%s %s" % (err.get("error", ""), err.get("error_description", ""))
        except ValueError:
            detail = payload[:300]
        raise OAuthError("%s answered %s: %s" % (url.split("?")[0], exc.code, detail.strip()))
    except Exception as exc:                                  # noqa: BLE001
        raise OAuthError("%s unreachable: %s" % (url.split("?")[0], exc))


def request(method, url, token, params=None, body=None, want_bytes=False,
            timeout=HTTP_TIMEOUT, headers=None):
    """(status, payload) without raising on HTTP errors: callers that probe need the code."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Authorization": "Bearer " + token}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            if want_bytes:
                return resp.status, payload
            return resp.status, (json.loads(payload.decode("utf-8")) if payload.strip() else {})
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload.decode("utf-8"))
        except ValueError:
            return exc.code, {"raw": payload.decode("utf-8", "replace")[:400]}
    except Exception as exc:                                  # noqa: BLE001
        raise OAuthError("%s unreachable: %s" % (url.split("?")[0], exc))


def check(status, payload):
    """Raise OAuthError for an HTTP error answer, with Google's message."""
    if status < 400:
        return payload
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        raise OAuthError("%s %s: %s" % (err.get("code", status), err.get("status", ""),
                                        err.get("message", "")))
    raise OAuthError("HTTP %s: %s" % (status, str(payload)[:400]))


# ----------------------------------------------------------------------------- OAuth
def pkce_pair():
    verifier = base64.urlsafe_b64encode(os.urandom(48)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()
    return verifier, challenge.rstrip("=")


def redirect_for(client, port=None):
    """(redirect_uri, host, port, path) for the client's kind."""
    if client["kind"] == "web":
        uri = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI") or WEB_REDIRECT_DEFAULT
        parsed = urllib.parse.urlparse(uri)
        return uri, "127.0.0.1", parsed.port or 80, parsed.path or "/"
    return None, "127.0.0.1", int(port or os.environ.get("GOOGLE_OAUTH_PORT") or 0), "/"


def auth_url(client, redirect_uri, scopes, state, challenge, login_hint=None):
    params = {"client_id": client["client_id"], "redirect_uri": redirect_uri,
              "response_type": "code", "scope": " ".join(scopes),
              # offline + consent are what earn a refresh token
              "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
              "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    if login_hint:
        params["login_hint"] = login_hint
    return AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params)


def _handler(path, result):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != path:
                # Content-Length matters: a favicon request must not stall the server.
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            params = urllib.parse.parse_qs(parsed.query)
            result.update({k: v[0] for k, v in params.items()})
            body = b"<h2>Done. You can close this tab and go back to the terminal.</h2>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass
    return Handler


def login(tool, scopes, timeout=600, no_browser=False, port=None, login_hint=None):
    """Run the browser flow and store a refresh token for `tool`. Returns granted scopes."""
    client = load_client()
    fixed_uri, host, bind_port, path = redirect_for(client, port)
    result = {}
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    try:
        httpd = socketserver.ThreadingTCPServer((host, bind_port), _handler(path, result))
    except OSError as exc:
        raise OAuthError("cannot listen on %s:%s (%s); is another login running?"
                         % (host, bind_port, exc))
    redirect_uri = fixed_uri or "http://%s:%d/" % (host, httpd.server_address[1])
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    url = auth_url(client, redirect_uri, scopes, state, challenge, login_hint)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        sys.stderr.write("\nOpen this URL and approve the permissions:\n\n%s\n\n" % url)
        sys.stderr.flush()
        if not no_browser:
            try:
                webbrowser.open(url)
            except Exception:                                 # noqa: BLE001
                pass
        deadline = time.time() + timeout
        while not result and time.time() < deadline:
            time.sleep(0.3)
    finally:
        httpd.shutdown()
        httpd.server_close()
    if not result:
        raise OAuthError("timed out after %ss waiting for the browser; run login again" % timeout)
    if "error" in result:
        raise OAuthError("authorization failed: %s" % result["error"])
    if not secrets.compare_digest(result.get("state", ""), state):
        raise OAuthError("state mismatch, aborting")
    tok = post_form(TOKEN_ENDPOINT, {
        "code": result.get("code", ""), "client_id": client["client_id"],
        "client_secret": client["client_secret"], "redirect_uri": redirect_uri,
        "grant_type": "authorization_code", "code_verifier": verifier})
    if not tok.get("refresh_token"):
        raise OAuthError("Google returned no refresh token; run login again (prompt=consent "
                         "is sent; revoke the app at myaccount.google.com if it persists)")
    save_json(token_path(tool), {
        "client_id": client["client_id"], "refresh_token": tok["refresh_token"],
        "access_token": tok.get("access_token", ""),
        "expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60,
        "scope": tok.get("scope", ""), "created_at": int(time.time())})
    return sorted(tok.get("scope", "").split())


def access_token(tool):
    """A valid access token, refreshed with the stored refresh token when needed."""
    tok = load_token(tool)
    if tok.get("access_token") and tok.get("expires_at", 0) > time.time():
        return tok["access_token"]
    client = load_client()
    if tok.get("client_id") and tok["client_id"] != client["client_id"]:
        raise OAuthError("the OAuth client changed since login; run: "
                         "kit/bundles/google/scripts/%s.py login" % tool)
    try:
        fresh = post_form(TOKEN_ENDPOINT, {
            "client_id": client["client_id"], "client_secret": client["client_secret"],
            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
    except OAuthError as exc:
        if "invalid_grant" in str(exc):
            raise OAuthError("the refresh token was revoked or expired (apps in Testing "
                             "expire after 7 days); run: kit/bundles/google/scripts/%s.py login"
                             % tool)
        raise
    tok["access_token"] = fresh["access_token"]
    tok["expires_at"] = time.time() + int(fresh.get("expires_in", 3600)) - 60
    save_json(token_path(tool), tok)
    return tok["access_token"]


def tokeninfo(token):
    """What a token can do, per Google. POST keeps the token out of URLs and logs."""
    return post_form(TOKENINFO_ENDPOINT, {"access_token": token})


def logout(tool, revoke=True):
    """Forget the tool's token; revoke it at Google too unless revoke=False."""
    path = token_path(tool)
    if not os.path.exists(path):
        return False
    if revoke:
        try:
            tok = load_token(tool)
            post_form(REVOKE_ENDPOINT, {"token": tok.get("refresh_token", "")})
        except OAuthError as exc:
            sys.stderr.write("warning: revoke failed (%s); the local token is removed anyway\n"
                             % exc)
    os.unlink(path)
    return True


# ----------------------------------------------------------------- shared CLI helpers
def add_login_args(sp):
    sp.add_argument("--no-browser", action="store_true", help="print the URL only")
    sp.add_argument("--timeout", type=int, default=600, help="seconds to wait for the browser")
    sp.add_argument("--port", type=int, help="fixed loopback port (Desktop clients)")
    sp.add_argument("--login-hint", help="preselect the Google account (an email address)")
    return sp


def run_login(tool, scopes, args, must_have=()):
    granted = login(tool, scopes, timeout=args.timeout, no_browser=args.no_browser,
                    port=args.port, login_hint=args.login_hint)
    print("logged in. Refresh token stored in %s (0600)." % token_path(tool))
    print("granted scopes:")
    for s in granted:
        print("  %s" % s)
    missing = [s for s in must_have if s not in granted]
    if missing:
        sys.stderr.write("warning: not granted: %s. Check the Data Access page of your "
                         "consent screen, then run login again.\n" % ", ".join(missing))
    return 0


def emit(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False))
        return True
    return False


def main_guard(fn):
    """Run a CLI main, turning OAuthError into one clean error line."""
    try:
        sys.exit(fn() or 0)
    except OAuthError as exc:
        die(str(exc))
    except KeyboardInterrupt:
        die("interrupted", 130)
