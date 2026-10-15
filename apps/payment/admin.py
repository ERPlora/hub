"""Django admin of the payment app: full CRUD over its tables, for the platform's staff only.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com and
has full CRUD over every table. The database still refuses an amount of 0 or less, an unknown status,
a repeated reference and a repeated method name; the ladder of a payment and its events are the
operations' (services.py), which the screens, the API and the assistant use.
"""

from django.contrib import admin

from apps.payment.models import Payment, PaymentCounter, PaymentMethod

#: Set by the database or the model: shown, never typed.
AUDIT = ("id", "created_at", "updated_at")


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "method_type", "bank_account_ref", "is_active")
    list_filter = ("method_type", "is_active")
    search_fields = ("name", "bank_account_ref")
    readonly_fields = AUDIT
    fields = (
        "id",
        "name",
        "method_type",
        "bank_account_ref",
        "is_active",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "payment_date",
        "beneficiary_name",
        "amount",
        "currency",
        "status",
        "method",
    )
    list_filter = ("status", "currency", "method")
    search_fields = ("reference", "beneficiary_name", "supplier_invoice_ref")
    date_hierarchy = "payment_date"
    list_select_related = ("method",)
    readonly_fields = AUDIT
    fields = (
        "id",
        "reference",
        "method",
        "payment_date",
        "amount",
        "currency",
        "beneficiary_name",
        "beneficiary_iban",
        "concept",
        "status",
        "supplier_invoice_ref",
        "cancel_reason",
        "approved_by",
        "approved_at",
        "sent_at",
        "completed_at",
        "cancelled_by",
        "cancelled_at",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )


@admin.register(PaymentCounter)
class PaymentCounterAdmin(admin.ModelAdmin):
    list_display = ("day", "last")
    readonly_fields = ("id",)
    fields = ("id", "day", "last")
