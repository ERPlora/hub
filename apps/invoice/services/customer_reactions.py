"""The platform's reaction to Customers: a card whose personal data was erased (GDPR). The invoices keep their copy, as the
law asks; the log of their emails keeps no address."""

from live.context import OperationContext
from live.operations import operation

from apps.invoice.models import InvoiceEmail
from apps.invoice.schemas.emails import ForgetCustomerIn, ForgottenOut
from apps.invoice.services.emails import DELIVER


@operation(
    "invoice.email.forget_customer",
    kind="command",
    permission=DELIVER,
    input=ForgetCustomerIn,
    output=ForgottenOut,
    ai={
        "description": "Platform reaction to customer.customer.erased (GDPR): the emails of the card's invoices lose the "
        "address they went to; the rest of their log stays.",
        "risk": "normal",
    },
)
def forget_customer(ctx: OperationContext, data: ForgetCustomerIn) -> dict:
    addressed = InvoiceEmail.objects.filter(invoice__customer_id=data.id).exclude(to_address="")
    return {"forgotten": addressed.update(to_address="")}
