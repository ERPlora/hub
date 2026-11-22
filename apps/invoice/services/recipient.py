"""The recipient of a document: what was sent, else the customer's card, as complete as a full invoice needs it.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload

from apps.customer.queries import find_customer
from apps.invoice.models import Invoice
from apps.invoice.schemas import NAME_MAX, TAX_ID_MAX, check_tax_id
from apps.invoice.services.writes import logger

RECIPIENT_INCOMPLETE = _("A full invoice needs the customer's name, tax ID and address.")


FIELD_REQUIRED = _("This field is required.")


TOO_LONG = _(
    "VeriFactu's record holds at most %(max)s characters here: shorten it (on the customer's card)."
)


def _recipient_of(invoice: Invoice) -> dict:
    return {
        "customer_id": invoice.customer_id,
        "customer_name": invoice.customer_name,
        "customer_tax_id": invoice.customer_tax_id,
        "customer_address": invoice.customer_address,
        "customer_country": invoice.customer_country,
        "customer_id_type": invoice.customer_id_type,
    }


def _card_address(card) -> str:
    town = " ".join(part for part in (card.postal_code, card.city) if part)
    return ", ".join(part for part in (card.address, town) if part)


def _without_tax_id(recipient: dict, why: str) -> dict:
    """A simplified invoice (F2) needs no recipient: a tax ID that does not check is left out (the name
    stays) instead of leaving the ticket undone, and the log says so."""
    logger.warning("invoice: a ticket goes without its recipient's tax ID (%s)", why)
    return {**recipient, "customer_tax_id": "", "customer_id_type": ""}


def _chosen_card(ctx: OperationContext, data):
    """The customer's card the recipient names (by id or reference), or ``None``; locked before the document's
    ticket and its series' number, as a charge takes them, and as Customers' writes and the Hub admin's «Delete»
    of a card do: a deletion under way is waited for and the card is gone (404, no number spent), and one that
    comes after waits for the document and finds it protecting the card."""
    if getattr(data, "customer_id", None) is None and not getattr(data, "customer", None):
        return None
    return find_customer(ctx, data.customer_id, data.customer, lock=True)


def _recipient(ctx: OperationContext, data, *, full: bool, fallback_name: str = "", card=None) -> dict:  # noqa: C901
    """The recipient: what was sent, else the customer card's (named by id or reference). A full invoice
    needs name, tax ID and address (409 with the missing fields); a tax ID taken from the card is checked."""
    if card is None:
        card = _chosen_card(ctx, data)
    name = (
        data.customer_name
        or (card.company_name or card.name if card else "")
        or fallback_name
    )
    tax_id = data.customer_tax_id or (card.tax_id if card else "")
    address = data.customer_address or (_card_address(card) if card else "")
    country = data.customer_country or (
        card.country if card and card.country != "ES" else ""
    )
    id_type = data.customer_id_type
    refusal = getattr(data, "tax_id_refusal", None)
    if tax_id and not data.customer_tax_id:
        # What the card says is read as what is typed (apps.customer.tax_ids); a refusal names its field.
        try:
            tax_id = check_tax_id(tax_id, country=country, id_type=id_type)
        except ValueError as error:
            refusal = (error.field, str(error))
    if refusal is None and len(tax_id) > TAX_ID_MAX:
        refusal = ("customer_tax_id", str(TOO_LONG) % {"max": TAX_ID_MAX})
    if refusal is not None and full:
        field, message = refusal
        raise InvalidPayload(message, fields={field: message})
    if len(name) > NAME_MAX:
        # A card holds 200 characters; VeriFactu's NombreRazon, 120.
        message = str(TOO_LONG) % {"max": NAME_MAX}
        if full:
            raise InvalidPayload(message, fields={"customer_name": message})
        logger.warning("invoice: a ticket goes without its recipient's name (%s)", message)
        name = ""
    if full:
        missing = [
            field
            for field, value in (
                ("customer_name", name),
                ("customer_tax_id", tax_id),
                ("customer_address", address),
            )
            if not value.strip()
        ]
        if missing:
            raise Conflict(
                str(RECIPIENT_INCOMPLETE),
                code="invoice.recipient_incomplete",
                fields={field: str(FIELD_REQUIRED) for field in missing},
            )
    recipient = {
        "customer": card,
        "customer_name": name,
        "customer_tax_id": tax_id,
        "customer_address": address,
        "customer_country": country,
        "customer_id_type": id_type,
    }
    if refusal is not None:
        return _without_tax_id(recipient, refusal[1])
    return recipient
