"""Django admin of the invoice app, for the platform's staff only (round 12, PLAN §17; hubs.erplora.com).

Series and issuer: full CRUD (what the admin saves does not go through the operations: no event; the
database still refuses a code twice in a year, two default series in a year and a second issuer). A
series keeps its code, year and type once made, and its prefix, format and counter once it numbered a
document (the number is in the VeriFactu chain); the issuer's tax ID is checked as in the operations.
Invoices and their lines: shown whole, every fiscal field read-only, never added (the number comes only
from the operations) nor deleted (an issued invoice is kept: RD 1619/2012 art. 19; it is corrected with a
rectifying invoice). Only the notes of an invoice can be changed. Ids and dates are always read-only.
"""

from django import forms
from django.contrib import admin

from apps.invoice.models import Invoice, InvoiceLine, InvoiceSeries, Issuer
from apps.invoice.queries import series_started
from apps.invoice.schemas import HOME_COUNTRY, check_tax_id

#: Set by the database or the model: shown, never typed.
AUDIT = ("id", "created_at", "updated_at")


def _audit_of(model) -> tuple:
    names = {field.name for field in model._meta.get_fields()}
    return tuple(name for name in AUDIT if name in names)


@admin.register(InvoiceSeries)
class InvoiceSeriesAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "year",
        "name",
        "invoice_type",
        "prefix",
        "format",
        "current_number",
        "is_active",
        "is_default",
    )
    list_filter = ("year", "invoice_type", "is_active", "is_default")
    search_fields = ("code", "name")
    readonly_fields = _audit_of(InvoiceSeries)

    def get_readonly_fields(self, request, obj=None) -> tuple:
        fields = tuple(self.readonly_fields)
        if obj is None:
            return fields
        fields += ("code", "year", "invoice_type")
        if series_started(obj):
            fields += ("prefix", "format", "current_number")
        return fields


class IssuerForm(forms.ModelForm):
    class Meta:
        model = Issuer
        fields = "__all__"

    def clean_tax_id(self) -> str:
        # The business's own NIF or CIF is checked and kept compact; a business abroad keeps it as written.
        value = self.cleaned_data["tax_id"]
        if (self.data.get("country") or HOME_COUNTRY).upper() != HOME_COUNTRY:
            return value.strip()
        try:
            return check_tax_id(value, country=HOME_COUNTRY, id_type="")
        except ValueError as refusal:
            raise forms.ValidationError(str(refusal)) from None


@admin.register(Issuer)
class IssuerAdmin(admin.ModelAdmin):
    form = IssuerForm
    list_display = (
        "legal_name",
        "tax_id",
        "country",
        "source",
        "synced_version",
        "updated_at",
    )
    readonly_fields = ("id", "updated_at", "synced_at")


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    can_delete = False
    fields = (
        "position",
        "description",
        "quantity",
        "unit_price",
        "discount_amount",
        "tax_rate",
        "surcharge_rate",
        "tax_category_key",
        "base_amount",
        "tax_amount",
        "total_amount",
        "product_id",
        "sale_line_id",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "invoice_type",
        "issue_date",
        "customer_name",
        "total_amount",
        "status",
        "source_type",
    )
    list_filter = ("invoice_type", "status", "source_type", "series_code", "year")
    search_fields = ("number", "customer_name", "customer_tax_id")
    list_select_related = ("series",)
    inlines = [InvoiceLineInline]

    def get_readonly_fields(self, request, obj=None) -> list[str]:
        return [
            field.name
            for field in Invoice._meta.concrete_fields
            if field.name != "notes"
        ]

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
