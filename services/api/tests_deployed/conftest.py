"""Smoke tests against a deployed API instance (Railway PR environment).

These tests are kept separate from ``services/api/tests`` on purpose: that
suite runs the app in-process against a throwaway Postgres, while this one
hits a live deployment over HTTP using only request/response contracts. They
never run as part of the default ``pytest`` invocation (the ``deployed`` and
``deployed_write`` markers are excluded in ``pyproject.toml``) and require
``TEST_API_BASE_URL``.

Hard rules (see docs/ci-pr-environments.md):
- read-only against any shared deployment; writes only ever happen under a
  throwaway tenant created with ``TEST_SETUP_TOKEN`` (skipped otherwise);
- no AI generation, Paddle checkout, or Stripe calls are triggered.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

API_BASE_URL = os.environ.get("TEST_API_BASE_URL", "").rstrip("/")
# Optional: slug of a seeded tenant whose public config can be asserted on.
PUBLIC_SLUG = os.environ.get("TEST_PUBLIC_SLUG", "")
# Optional: setup token allowing creation of a throwaway tenant for the
# intake test. When unset, that test skips (and no LLM-backed background
# auto-draft can ever fire from CI).
SETUP_TOKEN = os.environ.get("TEST_SETUP_TOKEN", "")
# Webhook secrets, resolved from the target environment (CI fetches them from
# Railway; locally: `railway variable list`). Write-suite webhook tests skip
# without them — a test can never invent a valid signature.
STRIPE_WEBHOOK_SECRET = os.environ.get("TEST_STRIPE_WEBHOOK_SECRET", "")
PADDLE_WEBHOOK_SECRET = os.environ.get("TEST_PADDLE_WEBHOOK_SECRET", "")
RESEND_WEBHOOK_SECRET = os.environ.get("TEST_RESEND_WEBHOOK_SECRET", "")
# Optional: a Paddle price id the target api recognises, used to assert plan
# re-derivation on subscription webhooks.
PADDLE_PRICE_ID_PRO = os.environ.get("TEST_PADDLE_PRICE_ID_PRO_MONTH", "")

requires_base_url = pytest.mark.skipif(not API_BASE_URL, reason="TEST_API_BASE_URL is not set")
requires_setup_token = pytest.mark.skipif(not SETUP_TOKEN, reason="TEST_SETUP_TOKEN is not set")
requires_stripe_secret = pytest.mark.skipif(
    not STRIPE_WEBHOOK_SECRET, reason="TEST_STRIPE_WEBHOOK_SECRET is not set"
)
requires_paddle_secret = pytest.mark.skipif(
    not PADDLE_WEBHOOK_SECRET, reason="TEST_PADDLE_WEBHOOK_SECRET is not set"
)
requires_resend_secret = pytest.mark.skipif(
    not RESEND_WEBHOOK_SECRET, reason="TEST_RESEND_WEBHOOK_SECRET is not set"
)


@pytest.fixture(scope="session")
def api() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=15.0)


@dataclass
class SeededTenant:
    """A throwaway tenant plus its admin's bearer token."""

    id: str
    slug: str
    code: str
    admin_email: str
    admin_password: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Tenant-ID": self.id}


@pytest.fixture(scope="session")
def make_tenant(api: httpx.Client) -> Iterator[Callable[[str], SeededTenant]]:
    """Factory creating throwaway tenants via the setup token.

    Every write-suite test gets its own tenant so state mutations (paywall,
    trial extension, reminders) never leak between tests.
    """

    def _make(prefix: str = "mtp-wr") -> SeededTenant:
        slug = f"{prefix}-{uuid.uuid4().hex[:10]}"
        admin_email = f"{slug}@example.com"
        admin_password = uuid.uuid4().hex
        resp = api.post(
            "/tenants",
            headers={"X-Setup-Token": SETUP_TOKEN},
            json={
                "slug": slug,
                "name": f"MTP WriteSuite {slug}",
                "admin_email": admin_email,
                "admin_password": admin_password,
                "admin_name": "MTP WriteSuite Admin",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        token_resp = api.post(
            "/auth/token", json={"email": admin_email, "password": admin_password}
        )
        assert token_resp.status_code == 200, token_resp.text
        return SeededTenant(
            id=body["id"],
            slug=slug,
            code=body.get("code") or "",
            admin_email=admin_email,
            admin_password=admin_password,
            token=token_resp.json()["access_token"],
        )

    yield _make
