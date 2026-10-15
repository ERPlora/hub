"""Django admin of the pricing app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. A raw admin write records no event and checks no business rule (no general list taken from
another, no coherence of a rule): the actions that need one call the operations of services.py. Only a
rule's tiers are read as the API reads them, because the price of a line reads them as such.
"""

import pydantic
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from apps.pricing.models import DiscountRule, PriceItem, PriceList
from apps.pricing.schemas import MAX_TIERS, TIERS_RISING, TOO_MANY_TIERS, Tier


class PriceItemInline(admin.TabularInline):
    model = PriceItem
    extra = 0
    fields = ("product", "service_id", "service_name", "min_quantity", "price")
    raw_id_fields = ("product",)


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "currency", "tax_included", "customer_group_id", "is_default", "is_active")
    list_filter = ("is_active", "is_default", "currency")
    search_fields = ("code", "name")
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")
    inlines = [PriceItemInline]
    fields = (
        "id",
        ("code", "name"),
        ("currency", "tax_included"),
        "customer_group_id",
        ("valid_from", "valid_until"),
        ("is_default", "is_active"),
        ("created_at", "created_by"),
        ("updated_at", "updated_by"),
    )


@admin.register(PriceItem)
class PriceItemAdmin(admin.ModelAdmin):
    list_display = ("price_list", "product", "service_name", "min_quantity", "price")
    list_filter = ("price_list",)
    search_fields = ("price_list__code", "product__name", "product__sku", "service_name")
    raw_id_fields = ("price_list", "product")
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")


class DiscountRuleForm(forms.ModelForm):
    """The rule's raw columns, with its tiers read as the API reads them (``schemas.Tier``, rising)."""

    class Meta:
        model = DiscountRule
        fields = "__all__"

    def clean_tiers(self):
        tiers = self.cleaned_data.get("tiers")
        if tiers in (None, ""):
            return []
        try:
            rows = pydantic.TypeAdapter(list[Tier]).validate_python(tiers)
        except pydantic.ValidationError as invalid:
            raise ValidationError(
                "; ".join(f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in invalid.errors())
            ) from None
        if len(rows) > MAX_TIERS:
            raise ValidationError(str(TOO_MANY_TIERS) % {"count": MAX_TIERS})
        quantities = [row.min_quantity for row in rows]
        if any(later <= earlier for earlier, later in zip(quantities, quantities[1:], strict=False)):
            raise ValidationError(str(TIERS_RISING))
        return [{"min_quantity": str(row.min_quantity), "percent": str(row.percent)} for row in rows]


@admin.register(DiscountRule)
class DiscountRuleAdmin(admin.ModelAdmin):
    form = DiscountRuleForm
    list_display = ("code", "name", "rule_type", "applies_to", "priority", "is_active")
    list_filter = ("is_active", "rule_type", "applies_to")
    search_fields = ("code", "name")
    raw_id_fields = ("category", "product")
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")
    fields = (
        "id",
        ("code", "name"),
        "rule_type",
        ("percent", "amount"),
        ("buy_quantity", "get_quantity"),
        "tiers",
        "applies_to",
        ("category", "product"),
        ("service_id", "service_name"),
        "customer_group_id",
        "min_quantity",
        ("valid_from", "valid_until"),
        ("priority", "is_active"),
        ("created_at", "created_by"),
        ("updated_at", "updated_by"),
    )
