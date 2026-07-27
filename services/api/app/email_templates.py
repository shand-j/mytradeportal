"""HTML email templates for transactional notifications."""

from datetime import datetime
from decimal import Decimal


def _base_html(title: str, content: str, tenant_name: str) -> str:
    """Wrap content in a minimal, professional HTML email shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }}
    .wrapper {{ max-width: 600px; margin: 32px auto; background: #ffffff; border-radius: 6px;
               border: 1px solid #e0e0e0; overflow: hidden; }}
    .header {{ background: #1a1a2e; color: #ffffff; padding: 20px 30px; font-size: 18px; font-weight: bold; }}
    .body {{ padding: 24px 30px; color: #333333; line-height: 1.6; }}
    .detail-row {{ display: flex; justify-content: space-between; border-bottom: 1px solid #eeeeee;
                  padding: 8px 0; font-size: 14px; }}
    .detail-row:last-child {{ border-bottom: none; }}
    .detail-label {{ color: #666666; }}
    .total-row {{ font-weight: bold; font-size: 15px; color: #1a1a2e; }}
    .footer {{ background: #f9f9f9; padding: 14px 30px; font-size: 12px; color: #888888;
               border-top: 1px solid #e0e0e0; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">{tenant_name}</div>
    <div class="body">{content}</div>
    <div class="footer">This message was sent by {tenant_name} via My Trade Portal.</div>
  </div>
</body>
</html>"""


def render_quote_sent_email(
    *,
    quote_ref: str,
    tenant_name: str,
    quote_title: str,
    subtotal: Decimal,
    vat_amount: Decimal,
    total: Decimal,
    vat_rate: Decimal,
    valid_until: datetime | None,
    customer_name: str,
) -> tuple[str, str]:
    """Return ``(subject, html_body)`` for a quote-sent notification."""
    subject = f"Your Quote from {tenant_name}"
    valid_until_line = (
        f'<div class="detail-row"><span class="detail-label">Valid Until</span>'
        f"<span>{valid_until.strftime('%d %B %Y')}</span></div>"
        if valid_until
        else ""
    )
    vat_pct = int(vat_rate * 100)
    content = f"""
<p>Dear {customer_name},</p>
<p>Please find your quote attached. Here is a summary:</p>
<div style="border: 1px solid #e0e0e0; border-radius: 4px; padding: 16px; margin: 16px 0;">
  <div class="detail-row"><span class="detail-label">Quote Reference</span><span>{quote_ref}</span></div>
  <div class="detail-row"><span class="detail-label">Description</span><span>{quote_title}</span></div>
  <div class="detail-row"><span class="detail-label">Subtotal</span><span>£{subtotal:,.2f}</span></div>
  <div class="detail-row"><span class="detail-label">VAT ({vat_pct}%)</span><span>£{vat_amount:,.2f}</span></div>
  {valid_until_line}
  <div class="detail-row total-row"><span>Total (inc. VAT)</span><span>£{total:,.2f}</span></div>
</div>
<p>If you have any questions, please reply to this email and we will be happy to help.</p>
<p>Kind regards,<br />{tenant_name}</p>"""
    return subject, _base_html(subject, content, tenant_name)


def render_invoice_sent_email(
    *,
    invoice_number: str,
    tenant_name: str,
    subtotal: Decimal,
    vat_amount: Decimal,
    total: Decimal,
    vat_rate: Decimal,
    issue_date: datetime,
    due_date: datetime | None,
    customer_name: str,
) -> tuple[str, str]:
    """Return ``(subject, html_body)`` for an invoice-sent notification."""
    subject = f"Invoice {invoice_number} from {tenant_name}"
    due_date_line = (
        f'<div class="detail-row"><span class="detail-label">Payment Due</span>'
        f"<span>{due_date.strftime('%d %B %Y')}</span></div>"
        if due_date
        else ""
    )
    vat_pct = int(vat_rate * 100)
    content = f"""
<p>Dear {customer_name},</p>
<p>Please find your invoice attached. Here is a summary:</p>
<div style="border: 1px solid #e0e0e0; border-radius: 4px; padding: 16px; margin: 16px 0;">
  <div class="detail-row"><span class="detail-label">Invoice Number</span><span>{invoice_number}</span></div>
  <div class="detail-row"><span class="detail-label">Issue Date</span><span>{issue_date.strftime("%d %B %Y")}</span></div>
  {due_date_line}
  <div class="detail-row"><span class="detail-label">Subtotal</span><span>£{subtotal:,.2f}</span></div>
  <div class="detail-row"><span class="detail-label">VAT ({vat_pct}%)</span><span>£{vat_amount:,.2f}</span></div>
  <div class="detail-row total-row"><span>Total (inc. VAT)</span><span>£{total:,.2f}</span></div>
</div>
<p>Please arrange payment by the due date shown above. If you have any questions, please reply to this email.</p>
<p>Kind regards,<br />{tenant_name}</p>"""
    return subject, _base_html(subject, content, tenant_name)
