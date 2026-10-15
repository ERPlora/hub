"""Django admin of the schedule app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. The intervals are lines of their day. A raw admin write records no event and skips the rules of
engine.py (sorted, never overlapping): the screens and the assistant go through services.py.
"""

from django.contrib import admin

from apps.schedule.models import (
    Override,
    OverrideInterval,
    ScheduleSettings,
    SpecialDay,
    SpecialDayInterval,
    WeekDay,
    WeekDayInterval,
)

INTERVAL_FIELDS = ("position", "open_time", "close_time")


class WeekDayIntervalInline(admin.TabularInline):
    model = WeekDayInterval
    extra = 0
    fields = INTERVAL_FIELDS


class SpecialDayIntervalInline(admin.TabularInline):
    model = SpecialDayInterval
    extra = 0
    fields = INTERVAL_FIELDS


class OverrideIntervalInline(admin.TabularInline):
    model = OverrideInterval
    extra = 0
    fields = INTERVAL_FIELDS


@admin.register(WeekDay)
class WeekDayAdmin(admin.ModelAdmin):
    list_display = ("__str__", "weekday", "is_closed", "updated_at")
    list_filter = ("is_closed",)
    readonly_fields = ("id", "updated_at")
    fields = ("id", "weekday", "is_closed", "updated_at")
    inlines = [WeekDayIntervalInline]


@admin.register(SpecialDay)
class SpecialDayAdmin(admin.ModelAdmin):
    list_display = ("date", "name", "is_closed", "recurring_yearly")
    list_filter = ("is_closed", "recurring_yearly")
    search_fields = ("name", "notes")
    date_hierarchy = "date"
    readonly_fields = ("id", "created_at", "updated_at")
    fields = (
        "id",
        "date",
        "name",
        "is_closed",
        "recurring_yearly",
        "notes",
        ("created_at", "updated_at"),
    )
    inlines = [SpecialDayIntervalInline]


@admin.register(Override)
class OverrideAdmin(admin.ModelAdmin):
    list_display = ("reason", "start_date", "end_date", "is_closed")
    list_filter = ("is_closed",)
    search_fields = ("reason",)
    readonly_fields = ("id", "created_at", "updated_at")
    fields = (
        "id",
        ("start_date", "end_date"),
        "reason",
        "is_closed",
        ("created_at", "updated_at"),
    )
    inlines = [OverrideIntervalInline]


@admin.register(ScheduleSettings)
class ScheduleSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "week_starts_on", "hours_confirmed", "updated_at")
    readonly_fields = ("id", "updated_at")
    fields = ("id", "week_starts_on", "hours_confirmed", "updated_at")
