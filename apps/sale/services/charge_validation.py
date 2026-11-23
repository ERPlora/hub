"""What a charge validates before it records the sale: the customer's details, the discounts, the payments, the
drawer and who served."""

import logging
from decimal import Decimal
from uuid import UUID

from django.db import DatabaseError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, InvalidPayload, OperationError
from live.operations import UnknownOperation, get

from apps.customer.queries import find_customer
from apps.customer.tax_ids import IdTypeRequired, InvalidCountry, InvalidTaxId, normalize_country, normalize_tax_id
from apps.sale import pricing
from apps.sale.models import OrderLine, PaymentMethod, Settings
from apps.sale.queries.business import CASH_LIMIT, LIMITS_CURRENCY, business_country, money_text
from apps.sale.queries.line_parts import ratio_of
from apps.sale.queries.other_apps import call_app
from apps.sale.queries.payment_methods import METHOD_NOT_AVAILABLE, allowed_types, find_method, held_methods
from apps.sale.schemas.checkout import CompleteIn, PaymentIn
from apps.sale.schemas.fields import COUNTRY_CODE
from apps.sale.services.discounts import DISCOUNTS_NOT_ALLOWED, DISCOUNT_OVER_LIMIT, _cap

logger = logging.getLogger(__name__)

PAYMENTS_MISMATCH = _("The payments do not add up to the total of the sale.")
INSUFFICIENT_TENDERED = _("What was handed over does not cover the amount.")
CASH_LIMIT_EXCEEDED = _(
    "By law, a sale of %(limit)s or more cannot be paid in cash, not even in part. Charge it by card, Bizum or bank transfer."
)
TAX_ID_INVALID = _("That tax ID is not valid.")
ID_TYPE_REQUIRED = _(
    "Say what kind of document a foreign tax ID is (EU VAT number, passport, tax ID of their country…)."
)
CASH_REGISTER_CLOSED = _(
    "The cash register is closed: open a cash session to charge in cash."
)
ADDED_AMOUNT_NOT_ACCEPTED = _(
    "This business has no app that adds anything to a charge, such as a tip: charge the sale alone."
)


def _customer_details(ctx: OperationContext, data: CompleteIn) -> tuple:
    """``(card, name, tax id, address, country)`` of the sale's customer: what was sent, else the card's.
    The name is the fiscal one, as Invoicing reads a card: its company when it has one (the NombreRazon
    that goes with the company's tax ID), else the person. The card is locked before the check, as Customers'
    writes and the Hub admin's «Delete» of a card take it: a deletion under way is waited for and the card is
    gone (404), and one that comes after waits for the charge and finds the sale that protects the card."""
    card = None
    if data.customer_id is not None or data.customer:
        card = find_customer(ctx, data.customer_id, data.customer, lock=True)
    name = data.customer_name or ((card.company_name or card.name) if card else "")
    tax_id = data.customer_tax_id or (card.tax_id if card else "")
    if data.customer_address:
        address = data.customer_address
    elif card:
        town = " ".join(part for part in (card.postal_code, card.city) if part)
        address = ", ".join(part for part in (card.address, town) if part)
    else:
        address = ""
    country = data.customer_country or (card.country if card else "")
    return card, name, tax_id, address, country


def _checked_country(country: str) -> str:
    """The recipient's country of an invoice as Invoicing reads it (ISO 3166-1 alpha-2); one an old card
    keeps that it would refuse («UK») is a 422 on its field, to fix before charging."""
    try:
        return normalize_country(country)
    except InvalidCountry:
        message = str(COUNTRY_CODE)
        raise InvalidPayload(
            message, code="invalid_field", fields={"customer_country": message}
        ) from None


def _checked_tax_id(tax_id: str, country: str, id_type: str) -> str:
    """The recipient's tax ID of an invoice as the document keeps it (``apps.customer.tax_ids``, the one
    reading of Customers and Invoicing): a Spanish NIF, NIE or CIF and an EU VAT number (02) must check;
    abroad, its kind of document (02–07) is required. A refusal is a 422 on its field."""
    try:
        return normalize_tax_id(tax_id, country=country, id_type=id_type)
    except IdTypeRequired:
        message = str(ID_TYPE_REQUIRED)
        raise InvalidPayload(
            message, code="invalid_field", fields={"customer_id_type": message}
        ) from None
    except InvalidTaxId:
        message = str(TAX_ID_INVALID)
        raise InvalidPayload(
            message, code="invalid_field", fields={"customer_tax_id": message}
        ) from None


def _check_discounts(  # noqa: PLR0913
    lines: list[OrderLine],
    percent: Decimal,
    amount: int,
    *,
    approved: bool,
    over_limit: bool,
    settings: Settings,
) -> None:
    discounted = (
        percent > 0 or amount > 0 or any(line.discount_percent > 0 for line in lines)
    )
    if discounted and not settings.allow_discounts:
        raise Conflict(str(DISCOUNTS_NOT_ALLOWED), code="sale.discounts_not_allowed")
    cap = _cap(over_limit, settings)
    if cap >= 100:
        return
    for line in lines:
        if not line.discount_approved_by and line.discount_percent > cap:
            raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")
    if approved:
        return
    # What is left to pay: a line a voucher pays is worth nothing (SALE-F27).
    payable = sum(
        pricing.line_amount(
            line.unit_price,
            ratio_of(line),
            line_percent=line.discount_percent,
            ticket_percent=percent,
            is_gift=line.is_gift,
        )
        for line in lines
        if line.voucher_session_id is None
    )
    if percent > cap or amount > payable * cap // 100:
        raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")


def _legs(data: CompleteIn, total: int, settings: Settings, operation: int) -> list[dict]:
    """The tenders, resolved and checked: methods allowed, amounts adding up, cash tendered, change, and
    no cash at all when the whole ``operation`` reaches the cash limit. What another app adds to a tender (a tip)
    is charged with it, on top of its amount, but never counts as the sale's."""
    _refuse_added_amounts(data.payments)
    if total == 0:
        if any(leg.amount or leg.extra for leg in data.payments):
            raise Conflict(
                str(PAYMENTS_MISMATCH), code="sale.payments_do_not_match_total"
            )
        return []
    legs = _resolved(data.payments or [PaymentIn(method="cash")], settings)
    _fill_the_rest(legs, total)
    for leg in legs:
        _settle(leg)
    _check_cash_limit(legs, operation)
    return legs


def _refuse_added_amounts(payments: list[PaymentIn]) -> None:
    """An amount added to a tender is only taken when an active app adds a step to the charge, which records it in
    its own app too (SALE-F39): otherwise the drawer, the card total and the receipt would hold money nobody accounts
    for. No app can declare such a step yet, so every added amount is refused."""
    if any(leg.extra for leg in payments):
        raise Conflict(str(ADDED_AMOUNT_NOT_ACCEPTED), code="sale.added_amount_not_accepted")


def _resolved(sent: list[PaymentIn], settings: Settings) -> list[dict]:
    """Each tender with its method, one the settings allow and that is still there."""
    allowed = allowed_types(settings, PaymentMethod.objects.filter(is_active=True))
    legs = []
    for leg in sent:
        method = find_method(leg.method_id, leg.method)
        if method.type not in allowed:
            raise Conflict(
                str(METHOD_NOT_AVAILABLE), code="sale.payment_method_not_available"
            )
        legs.append(
            {
                "method": method,
                "amount": leg.amount,
                "tendered": leg.tendered,
                "reference": leg.reference,
                "extra": leg.extra,
                "extra_label": leg.extra_label,
            }
        )
    # Held until the charge ends: one deleted since it was read is not available, as one never added.
    named = {leg["method"].id for leg in legs}
    if held_methods(named) != named:
        raise Conflict(
            str(METHOD_NOT_AVAILABLE), code="sale.payment_method_not_available"
        )
    return legs


def tender_amounts(sent: list[int | None], total: int) -> list[int] | None:
    """What each tender pays: the one without an amount, what the others leave; ``None`` when they cannot add up to
    the sale's ``total`` (more than one without an amount, or the others already reach it)."""
    given = sum(amount for amount in sent if amount is not None)
    amounts = [total - given if amount is None else amount for amount in sent]
    if (None in sent and given >= total) or sum(amounts) != total:
        return None
    return amounts


def _fill_the_rest(legs: list[dict], total: int) -> None:
    amounts = tender_amounts([leg["amount"] for leg in legs], total)
    if amounts is None:
        raise Conflict(str(PAYMENTS_MISMATCH), code="sale.payments_do_not_match_total")
    for leg, amount in zip(legs, amounts, strict=True):
        leg["amount"] = amount


def _settle(leg: dict) -> None:
    """What a tender takes is its amount and what is added to it: cash takes it out of what was handed over, and the
    rest is change; any other method charges exactly that."""
    owed = leg["amount"] + leg["extra"]
    if leg["method"].type != PaymentMethod.Type.CASH:
        leg["tendered"], leg["change"] = owed, 0
        return
    tendered = owed if leg["tendered"] is None else leg["tendered"]
    if tendered < owed:
        raise Conflict(str(INSUFFICIENT_TENDERED), code="sale.insufficient_tendered")
    leg["tendered"], leg["change"] = tendered, tendered - owed


def _check_cash_limit(legs: list[dict], operation: int) -> None:
    """By law, no cash at all, not even in part, when the whole operation reaches the country's limit."""
    limit = CASH_LIMIT.get(business_country())
    if limit is None or operation < limit:
        return
    if any(leg["method"].type == PaymentMethod.Type.CASH for leg in legs):
        raise Conflict(
            str(CASH_LIMIT_EXCEEDED) % {"limit": money_text(limit, LIMITS_CURRENCY)},
            code="sale.cash_limit_exceeded",
        )


#: Cash register's answer to «may the till charge cash now?» (CASH_REGISTER-F04).
DRAWER_CHECK = "cash_register.session.current"


def _check_drawer(ctx: OperationContext, legs: list[dict]) -> None:
    """SALE-F08 (CASH_REGISTER-F04): cash only with the drawer open. With a cash leg, Cash register is asked
    by name with the seller's session; «required» and no session open → 409 ``sale.cash_register_closed``.
    Cash register off, absent or failing (a refusal, a timeout) → the till charges: the lock gives way
    before the sales stop, and Cash register shows the charge among those of no shift (CASH_REGISTER-F17)."""
    if not any(leg["method"].type == PaymentMethod.Type.CASH for leg in legs):
        return
    try:
        drawer = call_app(ctx, DRAWER_CHECK, {}, "sale.cash_register_unavailable")
    except (OperationError, DatabaseError) as failure:
        logger.info(
            "sale: cash charged without asking Cash register (%s)",
            getattr(failure, "code", type(failure).__name__),
        )
        return
    if drawer.required and drawer.session is None:
        raise Conflict(str(CASH_REGISTER_CLOSED), code="sale.cash_register_closed")


#: Staff's answer to «whose record is the session's?» (SALE-F16): who «Me» is at the till.
CURRENT_MEMBER = "staff.member.current"


def _served_by(ctx: OperationContext, named: UUID | None, serving: UUID | None = None) -> UUID | None:
    """Who the sale is attributed to (SALE-F16): whoever the charge names (an integration's), else who serves the
    check (``serving``, the person chosen on the chip) or, left on «Me», the Staff record of whoever holds the
    session, asked by name (Staff is no requirement of Sales; its operation needs no Staff permission, so a cashier
    who does not see the team still sells as herself). Nobody without a record, without a user behind the session
    (the platform, an API key) or without Staff (absent or off): the sale counts for nobody, as the till warns. It
    is the sale's professional, for the lines of the check: a line with its own (an appointment's service) keeps it."""
    chosen = named or serving
    if chosen is not None:
        return chosen
    try:
        op = get(CURRENT_MEMBER)
        current = op(ctx, op.input.model_validate({}))
    except (UnknownOperation, AppInactive):
        return None
    return current.member.id if current.member else None
