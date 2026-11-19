"""The business a sale is made in: its currency, its country and the law's limits there, its day, and who acts."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import AI, operation

from apps.sale.schemas import BusinessDayOut, EmptyIn
from apps.tax.queries import business_jurisdiction, business_tax_kind, business_today
from apps.tax.schemas import TAX_KIND_NAMES
from base.approvals import approval_of, digest
from base import operations as platform
from base import business
from base.models import Approval

#: The currency Spanish law writes its limits in (Ley 7/2012, RD 1619/2012): the law's, not the business's.
LIMITS_CURRENCY = "EUR"
#: In a business of Spain, no cash at all from this total on (Ley 7/2012, art. 7), mixed included.
CASH_LIMIT = {"ES": 100_000}
#: In a business of Spain, a ticket (simplified invoice) up to this total, VAT included (RD 1619/2012).
TICKET_LIMIT = {"ES": 300_000}


TAX_CATEGORY_MISSING = _(
    "«%(name)s» cannot be sold: it has no tax category. Its %(tax)s is missing."
)


def business_currency(ctx: OperationContext) -> str:
    """The currency of ``ctx``'s business (ISO 4217), the one a sale charged now keeps: the one question every app that
    charges asks (``base.operations.business_currency``, BASE-F50), on ERPlora's own hub too, never a copy of its own.
    Sales' public answer: Cash register counts in it (``requires = ["sale"]``)."""
    return platform.business_currency(ctx.scope)


def business_country() -> str:
    """The business's country, from Taxes' one jurisdiction of the business (TAX-F11)."""
    country, _region = business_jurisdiction()
    return country


def actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:128] if ctx.actor is not None else ""


def authoriser(ctx: OperationContext) -> str:
    """Who authorised what ``ctx`` does (a discount above the maximum): the manager who approved this very request
    with their PIN on the cashier's device (BASE-F84), else the caller."""
    approval = approval_of(ctx)
    if approval is not None:
        approved_by = (
            Approval.objects.filter(token_digest=digest(approval.token), operation=approval.operation)
            .values_list("approved_by", flat=True)
            .first()
        )
        if approved_by:
            return approved_by[:128]
    return actor(ctx)


@operation(
    "sale.business_day.get",
    kind="query",
    permission="sale.view_sale",
    input=EmptyIn,
    output=BusinessDayOut,
    ai=AI(
        description="Today's date in the business's time zone (the business day sales are numbered and counted in).",
        asks={
            "en": (
                "what's the business date today?",
                "which day is the till on right now?",
            ),
            "es": (
                "¿a qué día estamos para el negocio?",
                "¿qué día de negocio es hoy?",
            ),
        },
    ),
)
def business_day(ctx: OperationContext, params: EmptyIn) -> dict:
    return {"today": business_today()}


def missing_tax(name: str) -> str:
    """Why an article without a tax category cannot be sold, naming the territory's tax (TAX-F11)."""
    return str(TAX_CATEGORY_MISSING) % {"name": name, "tax": TAX_KIND_NAMES[business_tax_kind()]}


def money_text(cents: int | None, currency: str = LIMITS_CURRENCY) -> str:
    """``cents`` (minor units of ``currency``, with its decimals: none in JPY) as the reader writes money in a sentence,
    thousands always grouped as every screen paints them («1.234,56 €», «€1,234.56», «PLN 1,234.56»);
    nothing is «—». Without a currency it is one of Spain's legal limits, which the law writes in euros (Invoicing says
    its ticket limit so too); any other amount passes its own, the sale's or the business's."""
    return "—" if cents is None else business.money_text(cents, currency)
