"""Django admin of the sale app, for the platform's staff only (hubs.erplora.com, PLAN §17–§18).

The open tables (payment methods, settings, departments, quick notes, open checks and their lines) have
full CRUD. What was charged is a fiscal document (PLAN-HUB §3.2, round 2026-10-20): a sale's number is its
simplified invoice's and the day's counter gives it, so sales, their lines and payments, the counter, and
refunds with their lines and payments are shown whole and never added nor deleted; only the notes of a sale
and of a refund can change. A charge is corrected by its void or its refunds, as at the till. What the admin
saves does not go through the operations (no event, no check of the open check). The «Delete» of an open check
locks it first (``lock_orders``), as every write on it does, and so does that of a department or a payment method
(``lock_rows``), which a write naming it holds.
"""

from django.contrib import admin
from live.operations import atomic

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
from apps.sale.services import lock_orders, lock_rows

AUDIT = ("id", "created_at", "updated_at")


def _readonly(model, extra=()) -> tuple:
    names = {field.name for field in model._meta.get_fields()}
    return tuple(name for name in AUDIT if name in names) + tuple(extra)


class LockedDeletion:
    """«Delete» (the row's page and the list's «Delete selected») locks the rows before Django checks what protects
    them and gathers what goes with them. A write under way holds an open check while it adds to it, moves lines in
    or out or charges it, and holds the department or the payment method it names while it writes the line or the
    tender that points at it: the deletion waits for it and then takes what it left, or answers «Cannot delete» once
    what the write wrote protects the row, instead of failing at its COMMIT or waiting for it in a circle."""

    def lock(self, ids) -> list:
        """Locks the rows ``ids`` of this admin's table in id order (``lock_rows``)."""
        return lock_rows(self.model, ids)

    def get_deleted_objects(self, objs, request):
        # Only the confirmed deletion (a POST, in its transaction) locks: the confirmation page does not wait.
        if request.method == "POST":
            self.lock([obj.pk for obj in objs])
        return super().get_deleted_objects(objs, request)

    # The actions run outside a transaction; the lock above lasts until the deletion ends.
    def response_action(self, request, queryset, *args, **kwargs):
        with atomic():
            return super().response_action(request, queryset, *args, **kwargs)


class ChargedAdmin(admin.ModelAdmin):
    """What was charged: every column shown and none typed but ``editable``; nothing added nor deleted."""

    editable: tuple[str, ...] = ()

    def get_readonly_fields(self, request, obj=None) -> tuple:
        return tuple(
            field.name
            for field in self.model._meta.concrete_fields
            if field.name not in self.editable
        )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return bool(self.editable) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ChargedInline(admin.TabularInline):
    """The lines or the payments of what was charged, shown read-only."""

    extra = 0

    def get_readonly_fields(self, request, obj=None) -> tuple:
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(PaymentMethod)
class PaymentMethodAdmin(LockedDeletion, admin.ModelAdmin):
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
class DepartmentAdmin(LockedDeletion, admin.ModelAdmin):
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
class OrderAdmin(LockedDeletion, admin.ModelAdmin):
    lock = staticmethod(lock_orders)
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


class SaleLineInline(ChargedInline):
    model = SaleLine
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


class SalePaymentInline(ChargedInline):
    model = SalePayment
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
class SaleAdmin(ChargedAdmin):
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
    editable = ("notes",)
    inlines = [SaleLineInline, SalePaymentInline]


@admin.register(SaleLine)
class SaleLineAdmin(ChargedAdmin):
    list_display = ("name", "sale", "quantity", "tax_rate", "line_total")
    search_fields = ("name", "sku", "sale__number")


@admin.register(SalePayment)
class SalePaymentAdmin(ChargedAdmin):
    list_display = (
        "sale",
        "method_name",
        "method_type",
        "amount",
        "tendered",
        "change",
    )
    search_fields = ("sale__number", "reference")


@admin.register(SaleCounter)
class SaleCounterAdmin(ChargedAdmin):
    list_display = ("day", "last")


class RefundPaymentInline(ChargedInline):
    model = RefundPayment
    fields = (
        "position",
        "sale_payment",
        "method",
        "method_name",
        "method_type",
        "amount",
    )


class RefundLineInline(ChargedInline):
    model = RefundLine
    fields = ("sale_line", "quantity")


@admin.register(Refund)
class RefundAdmin(ChargedAdmin):
    list_display = ("sale", "total", "reason", "created_at", "created_by")
    search_fields = ("sale__number", "reason", "idempotency_key")
    editable = ("note",)
    inlines = [RefundPaymentInline, RefundLineInline]


@admin.register(RefundPayment)
class RefundPaymentAdmin(ChargedAdmin):
    list_display = ("refund", "method_name", "amount")


@admin.register(RefundLine)
class RefundLineAdmin(ChargedAdmin):
    list_display = ("refund", "sale_line", "quantity")
