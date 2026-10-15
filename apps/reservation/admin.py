"""Django admin of the reservation app: full CRUD on every table for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations' rules
(the gate, the steps of a reservation, the holds of Tables) — the database's own constraints still refuse
what it never allows — and it leaves no event. What the database fills in (ids and timestamps) is shown,
not edited.
"""

from django.contrib import admin

from apps.reservation.models import (
    BlockedDate,
    Reservation,
    Settings,
    TimeSlot,
    WaitlistEntry,
)

AUTOMATIC = ("id", "created_at", "updated_at")
AUDIT = ("created_at", "updated_at", "created_by", "updated_by")


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "min_party_size",
        "max_party_size",
        "default_duration_minutes",
        "auto_confirm",
        "require_phone",
        "updated_at",
    )
    readonly_fields = ("id", "updated_at")
    fields = (
        "id",
        "min_party_size",
        "max_party_size",
        "min_advance_hours",
        "max_advance_days",
        "default_duration_minutes",
        "auto_confirm",
        "require_phone",
        "require_email",
        "no_show_window_minutes",
        "updated_at",
        "updated_by",
    )


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = (
        "day_of_week",
        "start_time",
        "end_time",
        "max_reservations",
        "max_covers",
        "is_deleted",
    )
    list_filter = ("day_of_week", "is_deleted")
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "day_of_week",
        "start_time",
        "end_time",
        "max_reservations",
        "max_covers",
        "is_deleted",
        "deleted_at",
        *AUDIT,
    )


@admin.register(BlockedDate)
class BlockedDateAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "reason",
        "is_full_day",
        "blocked_from",
        "blocked_until",
        "is_deleted",
    )
    list_filter = ("is_full_day", "is_deleted")
    search_fields = ("reason",)
    date_hierarchy = "date"
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "date",
        "reason",
        "is_full_day",
        "blocked_from",
        "blocked_until",
        "is_deleted",
        "deleted_at",
        *AUDIT,
    )


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "guest_name",
        "date",
        "time",
        "party_size",
        "table",
        "status",
        "source",
        "is_deleted",
    )
    list_filter = ("status", "source", "is_deleted")
    search_fields = ("guest_name", "guest_phone", "guest_email")
    date_hierarchy = "date"
    list_select_related = ("table",)
    raw_id_fields = ("customer", "table")
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "customer",
        "guest_name",
        "guest_phone",
        "guest_email",
        "date",
        "time",
        "party_size",
        "duration_minutes",
        "table",
        "status",
        "source",
        "notes",
        "internal_notes",
        "confirmed_at",
        "seated_at",
        "completed_at",
        "cancelled_at",
        "no_show_at",
        "cancellation_reason",
        "table_session_id",
        "is_deleted",
        "deleted_at",
        *AUDIT,
    )


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = (
        "guest_name",
        "date",
        "preferred_time",
        "party_size",
        "is_contacted",
        "reservation",
        "is_deleted",
    )
    list_filter = ("is_contacted", "is_deleted")
    search_fields = ("guest_name", "guest_phone", "guest_email")
    date_hierarchy = "date"
    raw_id_fields = ("customer", "reservation")
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "customer",
        "guest_name",
        "guest_phone",
        "guest_email",
        "date",
        "preferred_time",
        "party_size",
        "notes",
        "is_contacted",
        "contacted_at",
        "reservation",
        "is_deleted",
        "deleted_at",
        *AUDIT,
    )
