"""Unit tests for idempotent Supabase user creation."""

from types import SimpleNamespace
from typing import Any

import pytest
from app import supabase


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
        self.headers = {"content-type": "application/json"}

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Scripted httpx.Client stand-in; pops one queued response per request."""

    def __init__(self) -> None:
        self.queue: list[_FakeResponse] = []
        self.requests: list[tuple[str, str, Any]] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(self, url: str, headers: Any = None, json: Any = None) -> _FakeResponse:
        self.requests.append(("POST", url, json))
        return self.queue.pop(0)

    def get(self, url: str, headers: Any = None, params: Any = None) -> _FakeResponse:
        self.requests.append(("GET", url, params))
        return self.queue.pop(0)

    def put(self, url: str, headers: Any = None, json: Any = None) -> _FakeResponse:
        self.requests.append(("PUT", url, json))
        return self.queue.pop(0)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(
        "app.supabase.settings",
        SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role",
            supabase_anon_key="anon",
        ),
    )
    # conftest autouse forces is_supabase_configured() False; re-enable it here
    # (this fixture runs after the autouse one, so the patch wins).
    monkeypatch.setattr("app.supabase.is_supabase_configured", lambda: True)
    monkeypatch.setattr("app.supabase.httpx.Client", lambda: client)
    return client


def test_create_user_returns_new_user(fake_client: _FakeClient) -> None:
    fake_client.queue.append(_FakeResponse(201, {"id": "uid-1"}))

    user = supabase.admin_create_user("a@b.co", "pw", full_name="A", role="admin", tenant_id="t-1")

    assert user["id"] == "uid-1"
    method, url, body = fake_client.requests[0]
    assert method == "POST" and url.endswith("/admin/users")
    assert body["user_metadata"] == {"full_name": "A", "role": "admin", "tenant_id": "t-1"}


def test_create_user_adopts_existing_on_email_exists(fake_client: _FakeClient) -> None:
    fake_client.queue.extend(
        [
            _FakeResponse(422, {"code": 422, "error_code": "email_exists"}),
            _FakeResponse(
                200,
                {
                    "users": [
                        {"id": "uid-9", "email": "A@B.CO", "user_metadata": {"role": "customer"}}
                    ]
                },
            ),
            _FakeResponse(200, {"id": "uid-9"}),
        ]
    )

    user = supabase.admin_create_user("a@b.co", "new-pw", full_name="A", role="admin")

    assert user["id"] == "uid-9"
    # lookup (case-insensitive) then adoption PUT with merged metadata
    assert fake_client.requests[1][0] == "GET"
    method, url, body = fake_client.requests[2]
    assert method == "PUT" and url.endswith("/admin/users/uid-9")
    assert body["password"] == "new-pw"
    assert body["email_confirm"] is True
    assert body["user_metadata"] == {"role": "admin", "full_name": "A"}


def test_create_user_raises_when_adoption_finds_no_match(
    fake_client: _FakeClient,
) -> None:
    fake_client.queue.extend(
        [
            _FakeResponse(422, {"code": 422, "error_code": "email_exists"}),
            _FakeResponse(200, {"users": []}),
        ]
    )

    with pytest.raises(RuntimeError, match="Failed to create Supabase user"):
        supabase.admin_create_user("a@b.co", "pw")


def test_create_user_raises_on_unexpected_status(fake_client: _FakeClient) -> None:
    fake_client.queue.append(_FakeResponse(500, {"msg": "boom"}))

    with pytest.raises(RuntimeError, match="Failed to create Supabase user: 500"):
        supabase.admin_create_user("a@b.co", "pw")
