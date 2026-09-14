"""Tenant bank-transfer details shared by invoice emails and public pages.

Lives outside the routers so both ``app.routers.invoices`` (invoice emails),
``app.routers.public_docs`` (the no-auth web invoice page) and the reminder
scheduler can build the same block without router→router import cycles.
"""

from __future__ import annotations

from typing import Any


def tenant_payment_details(
    settings: dict[str, Any] | None, *, reference: str
) -> dict[str, str] | None:
    """Build the bank-transfer block from tenant settings.

    The payment reference defaults to the invoice number so the customer can
    always reconcile the transfer. Returns None when no bank details are
    configured so callers omit the block entirely.
    """
    if not settings:
        return None
    details = {
        "account_name": str(settings.get("bank_account_name", "") or ""),
        "sort_code": str(settings.get("bank_sort_code", "") or ""),
        "account_number": str(settings.get("bank_account_number", "") or ""),
        "reference": reference,
    }
    if not any(details[key] for key in ("account_name", "sort_code", "account_number")):
        return None
    return details
