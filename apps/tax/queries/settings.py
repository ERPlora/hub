"""The business's tax settings (TAX-F11): its country, the region it keeps and the tax its sales are declared with."""


from live.context import OperationContext
from live.operations import operation

from apps.tax.models import TaxSettings
from apps.tax.queries.jurisdiction import business_jurisdiction, tax_kind_of
from apps.tax.schemas.jurisdiction import TAX_REGIONS
from apps.tax.schemas.settings import SettingsGetIn, TaxSettingsOut


def settings_row(settings: TaxSettings | None) -> dict:
    """What applies: a region kept that is not one of the business's country's counts as none (TAX-F11)."""
    country, region = business_jurisdiction()
    return {
        "country_code": country,
        "region_code": region,
        "regions": list(TAX_REGIONS.get(country, ())),
        "tax_kind": tax_kind_of(country, region),
        "updated_at": settings.updated_at if settings else None,
    }


@operation(
    "tax.settings.get",
    kind="query",
    permission="tax.view",
    input=SettingsGetIn,
    output=TaxSettingsOut,
    ai={
        "asks": {
            "en": (
                "which tax region is the business in?",
                "is the business under VAT, IGIC or IPSI?",
                "what tax territory does the business operate in?",
            ),
            "es": (
                "¿qué fiscalidad tiene el negocio: península, Canarias, Ceuta o Melilla?",
                "¿cobro IVA o IGIC?",
                "dime la región de impuestos del negocio",
            ),
        },
        "description": "Read the business's tax region and country: the jurisdiction every sale and invoice is "
        "charged in. ES-CN is the Canary Islands (IGIC), ES-CE Ceuta and ES-ML Melilla (IPSI); empty is the "
        "whole country (VAT). Also the regions it may keep."
    },
)
def get_settings(ctx: OperationContext, params: SettingsGetIn) -> dict:
    return settings_row(TaxSettings.objects.first())
