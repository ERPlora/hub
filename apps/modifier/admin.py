"""Django admin of the modifier app: full CRUD on every table for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations, so
it leaves no event and does not hold the rules only they apply (the defaults of a group within its
maximum, a group full at 100 options). What the database holds it cannot break either: repeated names,
a maximum below the minimum, an option with its own tax category worth zero or less, and a link to
nothing, to two things or twice are refused. What the database fills in is shown, not edited.
"""

from django.contrib import admin

from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption

AUTOMATIC = ("id", "created_at", "updated_at")


class OptionInline(admin.TabularInline):
    model = ModifierOption
    extra = 0
    fields = (
        "name",
        "kitchen_name",
        "price_delta",
        "tax_category",
        "is_default",
        "sort_order",
    )


class LinkInline(admin.TabularInline):
    model = ModifierLink
    extra = 0
    fields = ("product", "category")
    autocomplete_fields = ("product", "category")


@admin.register(ModifierGroup)
class ModifierGroupAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "kitchen_name",
        "min_choices",
        "max_choices",
        "allow_repeat",
        "sort_order",
    )
    list_filter = ("allow_repeat",)
    search_fields = ("name", "kitchen_name")
    fields = (
        "id",
        "name",
        "kitchen_name",
        "min_choices",
        "max_choices",
        "allow_repeat",
        "sort_order",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )
    readonly_fields = AUTOMATIC
    inlines = [OptionInline, LinkInline]


@admin.register(ModifierOption)
class ModifierOptionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "group",
        "price_delta",
        "tax_category",
        "is_default",
        "sort_order",
    )
    list_filter = ("is_default",)
    search_fields = ("name", "kitchen_name", "group__name")
    list_select_related = ("group", "tax_category")
    fields = (
        "id",
        "group",
        "name",
        "kitchen_name",
        "price_delta",
        "tax_category",
        "is_default",
        "sort_order",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )
    readonly_fields = AUTOMATIC


@admin.register(ModifierLink)
class ModifierLinkAdmin(admin.ModelAdmin):
    list_display = ("group", "product", "category", "created_at")
    search_fields = ("group__name", "product__name", "product__sku", "category__name")
    list_select_related = ("group", "product", "category")
    autocomplete_fields = ("product", "category")
    fields = ("id", "group", "product", "category", "created_at", "created_by")
    readonly_fields = ("id", "created_at")
