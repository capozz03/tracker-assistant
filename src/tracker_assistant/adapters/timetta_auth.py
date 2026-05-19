"""OAuth2 client-credentials token manager for Timetta API.

Fetches access tokens from https://auth.timetta.com/connect/token using the
client_credentials grant and caches them in cache/token.json. Tokens are
refreshed automatically when within REFRESH_BUFFER_SECONDS of expiry.

Usage:
    auth = TimettaAuth(root=Path("."), client_id="...", client_secret="...")
    adapter = TimettaAdapter(auth=auth)
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://auth.timetta.com/connect/token"
_REFRESH_BUFFER_SECONDS = 60


class TimettaAuth:
    """Manages OAuth2 client_credentials access tokens with local file cache."""

    def __init__(
        self,
        root: Path,
        client_id: str,
        client_secret: str,
        scope: str = "",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._cache_file = root / "cache" / "token.json"

    def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token, refreshing from the auth server if needed."""
        if not force_refresh:
            cached = self._load_cache()
            if cached is not None:
                logger.debug("[FIX] token cache hit")
                return cached
        logger.debug("[FIX] token %s — fetching from %s", "force-refresh" if force_refresh else "cache miss", _TOKEN_URL)
        return self._fetch_and_cache()

    def _load_cache(self) -> str | None:
        if not self._cache_file.exists():
            return None
        try:
            data: dict[str, Any] = json.loads(self._cache_file.read_text(encoding="utf-8"))
            expires_at = datetime.fromisoformat(data["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
            if remaining > _REFRESH_BUFFER_SECONDS:
                return data["access_token"]
            logger.debug("[FIX] token: cached token expires in %.0fs — refreshing", remaining)
        except (KeyError, ValueError, OSError) as exc:
            logger.debug("[FIX] token: cache read error: %s", exc)
        return None

    def _fetch_and_cache(self) -> str:
        payload: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if self._scope:
            payload["scope"] = self._scope
        body = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            _TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            logger.error("[FIX] token: refresh failed status=%d body=%s", exc.code, body_text)
            raise RuntimeError(f"Timetta token refresh failed → {exc.code}: {body_text}") from exc

        access_token: str = result["access_token"]
        expires_in: int = int(result.get("expires_in", 3600))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache_file.write_text(
            json.dumps(
                {"access_token": access_token, "expires_at": expires_at.isoformat()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger.debug("[FIX] token: fetched and cached (expires_in=%ds)", expires_in)
        return access_token
