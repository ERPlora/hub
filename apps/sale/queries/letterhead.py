"""The business on paper (SALE-F21, SALE-F29): the name, tax ID and address the tickets and bills print."""

from uuid import UUID

from django.utils import translation
from live.context import OperationContext, system_context
from live.errors import OperationError
from live.operations import AI, UnknownOperation, get, operation

from apps.sale import paper
from apps.sale.queries.sales import find_sale
from apps.sale.queries.settings import current_settings
from apps.sale.schemas import LetterheadIn, LetterheadOut

#: What the papers read of other apps, by name: Invoicing is no ``requires`` of Sales.
ISSUER = "invoice.issuer.get"
DOCUMENT = "invoice.invoice.get"
BUSINESS = "base.business.get"


def _read_for_paper(ctx: OperationContext, name: str, data: dict | None = None):
    """Another app's answer for a paper, read as the platform (as ``business_currency``): whoever sells prints these
    data on every ticket, and a role or an API key that sells may hold no right over Invoicing. ``None`` when the app
    is absent, off or has no answer: the paper goes with what the business has."""
    try:
        op = get(name)
        return op(system_context(ctx.scope), op.input.model_validate(data or {}))
    except (UnknownOperation, OperationError):
        return None


def _issuer_on_paper(ctx: OperationContext, invoice_id: UUID | None) -> dict | None:
    """The issuer a paper names: the one its fiscal document says, whatever the issuer becomes later (a reprint says
    what the original said); without a document yet, the one Invoicing has today, once it is set up."""
    if invoice_id is not None:
        document = _read_for_paper(ctx, DOCUMENT, {"invoice_id": str(invoice_id)})
        if document is not None:
            return {"name": document.issuer_name, "tax_id": document.issuer_tax_id, "address": document.issuer_address}
    issuer = _read_for_paper(ctx, ISSUER)
    if issuer is None or not issuer.configured:
        return None
    return {"name": issuer.legal_name, "tax_id": issuer.tax_id, "address": issuer.address_line}


def business_letterhead(ctx: OperationContext, invoice_id: UUID | None = None) -> dict:
    """The business as the papers of the till name it (``paper.letterhead``), for a paper of the fiscal document
    ``invoice_id`` or of none."""
    header = current_settings().receipt_header
    issuer = _issuer_on_paper(ctx, invoice_id)
    registered = None if issuer or header.strip() else _read_for_paper(ctx, BUSINESS)
    return paper.letterhead(issuer, header=header, registered_name=registered.name if registered else "")


@operation(
    "sale.letterhead.get",
    kind="query",
    permission="sale.view_sale",
    input=LetterheadIn,
    output=LetterheadOut,
    ai=AI(
        description="Read the business's name, tax ID and address as the tickets and bills print them: those of the "
        "issuer in Invoicing, with the receipt header added under them; for a sale, those of its fiscal document.",
        asks={
            "en": (
                "what tax ID comes out on our receipts?",
                "under what name do our tickets print?",
            ),
            "es": (
                "¿qué NIF sale en los tiques?",
                "¿con qué nombre salen los tiques?",
            ),
        },
    ),
)
def get_letterhead(ctx: OperationContext, params: LetterheadIn) -> dict:
    invoice_id = None if params.sale_id is None else find_sale(params.sale_id, None).invoice_id
    with translation.override(ctx.language):
        return {"sale_id": params.sale_id, **business_letterhead(ctx, invoice_id)}
