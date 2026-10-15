"""Django admin of the service app: full CRUD on every table for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations'
rules (a name taken, a voucher's balance, the sessions that are never edited), so it warns rather than
prevents, and it leaves no event. The one rule it keeps is the categories' tree: a parent that would
close a loop is refused (a loop would leave the tree unreadable). What the database fills in (ids and timestamps) is shown, not edited.
"""

from django import forms
from django.contrib import admin

from apps.service.models import (
    CATEGORY_CYCLE,
    CATEGORY_LOOP,
    Assignment,
    Category,
    Grant,
    GrantAdjustment,
    Package,
    PackageItem,
    Redemption,
    Service,
    ServiceSettings,
    parent_problem,
)

AUTOMATIC = ("id", "created_at", "updated_at")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "pricing_type",
        "price",
        "duration_minutes",
        "tax_category",
        "is_active",
    )
    list_filter = ("is_active", "pricing_type", "is_bookable")
    search_fields = ("name", "sku", "barcode")
    list_select_related = ("category", "tax_category")
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "name",
        "description",
        "short_description",
        "category",
        "pricing_type",
        "price",
        "min_price",
        "max_price",
        "cost",
        "duration_minutes",
        "buffer_before",
        "buffer_after",
        "max_capacity",
        "is_bookable",
        "requires_confirmation",
        "allow_online_booking",
        "sort_order",
        "is_featured",
        "sku",
        "barcode",
        "notes",
        "tax_category",
        "is_active",
        "archived_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


class CategoryAdminForm(forms.ModelForm):
    """The one rule the admin keeps for the tree: a category never hangs from itself or a descendant."""

    class Meta:
        model = Category
        fields = "__all__"

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent is not None and self.instance.pk is not None:
            parent_of = dict(Category.objects.values_list("id", "parent_id"))
            problem = parent_problem(self.instance.pk, parent.pk, parent_of)
            if problem:
                raise forms.ValidationError(str(CATEGORY_CYCLE if problem == "cycle" else CATEGORY_LOOP))
        return parent


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    form = CategoryAdminForm
    list_display = ("name", "parent", "sort_order", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("name",)
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "name",
        "description",
        "parent",
        "icon",
        "color",
        "sort_order",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "service",
        "member",
        "custom_duration",
        "custom_price",
        "is_primary",
        "is_active",
    )
    list_filter = ("is_primary", "is_active")
    search_fields = ("service__name", "member__first_name", "member__last_name")
    list_select_related = ("service", "member")
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "service",
        "member",
        "custom_duration",
        "custom_price",
        "is_primary",
        "is_active",
        "created_at",
        "updated_at",
    )


class PackageItemInline(admin.TabularInline):
    model = PackageItem
    extra = 0
    fields = ("service", "sessions", "sort_order")


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "max_uses",
        "validity_days",
        "fixed_price",
        "is_active",
        "is_deleted",
    )
    list_filter = ("is_active", "is_deleted", "discount_type")
    search_fields = ("name",)
    readonly_fields = AUTOMATIC
    inlines = [PackageItemInline]
    fields = (
        "id",
        "name",
        "description",
        "discount_type",
        "discount_percent_bp",
        "discount_amount",
        "fixed_price",
        "validity_days",
        "max_uses",
        "sort_order",
        "is_active",
        "is_featured",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


class GrantAdjustmentInline(admin.TabularInline):
    model = GrantAdjustment
    extra = 0
    fields = ("uses_delta", "days_delta", "reason", "actor", "created_at")


class RedemptionInline(admin.TabularInline):
    model = Redemption
    extra = 0
    fields = (
        "service",
        "status",
        "order_line_id",
        "hold_until",
        "appointment_id",
        "sale_id",
        "settled_at",
        "note",
        "actor",
        "redeemed_at",
        "ended_at",
        "ended_by",
        "return_reference",
        "return_reason",
    )


@admin.register(Grant)
class GrantAdmin(admin.ModelAdmin):
    list_display = (
        "package",
        "customer",
        "granted_at",
        "amount",
        "max_uses",
        "validity_days",
        "voided_at",
    )
    list_filter = ("source",)
    search_fields = ("package__name", "customer__name", "sale_id")
    list_select_related = ("package", "customer")
    readonly_fields = AUTOMATIC
    inlines = [GrantAdjustmentInline, RedemptionInline]
    fields = (
        "id",
        "package",
        "customer",
        "granted_at",
        "source",
        "sale_id",
        "amount",
        "net_amount",
        "tax_amount",
        "max_uses",
        "validity_days",
        "note",
        "voided_at",
        "voided_by",
        "void_reason",
        "created_by",
        "created_at",
        "updated_at",
    )


@admin.register(ServiceSettings)
class ServiceSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "default_duration",
        "default_buffer_time",
        "default_tax_category",
        "allow_online_booking",
        "updated_at",
    )
    readonly_fields = ("id", "updated_at")
    fields = (
        "id",
        "default_duration",
        "default_buffer_time",
        "default_tax_category",
        "show_prices",
        "show_duration",
        "allow_online_booking",
        "updated_at",
        "updated_by",
    )
