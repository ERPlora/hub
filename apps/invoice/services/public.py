"""The full invoice a customer asks for from their ticket's public page (INVOICE-F04), without a session.

It is Invoicing's own ``invoice.invoice.substitute``, asked by name as the system for the ticket the code opens: one
full invoice (F3) per ticket, and asking again answers that same one without spending a number, whatever details come
with it."""

from live.context import OperationContext
from live.operations import INTERNAL, get, operation

from apps.invoice.queries.public import PUBLIC, delegated, fiscal_record, ticket_of_code
from apps.invoice.schemas.public import PublicIssueOut, PublicSubstituteIn

RECIPIENT = ("customer_name", "customer_country", "customer_id_type", "customer_tax_id", "customer_address")


@operation(
    "invoice.public.substitute",
    kind="command",
    permission=PUBLIC,
    input=PublicSubstituteIn,
    output=PublicIssueOut,
    ai=INTERNAL,
)
def public_substitute(ctx: OperationContext, data: PublicSubstituteIn) -> dict:
    ticket = ticket_of_code(ctx, data.code)
    substitute = get("invoice.invoice.substitute")
    asked = {"invoice_id": str(ticket.id), **data.model_dump(include=set(RECIPIENT))}
    result = substitute(delegated(ctx), substitute.input.model_validate(asked))
    record = fiscal_record(ctx, result.invoice.id)
    return {"issued": result.issued, "already": result.already, "invoice": result.invoice, "record": record}
