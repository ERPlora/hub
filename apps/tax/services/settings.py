"""The writes of the business's tax settings (TAX-F11)."""

from django.db import IntegrityError
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import atomic, operation
from live.outbox import record_event

from apps.tax import events
from apps.tax.models import ACTOR_MAX_LENGTH, TaxSettings
from apps.tax.queries.jurisdiction import business_jurisdiction
from apps.tax.queries.settings import settings_row
from apps.tax.schemas.jurisdiction import TAX_REGIONS
from apps.tax.schemas.settings import REGION_NOT_AVAILABLE, TaxSettingsIn, TaxSettingsOut


def _locked_settings(ctx: OperationContext) -> TaxSettings:
    """The business's settings row, locked; created (the whole country) the first time."""
    settings = TaxSettings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with atomic():
            return TaxSettings.objects.create(updated_by=_actor(ctx))
    except IntegrityError:
        return TaxSettings.objects.select_for_update().get()


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH] if ctx.actor is not None else ""


@operation(
    "tax.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tax.manage",
    input=TaxSettingsIn,
    output=TaxSettingsOut,
    ai={
        "asks": {
            "en": (
                "set the business's tax region to the Canary Islands",
                "we are in Ceuta: charge IPSI instead of VAT",
                "go back to the national VAT, with no special region",
            ),
            "es": (
                "cambia la región fiscal del negocio a Canarias",
                "estamos en Melilla: pasa el negocio al IPSI",
                "quita la región de Canarias y vuelve al IVA de la península",
            ),
        },
        "description": "Keep the business's tax region: ES-CN (Canary Islands, IGIC), ES-CE (Ceuta, IPSI), ES-ML "
        "(Melilla, IPSI), or empty for the whole country (VAT). From then on every sale and invoice charges the "
        "rule of that region; a category without one cannot be charged there until it has it (the national VAT "
        "never applies in those territories).",
        "risk": "high",
    },
)
def update_settings(ctx: OperationContext, data: TaxSettingsIn) -> dict:
    country, _kept = business_jurisdiction()
    region = data.region_code
    if region and region not in TAX_REGIONS.get(country, ()):
        message = str(REGION_NOT_AVAILABLE)
        raise InvalidPayload(message, code="tax.region_not_available", fields={"region_code": message})
    settings = _locked_settings(ctx)
    if settings.region_code != (region or ""):
        settings.region_code = region or ""
        settings.updated_by = _actor(ctx)
        settings.save(update_fields=["region_code", "updated_by", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {"country_code": country, "region_code": region})
    return settings_row(settings)
