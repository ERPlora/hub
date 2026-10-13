"""Django admin of the demo app: read only, because every write goes through an operation (and its event)."""

from django.contrib import admin

from apps.demo.models import Item, ItemLine


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ItemLineInline(ReadOnlyMixin, admin.TabularInline):
    model = ItemLine
    extra = 0
    fields = ("position", "text", "qty", "client_line_id")


@admin.register(Item)
class ItemAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("name",)
    fields = ("id", "name", "status", "note", "created_at", "updated_at")
    inlines = [ItemLineInline]
