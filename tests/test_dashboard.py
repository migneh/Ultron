"""
tests/test_dashboard.py — the phone dashboard: it must import, and it must not
answer anything without a token.

`dashboard/server.py` used to fail at import:

    _GLOBAL_DASHBOARD: "DashboardServer" | None = None

That module has no `from __future__ import annotations`, so the union was evaluated
at runtime and `str | None` raised TypeError. main.py wraps dashboard startup in
`except Exception`, so the failure surfaced as one line — "Dashboard disabled" — and
the entire phone remote (QR pairing, uploads, clipboard, websockets) never worked.

Requires fastapi + python-multipart; skipped cleanly where they are absent.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient
    import dashboard.server as S
    DASHBOARD_AVAILABLE = True
except Exception:                     # fastapi/uvicorn not installed in this env
    DASHBOARD_AVAILABLE = False

PROTECTED = [
    ("get", "/api/files", None),
    ("get", "/api/clipboard", None),
    ("get", "/api/tts?text=hi", None),
    ("get", "/uploads/anything.txt", None),
    ("post", "/api/command", {"text": "shutdown"}),
    ("post", "/api/wake", {}),
    ("post", "/api/pc-control", {"action": "lock"}),
    ("post", "/api/revoke-devices", {}),
    ("post", "/api/clipboard", {"text": "x"}),
]


@unittest.skipUnless(DASHBOARD_AVAILABLE, "fastapi not installed")
class DashboardImportTests(unittest.TestCase):
    def test_module_imports_at_all(self):
        self.assertTrue(hasattr(S, "DashboardServer"))
        self.assertGreater(len(S.DashboardServer().app.routes), 10)

    def test_global_accessor_tracks_the_latest_instance(self):
        """The accessor is how other modules find the running server.

        Asserting `is None` here would depend on whether another test already
        constructed one — assert the identity instead.
        """
        srv = S.DashboardServer()
        self.assertIs(S.get_dashboard(), srv)


@unittest.skipUnless(DASHBOARD_AVAILABLE, "fastapi not installed")
class DashboardAuthTests(unittest.TestCase):
    def setUp(self):
        self.srv = S.DashboardServer()
        self.srv._uploads_dir = Path(tempfile.mkdtemp())
        self.srv._uploads_dir.mkdir(parents=True, exist_ok=True)
        self.client = TestClient(self.srv.app)

    def tearDown(self):
        self.srv._uploads_dir = S.UPLOADS_DIR

    def _token(self) -> str:
        pin = self.srv.new_key()
        response = self.client.post("/login", json={"pin": pin})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["token"]

    def test_every_protected_endpoint_refuses_anonymous_callers(self):
        for method, path, payload in PROTECTED:
            with self.subTest(endpoint=f"{method.upper()} {path}"):
                r = getattr(self.client, method)(path, json=payload) if payload is not None \
                    else getattr(self.client, method)(path)
                self.assertEqual(r.status_code, 401, f"{path} answered {r.status_code}: {r.text[:120]}")

    def test_forged_bearer_token_is_refused(self):
        r = self.client.get("/api/files", headers={"Authorization": "Bearer not-a-real-token"})
        self.assertEqual(r.status_code, 401)

    def test_valid_token_is_accepted(self):
        r = self.client.get("/api/files", headers={"Authorization": f"Bearer {self._token()}"})
        self.assertEqual(r.status_code, 200)

    def test_login_pin_is_single_use(self):
        pin = self.srv.new_key()
        first = self.client.post("/login", json={"pin": pin})
        second = self.client.post("/login", json={"pin": pin})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 401, "a consumed pairing PIN was accepted twice")

    def test_expired_pin_is_refused(self):
        try:
            pin = self.srv.new_key(expiry_secs=-1)
        except TypeError:
            self.skipTest("new_key() takes no expiry argument")
        r = self.client.post("/login", json={"pin": pin})
        self.assertEqual(r.status_code, 401, "an expired pairing PIN was accepted")

    def test_websocket_requires_a_token(self):
        for url in ("/ws", "/ws?token=bogus"):
            with self.subTest(url=url):
                with self.assertRaises(Exception):
                    with self.client.websocket_connect(url) as ws:
                        ws.receive()


@unittest.skipUnless(DASHBOARD_AVAILABLE, "fastapi not installed")
class DashboardUploadTests(unittest.TestCase):
    def setUp(self):
        try:
            import python_multipart  # noqa: F401
        except ImportError:
            self.skipTest("python-multipart not installed — uploads are disabled")
        self.srv = S.DashboardServer()
        self.srv._uploads_dir = Path(tempfile.mkdtemp())
        self.srv._uploads_dir.mkdir(parents=True, exist_ok=True)
        self.client = TestClient(self.srv.app)
        pin = self.srv.new_key()
        self.headers = {"Authorization":
                        f"Bearer {self.client.post('/login', json={'pin': pin}).json()['token']}"}

    def tearDown(self):
        self.srv._uploads_dir = S.UPLOADS_DIR

    def test_upload_lands_inside_the_uploads_directory(self):
        r = self.client.post("/api/upload", headers=self.headers,
                             files={"file": ("note.txt", b"hello", "text/plain")})
        self.assertEqual(r.status_code, 200, r.text)
        name = r.json()["name"]
        self.assertTrue((self.srv._uploads_dir / name).exists())

    def test_upload_filename_cannot_escape_the_directory(self):
        r = self.client.post("/api/upload", headers=self.headers,
                             files={"file": ("../../evil.txt", b"pwn", "text/plain")})
        self.assertEqual(r.status_code, 200, r.text)
        saved = r.json()["name"]
        self.assertNotIn("/", saved)
        self.assertNotIn("..", saved)
        self.assertEqual(sorted(p.name for p in self.srv._uploads_dir.iterdir()), [saved])
        self.assertFalse((self.srv._uploads_dir.parent.parent / "evil.txt").exists())

    def test_download_requires_a_token(self):
        r = self.client.get("/uploads/note.txt")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
