"""The google bundle: OAuth storage and refresh, request shaping and parsers. No network:
the token endpoint is replaced in-process, and every file lives in a temp directory."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.helpers import ROOT

SCRIPTS = ROOT / "kit/bundles/google/scripts"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(SCRIPTS / "lib"))
go = load("google_oauth", SCRIPTS / "lib/google_oauth.py")
sys.modules["google_oauth"] = go
gchat = load("gchat_mod", SCRIPTS / "gchat.py")
gdocs = load("gdocs_mod", SCRIPTS / "gdocs.py")
gmail = load("gmail_mod", SCRIPTS / "gmail.py")


class OAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="google-test-"))
        self.env = {k: os.environ.get(k) for k in ("GOOGLE_OAUTH_DIR", "GOOGLE_OAUTH_CLIENT")}
        os.environ["GOOGLE_OAUTH_DIR"] = str(self.tmp / "google")
        os.environ.pop("GOOGLE_OAUTH_CLIENT", None)

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_client(self, kind="installed"):
        path = Path(go.client_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({kind: {"client_id": "cid.apps.example.com",
                                           "client_secret": "csecret", "redirect_uris": []}}))
        path.chmod(0o600)

    def test_missing_client_explains_the_setup(self):
        with self.assertRaises(go.OAuthError) as ctx:
            go.load_client()
        self.assertIn("Desktop OAuth client", str(ctx.exception))

    def test_client_kinds_and_redirects(self):
        self.write_client("installed")
        c = go.load_client()
        self.assertEqual((c["kind"], c["client_id"]), ("installed", "cid.apps.example.com"))
        uri, host, port, path = go.redirect_for(c)
        self.assertEqual((uri, host, port, path), (None, "127.0.0.1", 0, "/"))
        self.write_client("web")
        uri, host, port, path = go.redirect_for(go.load_client())
        self.assertEqual((uri, port, path), ("http://localhost:8085/callback", 8085, "/callback"))

    def test_auth_url_has_pkce_state_and_offline(self):
        self.write_client()
        verifier, challenge = go.pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        url = go.auth_url(go.load_client(), "http://127.0.0.1:5000/", ["s1", "s2"], "st", challenge)
        for part in ("code_challenge_method=S256", "state=st", "access_type=offline",
                     "prompt=consent", "scope=s1+s2", "redirect_uri=http%3A%2F%2F127.0.0.1%3A5000%2F"):
            self.assertIn(part, url)
        self.assertNotIn("csecret", url)

    def test_tokens_are_private_and_refresh(self):
        self.write_client()
        go.save_json(go.token_path("gdocs"), {"client_id": "cid.apps.example.com",
                                              "refresh_token": "r1", "access_token": "old",
                                              "expires_at": time.time() - 10})
        path = go.token_path("gdocs")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(os.path.dirname(path)).st_mode & 0o777, 0o700)
        calls = []
        saved = go.post_form
        go.post_form = lambda url, fields, timeout=60: (calls.append((url, fields)) or
                                                        {"access_token": "new", "expires_in": 3600})
        try:
            self.assertEqual(go.access_token("gdocs"), "new")
            self.assertEqual(go.access_token("gdocs"), "new")      # cached, no second call
        finally:
            go.post_form = saved
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["grant_type"], "refresh_token")
        self.assertEqual(json.loads(Path(path).read_text())["access_token"], "new")

    def test_client_change_and_revoked_grant_ask_for_login(self):
        self.write_client()
        go.save_json(go.token_path("gmail"), {"client_id": "other", "refresh_token": "r",
                                              "expires_at": 0})
        with self.assertRaises(go.OAuthError) as ctx:
            go.access_token("gmail")
        self.assertIn("client changed", str(ctx.exception))
        go.save_json(go.token_path("gmail"), {"client_id": "cid.apps.example.com",
                                              "refresh_token": "r", "expires_at": 0})
        saved = go.post_form

        def boom(url, fields, timeout=60):
            raise go.OAuthError("token endpoint answered 400: invalid_grant Token has been expired")
        go.post_form = boom
        try:
            with self.assertRaises(go.OAuthError) as ctx:
                go.access_token("gmail")
        finally:
            go.post_form = saved
        self.assertIn("gmail.py login", str(ctx.exception))

    def test_not_logged_in(self):
        with self.assertRaises(go.OAuthError) as ctx:
            go.load_token("gchat")
        self.assertIn("gchat.py login", str(ctx.exception))


class ParserTest(unittest.TestCase):
    def test_chat_send_body_sets_markdown_syntax(self):
        body = gchat.send_body("• one\n• two\nend", thread="spaces/A/threads/B")
        self.assertEqual(body["markupSyntax"], "MARKUP_SYNTAX_MARKDOWN")
        self.assertEqual(body["text"], "- one\n- two\n\nend")
        self.assertEqual(body["thread"], {"name": "spaces/A/threads/B"})
        self.assertEqual(gchat.send_body("```\na\nb\n```")["text"], "```\na\nb\n```")

    def test_chat_scopes_can_post(self):
        self.assertIn("https://www.googleapis.com/auth/chat.messages.create", gchat.SCOPES)

    def test_docs_ids_queries_and_indexes(self):
        self.assertEqual(gdocs.doc_id("https://docs.google.com/document/d/AbC_1-x/edit#h"), "AbC_1-x")
        self.assertEqual(gdocs.doc_id("AbC"), "AbC")
        with self.assertRaises(go.OAuthError):
            gdocs.doc_id("https://example.com/nothing")
        self.assertEqual(gdocs.drive_quote("it's"), "'it\\'s'")
        self.assertEqual(gdocs.utf16_len("a\U0001F600"), 3)
        doc = {"body": {"content": [
            {"endIndex": 1},
            {"paragraph": {"elements": [{"textRun": {"content": "Hello\n"}}]}, "endIndex": 7},
            {"table": {"tableRows": [{"tableCells": [
                {"content": [{"paragraph": {"elements": [{"textRun": {"content": "a\n"}}]}}]},
                {"content": [{"paragraph": {"elements": [{"textRun": {"content": "b\n"}}]}}]}]}]},
             "endIndex": 20}]}}
        self.assertEqual(gdocs.doc_text(doc), "Hello\na | b")
        self.assertEqual(gdocs.end_index(doc), 19)

    def test_gmail_parsing_is_safe(self):
        import base64
        enc = lambda s: base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")  # noqa: E731
        msg = {"id": "m1", "threadId": "t1", "snippet": "a &amp; b", "payload": {
            "headers": [{"name": "Subject", "value": "Hi"}, {"name": "From", "value": "x@example.com"}],
            "parts": [{"mimeType": "text/html", "body": {"data": enc("<p>Hello<br>world</p>")}},
                      {"mimeType": "application/pdf", "filename": "../../evil.pdf",
                       "body": {"attachmentId": "att1", "size": 3}}]}}
        text, atts = gmail.message_text(msg)
        self.assertEqual(text, "Hello\nworld")
        self.assertEqual(gmail.summarize(msg)["snippet"], "a & b")
        self.assertEqual(gmail.safe_name(atts[0]["filename"], "x"), "evil.pdf")
        self.assertEqual(gmail.safe_name("..", "fallback"), "fallback")
        self.assertEqual(gmail.SCOPES, ["https://www.googleapis.com/auth/gmail.readonly"])


class CliTest(unittest.TestCase):
    def test_help_and_clean_error_without_client(self):
        with tempfile.TemporaryDirectory(prefix="google-cli-") as tmp:
            env = dict(os.environ, HOME=tmp, GOOGLE_OAUTH_DIR=os.path.join(tmp, "g"),
                       PYTHONDONTWRITEBYTECODE="1")
            env.pop("GOOGLE_OAUTH_CLIENT", None)
            for script in ("gchat.py", "gdocs.py", "gmail.py"):
                proc = subprocess.run([sys.executable, str(SCRIPTS / script), "--help"],
                                      capture_output=True, text=True, env=env)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                proc = subprocess.run([sys.executable, str(SCRIPTS / script), "token"],
                                      capture_output=True, text=True, env=env)
                self.assertEqual(proc.returncode, 1)
                self.assertIn("not logged in", proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)

    def test_chat_send_dry_run_needs_no_token(self):
        with tempfile.TemporaryDirectory(prefix="google-cli-") as tmp:
            env = dict(os.environ, HOME=tmp, GOOGLE_OAUTH_DIR=os.path.join(tmp, "g"))
            proc = subprocess.run([sys.executable, str(SCRIPTS / "gchat.py"), "send", "spaces/A",
                                   "--text", "**hi**", "--dry-run"], capture_output=True, text=True,
                                  env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["body"]["markupSyntax"], "MARKUP_SYNTAX_MARKDOWN")


if __name__ == "__main__":
    unittest.main()
