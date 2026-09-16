"""Deployed-API smoke tests (see conftest for scope and rules)."""

import uuid

import httpx
import pytest

from .conftest import PUBLIC_SLUG, SETUP_TOKEN, requires_base_url

pytestmark = pytest.mark.deployed

BOGUS_TOKEN = "0" * 32
# A slug that is guaranteed not to resolve: reserved prefix + fresh UUID.
NONEXISTENT_SLUG = f"mtp-ci-{uuid.uuid4().hex[:12]}"


@requires_base_url
def test_health_returns_ok(api: httpx.Client) -> None:
    resp = api.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body.get("environment"), str)


@requires_base_url
def test_ready_probe_reports_dependency_checks(api: httpx.Client) -> None:
    resp = api.get("/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["status"] in ("ready", "degraded", "not_ready")
    if resp.status_code == 200:
        assert set(body["checks"]) == {"postgres", "qdrant"}


@requires_base_url
def test_auth_token_rejects_bad_credentials(api: httpx.Client) -> None:
    resp = api.post(
        "/auth/token",
        json={"email": "mtp-ci-nobody@example.com", "password": "not-a-password"},
    )
    assert resp.status_code == 401
    assert "detail" in resp.json()


@requires_base_url
def test_protected_endpoints_require_auth(api: httpx.Client) -> None:
    # Tenant-status (subscription gate) and payments status must both reject
    # unauthenticated callers rather than leaking data or 500ing.
    assert api.get("/auth/tenant-status").status_code == 401
    assert api.get("/payments/status").status_code == 401


@requires_base_url
def test_public_config_unknown_slug_is_404(api: httpx.Client) -> None:
    resp = api.get(f"/businesses/{NONEXISTENT_SLUG}/public-config")
    assert resp.status_code == 404


@requires_base_url
def test_public_docs_bogus_token_is_404(api: httpx.Client) -> None:
    for kind in ("quote", "invoice"):
        resp = api.get(f"/public/{kind}/{BOGUS_TOKEN}")
        assert resp.status_code == 404, kind


@requires_base_url
def test_public_docs_unknown_kind_is_404(api: httpx.Client) -> None:
    resp = api.get(f"/public/widget/{BOGUS_TOKEN}")
    assert resp.status_code == 404


@requires_base_url
def test_resend_webhook_rejects_bad_signature(api: httpx.Client) -> None:
    # With the webhook secret configured a bad signature is a clean 401;
    # without it the endpoint is a clean 503. Never a 500.
    resp = api.post("/webhooks/resend", json={"type": "email.sent"})
    assert resp.status_code in (401, 503)
    assert "detail" in resp.json()


@requires_base_url
def test_intake_unknown_slug_is_404_without_writes(api: httpx.Client) -> None:
    resp = api.post(
        f"/businesses/{NONEXISTENT_SLUG}/quote-requests",
        json={
            "contact": {"name": "MTP CI", "email": "mtp-ci@example.com"},
            "raw_text": "CI smoke test - must never be stored",
            "sync_check": False,
        },
    )
    assert resp.status_code == 404


@requires_base_url
def test_openapi_docs_available(api: httpx.Client) -> None:
    resp = api.get("/docs")
    assert resp.status_code == 200


@requires_base_url
def test_public_config_seeded_slug_contract(api: httpx.Client) -> None:
    if not PUBLIC_SLUG:
        pytest.skip("TEST_PUBLIC_SLUG is not set (seeded tenant unknown)")
    resp = api.get(f"/businesses/{PUBLIC_SLUG}/public-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == PUBLIC_SLUG
    assert "name" in body


@requires_base_url
def test_intake_ack_under_throwaway_tenant(api: httpx.Client) -> None:
    """Create a tenant via the setup token and submit a public quote request.

    Skipped unless TEST_SETUP_TOKEN is provided. Note: submitting an intake
    schedules the background AI auto-draft against the target environment's
    LLM config, so this test must NOT run in CI (no live LLM calls).
    """
    if not SETUP_TOKEN:
        pytest.skip("TEST_SETUP_TOKEN is not set (refusing to write to a shared deployment)")

    slug = f"mtp-ci-{uuid.uuid4().hex[:10]}"
    tenant = api.post(
        "/tenants",
        headers={"X-Setup-Token": SETUP_TOKEN},
        json={
            "slug": slug,
            "name": "MTP CI Throwaway",
            "admin_email": f"mtp-ci-{uuid.uuid4().hex[:8]}@example.com",
            "admin_password": uuid.uuid4().hex,
            "admin_name": "MTP CI",
        },
    )
    assert tenant.status_code == 201, tenant.text
    resp = api.post(
        f"/businesses/{slug}/quote-requests",
        json={
            "contact": {"name": "MTP CI", "email": "mtp-ci@example.com"},
            "raw_text": "Replace a single socket in the kitchen.",
            "category": "sockets",
            "sync_check": False,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "id" in body and "reference" in body
    assert body["status"] in ("new", "received", "open", "pending")
    # sync_check=false means no inline AI check is awaited in the ack.
    assert body.get("ai_check") is None
    # No cleanup endpoint exists; the tenant is throwaway and only ever lives
    # in an ephemeral PR environment (or a local dev database).
