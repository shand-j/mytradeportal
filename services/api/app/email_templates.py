"""Inline email templates.

Kept as Python functions returning ``(subject, html, text)`` tuples so
callers can log the subject and the text fallback stays cheap to update
without a template engine. If templates get numerous we'll swap this for
Jinja + a ``templates/`` directory.
"""

from __future__ import annotations

from html import escape


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
    <p>{escape(greeting)}</p>
    <p>We received a request to reset your My Trade Portal password. Click the button below to choose a new one on our website — the link expires in 30 minutes and can only be used once.</p>
    <p style="margin:24px 0;">
      <a href="{reset_url}" style="background:#FFC107;color:#0F1E26;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:700;">Reset password</a>
    </p>
    <p style="color:#64748b;font-size:13px;">If the button doesn't work, copy and paste this link:<br><a href="{reset_url}" style="color:#CC8F00;">{reset_url}</a></p>
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


def _payment_details_block(
    payment_details: dict[str, str] | None,
) -> tuple[str, str]:
    """Render the bank-transfer block for an invoice email as (text, html).

    Returns empty strings when the tenant has not configured any bank details,
    so invoice emails stay unchanged for businesses that take payment another
    way. Rows are HTML-escaped — these values come from tenant settings.
    """
    if not payment_details:
        return "", ""
    rows = [
        ("Account name", payment_details.get("account_name", "")),
        ("Sort code", payment_details.get("sort_code", "")),
        ("Account number", payment_details.get("account_number", "")),
        ("Payment reference", payment_details.get("reference", "")),
    ]
    rows = [(label, value) for label, value in rows if value]
    if not rows:
        return "", ""
    text = "Pay by bank transfer:\n" + "\n".join(f"  {label}: {value}" for label, value in rows)
    text += "\n\n"
    html_rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b;">{escape(label)}</td>'
        f'<td style="padding:4px 0;font-weight:600;">{escape(value)}</td></tr>'
        for label, value in rows
    )
    html = f"""\
    <div style="background:#f1f5f9;border-radius:8px;padding:16px;margin:16px 0;">
      <p style="margin:0 0 8px;font-weight:600;">Pay by bank transfer</p>
      <table style="border-collapse:collapse;font-size:14px;">{html_rows}</table>
    </div>
"""
    return text, html


def invoice_sent(
    *,
    customer_name: str,
    business_name: str,
    invoice_number: str,
    invoice_total: str,
    payment_details: dict[str, str] | None = None,
) -> tuple[str, str, str]:
    """Invoice-issued email. (subject, html, text).

    ``payment_details`` carries the tenant's bank-transfer details (keys:
    ``account_name``, ``sort_code``, ``account_number``, ``reference``); the
    block is omitted entirely when the tenant has not configured them.
    """
    subject = f"Invoice {invoice_number} from {business_name}"
    payment_text, payment_html = _payment_details_block(payment_details)
    text = (
        f"Hi {customer_name},\n\n"
        f"{business_name} has sent you invoice {invoice_number}.\n"
        f"Total due: {invoice_total}\n\n"
        f"{payment_text}"
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
{payment_html}\
    <p>Open the app to view and pay.</p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def account_created(
    *,
    name: str | None,
    business_name: str,
    login_url: str | None,
) -> tuple[str, str, str]:
    """Welcome email after a homeowner registers. (subject, html, text)."""
    greeting = f"Hi {name}," if name else "Hi,"
    subject = f"Your {business_name} customer account is ready"
    if login_url:
        text_cta = f"Sign in here to view your quotes and messages:\n{login_url}\n\n"
        html_cta = f"""\
    <p style="margin:24px 0;">
      <a href="{login_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Sign in</a>
    </p>
    <p style="color:#64748b;font-size:13px;">If the button doesn't work, copy and paste this link:<br><a href="{login_url}" style="color:#4F46E5;">{login_url}</a></p>
"""
    else:
        text_cta = "Open the app to view your quotes and messages.\n\n"
        html_cta = "<p>Open the app to view your quotes and messages.</p>"
    text = (
        f"{greeting}\n\n"
        f"Your customer account with {business_name} has been created.\n\n"
        f"{text_cta}"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Welcome to {business_name}</h1>
    <p>{greeting}</p>
    <p>Your customer account with <strong>{business_name}</strong> has been created. Use it to track your quote requests, view quotes and chat with your electrician.</p>
{html_cta}
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def triage_question(
    *,
    customer_name: str,
    business_name: str,
    question: str,
    chat_url: str | None,
) -> tuple[str, str, str]:
    """AI follow-up question email. (subject, html, text)."""
    subject = f"{business_name} has a question about your quote request"
    if chat_url:
        text_cta = f"Reply in the chat here:\n{chat_url}\n\n"
        html_cta = f"""\
    <p style="margin:24px 0;">
      <a href="{chat_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Reply in chat</a>
    </p>
    <p style="color:#64748b;font-size:13px;">If the button doesn't work, copy and paste this link:<br><a href="{chat_url}" style="color:#4F46E5;">{chat_url}</a></p>
"""
    else:
        text_cta = "Open the app to reply in the chat.\n\n"
        html_cta = "<p>Open the app to reply in the chat.</p>"
    text = (
        f"Hi {customer_name},\n\n"
        f"{business_name} is preparing your quote and needs one more detail:\n\n"
        f'"{question}"\n\n'
        f"{text_cta}"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">One question about your quote</h1>
    <p>Hi {customer_name},</p>
    <p><strong>{business_name}</strong> is preparing your quote and needs one more detail:</p>
    <p style="background:#f1f5f9;border-radius:8px;padding:12px 16px;font-style:italic;">{question}</p>
{html_cta}
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def quote_accepted(
    *,
    customer_name: str,
    business_name: str,
    quote_title: str,
    quote_total: str,
) -> tuple[str, str, str]:
    """Confirmation email after the customer accepts a quote. (subject, html, text)."""
    subject = f"Quote accepted — {business_name}"
    text = (
        f"Hi {customer_name},\n\n"
        f"Thanks — you've accepted the quote for '{quote_title}' from {business_name}.\n"
        f"Total: {quote_total}\n\n"
        f"{business_name} will be in touch to schedule the work.\n\n"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Quote accepted</h1>
    <p>Hi {customer_name},</p>
    <p>Thanks — you've accepted the quote for <strong>{quote_title}</strong> from <strong>{business_name}</strong>.</p>
    <p style="font-size:20px;font-weight:700;margin:16px 0;">Total: {quote_total}</p>
    <p>{business_name} will be in touch to schedule the work.</p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text
