"""Django admin of the tax app: full CRUD over its tables, for the platform's staff only.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com and
has full CRUD over every table, fiscal ones included. The database still refuses a rate outside 0–100,
a rate on a class that charges no tax, a backwards range and a root's twin; the overlap and the
coherence of a component are checked by the operations (services.py), which the screens and the API use.
"""

from django.contrib import admin

from apps.tax.models import TaxAlias, TaxCategory, TaxRule, TaxSettings

#: Set by the database or the model: shown, never typed.
AUDIT = ("id", "created_at", "updated_at")


@admin.register(TaxCategory)
class TaxCategoryAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "is_system", "is_active")
    list_filter = ("is_system", "is_active")
    search_fields = ("key", "name")
    readonly_fields = AUDIT
    fields = (
        "id",
        "key",
        "name",
        "description",
        "is_system",
        "is_active",
        "created_at",
        "updated_at",
    )


class ComponentInline(admin.TabularInline):
    model = TaxRule
    fk_name = "parent"
    extra = 0
    fields = (
        "component_label",
        "tax_type",
        "rate_pct",
        "valid_from",
        "valid_to",
        "is_active",
    )


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "country_code",
        "region_code",
        "rate_pct",
        "tax_type",
        "operation_class",
        "valid_from",
        "valid_to",
        "is_active",
    )
    list_filter = ("country_code", "tax_type", "operation_class", "is_active")
    search_fields = ("category__key", "country_code", "region_code")
    readonly_fields = AUDIT
    list_select_related = ("category",)
    fields = (
        "id",
        "category",
        "country_code",
        "region_code",
        "rate_pct",
        "tax_type",
        "operation_class",
        "exempt_reason",
        "regime_key",
        "parent",
        "component_label",
        "valid_from",
        "valid_to",
        "is_active",
        "created_at",
        "updated_at",
    )
    inlines = [ComponentInline]


@admin.register(TaxAlias)
class TaxAliasAdmin(admin.ModelAdmin):
    list_display = ("alias", "category", "source", "is_active")
    list_filter = ("source", "is_active")
    search_fields = ("alias", "category__key")
    readonly_fields = AUDIT
    list_select_related = ("category",)
    fields = (
        "id",
        "alias",
        "category",
        "source",
        "is_active",
        "created_at",
        "updated_at",
    )


@admin.register(TaxSettings)
class TaxSettingsAdmin(admin.ModelAdmin):
    list_display = ("region_code", "updated_at", "updated_by")
    readonly_fields = ("id", "updated_at", "updated_by")
    fields = ("id", "region_code", "updated_at", "updated_by")
