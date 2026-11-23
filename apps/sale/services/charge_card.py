"""The card of a charge through the assistant (``ai={"summary": charge_card.summary}``): how much it charges and how,
as the charge sheet's button says it — the total as the server values it, each tender by its method and what it pays
—, never the check's version, which only the charge sheet sends."""

from typing import Any

from live import assistant as shared
from live.assistant import NAMED, label
from live.context import OperationContext
from live.errors import Conflict
from live.operations import get
from pydantic import ValidationError

from apps.sale.queries.payment_methods import find_method
from apps.sale.schemas.checkout import ChargeLinesIn, CompleteIn, PaymentIn
from apps.sale.services.charge_validation import tender_amounts

CHARGE = "sale.sale.complete"
PREVIEW = "sale.checkout.preview"
#: A newer version of the check refuses the charge; the person checks what it charges, its total.
SCREEN_ONLY = ("order_version",)


def _method_name(leg: PaymentIn) -> str | None:
    """The tender's method as the charge finds it, in the active language; words it does not find, as said."""
    try:
        return find_method(leg.method_id, leg.method).display_name
    except Conflict:
        return leg.method


def _tender(leg: PaymentIn, amount: int | None) -> dict[str, Any]:
    said: dict[str, Any] = {"method": _method_name(leg)}
    return said if amount is None else {**said, "amount": {"kind": "money", "value": amount}}


def _payments(data: CompleteIn, total: int) -> dict:
    """The tenders, each by its method and what it pays (``tender_amounts``); none sent is cash for the whole, as the
    charge takes it. Tenders that do not add up go with the amounts sent: the charge refuses them."""
    legs = data.payments or [PaymentIn(method="cash")]
    sent = [leg.amount for leg in legs]
    amounts = tender_amounts(sent, total)
    if amounts is None:
        amounts = sent
    tenders = [_tender(leg, amount) for leg, amount in zip(legs, amounts, strict=True)]
    return {"name": "payments", "label": label(get(CHARGE), "payments", None), "kind": "list", "value": tenders, NAMED: True}


def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """What is charged, its total and how it is paid. Data that cannot be valued (no check nor lines, a check this
    person cannot read) keep the card as their data say it: no total is made up, and the charge refuses them."""
    try:
        data = CompleteIn.model_validate(arguments)
    except ValidationError:
        return fields
    preview = get(PREVIEW)
    failure, valued = shared.run(ctx, preview, {name: arguments[name] for name in ChargeLinesIn.model_fields if name in arguments})
    if failure is not None:
        return fields
    total = {"name": "total", "label": label(get(CHARGE), "total", None), "kind": "money", "value": valued.total}
    charged = [field for field in fields if field["name"] in ChargeLinesIn.model_fields]
    rest = [field for field in fields if field["name"] not in {*ChargeLinesIn.model_fields, *SCREEN_ONLY, "payments"}]
    return [*charged, total, _payments(data, valued.total), *rest]
