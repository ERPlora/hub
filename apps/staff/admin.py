"""Django admin of the staff app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables; it repeals the read-only admin of round 9 that apps/demo still copies. A raw admin write
records no event: the actions that need one call the operations of services.py.
"""

from django.contrib import admin

from apps.staff.models import (
    Member,
    Role,
    Schedule,
    ScheduleDay,
    StaffSettings,
    TimeOff,
)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "role", "status", "is_bookable", "user")
    list_filter = ("status", "is_bookable")
    search_fields = ("first_name", "last_name", "email", "phone", "employee_number")
    readonly_fields = ("id", "created_at", "updated_at")
    fields = (
        "id",
        ("first_name", "last_name"),
        ("email", "phone", "employee_number"),
        ("role", "user"),
        ("status", "is_bookable", "booking_buffer"),
        ("hire_date", "termination_date", "termination_reason"),
        ("color", "specialties"),
        "bio",
        ("hourly_rate", "commission_rate"),
        "notes",
        ("created_at", "updated_at"),
    )


class ScheduleDayInline(admin.TabularInline):
    model = ScheduleDay
    extra = 0
    fields = ("weekday", "start_time", "end_time", "break_start", "break_end")


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "member",
        "is_default",
        "effective_from",
        "effective_until",
        "is_active",
    )
    list_filter = ("is_default", "is_active")
    search_fields = ("name", "member__first_name", "member__last_name")
    inlines = [ScheduleDayInline]


@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "leave_type",
        "start_date",
        "end_date",
        "is_full_day",
        "status",
    )
    list_filter = ("status", "leave_type", "is_full_day")
    search_fields = ("member__first_name", "member__last_name")


@admin.register(StaffSettings)
class StaffSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "default_work_start", "default_work_end", "updated_at")
    exclude = ("slot",)
