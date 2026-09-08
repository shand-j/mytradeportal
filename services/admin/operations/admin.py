"""Django admin registrations for the operations core."""

from typing import ClassVar

from django.contrib import admin

from operations.forms import TenantAdminForm, UserAdminForm
from operations.models import (
    Appointment,
    AuditLog,
    Communication,
    Contact,
    CostItem,
    Customer,
    Invoice,
    InvoiceLineItem,
    Job,
    Payment,
    Quote,
    QuoteLineItem,
    Tenant,
    User,
)


class TenantScopedAdminMixin:
    """Mixin that adds tenant filtering/searching to admin change lists."""

    list_filter: ClassVar[tuple[str, ...]] = ("tenant", "status")
    search_fields: ClassVar[tuple[str, ...]] = ("tenant__name",)


class QuoteLineItemInline(admin.TabularInline):
    """Inline editor for quote line items."""

    model = QuoteLineItem
    extra = 0
    fields = ("description", "quantity", "unit_price", "total")
    readonly_fields = ("total",)


class InvoiceLineItemInline(admin.TabularInline):
    """Inline editor for invoice line items."""

    model = InvoiceLineItem
    extra = 0
    fields = ("description", "quantity", "unit_price", "total")
    readonly_fields = ("total",)


class PaymentInline(admin.TabularInline):
    """Inline display of payments against an invoice."""

    model = Payment
    extra = 0
    fields = ("amount", "currency_code", "status", "provider_transaction_id", "paid_at")
    readonly_fields = fields


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """Admin for tenants/businesses."""

    form = TenantAdminForm
    list_display = ("name", "slug", "is_active", "paddle_sandbox", "created_at")
    list_filter = ("is_active", "paddle_sandbox")
    search_fields = ("name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Contact)
class ContactAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for customers/leads."""

    list_display = ("name", "email", "phone", "tenant", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name", "email", "phone", "postcode")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Customer)
class CustomerAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for homeowner accounts (logins for the customer portal)."""

    list_display = ("full_name", "email", "phone", "postcode", "tenant", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("full_name", "email", "phone", "postcode")
    # The hash is shown so it's obvious a credential exists; it is one-way —
    # the plaintext is never stored or recoverable.
    readonly_fields = ("id", "password_hash", "created_at", "updated_at")


@admin.register(User)
class UserAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for tenant staff."""

    form = UserAdminForm
    list_display = ("full_name", "email", "role", "tenant", "is_active")
    list_filter = ("tenant", "role", "is_active")
    search_fields = ("full_name", "email")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Quote)
class QuoteAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for quotes."""

    list_display = ("title", "contact", "tenant", "status", "total", "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("title", "contact__name")
    readonly_fields = (
        "id",
        "subtotal",
        "vat_amount",
        "total",
        "approved_at",
        "sent_at",
        "created_at",
        "updated_at",
    )
    inlines = [QuoteLineItemInline]


@admin.register(Job)
class JobAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for jobs/work orders."""

    list_display = ("title", "contact", "tenant", "status", "scheduled_start", "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("title", "contact__name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Appointment)
class AppointmentAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for appointments."""

    list_display = ("title", "contact", "tenant", "status", "start_at", "end_at")
    list_filter = ("tenant", "status")
    search_fields = ("title", "contact__name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Invoice)
class InvoiceAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for invoices."""

    list_display = (
        "invoice_number",
        "contact",
        "tenant",
        "status",
        "total",
        "issue_date",
        "paid_at",
    )
    list_filter = ("tenant", "status")
    search_fields = ("invoice_number", "contact__name")
    readonly_fields = (
        "id",
        "subtotal",
        "vat_amount",
        "total",
        "created_at",
        "updated_at",
    )
    inlines = [InvoiceLineItemInline, PaymentInline]


@admin.register(Payment)
class PaymentAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for payment records."""

    list_display = (
        "invoice",
        "tenant",
        "amount",
        "currency_code",
        "status",
        "provider_transaction_id",
        "paid_at",
    )
    list_filter = ("tenant", "status", "currency_code")
    search_fields = ("provider_transaction_id", "provider_checkout_id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(Communication)
class CommunicationAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    """Admin for communication logs."""

    list_display = ("channel", "direction", "contact", "tenant", "status", "created_at")
    list_filter = ("tenant", "channel", "direction", "status")
    search_fields = ("subject", "body", "contact__name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(CostItem)
class CostItemAdmin(admin.ModelAdmin):
    """Shared cost database items."""

    list_display = ("code", "category", "trade", "region", "unit_price", "currency", "is_active")
    list_filter = ("trade", "region", "category", "is_active", "source")
    search_fields = ("code", "description", "category")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for audit log entries (read-only)."""

    list_display = ("action", "entity_type", "tenant", "created_at")
    list_filter = ("tenant", "action", "entity_type")
    search_fields = ("entity_type", "entity_id")
    readonly_fields = ("id", "created_at", "updated_at")
