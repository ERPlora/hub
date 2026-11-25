"""Django admin of Online orders: the tables' codes, for the platform's staff to look at. A code is changed only by
regenerating it (``online_order.qr_code.regenerate``, with its event), never here."""

from django.contrib import admin

from apps.online_order.models import TableCode


@admin.register(TableCode)
class TableCodeAdmin(admin.ModelAdmin):
    list_display = ("table_id", "code", "issued_at")
    search_fields = ("table_id", "code")
    readonly_fields = ("id", "table_id", "code", "issued_at")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
