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


def _magic_link_cta(url: str, label: str) -> tuple[str, str]:
    """Primary sign-in CTA block for a magic portal link, as (text, html)."""
    text = f"{label}:\n{url}\n\n"
    html = f"""\
    <p style="margin:24px 0;">
      <a href="{url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">{label}</a>
    </p>
    <p style="color:#64748b;font-size:13px;">This link signs you in — no password needed. If the button doesn't work, copy and paste it:<br><a href="{url}" style="color:#4F46E5;">{url}</a></p>
"""
    return text, html


def _view_only_secondary(view_url: str) -> tuple[str, str]:
    """Secondary view-only document link shown under a magic-link CTA."""
    text = f"Prefer not to sign in? View a read-only copy here:\n{view_url}\n\n"
    html = f"""\
    <p style="color:#64748b;font-size:13px;">Prefer not to sign in? <a href="{view_url}" style="color:#4F46E5;">View a read-only copy</a> instead.</p>
"""
    return text, html


def quote_ready(
    *,
    customer_name: str,
    business_name: str,
    quote_title: str,
    quote_total: str,
    view_url: str,
    portal_url: str | None = None,
) -> tuple[str, str, str]:
    """Quote-issued email. (subject, html, text).

    ``portal_url`` is the magic sign-in link to the customer portal; when
    present it becomes the primary CTA and ``view_url`` (the view-only
    document page) drops to a secondary "view without signing in" link.
    """
    subject = f"Your quote from {business_name}"
    if portal_url:
        text_cta, html_cta = _magic_link_cta(portal_url, "View and accept your quote")
        text_secondary, html_secondary = _view_only_secondary(view_url)
    else:
        text_cta = f"View and accept the quote here:\n{view_url}\n\n"
        html_cta = f"""\
    <p style="margin:24px 0;">
      <a href="{view_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">View quote</a>
    </p>
    <p style="color:#64748b;font-size:13px;">If the button doesn't work, copy and paste this link:<br><a href="{view_url}" style="color:#4F46E5;">{view_url}</a></p>
"""
        text_secondary, html_secondary = "", ""
    text = (
        f"Hi {customer_name},\n\n"
        f"{business_name} has sent you a quote for '{quote_title}'.\n"
        f"Total: {quote_total}\n\n"
        f"{text_cta}"
        f"{text_secondary}"
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
{html_cta}\
{html_secondary}\
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
    view_url: str | None = None,
    portal_url: str | None = None,
) -> tuple[str, str, str]:
    """Invoice-issued email. (subject, html, text).

    ``payment_details`` carries the tenant's bank-transfer details (keys:
    ``account_name``, ``sort_code``, ``account_number``, ``reference``); the
    block is omitted entirely when the tenant has not configured them.
    ``portal_url`` is the magic sign-in link to the customer portal; when
    present it becomes the primary CTA and ``view_url`` (the view-only
    document/pay page) drops to a secondary "view without signing in" link.
    When neither is present the email falls back to the app-only copy.
    """
    subject = f"Invoice {invoice_number} from {business_name}"
    payment_text, payment_html = _payment_details_block(payment_details)
    if portal_url:
        text_cta, html_cta = _magic_link_cta(portal_url, "View and pay your invoice")
        if view_url:
            text_secondary, html_secondary = _view_only_secondary(view_url)
        else:
            text_secondary, html_secondary = "", ""
    elif view_url:
        text_cta = f"View your invoice online here:\n{view_url}\n\n"
        html_cta = f"""\
    <p style="margin:24px 0;">
      <a href="{view_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">View invoice</a>
    </p>
    <p style="color:#64748b;font-size:13px;">If the button doesn't work, copy and paste this link:<br><a href="{view_url}" style="color:#4F46E5;">{view_url}</a></p>
"""
        text_secondary, html_secondary = "", ""
    else:
        text_cta = "Open the app to view and pay.\n\n"
        html_cta = "    <p>Open the app to view and pay.</p>\n"
        text_secondary, html_secondary = "", ""
    text = (
        f"Hi {customer_name},\n\n"
        f"{business_name} has sent you invoice {invoice_number}.\n"
        f"Total due: {invoice_total}\n\n"
        f"{payment_text}"
        f"{text_cta}"
        f"{text_secondary}"
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
{html_cta}\
{html_secondary}\
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def quote_reminder(
    *,
    customer_name: str,
    business_name: str,
    quote_title: str,
    quote_total: str,
    view_url: str | None = None,
    portal_url: str | None = None,
    personal_message: str | None = None,
) -> tuple[str, str, str]:
    """Follow-up email for a sent-but-unanswered quote. (subject, html, text).

    ``portal_url`` is the magic sign-in link; when present it is the primary
    CTA and ``view_url`` (the view-only document page, when also given) drops
    to a secondary "view without signing in" link. When neither is present
    the email falls back to the app-only copy.

    ``personal_message`` is an optional AI-drafted personalised paragraph
    (F2); when present it is shown directly under the greeting, ahead of the
    standard copy. The static template stays the skeleton either way.
    """
    subject = f"Reminder: your quote from {business_name}"
    if portal_url:
        text_cta, html_cta = _magic_link_cta(portal_url, "View and accept your quote")
        if view_url:
            text_secondary, html_secondary = _view_only_secondary(view_url)
        else:
            text_secondary, html_secondary = "", ""
    elif view_url:
        text_cta = f"View and accept the quote here:\n{view_url}\n\n"
        html_cta = f"""\
    <p style="margin:24px 0;">
      <a href="{view_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">View quote</a>
    </p>
    <p style="color:#64748b;font-size:13px;">If the button doesn't work, copy and paste this link:<br><a href="{view_url}" style="color:#4F46E5;">{view_url}</a></p>
"""
        text_secondary, html_secondary = "", ""
    else:
        text_cta = "Open the app to view and accept the quote.\n\n"
        html_cta = "    <p>Open the app to view and accept the quote.</p>\n"
        text_secondary, html_secondary = "", ""
    text_personal = f"{personal_message}\n\n" if personal_message else ""
    html_personal = f"    <p>{personal_message}</p>\n" if personal_message else ""
    text = (
        f"Hi {customer_name},\n\n"
        f"{text_personal}"
        f"Just a friendly reminder that {business_name} sent you a quote for "
        f"'{quote_title}'.\n"
        f"Total: {quote_total}\n\n"
        f"{text_cta}"
        f"{text_secondary}"
        f"If you have any questions, just reply to this email.\n\n"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Your quote is waiting</h1>
    <p>Hi {customer_name},</p>
{html_personal}\
    <p>Just a friendly reminder that <strong>{business_name}</strong> sent you a quote for <strong>{quote_title}</strong>.</p>
    <p style="font-size:20px;font-weight:700;margin:16px 0;">Total: {quote_total}</p>
{html_cta}\
{html_secondary}\
    <p style="color:#64748b;font-size:13px;">If you have any questions, just reply to this email.</p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def invoice_reminder(
    *,
    customer_name: str,
    business_name: str,
    invoice_number: str,
    invoice_total: str,
    payment_details: dict[str, str] | None = None,
    view_url: str | None = None,
    portal_url: str | None = None,
    personal_message: str | None = None,
) -> tuple[str, str, str]:
    """Payment-chasing email for an unpaid sent invoice. (subject, html, text).

    ``payment_details`` carries the tenant's bank-transfer details (same
    shape as :func:`invoice_sent`); the block is omitted when unconfigured.
    ``portal_url`` is the magic sign-in link; when present it is the primary
    CTA and ``view_url`` (the secure web invoice page, when also given) drops
    to a secondary "view without signing in" link. When neither is present
    the email falls back to the app-only copy.

    ``personal_message`` is an optional AI-drafted personalised paragraph
    (F2); when present it is shown directly under the greeting, ahead of the
    standard copy.
    """
    subject = f"Reminder: invoice {invoice_number} from {business_name}"
    payment_text, payment_html = _payment_details_block(payment_details)
    if portal_url:
        action_text, action_html = _magic_link_cta(portal_url, "View and pay your invoice")
        if view_url:
            text_secondary, html_secondary = _view_only_secondary(view_url)
        else:
            text_secondary, html_secondary = "", ""
    elif view_url:
        action_text = f"View and pay online:\n{view_url}\n\n"
        action_html = (
            f'<p><a href="{view_url}" style="display:inline-block;background:#0F1E26;'
            'color:#FFC107;padding:12px 24px;text-decoration:none;font-weight:700;">'
            "View and pay online</a></p>"
        )
        text_secondary, html_secondary = "", ""
    else:
        action_text = "Open the app to view and pay.\n\n"
        action_html = "    <p>Open the app to view and pay.</p>"
        text_secondary, html_secondary = "", ""
    text_personal = f"{personal_message}\n\n" if personal_message else ""
    html_personal = f"    <p>{personal_message}</p>\n" if personal_message else ""
    text = (
        f"Hi {customer_name},\n\n"
        f"{text_personal}"
        f"This is a reminder that invoice {invoice_number} from {business_name} "
        f"is still awaiting payment.\n"
        f"Total due: {invoice_total}\n\n"
        f"{payment_text}"
        f"{action_text}"
        f"{text_secondary}"
        f"If you have already paid, please ignore this reminder.\n\n"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Payment reminder — invoice {invoice_number}</h1>
    <p>Hi {customer_name},</p>
{html_personal}\
    <p>This is a reminder that invoice <strong>{invoice_number}</strong> from <strong>{business_name}</strong> is still awaiting payment.</p>
    <p style="font-size:20px;font-weight:700;margin:16px 0;">Total due: {invoice_total}</p>
{payment_html}\
{action_html}
{html_secondary}\
    <p style="color:#64748b;font-size:13px;">If you have already paid, please ignore this reminder.</p>
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
    portal_url: str | None = None,
) -> tuple[str, str, str]:
    """Confirmation email after the customer accepts a quote. (subject, html, text).

    Tells the customer their booking request is now pending — the follow-up
    ``booking_confirmed`` email lands once the electrician schedules the work.
    ``portal_url`` is the magic sign-in link to track the booking in the
    customer portal; omitted when the customer has no portal account.
    """
    subject = f"Quote accepted — {business_name}"
    if portal_url:
        text_cta, html_cta = _magic_link_cta(portal_url, "Track your booking")
    else:
        text_cta, html_cta = "", ""
    text = (
        f"Hi {customer_name},\n\n"
        f"Thanks — you've accepted the quote for '{quote_title}' from {business_name}.\n"
        f"Total: {quote_total}\n\n"
        f"Your booking request is pending — we'll email you as soon as "
        f"{business_name} has scheduled the work.\n\n"
        f"{text_cta}"
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
    <p>Your booking request is <strong>pending</strong> — we'll email you as soon as {business_name} has scheduled the work.</p>
{html_cta}\
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def booking_confirmed(
    *,
    customer_name: str,
    business_name: str,
    job_title: str,
    visit_date: str,
    time_window: str,
    address: str | None = None,
    tradie_name: str | None = None,
    tradie_phone: str | None = None,
    claim_url: str | None = None,
) -> tuple[str, str, str]:
    """Booking confirmation after the electrician schedules the job.

    ``visit_date``/``time_window`` are pre-formatted display strings (the
    caller owns locale formatting). ``tradie_name``/``tradie_phone`` identify
    who is coming; ``address`` is the visit location. Changes are handled by
    replying — the sender's Reply-To is the tenant's own address. When the
    customer has a passwordless (auto-provisioned) account, ``claim_url`` is
    a magic link into the account-claim page and the email gains a "Create
    your account" block; customers with a password get no such CTA.
    """
    subject = f"Booking confirmed — {business_name}"
    details_text = f"Date: {visit_date}\nTime: {time_window}\n"
    details_rows = (
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b;">Date</td>'
        f'<td style="padding:4px 0;font-weight:600;">{escape(visit_date)}</td></tr>'
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b;">Time</td>'
        f'<td style="padding:4px 0;font-weight:600;">{escape(time_window)}</td></tr>'
    )
    if address:
        details_text += f"Address: {address}\n"
        details_rows += (
            '<tr><td style="padding:4px 12px 4px 0;color:#64748b;">Address</td>'
            f'<td style="padding:4px 0;font-weight:600;">{escape(address)}</td></tr>'
        )
    if tradie_name:
        tradie_line = f"{tradie_name}"
        if tradie_phone:
            tradie_line += f" ({tradie_phone})"
        details_text += f"Your tradesperson: {tradie_line}\n"
        details_rows += (
            '<tr><td style="padding:4px 12px 4px 0;color:#64748b;">Your tradesperson</td>'
            f'<td style="padding:4px 0;font-weight:600;">{escape(tradie_line)}</td></tr>'
        )
    if claim_url:
        text_claim = (
            "Manage your quote, booking and invoices in one place — "
            f"create your account here:\n{claim_url}\n\n"
        )
        html_claim = f"""\
    <div style="background:#f1f5f9;border-radius:8px;padding:16px;margin:16px 0;">
      <p style="margin:0 0 8px;font-weight:600;">Create your account</p>
      <p style="margin:0 0 12px;color:#475569;font-size:14px;">Manage your quote, booking and invoices in one place.</p>
      <a href="{claim_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Create your account</a>
    </div>
"""
    else:
        text_claim, html_claim = "", ""
    text = (
        f"Hi {customer_name},\n\n"
        f"Good news — {business_name} has booked in your job '{job_title}'.\n\n"
        f"{details_text}\n"
        "Need to change it? Just reply to this email and we'll rearrange.\n\n"
        f"{text_claim}"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Booking confirmed</h1>
    <p>Hi {customer_name},</p>
    <p>Good news — <strong>{business_name}</strong> has booked in your job <strong>{job_title}</strong>.</p>
    <div style="background:#f1f5f9;border-radius:8px;padding:16px;margin:16px 0;">
      <table style="border-collapse:collapse;font-size:14px;">{details_rows}</table>
    </div>
    <p>Need to change it? Just reply to this email and we'll rearrange.</p>
{html_claim}\
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def payment_received(
    *,
    customer_name: str,
    business_name: str,
    invoice_number: str,
    amount_paid: str,
    paid_date: str,
    review_url: str | None = None,
    card_payment: bool = True,
) -> tuple[str, str, str]:
    """Payment confirmation after an invoice is settled. (subject, html, text).

    Positions itself as the confirmation + thank-you. ``card_payment=True``
    (Stripe webhook path) mentions that Stripe also emails a card receipt;
    ``card_payment=False`` (manual mark-paid, e.g. bank transfer) omits that —
    the copy must never claim a card payment that did not happen. When the
    tenant has configured a ``review_url`` (tenant settings), a review prompt
    CTA is appended.
    """
    subject = f"Payment received — invoice {invoice_number}"
    if review_url:
        text_review = (
            f"How did we do? Leave {business_name} a review — it only takes a minute:\n"
            f"{review_url}\n\n"
        )
        html_review = f"""\
    <div style="background:#f1f5f9;border-radius:8px;padding:16px;margin:16px 0;">
      <p style="margin:0 0 8px;font-weight:600;">How did we do?</p>
      <p style="margin:0 0 12px;color:#475569;font-size:14px;">Your feedback helps {business_name} win more work — it only takes a minute.</p>
      <a href="{escape(review_url)}" style="background:#FFC107;color:#0F1E26;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:700;">Leave {business_name} a review</a>
    </div>
"""
    else:
        text_review, html_review = "", ""
    receipt_note = (
        "This email confirms your payment. Stripe will also email you a card "
        "receipt for your records.\n\n"
        if card_payment
        else "This email confirms your payment.\n\n"
    )
    receipt_note_html = (
        '<p style="color:#475569;font-size:14px;">This email confirms your payment. '
        "Stripe will also email you a card receipt for your records.</p>"
        if card_payment
        else ""
    )
    text = (
        f"Hi {customer_name},\n\n"
        f"Thank you — {business_name} has received your payment of {amount_paid} "
        f"for invoice {invoice_number}, paid on {paid_date}.\n\n"
        f"{receipt_note}"
        f"{text_review}"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Payment received — thank you</h1>
    <p>Hi {customer_name},</p>
    <p>Thank you — <strong>{business_name}</strong> has received your payment.</p>
    <div style="background:#f1f5f9;border-radius:8px;padding:16px;margin:16px 0;">
      <table style="border-collapse:collapse;font-size:14px;">
        <tr><td style="padding:4px 12px 4px 0;color:#64748b;">Invoice</td><td style="padding:4px 0;font-weight:600;">{invoice_number}</td></tr>
        <tr><td style="padding:4px 12px 4px 0;color:#64748b;">Amount paid</td><td style="padding:4px 0;font-weight:600;">{amount_paid}</td></tr>
        <tr><td style="padding:4px 12px 4px 0;color:#64748b;">Paid on</td><td style="padding:4px 0;font-weight:600;">{escape(paid_date)}</td></tr>
      </table>
    </div>
{receipt_note_html}\
{html_review}\
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def chat_message(
    *,
    customer_name: str,
    business_name: str,
    message_preview: str,
    reply_url: str,
) -> tuple[str, str, str]:
    """New staff chat message notification. (subject, html, text).

    Sent alongside the push notification for customers whose contact
    preference is app-or-email (never for phone-only customers).
    ``message_preview`` is pre-truncated by the caller (~200 chars) and
    HTML-escaped here; ``reply_url`` is the magic sign-in link that lands on
    the portal page for the conversation's quote.
    """
    subject = f"New message from {business_name}"
    text = (
        f"Hi {customer_name},\n\n"
        f"{business_name} sent you a message:\n\n"
        f'"{message_preview}"\n\n'
        f"Reply in the portal:\n{reply_url}\n\n"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">New message</h1>
    <p>Hi {customer_name},</p>
    <p><strong>{business_name}</strong> sent you a message:</p>
    <p style="background:#f1f5f9;border-radius:8px;padding:12px 16px;font-style:italic;">{escape(message_preview)}</p>
    <p style="margin:24px 0;">
      <a href="{reply_url}" style="background:#4F46E5;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Reply in the portal</a>
    </p>
    <p style="color:#64748b;font-size:13px;">This link signs you in — no password needed. If the button doesn't work, copy and paste it:<br><a href="{reply_url}" style="color:#4F46E5;">{reply_url}</a></p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text


def payment_failed(
    *,
    business_name: str,
    portal_url: str | None,
    attempt: int,
    max_attempts: int,
) -> tuple[str, str, str]:
    """Dunning email to the tenant owner when their subscription payment fails.

    (subject, html, text). ``portal_url`` is a short-lived Paddle customer
    portal session URL (update payment method / download invoices) — the
    primary CTA. ``attempt``/``max_attempts`` render the "reminder N of M"
    framing; attempt 1 is the notice, later attempts are follow-ups on the
    dunning cadence. The email goes to the account email that pays for the
    business's subscription, not to one of their customers.
    """
    subject = "Action needed: your My Trade Portal payment failed"
    if portal_url:
        action_text = (
            "Update your payment method here (takes a minute):\n"
            f"{portal_url}\n\n"
            "The link opens your secure Paddle billing page.\n\n"
        )
        action_html = f"""\
    <p style="margin:24px 0;">
      <a href="{portal_url}" style="background:#0F1E26;color:#FFC107;padding:12px 24px;text-decoration:none;font-weight:700;">Update payment method</a>
    </p>
    <p style="color:#64748b;font-size:13px;">The link opens your secure Paddle billing page. If the button doesn't work, copy and paste it:<br><a href="{portal_url}" style="color:#4F46E5;">{portal_url}</a></p>
"""
    else:
        action_text = (
            "Open the app → Settings → Manage subscription to update your payment method.\n\n"
        )
        action_html = (
            "    <p>Open the app → Settings → Manage subscription to update your method.</p>\n"
        )
    if attempt == 1:
        lead_text = (
            f"We tried to collect payment for {business_name}'s My Trade Portal "
            "subscription and it failed — most often an expired or replaced card."
        )
        lead_html = (
            f"<p>We tried to collect payment for <strong>{business_name}</strong>'s "
            "My Trade Portal subscription and it failed — most often an expired or "
            "replaced card.</p>"
        )
    else:
        lead_text = (
            f"Reminder {attempt} of {max_attempts}: payment for {business_name}'s "
            "My Trade Portal subscription is still failing."
        )
        lead_html = (
            f"<p><strong>Reminder {attempt} of {max_attempts}:</strong> payment for "
            f"<strong>{business_name}</strong>'s My Trade Portal subscription is "
            "still failing.</p>"
        )
    text = (
        f"Hello,\n\n"
        f"{lead_text}\n\n"
        f"{action_text}"
        "Your account stays active while we retry the payment, but access is "
        "paused if it keeps failing — updating your payment method now is the "
        "quickest fix.\n\n"
        "Once the payment succeeds this notice stops automatically.\n\n"
        "— My Trade Portal"
    )
    html = f"""\
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
    <h1 style="font-size:22px;margin:0 0 12px;">Your payment failed</h1>
    {lead_html}
{action_html}\
    <p>Your account stays active while we retry the payment, but access is paused if it keeps failing — updating your payment method now is the quickest fix.</p>
    <p style="color:#64748b;font-size:13px;">Once the payment succeeds this notice stops automatically.</p>
    <p style="color:#64748b;font-size:13px;margin-top:32px;">— My Trade Portal</p>
  </body>
</html>
"""
    return subject, html, text
