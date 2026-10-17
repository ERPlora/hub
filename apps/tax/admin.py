"""Django admin of the tax app: full CRUD over its tables, for the platform's staff only.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com and
has full CRUD over every table, fiscal ones included. The database still refuses a rate outside 0–100,
a rate on a class that charges no tax, a backwards range and a root's twin; the overlap and the
coherence of a component are checked by the operations (services.py), which the screens and the API use.
The business's region is kept through its own operation, as its screen does (TAX-F11).
"""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.operations import get

from apps.tax.models import WHOLE_COUNTRY, TaxAlias, TaxCategory, TaxRule, TaxSettings
from apps.tax.queries import business_jurisdiction
from apps.tax.schemas import REGION_TAX_KINDS, TAX_REGIONS
from base.admin import ADMIN_HUB_SESSION_KEY

#: Set by the database or the model: shown, never typed.
AUDIT = ("id", "created_at", "updated_at")
CHOOSE_A_HUB = _("Choose a hub first (its link in the SaaS admin): the region is kept on that hub.")


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


def region_choices() -> list[tuple[str, str]]:
    """What the screen offers: the tax territories of the business's country, or none (the whole country)."""
    country, _region = business_jurisdiction()
    territories = [
        (code, f"{code} · {TaxRule.TaxType(REGION_TAX_KINDS[code]).label}") for code in TAX_REGIONS.get(country, ())
    ]
    return [("", str(WHOLE_COUNTRY)), *territories]


def _staff_context(request) -> OperationContext | None:
    """The staff member on the hub chosen in the admin session, allowed only to keep the region; ``None``
    without a hub."""
    slug = request.session.get(ADMIN_HUB_SESSION_KEY)
    if not slug:
        return None
    return OperationContext(
        scope=Scope("host", slug),
        actor=request.user,
        permissions=frozenset({"tax.manage"}),
        language=getattr(request, "LANGUAGE_CODE", "en"),
        request=request,
    )


class TaxSettingsForm(forms.ModelForm):
    """Only the region, one of the screen's choices; keeping it IS ``tax.settings.update``, run when the form is
    validated so that its refusal is the field's error. ``request`` is set by ``TaxSettingsAdmin.get_form``."""

    request = None
    region_code = forms.ChoiceField(
        label=TaxSettings._meta.get_field("region_code").verbose_name, choices=region_choices, required=False
    )

    class Meta:
        model = TaxSettings
        fields = ("region_code",)

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        ctx = _staff_context(self.request)
        if ctx is None:
            raise ValidationError(str(CHOOSE_A_HUB))
        operation = get("tax.settings.update")
        try:
            operation(ctx, operation.input.model_validate({"region_code": cleaned["region_code"] or None}))
        except OperationError as refusal:
            raise ValidationError({"region_code": refusal.message}) from None
        return cleaned


@admin.register(TaxSettings)
class TaxSettingsAdmin(admin.ModelAdmin):
    form = TaxSettingsForm
    list_display = ("region_code", "updated_at", "updated_by")
    readonly_fields = ("id", "updated_at", "updated_by")
    fields = ("id", "region_code", "updated_at", "updated_by")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        form.request = request
        return form

    def save_model(self, request, obj, form, change) -> None:
        """Nothing to write: the operation kept the region (its actor and its event) when the form was
        validated. The admin's log and its redirect point at the row it kept, the first time included."""
        kept = TaxSettings.objects.get()
        obj.pk, obj.updated_at, obj.updated_by = kept.pk, kept.updated_at, kept.updated_by

    def has_add_permission(self, request) -> bool:
        # One row at most (``tax_settings_single_row``): once it exists, the staff changes it, never adds another.
        return super().has_add_permission(request) and not TaxSettings.objects.exists()
