"""Normalisation for the preferred contact method captured at intake."""

from typing import Any

# The only channels staff can follow up on outside the app; anything else the
# homeowner picked (in_app_chat, sms, whatsapp, ...) is not a staff follow-up
# channel and normalises to None.
_FOLLOW_UP_METHODS = {"email", "phone"}


def normalise_preferred_contact(value: Any) -> str | None:
    """Normalise a captured preferred-contact value to "email" | "phone" | None.

    Accepts a plain string (the mobile app sends
    ``structuredData.preferredContact`` as one of "in_app_chat" | "phone" |
    "sms" | "whatsapp" | "email") or a ``{"method": ...}`` dict (the tenant
    portal's shape). Unknown or missing values normalise to None.
    """
    if isinstance(value, dict):
        value = value.get("method")
    if not isinstance(value, str):
        return None
    method = value.strip().lower()
    return method if method in _FOLLOW_UP_METHODS else None
