"""Django admin of the attendance app, for the platform's staff only (round 12, PLAN §17; hubs.erplora.com).

Settings: full CRUD (what the admin saves does not go through the operations: no event; the database
still refuses a radius outside the five, hours outside 1–24 and half a workplace). Working days, their
breaks and their corrections: shown whole, read-only, never added nor deleted. The law keeps the
working-day record four years and a time only changes with a correction that leaves its trail
(art. 34.9 ET): that is the operation `attendance.record.correct`, which the screens, the assistant and
the API use. Only a day's internal note can be changed here. It departs from the admin's «full CRUD
over every table» as `invoice` does for its invoices (RD 1619/2012).
"""

from django.contrib import admin

from apps.attendance.models import AttendanceSettings, Break, Correction, Record


class BreakInline(admin.TabularInline):
    model = Break
    extra = 0
    can_delete = False
    fields = ("started_at", "ended_at", "created_at", "updated_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class CorrectionInline(admin.TabularInline):
    model = Correction
    extra = 0
    can_delete = False
    fk_name = "record"
    fields = (
        "created_at",
        "created_by",
        "old_clock_in_at",
        "old_clock_out_at",
        "old_status",
        "new_clock_in_at",
        "new_clock_out_at",
        "new_status",
        "reason",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = (
        "work_date",
        "member",
        "clock_in_at",
        "clock_out_at",
        "status",
        "source",
    )
    list_filter = ("status", "source", "work_date")
    search_fields = ("member__first_name", "member__last_name")
    list_select_related = ("member",)
    date_hierarchy = "work_date"
    inlines = [BreakInline, CorrectionInline]

    def get_readonly_fields(self, request, obj=None) -> list[str]:
        return [
            field.name for field in Record._meta.concrete_fields if field.name != "note"
        ]

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Correction)
class CorrectionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "record",
        "created_by",
        "old_status",
        "new_status",
        "reason",
    )
    search_fields = (
        "record__member__first_name",
        "record__member__last_name",
        "reason",
    )
    list_select_related = ("record__member", "created_by")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(AttendanceSettings)
class AttendanceSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "require_location",
        "geofence_radius_m",
        "workplace_lat",
        "workplace_lng",
        "auto_close_after_hours",
        "updated_at",
    )
    readonly_fields = ("id", "updated_by", "updated_at")
