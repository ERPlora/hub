"""Django admin of the customer app: full CRUD over every table, for the platform's staff.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub admin, only on ``hubs.erplora.com``, has
full CRUD over a hub's tables; what each staff member may do is Django's own permissions. A change
made here writes no event to the outbox: the screens see it on their next re-run.
"""

from django.contrib import admin

from apps.customer.models import (
    Activity,
    Consent,
    Customer,
    CustomerGroup,
    CustomerTag,
    CustomField,
    CustomFieldValue,
    HealthRecord,
    OrderLink,
    Purchase,
)


class CustomFieldValueInline(admin.TabularInline):
    model = CustomFieldValue
    extra = 0
    fields = ("field", "value")


class PurchaseInline(admin.TabularInline):
    model = Purchase
    extra = 0
    fields = ("sale_id", "amount", "currency", "status", "recorded_at", "voided_at")


class ConsentInline(admin.TabularInline):
    model = Consent
    extra = 0
    fields = (
        "purpose",
        "channel",
        "state",
        "contact_point",
        "source",
        "recorded_by",
        "occurred_at",
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "email",
        "phone",
        "lifecycle_stage",
        "total_spent",
        "is_active",
        "deleted_at",
    )
    list_filter = ("lifecycle_stage", "source", "is_active")
    search_fields = ("name", "email", "phone", "tax_id", "company_name")
    readonly_fields = ("id", "created_at", "updated_at")
    fields = (
        "id",
        "name",
        "email",
        "phone",
        "tax_id",
        "company_name",
        "address",
        "city",
        "postal_code",
        "country",
        "avatar",
        "birthday",
        "anniversary",
        "source",
        "lifecycle_stage",
        "preferred_channel",
        "notes",
        "is_active",
        "total_purchases",
        "total_spent",
        "last_purchase_at",
        "groups",
        "tags",
        "created_at",
        "updated_at",
        "deleted_at",
        "merged_into",
        "erased_at",
    )
    inlines = [CustomFieldValueInline, PurchaseInline, ConsentInline]


@admin.register(CustomerGroup)
class CustomerGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


@admin.register(CustomerTag)
class CustomerTagAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(CustomField)
class CustomFieldAdmin(admin.ModelAdmin):
    list_display = ("name", "field_type", "is_required", "sort_order", "is_active")
    list_filter = ("field_type", "is_required", "is_active")
    search_fields = ("name",)


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("customer", "kind", "title", "actor", "created_at")
    list_filter = ("kind",)
    search_fields = ("text", "title", "related_id")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "sale_id",
        "amount",
        "currency",
        "status",
        "recorded_at",
    )
    list_filter = ("status",)
    search_fields = ("sale_id",)


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ("customer", "purpose", "channel", "state", "source", "occurred_at")
    list_filter = ("purpose", "channel", "state", "source")


@admin.register(OrderLink)
class OrderLinkAdmin(admin.ModelAdmin):
    list_display = ("order_id", "customer", "linked_at")
    search_fields = ("order_id",)


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    # Health data (CUSTOMER-F32): the list shows whose record it is and when it changed, not its data.
    list_display = ("customer", "updated_at", "updated_by")
    raw_id_fields = ("customer",)
