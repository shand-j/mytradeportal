"""Inline email templates.

Kept as Python functions returning ``(subject, html, text)`` tuples so
callers can log the subject and the text fallback stays cheap to update
without a template engine. If templates get numerous we'll swap this for
Jinja + a ``templates/`` directory.
"""

from __future__ import annotations


def password_reset(*, name: str | None, reset_url: str) -> tuple[str, str, str]:
    greeting = f"Hi {name}," if name else "Hi,"
    subject = "Reset your My Trade Portal password"
    text = (
        f"{greeting}\n\n"
        "We received a request to reset your password.\n"
        "Follow this link to set a new one (expires in 30 minutes):\n\n"
        f"{reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email.\n\n"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Reset your password</h1>
    <p>{greeting}</p>
    <p>We received a request to reset your My Trade Portal password. Click the button below to set a new one — the link expires in 30 minutes.</p>
    <p style="margin:24px 0;">
      <a href="{reset_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Reset password</a>
    </p>
    <p style="color:#64748b;font-size:13px;">If the button doesn't work, copy and paste this link:<br><a href="{reset_url}" style="color:#4F46E5;">{reset_url}</a></p>
    <p style="color:#64748b;font-size:13px;">If you didn't request this, you can safely ignore this email.</p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def quote_ready(
    *,
    customer_name: str,
    business_name: str,
    quote_title: str,
    quote_total: str,
    view_url: str,
) -> tuple[str, str, str]:
    subject = f"Your quote from {business_name}"
    text = (
        f"Hi {customer_name},\n\n"
        f"{business_name} has sent you a quote for '{quote_title}'.\n"
        f"Total: {quote_total}\n\n"
        f"View and accept the quote here:\n{view_url}\n\n"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Your quote is ready</h1>
    <p>Hi {customer_name},</p>
    <p><strong>{business_name}</strong> has sent you a quote for <strong>{quote_title}</strong>.</p>
    <p style="font-size:20px;font-weight:700;margin:16px 0;">Total: {quote_total}</p>
    <p style="margin:24px 0;">
      <a href="{view_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">View quote</a>
    </p>
    <p style="color:#64748b;font-size:13px;">If the button doesn't work, copy and paste this link:<br><a href="{view_url}" style="color:#4F46E5;">{view_url}</a></p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def invoice_sent(
    *,
    customer_name: str,
    business_name: str,
    invoice_number: str,
    invoice_total: str,
) -> tuple[str, str, str]:
    """Invoice-issued email. (subject, html, text)."""
    subject = f"Invoice {invoice_number} from {business_name}"
    text = (
        f"Hi {customer_name},\n\n"
        f"{business_name} has sent you invoice {invoice_number}.\n"
        f"Total due: {invoice_total}\n\n"
        "Open the app to view and pay.\n\n"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Invoice {invoice_number}</h1>
    <p>Hi {customer_name},</p>
    <p><strong>{business_name}</strong> has sent you an invoice.</p>
    <p style="font-size:20px;font-weight:700;margin:16px 0;">Total due: {invoice_total}</p>
    <p>Open the app to view and pay.</p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text
