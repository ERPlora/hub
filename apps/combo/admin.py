"""Django admin of the combo app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. A raw admin write records no event and checks no business rule beyond the database's (a menu
eaten in with its tax category, a course's ceiling, a product once per course): the screens and the
assistant go through services.py.
"""

from django.contrib import admin

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo


class ChoiceGroupInline(admin.TabularInline):
    model = ChoiceGroup
    extra = 0
    fields = ("name", "min_choices", "max_choices", "allow_repeat", "sort_order")
    show_change_link = True


class ChoiceOptionInline(admin.TabularInline):
    model = ChoiceOption
    extra = 0
    fields = ("product", "price_delta", "is_available", "sort_order")
    raw_id_fields = ("product",)


@admin.register(Combo)
class ComboAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "supply_kind",
        "tax_category",
        "is_active",
        "sort_order",
    )
    list_filter = ("supply_kind", "is_active")
    search_fields = ("name", "kitchen_name")
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")
    inlines = [ChoiceGroupInline]


@admin.register(ChoiceGroup)
class ChoiceGroupAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "combo",
        "min_choices",
        "max_choices",
        "allow_repeat",
        "sort_order",
    )
    search_fields = ("name", "combo__name")
    raw_id_fields = ("combo",)
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [ChoiceOptionInline]


@admin.register(ChoiceOption)
class ChoiceOptionAdmin(admin.ModelAdmin):
    list_display = ("product", "group", "price_delta", "is_available", "sort_order")
    list_filter = ("is_available",)
    search_fields = (
        "product__name",
        "product__sku",
        "group__name",
        "group__combo__name",
    )
    raw_id_fields = ("group", "product")
    readonly_fields = ("id", "created_at", "updated_at")
