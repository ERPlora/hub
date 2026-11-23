"""The issuer of the documents (INVOICE-F21): set by hand or handed over by the platform, and copied onto every
document.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.invoice import events
from apps.invoice.models import Invoice, Issuer
from apps.invoice.queries import issuer_row
from apps.invoice.schemas import IssuerIn, IssuerOut, IssuerSyncIn, IssuerSyncOut
from apps.invoice.services.writes import _now, actor

ISSUER_MISSING = _(
    "Set up the issuer (the business's legal name, tax ID and address) in Invoicing → Issuer before issuing "
    "documents."
)


def _configured_issuer() -> Issuer:
    issuer = Issuer.objects.first()
    if issuer is None or not issuer.configured:
        raise Conflict(str(ISSUER_MISSING), code="invoice.issuer_missing")
    return issuer


def _save_issuer(ctx: OperationContext, data: IssuerIn, **extra) -> Issuer:
    values = {
        "legal_name": data.legal_name,
        "tax_id": data.tax_id,
        "address": data.address,
        "postal_code": data.postal_code,
        "city": data.city,
        "province": data.province,
        "country": data.country,
        "intra_eu_operator": data.intra_eu_operator,
        "updated_by": actor(ctx),
        **extra,
    }
    issuer, _created = Issuer.objects.update_or_create(singleton=True, defaults=values)
    record_event(ctx, events.ISSUER_UPDATED, {"source": issuer.source})
    return issuer


@operation(
    "invoice.issuer.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="invoice.manage_issuer",
    input=IssuerIn,
    output=IssuerOut,
    ai={
        "asks": {
            "en": (
                "change the company name on our invoices to Carpintería Lema SL",
                "update the issuer's address to Calle Real 5",
                "we moved: put Calle Real 5 as the issuer's address",
            ),
            "es": (
                "cambia la razón social de las facturas a Carpintería Lema SL",
                "pon la dirección del emisor en Calle Real 5",
                "cambia en el emisor el domicilio a Calle Real 5",
            ),
        },
        "description": "Set the issuer of the invoices: the business's legal name, tax ID (a Spanish NIF or CIF is "
        "checked), address and whether it is registered for intra-EU operations (ROI), which makes its documents "
        "print its EU VAT number. Every document issued from now on carries it; the ones issued keep theirs.",
        "risk": "high",
    },
)
def update_issuer(ctx: OperationContext, data: IssuerIn) -> dict:
    return issuer_row(_save_issuer(ctx, data, source=Issuer.Source.MANUAL))


@operation(
    "invoice.issuer.sync",
    kind="command",
    # Declared by no role: only the system context (``*``) holds it.
    permission="invoice.sync_issuer",
    input=IssuerSyncIn,
    output=IssuerSyncOut,
    ai={
        "description": "System only: the platform hands over the business's tax identity from the ERPlora account "
        "(the SaaS's photo of the hub) with its version; an older version than the one kept is ignored.",
        "risk": "high",
    },
)
def sync_issuer(ctx: OperationContext, data: IssuerSyncIn) -> dict:
    current = Issuer.objects.select_for_update().first()
    if (
        current is not None
        and current.synced_version is not None
        and data.version <= current.synced_version
    ):
        return {"applied": False, "issuer": issuer_row(current)}
    issuer = _save_issuer(
        ctx,
        data,
        source=Issuer.Source.SAAS,
        synced_version=data.version,
        synced_at=_now(),
    )
    return {"applied": True, "issuer": issuer_row(issuer)}


def _issuer_copy(issuer: Issuer) -> dict:
    return {
        "issuer_name": issuer.legal_name,
        "issuer_tax_id": issuer.tax_id,
        "issuer_address": issuer.address_line,
        "issuer_country": issuer.country,
        "issuer_intra_eu_operator": issuer.intra_eu_operator,
    }


def _issuer_of(invoice: Invoice) -> dict:
    return {
        "issuer_name": invoice.issuer_name,
        "issuer_tax_id": invoice.issuer_tax_id,
        "issuer_address": invoice.issuer_address,
        "issuer_country": invoice.issuer_country,
        "issuer_intra_eu_operator": invoice.issuer_intra_eu_operator,
    }
