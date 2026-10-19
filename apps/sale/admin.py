"""Django admin of the sale app: full CRUD over its tables, for the platform's staff only.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com and
has full CRUD over every table, fiscal ones included. What it saves does not go through the operations
(no event, no numbering, no check of the tenders); the database still refuses a negative amount, a line
that does not square, a payment whose change is not tendered − amount and a refund over the total. An open
check's «Delete» locks it first (``lock_orders``), as every write on it does.
"""

from django.contrib import admin
from django.db import transaction

from apps.sale.models import (
    Department,
    Order,
    OrderLine,
    PaymentMethod,
    QuickNote,
    Refund,
    RefundLine,
    RefundPayment,
    Sale,
    SaleCounter,
    SaleLine,
    SalePayment,
    Settings,
)
from apps.sale.services import lock_orders

AUDIT = ("id", "created_at", "updated_at")


def _readonly(model, extra=()) -> tuple:
    names = {field.name for field in model._meta.get_fields()}
    return tuple(name for name in AUDIT if name in names) + tuple(extra)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "is_system", "is_active", "sort_order")
    list_filter = ("type", "is_system", "is_active")
    search_fields = ("name",)
    readonly_fields = _readonly(PaymentMethod)


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "require_customer",
        "allow_discounts",
        "max_discount_percent",
        "updated_at",
    )
    readonly_fields = _readonly(Settings)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "tax_category", "sort_order", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("name",)
    list_select_related = ("tax_category",)
    readonly_fields = _readonly(Department)


@admin.register(QuickNote)
class QuickNoteAdmin(admin.ModelAdmin):
    list_display = ("text", "sort_order", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("text",)
    readonly_fields = _readonly(QuickNote)


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    fields = (
        "position",
        "name",
        "quantity",
        "unit_price",
        "discount_percent",
        "is_gift",
        "line_total",
        "round_no",
        "sale",
        "removed_at",
    )
    readonly_fields = ("sale",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "status",
        "source",
        "provisional_total",
        "version",
        "created_at",
    )
    list_filter = ("status", "source")
    search_fields = ("label", "id")
    readonly_fields = _readonly(Order)
    inlines = [OrderLineInline]

    # «Delete» (the check's page and the list's «Delete selected») locks the checks before Django checks what
    # protects them and gathers their lines. A write under way holds a check while it adds a line, moves lines
    # in or out, or charges it: the deletion waits for it and then takes what it left, or answers «Cannot
    # delete» once a sale charged it, instead of failing at its COMMIT or waiting for it in a circle.
    def get_deleted_objects(self, objs, request):
        if request.method == "POST":
            lock_orders([obj.pk for obj in objs])
        return super().get_deleted_objects(objs, request)

    # The actions run outside a transaction; the lock above lasts until the deletion ends.
    def response_action(self, request, queryset, *args, **kwargs):
        with transaction.atomic():
            return super().response_action(request, queryset, *args, **kwargs)


@admin.register(OrderLine)
class OrderLineAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "order",
        "quantity",
        "unit_price",
        "line_total",
        "round_no",
        "sale",
        "removed_at",
    )
    search_fields = ("name", "sku", "order__id")
    readonly_fields = _readonly(OrderLine)
    raw_id_fields = ("order", "sale", "department")


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    fields = (
        "position",
        "name",
        "quantity",
        "unit_price",
        "tax_rate",
        "net_amount",
        "tax_amount",
        "line_total",
    )


class SalePaymentInline(admin.TabularInline):
    model = SalePayment
    extra = 0
    fields = (
        "position",
        "method",
        "method_name",
        "method_type",
        "amount",
        "tendered",
        "change",
        "reference",
    )


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "business_day",
        "status",
        "document_type",
        "customer_name",
        "total",
        "refunded_total",
    )
    list_filter = ("status", "document_type", "business_day")
    search_fields = ("number", "customer_name", "idempotency_key")
    readonly_fields = _readonly(Sale)
    raw_id_fields = ("order", "customer")
    inlines = [SaleLineInline, SalePaymentInline]


@admin.register(SaleLine)
class SaleLineAdmin(admin.ModelAdmin):
    list_display = ("name", "sale", "quantity", "tax_rate", "line_total")
    search_fields = ("name", "sku", "sale__number")
    readonly_fields = _readonly(SaleLine)
    raw_id_fields = ("sale",)


@admin.register(SalePayment)
class SalePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "sale",
        "method_name",
        "method_type",
        "amount",
        "tendered",
        "change",
    )
    search_fields = ("sale__number", "reference")
    readonly_fields = _readonly(SalePayment)
    raw_id_fields = ("sale",)


@admin.register(SaleCounter)
class SaleCounterAdmin(admin.ModelAdmin):
    list_display = ("day", "last")
    readonly_fields = _readonly(SaleCounter)


class RefundPaymentInline(admin.TabularInline):
    model = RefundPayment
    extra = 0
    fields = (
        "position",
        "sale_payment",
        "method",
        "method_name",
        "method_type",
        "amount",
    )
    raw_id_fields = ("sale_payment",)


class RefundLineInline(admin.TabularInline):
    model = RefundLine
    extra = 0
    fields = ("sale_line", "quantity")
    raw_id_fields = ("sale_line",)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("sale", "total", "reason", "created_at", "created_by")
    search_fields = ("sale__number", "reason", "idempotency_key")
    readonly_fields = _readonly(Refund)
    raw_id_fields = ("sale",)
    inlines = [RefundPaymentInline, RefundLineInline]


@admin.register(RefundPayment)
class RefundPaymentAdmin(admin.ModelAdmin):
    list_display = ("refund", "method_name", "amount")
    readonly_fields = _readonly(RefundPayment)
    raw_id_fields = ("refund", "sale_payment")


@admin.register(RefundLine)
class RefundLineAdmin(admin.ModelAdmin):
    list_display = ("refund", "sale_line", "quantity")
    readonly_fields = _readonly(RefundLine)
    raw_id_fields = ("refund", "sale_line")
