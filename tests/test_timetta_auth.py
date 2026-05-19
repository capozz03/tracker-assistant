from __future__ import annotations

import io
import json
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracker_assistant.adapters.timetta_adapter import TimettaAdapter
from tracker_assistant.adapters.timetta_auth import TimettaAuth


def _make_auth(root: Path, scope: str = "") -> TimettaAuth:
    return TimettaAuth(root=root, client_id="cid", client_secret="csecret", scope=scope)


def _token_response(token: str = "fresh-token", expires_in: int = 3600) -> MagicMock:
    body = json.dumps({"access_token": token, "expires_in": expires_in}).encode()
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = body
    return mock


def _write_cache(cache_file: Path, token: str, expires_at: datetime) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"access_token": token, "expires_at": expires_at.isoformat()}),
        encoding="utf-8",
    )


class TestGetTokenCacheMiss:
    def test_fetches_token_when_no_cache_file(self, tmp_path):
        auth = _make_auth(tmp_path)
        with patch("urllib.request.urlopen", return_value=_token_response("tok-1")) as m:
            token = auth.get_token()
        assert token == "tok-1"
        assert m.call_count == 1

    def test_writes_cache_after_fetch(self, tmp_path):
        auth = _make_auth(tmp_path)
        with patch("urllib.request.urlopen", return_value=_token_response("tok-2")):
            auth.get_token()
        cache_file = tmp_path / "cache" / "token.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["access_token"] == "tok-2"
        assert "expires_at" in data

    def test_posts_to_correct_url(self, tmp_path):
        auth = _make_auth(tmp_path)
        urls: list[str] = []

        def fake_urlopen(req):
            urls.append(req.full_url)
            return _token_response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            auth.get_token()

        assert urls[0] == "https://auth.timetta.com/connect/token"

    def test_sends_client_credentials_grant(self, tmp_path):
        auth = _make_auth(tmp_path)
        bodies: list[bytes] = []

        def fake_urlopen(req):
            bodies.append(req.data)
            return _token_response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            auth.get_token()

        import urllib.parse
        params = dict(urllib.parse.parse_qsl(bodies[0].decode()))
        assert params["grant_type"] == "client_credentials"
        assert params["client_id"] == "cid"
        assert params["client_secret"] == "csecret"
        assert "scope" not in params

    def test_sends_scope_when_provided(self, tmp_path):
        auth = _make_auth(tmp_path, scope="api.read")
        bodies: list[bytes] = []

        def fake_urlopen(req):
            bodies.append(req.data)
            return _token_response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            auth.get_token()

        import urllib.parse
        params = dict(urllib.parse.parse_qsl(bodies[0].decode()))
        assert params["scope"] == "api.read"


class TestGetTokenCacheHit:
    def test_returns_cached_token_without_network(self, tmp_path):
        auth = _make_auth(tmp_path)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        _write_cache(tmp_path / "cache" / "token.json", "cached-tok", future)

        with patch("urllib.request.urlopen") as m:
            token = auth.get_token()

        assert token == "cached-tok"
        m.assert_not_called()

    def test_cache_near_expiry_triggers_refresh(self, tmp_path):
        auth = _make_auth(tmp_path)
        # expires in 30 seconds — within the 60-second buffer
        near_expiry = datetime.now(timezone.utc) + timedelta(seconds=30)
        _write_cache(tmp_path / "cache" / "token.json", "old-tok", near_expiry)

        with patch("urllib.request.urlopen", return_value=_token_response("new-tok")) as m:
            token = auth.get_token()

        assert token == "new-tok"
        assert m.call_count == 1

    def test_expired_cache_triggers_refresh(self, tmp_path):
        auth = _make_auth(tmp_path)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        _write_cache(tmp_path / "cache" / "token.json", "expired-tok", past)

        with patch("urllib.request.urlopen", return_value=_token_response("refreshed-tok")) as m:
            token = auth.get_token()

        assert token == "refreshed-tok"
        assert m.call_count == 1

    def test_corrupt_cache_file_triggers_refresh(self, tmp_path):
        auth = _make_auth(tmp_path)
        cache_file = tmp_path / "cache" / "token.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("not-json", encoding="utf-8")

        with patch("urllib.request.urlopen", return_value=_token_response("fresh-tok")) as m:
            token = auth.get_token()

        assert token == "fresh-tok"
        assert m.call_count == 1


class TestForceRefresh:
    def test_bypasses_valid_cache(self, tmp_path):
        auth = _make_auth(tmp_path)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        _write_cache(tmp_path / "cache" / "token.json", "cached-tok", future)

        with patch("urllib.request.urlopen", return_value=_token_response("force-tok")) as m:
            token = auth.get_token(force_refresh=True)

        assert token == "force-tok"
        assert m.call_count == 1

    def test_updates_cache_after_force_refresh(self, tmp_path):
        auth = _make_auth(tmp_path)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        cache_file = tmp_path / "cache" / "token.json"
        _write_cache(cache_file, "old-tok", future)

        with patch("urllib.request.urlopen", return_value=_token_response("new-tok")):
            auth.get_token(force_refresh=True)

        data = json.loads(cache_file.read_text())
        assert data["access_token"] == "new-tok"


class TestFetchErrors:
    def test_raises_runtime_error_on_http_error(self, tmp_path):
        auth = _make_auth(tmp_path)
        err = urllib.error.HTTPError(
            url="https://auth.timetta.com/connect/token",
            code=400,
            msg="Bad Request",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":"invalid_client"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError, match="400"):
                auth.get_token()

    def test_error_message_includes_status_code(self, tmp_path):
        auth = _make_auth(tmp_path)
        err = urllib.error.HTTPError(
            url="https://auth.timetta.com/connect/token",
            code=401,
            msg="Unauthorized",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":"unauthorized_client"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError, match="401"):
                auth.get_token()


class TestAdapterRetryOn401:
    def _make_auth_with_token(self, tmp_path: Path, token: str) -> TimettaAuth:
        auth = _make_auth(tmp_path)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        _write_cache(tmp_path / "cache" / "token.json", token, future)
        return auth

    def _mock_response(self, payload: dict) -> MagicMock:
        body = json.dumps(payload).encode()
        mock = MagicMock()
        mock.__enter__ = lambda s: s
        mock.__exit__ = MagicMock(return_value=False)
        mock.read.return_value = body
        return mock

    def test_retries_once_on_401_with_fresh_token(self, tmp_path):
        auth = self._make_auth_with_token(tmp_path, "expired-token")
        adapter = TimettaAdapter(auth=auth)

        call_count = 0

        def fake_urlopen(req):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: 401 (simulates expired token on API side)
                raise urllib.error.HTTPError(
                    url=req.full_url,
                    code=401,
                    msg="Unauthorized",
                    hdrs=None,  # type: ignore[arg-type]
                    fp=io.BytesIO(b'{"error":"expired_token"}'),
                )
            # Second call: success after token refresh
            return self._mock_response({"value": [{"id": "p1"}]})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with patch.object(auth, "_fetch_and_cache", return_value="refreshed-token") as mock_fetch:
                result = adapter.get_projects()

        assert call_count == 2
        assert mock_fetch.call_count == 1
        assert result == [{"id": "p1"}]

    def test_does_not_retry_twice_on_repeated_401(self, tmp_path):
        auth = self._make_auth_with_token(tmp_path, "bad-token")
        adapter = TimettaAdapter(auth=auth)

        def always_401(req):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=401,
                msg="Unauthorized",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"error":"unauthorized"}'),
            )

        with patch("urllib.request.urlopen", side_effect=always_401):
            with patch.object(auth, "_fetch_and_cache", return_value="still-bad"):
                with pytest.raises(RuntimeError, match="401"):
                    adapter.get_projects()

    def test_static_token_adapter_does_not_retry_on_401(self):
        adapter = TimettaAdapter(token="static-token")

        def always_401(req):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=401,
                msg="Unauthorized",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"error":"unauthorized"}'),
            )

        call_count = 0

        def counting_401(req):
            nonlocal call_count
            call_count += 1
            always_401(req)

        with patch("urllib.request.urlopen", side_effect=counting_401):
            with pytest.raises(RuntimeError, match="401"):
                adapter.get_projects()

        assert call_count == 1  # no retry for static token
