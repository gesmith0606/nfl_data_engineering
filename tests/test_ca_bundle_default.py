"""nflverse downloads must not depend on the OS certificate store.

2026-11-03 / 11-10: on the Windows PC every Bronze ingest failed with
``CERTIFICATE_VERIFY_FAILED: unable to get issuer certificate`` until
``SSL_CERT_FILE`` was pointed at certifi's bundle by hand, and each ingest
then "succeeded" with 0 rows (the error is swallowed per season), so the
week's board silently could not be built.
"""

from __future__ import annotations

import sys
from pathlib import Path

import certifi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import nfl_data_adapter  # noqa: E402


def test_sets_certifi_bundle_when_unset(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    nfl_data_adapter.ensure_ca_bundle()
    import os

    assert os.environ["SSL_CERT_FILE"] == certifi.where()


def test_respects_an_explicit_bundle(monkeypatch, tmp_path):
    custom = tmp_path / "corp-ca.pem"
    custom.write_text("x")
    monkeypatch.setenv("SSL_CERT_FILE", str(custom))
    nfl_data_adapter.ensure_ca_bundle()
    import os

    assert os.environ["SSL_CERT_FILE"] == str(custom)


def test_any_configured_ca_wins_over_certifi(monkeypatch):
    # Review 2026-11-10: a corporate root set via REQUESTS_CA_BUNDLE /
    # SSL_CERT_DIR must not be silently replaced by certifi's public roots.
    import os

    for var in ("SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        for other in ("SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
            monkeypatch.delenv(other, raising=False)
        monkeypatch.setenv(var, "/etc/corp")
        nfl_data_adapter.ensure_ca_bundle()
        assert "SSL_CERT_FILE" not in os.environ, var
