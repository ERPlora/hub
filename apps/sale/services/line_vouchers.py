"""A line of an open check paid with a customer's voucher (SALE-F27): applying the voucher and taking it off."""

from fractions import Fraction

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, operation

from apps.sale import pricing
from apps.sale.models import OrderLine
from apps.sale.queries.line_parts import provisional_total
from apps.sale.queries.other_apps import call_services
from apps.sale.schemas import OrderApplyVoucherIn, OrderLineRefIn, OrderOut
from apps.sale.services.discounts import DISCOUNT_OUT_OF_RANGE
from apps.sale.services.orders import _open_order, _out, _pending_line, _touch

LINE_NOT_COVERABLE = _(
    "Only a line of a service of Services that is not a comp can be paid with a voucher."
)
VOUCHER_NEEDS_ONE_UNIT = _("A voucher pays a line of one unit: split the line first.")
LINE_ALREADY_COVERED = _("That line is already paid with a voucher.")
LINE_NOT_COVERED = _("That line is not paid with any voucher.")


def _clear_voucher(line: OrderLine) -> None:
    line.voucher_session_id = None
    line.voucher_grant_id = None
    line.voucher_name = ""
    line.voucher_remaining = None
    line.voucher_hold_until = None


def _release_vouchers(ctx: OperationContext, lines) -> None:
    """Gives the sessions held for ``lines`` back to their vouchers (SERVICE-F23). With Services off, the
    write goes on: a held session stops counting on its own at its deadline (SERVICE-F25).

    One release per session, by voucher id and then session id: the order ``service.session.settle``
    locks the vouchers in, so two tills on the same vouchers queue instead of locking each other."""
    covered = sorted(
        (line for line in lines if line.voucher_session_id is not None),
        key=lambda line: (line.voucher_grant_id.int, line.voucher_session_id.int),
    )
    for line in covered:
        try:
            call_services(
                ctx, "service.session.release", {"id": line.voucher_session_id}
            )
        except Conflict as refusal:
            if refusal.code != "sale.services_unavailable":
                raise


@operation(
    "sale.order.apply_voucher",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderApplyVoucherIn,
    output=OrderOut,
    expose_api=True,
    ai=AI(
        description="Pay a line of a service of an open check with one session of a customer's voucher (Services): the "
        "session is held for the line and the line is charged at 0. Resolve the check with sale.order.list(search=...) "
        "and its line with sale.order.get, then read the customer's vouchers for that service with "
        "service.grant.tender_options; never ask the person for order_id, line_id or grant_id. One unit per line "
        "(split it first). The sale must then be charged to the voucher's owner.",
        risk="normal",
        asks={
            "en": (
                "use a session of Ana's voucher for the haircut",
                "the massage goes on her pack of sessions",
            ),
            "es": (
                "usa una sesión del bono de Ana para el corte",
                "el masaje se lo descuentas del bono",
            ),
        },
    ),
)
def apply_voucher(ctx: OperationContext, data: OrderApplyVoucherIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id, unfired=False)
    if line.service_id is None or line.is_gift:
        raise Conflict(str(LINE_NOT_COVERABLE), code="sale.line_not_coverable")
    if line.voucher_session_id is not None:
        raise Conflict(str(LINE_ALREADY_COVERED), code="sale.line_already_covered")
    if line.quantity != 1:
        raise Conflict(
            str(VOUCHER_NEEDS_ONE_UNIT), code="sale.voucher_needs_one_unit"
        )
    session = call_services(
        ctx,
        "service.session.hold",
        {
            "grant_id": data.grant_id,
            "service_id": line.service_id,
            "order_line_id": line.id,
        },
    )
    line.voucher_session_id = session.id
    line.voucher_grant_id = session.grant_id
    line.voucher_name = session.package_name
    line.voucher_remaining = session.remaining
    line.voucher_hold_until = session.hold_until
    line.line_total = provisional_total(line)
    line.save()
    # A fixed ticket discount never comes off more than is left to pay (the hold rolls back with it).
    if order.discount_amount:
        left = sum(
            pricing.half_up(
                Fraction(other.line_total) * (1 - Fraction(order.discount_percent) / 100)
            )
            for other in order.lines.live().unpaid()
            if not other.is_gift
        )
        if order.discount_amount > left:
            raise Conflict(
                str(DISCOUNT_OUT_OF_RANGE), code="sale.discount_out_of_range"
            )
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.remove_voucher",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderLineRefIn,
    output=OrderOut,
    expose_api=True,
    ai=AI(
        description="Undo the voucher of a line of an open check: its session goes back to the voucher and the line is "
        "charged at its price again. Resolve the check with sale.order.list(search=...) and its line with "
        "sale.order.get; never ask the person for order_id or line_id. Only before the sale is charged.",
        risk="normal",
        asks={
            "en": (
                "don't use the voucher for the haircut after all",
                "leave the voucher unused on this check",
            ),
            "es": (
                "al final no uses el bono en el corte",
                "deja el bono sin usar en esta cuenta",
            ),
        },
    ),
)
def remove_voucher(ctx: OperationContext, data: OrderLineRefIn) -> dict:
    order = _open_order(data.order_id)
    line = _pending_line(order, data.line_id, unfired=False)
    if line.voucher_session_id is None:
        raise Conflict(str(LINE_NOT_COVERED), code="sale.line_not_covered")
    _release_vouchers(ctx, [line])
    _clear_voucher(line)
    line.line_total = provisional_total(line)
    line.save()
    _touch(ctx, order)
    return _out(order)
