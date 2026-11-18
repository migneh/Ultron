"""
tests/test_dashboard_certs.py — the certificate the phone dashboard depends on.

Every install generates its own self-signed pair on first run (a private key
shipped in a repository is the same as no private key at all). The question this
file guards is narrower: does the app know whether that pair *works*?

It used to answer by `Path.exists()`. Reproduced: truncate `ultron.crt` in half —
exactly what a crash during first-run generation leaves behind — and

    _ssl_enabled()  -> True      # QR code keeps saying https://
    _ensure_certs() -> True      # nothing thinks there is a problem
    ssl.load_cert_chain(...)     -> SSLError: [SSL] PEM lib

so uvicorn refused to bind, the failure was one line of stdout, and the Remote
Control panel went on handing out a URL for a port that answered nothing. The
same pair is now validated by the very call uvicorn makes, and an unusable or
expired certificate is replaced instead of trusted.

Everything runs against a temporary directory: the machine's real
config/certs is never read or written.
"""
from __future__ import annotations

import datetime
import ssl
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard import server as ds

try:
    import cryptography                                     # noqa: F401
    _HAVE_CRYPTO = True
except Exception:                                            # pragma: no cover
    _HAVE_CRYPTO = False

needs_crypto = unittest.skipUnless(_HAVE_CRYPTO, "cryptography not installed")
needs_dashboard = unittest.skipUnless(ds._DEPS_OK, "fastapi/uvicorn not installed")


class _TempCerts(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._saved = ds.BASE_DIR
        ds.BASE_DIR = Path(self._dir.name)
        self.certs = ds.BASE_DIR / "config" / "certs"

    def tearDown(self):
        ds.BASE_DIR = self._saved
        self._dir.cleanup()

    def loads(self, key: Path, crt: Path) -> None:
        """Raises if Python cannot start a TLS server with this pair."""
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
            certfile=str(crt), keyfile=str(key))


@needs_crypto
class FirstRunTests(_TempCerts):
    def test_first_run_produces_a_pair_that_loads(self):
        self.assertTrue(ds._ensure_certs())
        self.loads(self.certs / "ultron.key", self.certs / "ultron.crt")

    def test_the_pair_is_the_one_the_server_would_use(self):
        ds._ensure_certs()
        pair = ds._tls_pair()
        self.assertIsNotNone(pair)
        self.assertEqual([p.name for p in pair], ["ultron.key", "ultron.crt"])
        self.assertTrue(ds.DashboardServer._ssl_enabled())

    def test_the_private_key_is_not_world_readable(self):
        if sys.platform == "win32":                     # chmod is a no-op there
            self.skipTest("POSIX permissions only")
        ds._ensure_certs()
        mode = (self.certs / "ultron.key").stat().st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o600)

    def test_the_certificate_covers_localhost_and_loopback(self):
        from cryptography import x509
        ds._ensure_certs()
        cert = x509.load_pem_x509_certificate((self.certs / "ultron.crt").read_bytes())
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value
        self.assertIn("localhost", san.get_values_for_type(x509.DNSName))
        self.assertIn("127.0.0.1",
                      [str(ip) for ip in san.get_values_for_type(x509.IPAddress)])

    def test_the_certificate_lasts_years_not_days(self):
        from cryptography import x509
        ds._ensure_certs()
        cert = x509.load_pem_x509_certificate((self.certs / "ultron.crt").read_bytes())
        expires = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        self.assertGreater(expires - datetime.datetime.now(datetime.timezone.utc),
                           datetime.timedelta(days=365))

    def test_a_second_call_changes_nothing(self):
        ds._ensure_certs()
        before = (self.certs / "ultron.crt").read_bytes()
        self.assertTrue(ds._ensure_certs())
        self.assertEqual((self.certs / "ultron.crt").read_bytes(), before)


@needs_crypto
class BrokenPairTests(_TempCerts):
    def _half_write(self, name: str) -> None:
        ds._ensure_certs()
        path = self.certs / name
        data = path.read_bytes()
        path.write_bytes(data[: len(data) // 2])

    def test_a_half_written_certificate_is_not_reported_as_usable(self):
        self._half_write("ultron.crt")
        self.assertIsNone(ds._tls_pair())
        self.assertFalse(ds.DashboardServer._ssl_enabled(),
                         "the QR code would advertise https:// on a dead port")

    def test_a_half_written_certificate_is_replaced(self):
        self._half_write("ultron.crt")
        broken = (self.certs / "ultron.crt").read_bytes()

        self.assertTrue(ds._ensure_certs())

        self.assertNotEqual((self.certs / "ultron.crt").read_bytes(), broken)
        self.loads(self.certs / "ultron.key", self.certs / "ultron.crt")
        self.assertTrue(ds.DashboardServer._ssl_enabled())

    def test_a_half_written_key_is_replaced(self):
        self._half_write("ultron.key")
        self.assertIsNone(ds._tls_pair())
        self.assertTrue(ds._ensure_certs())
        self.loads(self.certs / "ultron.key", self.certs / "ultron.crt")

    def test_an_expired_certificate_is_replaced(self):
        self.certs.mkdir(parents=True, exist_ok=True)
        # A valid pair, then re-issued with dates in the past.
        ds._ensure_certs()
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        who = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ultron Dashboard")])
        now = datetime.datetime.now(datetime.timezone.utc)
        expired = (
            x509.CertificateBuilder().subject_name(who).issuer_name(who)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=400))
            .not_valid_after(now - datetime.timedelta(days=35))
            .sign(key, hashes.SHA256())
        )
        (self.certs / "ultron.key").write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()))
        (self.certs / "ultron.crt").write_bytes(
            expired.public_bytes(serialization.Encoding.PEM))

        self.loads(self.certs / "ultron.key", self.certs / "ultron.crt")   # it does load
        self.assertIsNone(ds._tls_pair(), "an expired certificate is not a usable one")

        self.assertTrue(ds._ensure_certs())
        cert = x509.load_pem_x509_certificate((self.certs / "ultron.crt").read_bytes())
        expires = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        self.assertGreater(expires, now)


@needs_crypto
class LegacyPairTests(_TempCerts):
    def test_an_old_jarvis_pair_is_still_honoured(self):
        self.certs.mkdir(parents=True, exist_ok=True)
        ds._ensure_certs()                                   # produces ultron.*
        (self.certs / "jarvis.key").write_bytes((self.certs / "ultron.key").read_bytes())
        (self.certs / "jarvis.crt").write_bytes((self.certs / "ultron.crt").read_bytes())
        (self.certs / "ultron.key").unlink()
        (self.certs / "ultron.crt").unlink()

        self.assertEqual([p.name for p in ds._tls_pair()], ["jarvis.key", "jarvis.crt"])
        self.assertTrue(ds._ensure_certs())
        self.assertFalse((self.certs / "ultron.crt").exists(),
                         "an existing jarvis pair must not be silently replaced")


@needs_crypto
@needs_dashboard
class UrlTests(_TempCerts):
    """get_url() decides what the QR code says, so it must not guess."""

    def _server(self):
        # Only _ip and the certificate state are read by the URL helpers.
        srv = ds.DashboardServer.__new__(ds.DashboardServer)
        srv._ip = "192.168.1.5"
        return srv

    def test_no_certificate_means_an_http_url(self):
        srv = self._server()
        self.assertEqual(srv.get_url(), "http://192.168.1.5:8000")
        self.assertEqual(srv.get_manual_url(), "192.168.1.5:8000")

    def test_a_usable_certificate_means_an_https_url(self):
        ds._ensure_certs()
        srv = self._server()
        self.assertEqual(srv.get_url(), "https://192.168.1.5:8000")
        self.assertEqual(srv.get_manual_url(), "192.168.1.5:8001")

    def test_a_broken_certificate_falls_back_to_the_http_url(self):
        ds._ensure_certs()
        crt = self.certs / "ultron.crt"
        crt.write_bytes(crt.read_bytes()[:50])
        self.assertEqual(self._server().get_url(), "http://192.168.1.5:8000")


if __name__ == "__main__":
    unittest.main(verbosity=2)
