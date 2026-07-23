"""Application-wide rate limiter built on :mod:`slowapi`.

We rate-limit two surfaces today:

* ``/auth/login`` — bucketed by source IP to slow brute-force credential
  stuffing. Per-IP rather than per-tenant because the attacker controls the
  tenant id and we want the limit to bind regardless.
* ``/quotes/generate-boq`` and ``/quotes/{id}/boq/regenerate`` — bucketed by
  tenant so a single business cannot exhaust the AI/LLM budget by spraying
  quote generations.

The limiter is enabled by default and reads from in-memory storage. The
``limiter.enabled = False`` knob is flipped off in the test conftest so the
existing integration tests are not perturbed; a dedicated test in
``test_rate_limit.py`` toggles it back on to assert the behaviour.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from slowapi import Limiter
from slowapi.util import get_remote_address

if TYPE_CHECKING:
    from fastapi import Request


def _tenant_key(request: Request) -> str:
    """Bucket per tenant when the request carries an ``X-Tenant-ID`` header.

    Falls back to the source IP for anonymous or pre-auth calls so we never
    accidentally share a single bucket across the world.
    """
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return f"tenant:{tenant_id}"
    return f"ip:{get_remote_address(request)}"


# Default key is per-IP. Per-tenant decorators pass ``key_func=tenant_key``.
limiter = Limiter(key_func=get_remote_address, enabled=True)


# Export ``tenant_key`` so router decorators can opt into per-tenant buckets.
tenant_key = _tenant_key

__all__ = ["limiter", "tenant_key"]
