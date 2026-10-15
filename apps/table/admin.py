"""Django admin of the table app: full CRUD on every table for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations'
rules (a table seated twice, a number taken: the database's own constraints still refuse those) and it
leaves no event. A table's status is computed when read, so the admin edits what is stored: ``blocked``,
the checks and their trail, the holds. What the database fills in (ids and timestamps) is shown, not
edited.
"""

from django.contrib import admin

from apps.table.models import (
    Hold,
    SessionMove,
    Table,
    TableSession,
    TableSettings,
    Zone,
)

AUTOMATIC = ("id", "created_at", "updated_at")


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "sort_order", "is_active", "is_deleted")
    list_filter = ("is_active", "is_deleted", "color")
    search_fields = ("name", "description")
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "name",
        "description",
        "color",
        "sort_order",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "name",
        "zone",
        "capacity",
        "shape",
        "blocked",
        "is_active",
        "is_deleted",
    )
    list_filter = ("zone", "shape", "blocked", "is_active", "is_deleted")
    search_fields = ("number", "name")
    list_select_related = ("zone",)
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "zone",
        "number",
        "name",
        "capacity",
        "shape",
        "position_x",
        "position_y",
        "width",
        "height",
        "blocked",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


class SessionMoveInline(admin.TabularInline):
    """The check's trail through the tables: where it sat, from when to when and why."""

    model = SessionMove
    extra = 0
    fields = (
        "table",
        "assigned_at",
        "released_at",
        "assignment_reason",
        "release_reason",
    )
    raw_id_fields = ("table",)


@admin.register(TableSession)
class TableSessionAdmin(admin.ModelAdmin):
    list_display = (
        "table",
        "status",
        "guests_count",
        "waiter_name",
        "opened_at",
        "closed_at",
        "is_deleted",
    )
    list_filter = ("status", "is_deleted")
    search_fields = ("table__number", "waiter_name", "notes", "order_id")
    list_select_related = ("table",)
    raw_id_fields = ("table", "transferred_from", "merged_into", "split_from")
    readonly_fields = AUTOMATIC
    inlines = [SessionMoveInline]
    fields = (
        "id",
        "table",
        "order_id",
        "status",
        "guests_count",
        "waiter_id",
        "waiter_name",
        "opened_at",
        "closed_at",
        "notes",
        "transferred_from",
        "merged_into",
        "split_from",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(Hold)
class HoldAdmin(admin.ModelAdmin):
    list_display = (
        "table",
        "label",
        "held_from",
        "held_until",
        "party_size",
        "source",
        "status",
    )
    list_filter = ("status", "source")
    search_fields = ("label", "source_ref", "table__number")
    list_select_related = ("table",)
    raw_id_fields = ("table",)
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "table",
        "source",
        "source_ref",
        "held_from",
        "held_until",
        "party_size",
        "label",
        "customer_id",
        "status",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(TableSettings)
class TableSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "prompt_guests_on_seat",
        "timer_warning_minutes",
        "timer_critical_minutes",
    )
    readonly_fields = ("id", "updated_at")
    fields = (
        "id",
        "prompt_guests_on_seat",
        "timer_warning_minutes",
        "timer_critical_minutes",
        "updated_at",
        "updated_by",
    )
