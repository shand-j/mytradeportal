"""Django admin registrations for the operations core."""

from typing import ClassVar

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from operations.forms import TenantAdminForm, UserAdminForm
from operations.models import (
    AiCallEvent,
    AiRollupUserDay,
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
    actions = ("reset_password",)

    @admin.action(description="Reset password to a temporary value (shown once)")
    def reset_password(self, request: HttpRequest, queryset: QuerySet) -> None:
        import secrets

        import bcrypt

        for customer in queryset:
            temporary = secrets.token_urlsafe(10)
            customer.password_hash = bcrypt.hashpw(
                temporary.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            customer.save(update_fields=["password_hash"])
            self.message_user(
                request,
                f"{customer.email}: temporary password '{temporary}' — shown once, "
                "ask the customer to change it after logging in.",
            )


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


@admin.register(AiRollupUserDay)
class AiRollupUserDayAdmin(admin.ModelAdmin):
    """Per-user daily AI usage rollup — the monthly AI cost leaderboard.

    Sort the changelist by date + cost (the default ordering) and use the
    date hierarchy to drill into a month; filter by tenant to rank users.
    Read-only: rows are folded nightly by the API's rollup job.
    """

    date_hierarchy = "date"
    list_display = (
        "date",
        "tenant",
        "user",
        "feature",
        "generations",
        "cost_gbp",
        "latency_p95",
        "quotes_sent",
    )
    list_filter = ("tenant", "feature")
    search_fields = ("tenant__name", "user__full_name", "user__email")
    readonly_fields = (
        "id",
        "date",
        "tenant",
        "user",
        "feature",
        "generations",
        "retries",
        "tokens_input",
        "tokens_output",
        "tokens_cached",
        "est_cost_usd",
        "cost_gbp",
        "latency_p50",
        "latency_p95",
        "avg_keep_rate",
        "quotes_sent",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(AiCallEvent)
class AiCallEventAdmin(admin.ModelAdmin):
    """Raw AI call events behind the rollups (read-only drill-down)."""

    date_hierarchy = "created_at"
    list_display = (
        "created_at",
        "feature",
        "status",
        "gen_ai_request_model",
        "est_cost_usd",
        "cost_gbp",
        "latency_seconds",
        "trace_id",
    )
    list_filter = ("feature", "status", "gen_ai_request_model")
    search_fields = ("trace_id", "quote_id", "tenant_id", "user_id")
    readonly_fields = (
        "id",
        "created_at",
        "tenant_id",
        "user_id",
        "feature",
        "gen_ai_provider_name",
        "gen_ai_request_model",
        "gen_ai_usage_input_tokens",
        "gen_ai_usage_output_tokens",
        "gen_ai_usage_cached_input_tokens",
        "est_cost_usd",
        "cost_gbp",
        "fx_rate",
        "fx_rate_date",
        "latency_seconds",
        "status",
        "attempt_no",
        "parent_event_id",
        "trace_id",
        "prompt_version",
        "confidence",
        "completeness",
        "retrieval_status",
        "quote_id",
        "quote_request_id",
        "raw_payload",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False
