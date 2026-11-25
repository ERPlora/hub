"""Django admin of the tips app, for the platform's staff. A raw admin write records no event and moves nothing in the
drawer: it is support's way to repair a row; the screens, the API and the assistant write through the operations."""

from django.contrib import admin

from apps.tip.models import Settings, Tip


@admin.register(Tip)
class TipAdmin(admin.ModelAdmin):
    list_display = ("created_at", "sale", "member", "method_name", "amount", "status")
    list_filter = ("status", "method_type")
    search_fields = ("sale__number", "member__first_name", "member__last_name")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("sale", "member", "method", "session")


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ("enabled", "allow_custom", "preselected", "updated_at")
    readonly_fields = ("id", "updated_at")
