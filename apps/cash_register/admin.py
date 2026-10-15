"""Django admin of the cash register app: full CRUD over its tables, for the platform's staff only.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com and has
full CRUD over every table. What it saves does not go through the operations (no event, no number, no
check of the open session); the database still refuses a negative amount, a second open session, a
difference that is not counted − expected and a sale line copied twice.
"""

from django.contrib import admin

from apps.cash_register.models import (
    Count,
    Movement,
    Register,
    Session,
    SessionCounter,
    Settings,
)

READ_ONLY = ("id", "created_at", "updated_at", "opened_at", "closed_at", "counted_at")


def _readonly(model, extra=()) -> tuple:
    names = {field.name for field in model._meta.get_fields()}
    return tuple(name for name in READ_ONLY if name in names) + tuple(extra)


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "enable_cash_register",
        "require_closing_balance",
        "require_blind_count",
        "auto_close_enabled",
        "auto_close_time",
        "updated_at",
    )
    readonly_fields = _readonly(Settings)


@admin.register(Register)
class RegisterAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = _readonly(Register)


@admin.register(SessionCounter)
class SessionCounterAdmin(admin.ModelAdmin):
    list_display = ("day", "last")
    readonly_fields = _readonly(SessionCounter)


class MovementInline(admin.TabularInline):
    model = Movement
    extra = 0
    fields = (
        "created_at",
        "type",
        "amount",
        "method_type",
        "method_name",
        "sale_number",
        "description",
        "created_by",
    )
    readonly_fields = _readonly(Movement)
    show_change_link = True


class CountInline(admin.TabularInline):
    model = Count
    extra = 0
    fields = ("counted_at", "type", "total", "notes", "counted_by")
    readonly_fields = _readonly(Count)
    show_change_link = True


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "status",
        "register",
        "opened_at",
        "opening_balance",
        "expected_balance",
        "closing_balance",
        "difference",
        "auto_closed",
    )
    list_filter = ("status", "auto_closed", "register")
    search_fields = ("number", "opened_by", "closed_by")
    list_select_related = ("register",)
    readonly_fields = _readonly(Session)
    inlines = [MovementInline, CountInline]


@admin.register(Movement)
class MovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "session",
        "type",
        "amount",
        "method_type",
        "sale_number",
        "description",
    )
    list_filter = ("type", "method_type")
    search_fields = ("description", "sale_number", "created_by")
    list_select_related = ("session",)
    raw_id_fields = ("session", "sale", "sale_payment", "refund_payment")
    readonly_fields = _readonly(Movement)


@admin.register(Count)
class CountAdmin(admin.ModelAdmin):
    list_display = ("counted_at", "session", "type", "total", "counted_by")
    list_filter = ("type",)
    list_select_related = ("session",)
    raw_id_fields = ("session",)
    readonly_fields = _readonly(Count)
