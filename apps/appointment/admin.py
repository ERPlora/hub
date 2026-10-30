"""Django admin of the appointment app: full CRUD on every table for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations' rules
(an overlap, the numbering, a charged appointment), so it warns rather than prevents, and it leaves no
event. What the database fills in (ids and timestamps) is shown, not edited. An appointment's or a series'
«Delete» locks it first (``lock_appointments``, ``lock_series``), as every write on it does.
"""

from collections.abc import Callable

from django.contrib import admin
from live.operations import atomic

from apps.appointment.models import (
    Appointment,
    AppointmentService,
    BlockedTime,
    Counter,
    History,
    Recurring,
    RecurringService,
    Settings,
)
from apps.appointment.services import lock_appointments, lock_series

AUTOMATIC = ("id", "created_at", "updated_at")


class LockedDeletion:
    """«Delete» (the row's page and the list's «Delete selected») locks the rows with ``lock`` before Django
    checks what protects them and gathers what goes with them. A write under way holds a row while it adds to
    what hangs from it (a history line, service lines, booked appointments, a split series): the deletion
    waits for it and then takes what it added, or answers «Cannot delete» when that protects the row, instead
    of failing at its COMMIT."""

    #: Locks the rows of these ids in id order (``lock_appointments``, ``lock_series``).
    lock: Callable[[list], list]

    def get_deleted_objects(self, objs, request):
        if request.method == "POST":
            self.lock([obj.pk for obj in objs])
        return super().get_deleted_objects(objs, request)

    # The actions run outside a transaction; the lock above lasts until the deletion ends.
    def response_action(self, request, queryset, *args, **kwargs):
        with atomic():
            return super().response_action(request, queryset, *args, **kwargs)


class AppointmentServiceInline(admin.TabularInline):
    model = AppointmentService
    extra = 0
    fields = ("position", "service", "name", "price", "duration_minutes")
    raw_id_fields = ("service",)


class HistoryInline(admin.TabularInline):
    model = History
    extra = 0
    fields = (
        "at",
        "action",
        "actor",
        "by_customer",
        "reason",
        "old_value",
        "new_value",
    )
    readonly_fields = ("id", "at")


@admin.register(Appointment)
class AppointmentAdmin(LockedDeletion, admin.ModelAdmin):
    lock = staticmethod(lock_appointments)
    list_display = (
        "number",
        "start",
        "customer_name",
        "staff_name",
        "status",
        "source",
        "sale_id",
        "deleted_at",
    )
    list_filter = ("status", "source")
    search_fields = ("number", "customer_name", "staff_name", "customer_phone")
    date_hierarchy = "start"
    raw_id_fields = ("customer", "staff", "recurring")
    readonly_fields = AUTOMATIC
    inlines = [AppointmentServiceInline, HistoryInline]
    fields = (
        "id",
        "number",
        "customer",
        "customer_name",
        "customer_phone",
        "customer_email",
        "staff",
        "staff_name",
        "start",
        "end",
        "duration_minutes",
        "status",
        "source",
        "notes",
        "internal_notes",
        "cancelled_at",
        "cancellation_reason",
        "cancelled_by_customer",
        "sale_id",
        "order_id",
        "charged_at",
        "recurring",
        "occurrence_date",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )


@admin.register(BlockedTime)
class BlockedTimeAdmin(admin.ModelAdmin):
    list_display = ("title", "block_type", "start", "end", "all_day", "staff")
    list_filter = ("block_type", "all_day")
    search_fields = ("title", "reason")
    raw_id_fields = ("staff",)
    readonly_fields = AUTOMATIC
    fields = (
        "id",
        "title",
        "block_type",
        "start",
        "end",
        "all_day",
        "staff",
        "reason",
        "created_at",
        "updated_at",
        "created_by",
    )


class RecurringServiceInline(admin.TabularInline):
    model = RecurringService
    extra = 0
    fields = ("position", "service")
    raw_id_fields = ("service",)


@admin.register(Recurring)
class RecurringAdmin(LockedDeletion, admin.ModelAdmin):
    lock = staticmethod(lock_series)
    list_display = (
        "customer_name",
        "staff_name",
        "frequency",
        "day_of_week",
        "time",
        "start_date",
        "is_active",
    )
    list_filter = ("frequency", "is_active")
    search_fields = ("customer_name", "staff_name")
    raw_id_fields = ("customer", "staff", "split_from")
    readonly_fields = AUTOMATIC
    inlines = [RecurringServiceInline]
    fields = (
        "id",
        "customer",
        "customer_name",
        "staff",
        "staff_name",
        "frequency",
        "day_of_week",
        "time",
        "duration_minutes",
        "start_date",
        "end_date",
        "max_occurrences",
        "is_active",
        "split_from",
        "deleted_at",
        "created_at",
        "updated_at",
        "created_by",
    )


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = (
        "default_duration",
        "min_booking_notice",
        "max_advance_booking",
        "allow_overlapping",
        "updated_at",
    )
    readonly_fields = ("id", "updated_at")
    fields = (
        "id",
        "default_duration",
        "min_booking_notice",
        "max_advance_booking",
        "allow_overlapping",
        "allow_customer_cancellation",
        "cancellation_notice_hours",
        "calendar_start_hour",
        "calendar_end_hour",
        "slot_interval",
        "auto_confirm_online",
        "updated_at",
        "updated_by",
    )


@admin.register(Counter)
class CounterAdmin(admin.ModelAdmin):
    list_display = ("day", "last_number")
    readonly_fields = ("id",)
    fields = ("id", "day", "last_number")
