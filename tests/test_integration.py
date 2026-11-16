import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen
import zipfile

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from PIL import Image
import pymupdf

from revisor import ai, vault
from revisor.auth import Auth, AuthError, ISSUER, RESOURCE, validate_callback
from revisor.corpus import Corpus, prepare, sha256


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def image(self):
        stream = io.BytesIO()
        Image.new("RGB", (30, 20), "white").save(stream, format="JPEG")
        return stream.getvalue()

    def test_vault_encrypts_and_roundtrips(self):
        path = self.root / "credentials.dpapi"
        value = {"access_token": "segredo-test-123", "unicode": "qualificação"}
        vault.write(path, value)
        self.assertNotIn(b"segredo-test-123", path.read_bytes())
        self.assertEqual(vault.read(path), value)

    def test_vault_corruption_fails(self):
        path = self.root / "credentials.dpapi"
        path.write_bytes(b"invalid")
        with self.assertRaises(RuntimeError):
            vault.read(path)

    def test_callback_new_and_returning(self):
        self.assertEqual(validate_callback("/auth/callback?state=a&code=c&client_id=oaiapp_test", "a"), ("c", "oaiapp_test"))
        self.assertEqual(validate_callback("/auth/callback?state=a&code=c", "a", "oaiapp_test"), ("c", "oaiapp_test"))

    def test_callback_rejects_forgery(self):
        for query in ["state=b&code=c&client_id=oaiapp_test", "state=a&error=access_denied",
                      "state=a&code=c", "state=a&code=c&client_id=dynamic_agent_client",
                      "state=a&state=a&code=c&client_id=oaiapp_test"]:
            with self.subTest(query=query), self.assertRaises(AuthError):
                validate_callback("/auth/callback?" + query, "a")
        with self.assertRaises(AuthError):
            validate_callback("/auth/callback?state=a&code=c&client_id=other", "a", "oaiapp_test")

    def test_oauth_pkce_and_real_id_token_validation(self):
        auth = Auth(self.root)
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        seen = {}
        pending = {}
        doc = dict(issuer=ISSUER, authorization_endpoint=ISSUER + "/api/accounts/authorize",
                   token_endpoint=ISSUER + "/api/accounts/oauth/token",
                   jwks_uri=ISSUER + "/.well-known/jwks.json", revocation_endpoint=ISSUER + "/revoke")

        def browser(url):
            params = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
            seen.update(params)
            pending["path"] = "/auth/callback?" + urlencode(dict(
                state=params["state"], code="test-code", client_id="oaiapp_test"))
            return True

        class FakeServer:
            server_port = 54321

            def __init__(self, address, handler):
                self.handler = handler

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def handle_request(self):
                handler = object.__new__(self.handler)
                handler.path = pending["path"]
                handler.wfile = io.BytesIO()
                handler.send_response = MagicMock()
                handler.send_header = MagicMock()
                handler.end_headers = MagicMock()
                handler.do_GET()
                handler.send_response.assert_called_once_with(200)

        def request(method, url, **kwargs):
            if method == "GET":
                return doc
            form = kwargs["data"]
            challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).decode().rstrip("=")
            self.assertEqual(challenge, seen["code_challenge"])
            self.assertEqual(form["redirect_uri"], seen["redirect_uri"])
            self.assertEqual(form["client_id"], "oaiapp_test")
            claims = dict(sub="subject", email="user@example.test", iss=ISSUER, aud="oaiapp_test",
                          exp=int(time.time()) + 600, iat=int(time.time()), nonce=seen["nonce"])
            return dict(id_token=jwt.encode(claims, private, algorithm="RS256"), access_token="access",
                        refresh_token="refresh", token_type="Bearer", expires_in=3600,
                        scope="openid resource.invoke chatgpt.tokens.use.direct")
        jwks = MagicMock()
        jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=private.public_key())
        with patch("revisor.auth.HTTPServer", FakeServer), patch("revisor.auth.request_json", side_effect=request), patch("revisor.auth.webbrowser.open", side_effect=browser), patch("revisor.auth.jwt.PyJWKClient", return_value=jwks):
            message = auth.sign_in()
        self.assertIn("autorizado", message)
        self.assertEqual(seen["client_id"], "dynamic_agent_client")
        self.assertEqual(seen["resource"], RESOURCE)
        self.assertEqual(auth.access_token(), "access")
        self.assertEqual(Auth(self.root).host_id, auth.host_id)

    def seed_account(self, scopes=None, expired=False):
        auth = Auth(self.root)
        auth.save({"active": "client", "accounts": {"client": dict(client_id="client", subject="sub", email="x",
            access_token="access", refresh_token="refresh", id_token="id", expires_at=time.time() + (-1 if expired else 600),
            scopes=scopes if scopes is not None else ["resource.invoke", "chatgpt.tokens.use.direct"])}})
        return auth

    def test_identity_without_plan_cannot_infer(self):
        auth = self.seed_account(scopes=["openid"])
        with self.assertRaises(AuthError):
            auth.access_token()

    def test_refresh_preserves_and_rotates(self):
        auth = self.seed_account(expired=True)
        with patch.object(auth, "discovery", return_value={"token_endpoint": ISSUER + "/token"}), patch("revisor.auth.request_json", return_value=dict(access_token="new", refresh_token="rotated", expires_in=600)) as request:
            self.assertEqual(auth.access_token(), "new")
        self.assertNotIn("scope", request.call_args.kwargs["data"])
        self.assertEqual(auth.load()["accounts"]["client"]["refresh_token"], "rotated")

    def test_logout_clears_tokens_retains_registration(self):
        auth = self.seed_account()
        with patch.object(auth, "discovery", return_value={"revocation_endpoint": ISSUER + "/revoke"}), patch("revisor.auth.requests.post", return_value=SimpleNamespace(status_code=200)):
            auth.sign_out()
        account = auth.load()["accounts"]["client"]
        self.assertEqual(account["subject"], "sub")
        self.assertNotIn("refresh_token", account)
        self.assertIsNone(auth.load()["active"])

    def test_corpus_deduplicates_and_does_not_modify_source(self):
        corpus = Corpus(self.root / "corpus")
        source = self.root / "image.jpg"
        source.write_bytes(self.image())
        digest = sha256(source)
        corpus.import_file(source)
        corpus.import_file(source)
        self.assertEqual(len(corpus.entries()), 1)
        self.assertEqual(digest, sha256(source))
        attachment = prepare(corpus.entries()[0])
        self.assertEqual(attachment["sha256"], digest)
        self.assertTrue(attachment["data"].startswith("data:image/jpeg;base64,"))

    def test_zip_traversal_is_rejected(self):
        path = self.root / "unsafe.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../escape.jpg", self.image())
        with self.assertRaises(ValueError):
            Corpus(self.root / "corpus").import_file(path)
        self.assertFalse((self.root / "escape.jpg").exists())

    def test_zip_imports_supported_files_only(self):
        path = self.root / "safe.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("folder/photo.jpg", self.image())
            archive.writestr("ignore.exe", b"no")
        corpus = Corpus(self.root / "corpus")
        corpus.import_file(path)
        self.assertEqual([e[1] for e in corpus.entries()], ["photo.jpg"])

    def test_tampered_corpus_is_rejected(self):
        corpus = Corpus(self.root / "corpus")
        corpus.add_bytes("photo.jpg", self.image())
        entry = corpus.entries()[0]
        Path(entry[3]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            prepare(entry)

    def test_pdf_renders_only_selected_page(self):
        path = self.root / "report.pdf"
        doc = pymupdf.open()
        doc.new_page().insert_text((50, 50), "Page 1")
        doc.new_page().insert_text((50, 50), "Page 2")
        doc.save(path)
        doc.close()
        corpus = Corpus(self.root / "corpus")
        corpus.import_file(path)
        first, second = (prepare(corpus.entries()[0], p) for p in (1, 2))
        self.assertNotEqual(first["data"], second["data"])
        self.assertEqual(second["page"], 2)
        with self.assertRaises(ValueError):
            prepare(corpus.entries()[0], 3)

    def stream_client(self, events):
        client = MagicMock()
        client.responses.create.return_value.__enter__.return_value = iter(events)
        return client

    def test_inference_contract(self):
        auth = MagicMock()
        auth.access_token.return_value = "token"
        client = self.stream_client([SimpleNamespace(type="response.output_text.delta", delta="Sugestão"), SimpleNamespace(type="response.completed")])
        with patch("revisor.ai.OpenAI", return_value=client):
            self.assertEqual(ai.analyze(auth, "selected-model", "conferir", [{"name": "x", "page": 1, "sha256": "hash", "data": "data:image/jpeg;base64,abc"}]), "Sugestão")
        payload = client.responses.create.call_args.kwargs
        self.assertFalse(payload["store"])
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["model"], "selected-model")
        self.assertNotIn("max_output_tokens", payload)
        self.assertNotIn("file_search", str(payload))

    def test_incomplete_or_failed_stream_never_returns_partial_result(self):
        for terminal in (None, "response.failed", "response.incomplete", "error"):
            events = [SimpleNamespace(type="response.output_text.delta", delta="partial")]
            if terminal:
                events.append(SimpleNamespace(type=terminal))
            with self.subTest(terminal=terminal), patch("revisor.ai.OpenAI", return_value=self.stream_client(events)), self.assertRaises(AuthError):
                ai.analyze(MagicMock(), "model", "question", [])


if __name__ == "__main__":
    unittest.main()
