"""Smoke tests against a deployed API instance (Railway PR environment).

These tests are kept separate from ``services/api/tests`` on purpose: that
suite runs the app in-process against a throwaway Postgres, while this one
hits a live deployment over HTTP using only request/response contracts. They
never run as part of the default ``pytest`` invocation (the ``deployed``
marker is excluded in ``pyproject.toml``) and require ``TEST_API_BASE_URL``.

Hard rules (see docs/ci-pr-environments.md):
- read-only against any shared deployment; writes only ever happen under a
  throwaway tenant created with ``TEST_SETUP_TOKEN`` (skipped otherwise);
- no AI generation, Paddle checkout, or Stripe calls are triggered.
"""

import os

import httpx
import pytest

API_BASE_URL = os.environ.get("TEST_API_BASE_URL", "").rstrip("/")
# Optional: slug of a seeded tenant whose public config can be asserted on.
PUBLIC_SLUG = os.environ.get("TEST_PUBLIC_SLUG", "")
# Optional: setup token allowing creation of a throwaway tenant for the
# intake test. When unset, that test skips (and no LLM-backed background
# auto-draft can ever fire from CI).
SETUP_TOKEN = os.environ.get("TEST_SETUP_TOKEN", "")

requires_base_url = pytest.mark.skipif(not API_BASE_URL, reason="TEST_API_BASE_URL is not set")


@pytest.fixture(scope="session")
def api() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=15.0)
