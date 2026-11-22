"""The issuer of the invoices (INVOICE-F21)."""

from live.context import OperationContext
from live.operations import operation

from apps.invoice.models import Issuer
from apps.invoice.schemas import IssuerGetIn, IssuerOut


def issuer_row(issuer: Issuer | None) -> dict:
    """An ``IssuerOut``; an empty one while nothing is set up."""
    updated = issuer.updated_at if issuer is not None else None
    issuer = issuer or Issuer(legal_name="", tax_id="", address="")
    return {
        "configured": issuer.configured,
        "legal_name": issuer.legal_name,
        "tax_id": issuer.tax_id,
        "address": issuer.address,
        "postal_code": issuer.postal_code,
        "city": issuer.city,
        "province": issuer.province,
        "country": issuer.country,
        "address_line": issuer.address_line,
        "source": issuer.source,
        "synced_version": issuer.synced_version,
        "synced_at": issuer.synced_at,
        "updated_at": updated,
    }


@operation(
    "invoice.issuer.get",
    kind="query",
    permission="invoice.view_invoice",
    input=IssuerGetIn,
    output=IssuerOut,
    ai={
        "asks": {
            "en": (
                "what company name and tax ID go on our invoices?",
                "get me the issuer of our invoices",
            ),
            "es": (
                "¿qué razón social y CIF salen en nuestras facturas?",
                "¿con qué emisor salen nuestras facturas?",
            ),
        },
        "description": "The issuer of the invoices: the business's legal name, tax ID and address, whether it is set "
        "up (without it no document is issued) and whether it came from the ERPlora account."
    },
)
def get_issuer(ctx: OperationContext, params: IssuerGetIn) -> dict:
    return issuer_row(Issuer.objects.first())
