"""YAHOO_REFRESH_TOKEN env seeding — headless (HF Spaces) Yahoo auth.

Deployed backends have no browser and no persisted token file; a refresh
token minted once locally and set as an env secret must be enough to boot
the OAuth manager into a refreshable state.
"""

import json

from src.yahoo_oauth import YahooOAuth


class TestEnvSeed:
    def test_seeds_refresh_token_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YAHOO_REFRESH_TOKEN", "rt-123")
        mgr = YahooOAuth(
            client_id="cid",
            client_secret="cs",
            token_path=str(tmp_path / "missing.json"),
        )
        assert mgr._tokens == {"refresh_token": "rt-123"}
        # No access token / expiry → first get_access_token() takes the
        # refresh path instead of failing with "re-auth required".
        assert mgr._is_expired() is True

    def test_no_seed_without_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YAHOO_REFRESH_TOKEN", raising=False)
        mgr = YahooOAuth(
            client_id="cid",
            client_secret="cs",
            token_path=str(tmp_path / "missing.json"),
        )
        assert mgr._tokens == {}

    def test_token_file_takes_precedence_over_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YAHOO_REFRESH_TOKEN", "rt-env")
        token_file = tmp_path / "tokens.json"
        token_file.write_text(json.dumps({"refresh_token": "rt-file"}))
        mgr = YahooOAuth(
            client_id="cid", client_secret="cs", token_path=str(token_file)
        )
        assert mgr._tokens["refresh_token"] == "rt-file"
