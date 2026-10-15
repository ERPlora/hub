"""Django admin of the kitchen app: full CRUD on every table for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations' rules
(a station's name taken twice: the database's own constraints still refuse it) and it leaves no event. The
dishes are an inline of their ticket. What the database fills in (ids and timestamps) is shown, not edited.
"""

from django.contrib import admin

from apps.kitchen.models import (
    CategoryRoute,
    DayCounter,
    KitchenSettings,
    LogEntry,
    ProductRoute,
    Station,
    Ticket,
    TicketItem,
)

AUTOMATIC = ("id", "created_at", "updated_at")


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "color",
        "destination",
        "printer_usage",
        "printer_name",
        "is_active",
        "is_deleted",
    )
    list_filter = ("destination", "printer_usage", "is_active", "is_deleted")
    search_fields = ("name", "printer_name")
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "name",
        "color",
        "destination",
        "printer_usage",
        "printer_name",
        "sort_order",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(ProductRoute)
class ProductRouteAdmin(admin.ModelAdmin):
    list_display = ("product", "station")
    list_filter = ("station",)
    search_fields = ("product__name",)
    list_select_related = ("product", "station")
    raw_id_fields = ("product",)
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "product",
        "station",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(CategoryRoute)
class CategoryRouteAdmin(admin.ModelAdmin):
    list_display = ("category", "station")
    list_filter = ("station",)
    search_fields = ("category__name",)
    list_select_related = ("category", "station")
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "category",
        "station",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(KitchenSettings)
class KitchenSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "warning_minutes",
        "critical_minutes",
        "works_from_screen",
        "print_pass",
    )
    readonly_fields = ("id", "updated_at")
    fields = (
        "id",
        "show_timer",
        "warning_minutes",
        "critical_minutes",
        "color_coding",
        "sound_enabled",
        "sound_volume",
        "sound_tone",
        "print_pass",
        "works_from_screen",
        "screen_changed_at",
        "default_order_type",
        "receiving_since",
        "updated_at",
        "updated_by",
    )


@admin.register(DayCounter)
class DayCounterAdmin(admin.ModelAdmin):
    list_display = ("day", "last_number")
    readonly_fields = ("id",)
    fields = ("id", "day", "last_number")


class TicketItemInline(admin.TabularInline):
    model = TicketItem
    extra = 0
    readonly_fields = ("id",)
    fields = (
        "id",
        "position",
        "name",
        "quantity",
        "unit",
        "notes",
        "station",
        "station_name",
        "destination",
        "printer_usage",
        "printer_name",
        "status",
        "void_reason",
        "ready_at",
        "sale_line_id",
        "product_id",
        "total",
    )


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "label",
        "order_type",
        "priority",
        "status",
        "round_no",
        "received_at",
        "is_deleted",
    )
    list_filter = ("status", "priority", "order_type", "is_deleted")
    search_fields = ("number", "label")
    date_hierarchy = "received_at"
    readonly_fields = AUTOMATIC
    inlines = [TicketItemInline]
    fields = (
        "id",
        "number",
        "day",
        "sequence",
        "order_id",
        "round_no",
        "label",
        "order_type",
        "priority",
        "status",
        "notes",
        "waiter",
        "received_at",
        "started_at",
        "ready_at",
        "served_at",
        "cancelled_at",
        "rush_count",
        "reprint_count",
        "total",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "ticket", "item", "actor", "notes")
    list_filter = ("action",)
    search_fields = ("ticket__number", "notes", "actor")
    list_select_related = ("ticket", "item")
    raw_id_fields = ("ticket", "item")
    readonly_fields = ("id",)
    fields = (
        "id",
        "ticket",
        "item",
        "station",
        "action",
        "actor",
        "notes",
        "created_at",
    )
