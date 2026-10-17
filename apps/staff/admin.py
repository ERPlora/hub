"""Django admin of the staff app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables; it repeals the read-only admin of round 9 that apps/demo still copies. A raw admin write
records no event: the actions that need one call the operations of services.py. A record's «Delete»
locks it first (``lock_members``), as every write on that person does: it waits for the one under way
and only then checks what protects the record.
"""

from django.contrib import admin
from django.db import transaction

from apps.staff.models import (
    Member,
    Role,
    Schedule,
    ScheduleDay,
    StaffSettings,
    TimeOff,
)
from apps.staff.services import lock_members


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

    # Django deletes what hangs from a record (schedules, time off, who performs a service…) and then the
    # record. Entering through the record first, as every write on that person does, it waits for a write
    # under way and then deletes what that write left, instead of waiting for it in a circle.
    def delete_model(self, request, obj):
        with transaction.atomic():
            lock_members([obj.pk])
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            lock_members(queryset.values_list("pk", flat=True))
            super().delete_queryset(request, queryset)

    # Before deleting, the delete page and «Delete selected» check what protects the records (their days
    # clocked in, their appointments), and a write under way may be adding one. Locked before the check, it
    # waits for that write and sees what it left: «Cannot delete», as for a record protected before.
    def get_deleted_objects(self, objs, request):
        if request.method == "POST":
            lock_members([obj.pk for obj in objs])
        return super().get_deleted_objects(objs, request)

    # The actions run outside a transaction; the lock above lasts until the deletion ends.
    def response_action(self, request, queryset, *args, **kwargs):
        with transaction.atomic():
            return super().response_action(request, queryset, *args, **kwargs)


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
