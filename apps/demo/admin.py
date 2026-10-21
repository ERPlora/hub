"""Django admin of the demo app: full CRUD on items and their lines, for the platform's staff.

Round 12 (PLAN §17, PLAN-HUB §3.2, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of
a hub's tables but the fiscal ones. A raw admin write records no event and checks no rule of
services.py (no closed item, no next position): it is support's way to repair a row, as in every
other app's admin; the screens, the API and the assistant write through the operations.
"""

from django.contrib import admin

from apps.demo.models import Item, ItemLine


class ItemLineInline(admin.TabularInline):
    model = ItemLine
    extra = 0
    fields = ("position", "text", "qty", "client_line_id")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("name",)
    fields = ("id", "name", "status", "note", "created_at", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [ItemLineInline]
