from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import jwt

from .events import normalize_testflight_submission

if TYPE_CHECKING:
    from .config import Settings
    from .domain import EngineeringEvent


class AppStoreConnectClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.Client(base_url=settings.appstore_api_url, timeout=60)
        self._token = ""
        self._token_created = datetime.min.replace(tzinfo=UTC)

    def close(self) -> None:
        self.client.close()

    def token(self) -> str:
        now = datetime.now(UTC)
        if self._token and now - self._token_created < timedelta(minutes=10):
            return self._token
        if not (
            self.settings.appstore_key_id
            and self.settings.appstore_issuer_id
            and self.settings.appstore_key()
        ):
            raise RuntimeError("App Store Connect credentials are not configured")
        self._token = jwt.encode(
            {
                "iss": self.settings.appstore_issuer_id,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=15)).timestamp()),
                "aud": "appstoreconnect-v1",
            },
            self.settings.appstore_key(),
            algorithm="ES256",
            headers={"kid": self.settings.appstore_key_id, "typ": "JWT"},
        )
        self._token_created = now
        return self._token

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.client.get(
            path,
            headers={"Authorization": f"Bearer {self.token()}"},
            **kwargs,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload

    def poll(self) -> list[EngineeringEvent]:
        app_id = self.settings.appstore_app_id
        if not app_id:
            raise RuntimeError("ENGINEERING_APPSTORE_APP_ID is not configured")
        events: list[EngineeringEvent] = []
        collections = (
            ("crash", f"/v1/apps/{app_id}/betaFeedbackCrashSubmissions"),
            ("screenshot", f"/v1/apps/{app_id}/betaFeedbackScreenshotSubmissions"),
        )
        for kind, path in collections:
            for submission in self._paginate(path):
                payload = dict(submission)
                payload["kind"] = kind
                crash_log = self._crash_log(submission) if kind == "crash" else ""
                events.append(
                    normalize_testflight_submission(payload, self.settings.repository, crash_log)
                )
        return events

    def _paginate(self, path: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        next_path: str | None = path
        while next_path and len(results) < 1000:
            payload = self.get(next_path, params={"limit": 200} if next_path == path else None)
            results.extend(payload.get("data") or [])
            next_path = (payload.get("links") or {}).get("next")
        return results

    def _crash_log(self, submission: dict[str, Any]) -> str:
        relationship = ((submission.get("relationships") or {}).get("betaCrashLog") or {}).get(
            "data"
        ) or {}
        log_id = relationship.get("id")
        if not log_id:
            return ""
        payload = self.get(f"/v1/betaCrashLogs/{log_id}")
        attributes = (payload.get("data") or {}).get("attributes") or {}
        return str(attributes.get("crashLog") or attributes.get("log") or "")
