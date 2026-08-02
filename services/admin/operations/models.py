"""Unmanaged Django models mirroring the FastAPI operations schema.

These models are read-only for Django migrations (`managed = False`) so the
FastAPI model-based schema init remains the single source of truth for the
operational schema.
"""

import uuid

from django.db import models


class Tenant(models.Model):
    """A trade business tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=63)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict)
    paddle_sandbox = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "tenants"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Contact(models.Model):
    """A customer or lead."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    postcode = models.CharField(max_length=20, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "contacts"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class User(models.Model):
    """A staff member belonging to a tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    email = models.EmailField()
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    password_hash = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "users"
        ordering = ["full_name"]

    def __str__(self) -> str:
        return self.full_name


class Quote(models.Model):
    """A quote sent to a customer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    contact = models.ForeignKey(
        Contact,
        db_column="contact_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    valid_until = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    extra_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "quotes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class QuoteLineItem(models.Model):
    """A line item on a quote."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    quote = models.ForeignKey(
        Quote,
        db_column="quote_id",
        on_delete=models.DO_NOTHING,
        related_name="line_items",
    )
    description = models.TextField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "quote_line_items"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.description


class Job(models.Model):
    """A work order created from a quote or directly."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    contact = models.ForeignKey(
        Contact,
        db_column="contact_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    quote = models.ForeignKey(
        Quote,
        db_column="quote_id",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="+",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "jobs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class Appointment(models.Model):
    """A scheduled appointment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    contact = models.ForeignKey(
        Contact,
        db_column="contact_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    job = models.ForeignKey(
        Job,
        db_column="job_id",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="+",
    )
    title = models.CharField(max_length=255)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(max_length=50)
    address = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "appointments"
        ordering = ["-start_at"]

    def __str__(self) -> str:
        return f"{self.title} @ {self.start_at}"


class Invoice(models.Model):
    """An invoice for completed work."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    contact = models.ForeignKey(
        Contact,
        db_column="contact_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    job = models.ForeignKey(
        Job,
        db_column="job_id",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="+",
    )
    quote = models.ForeignKey(
        Quote,
        db_column="quote_id",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="+",
    )
    invoice_number = models.CharField(max_length=50)
    status = models.CharField(max_length=50)
    issue_date = models.DateTimeField()
    due_date = models.DateTimeField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(null=True, blank=True)
    paddle_checkout_id = models.CharField(max_length=255, null=True, blank=True)
    paddle_transaction_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "invoices"
        ordering = ["-issue_date"]

    def __str__(self) -> str:
        return f"{self.invoice_number} ({self.status})"


class InvoiceLineItem(models.Model):
    """A line item on an invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    invoice = models.ForeignKey(
        Invoice,
        db_column="invoice_id",
        on_delete=models.DO_NOTHING,
        related_name="line_items",
    )
    description = models.TextField()
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "invoice_line_items"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.description


class Payment(models.Model):
    """A payment record linked to Paddle."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    invoice = models.ForeignKey(
        Invoice,
        db_column="invoice_id",
        on_delete=models.DO_NOTHING,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency_code = models.CharField(max_length=3)
    status = models.CharField(max_length=50)
    provider = models.CharField(max_length=50)
    provider_transaction_id = models.CharField(max_length=255, null=True, blank=True)
    provider_checkout_id = models.CharField(max_length=255, null=True, blank=True)
    provider_payload = models.JSONField(default=dict)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "payments"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.amount} {self.currency_code} ({self.status})"


class Communication(models.Model):
    """A logged message/email/SMS/call with a contact."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    contact = models.ForeignKey(
        Contact,
        db_column="contact_id",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name="+",
    )
    channel = models.CharField(max_length=50)
    direction = models.CharField(max_length=10)
    subject = models.CharField(max_length=255, null=True, blank=True)
    body = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50)
    provider_message_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "communications"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.channel} ({self.direction})"


class AuditLog(models.Model):
    """Immutable audit log entries."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        db_column="tenant_id",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=50)
    entity_id = models.UUIDField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "audit_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}"


class CostItem(models.Model):
    """A priced cost item from the shared cost database."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=63, unique=True)
    trade = models.CharField(max_length=50)
    region = models.CharField(max_length=50)
    category = models.CharField(max_length=100)
    description = models.TextField()
    unit = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=50)
    extra_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "cost_items"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code
