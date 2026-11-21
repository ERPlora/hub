"""The valuation of a charge, shared by its preview and the checkout, and the counter sale's lines."""

import datetime as dt
from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from django.db.models import Sum
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, operation

from apps.sale import pricing
from apps.sale.models import Order, OrderLine, Sale
from apps.sale.queries.business import CASH_LIMIT, LIMITS_CURRENCY, TICKET_LIMIT, business_country
from apps.sale.queries.departments import hold_departments
from apps.sale.queries.line_parts import charge_parts, combo_name, dish_name, dishes_of, folded_names, is_child, ratio_of
from apps.sale.queries.order_lines import (
    freeze_combo_line,
    freeze_open_line,
    freeze_product_line,
    inventory_units,
    refresh_combos,
)
from apps.sale.queries.orders import ORDER_CHANGED, find_order, pending_lines
from apps.sale.queries.service_lines import Booking, freeze_service_line
from apps.sale.queries.settings import current_settings
from apps.sale.schemas.checkout import PreviewIn, PreviewOut
from apps.tax.models import TaxCategory


def lines_to_charge(order: Order, line_ids: list[UUID]) -> tuple[list[OrderLine], bool]:
    """``(lines, closes)``: the lines named (all that are left when none is) and whether the charge
    takes the last of them. A line named that is gone (removed, voided, charged, of another check)
    means the check changed under the screen."""
    pending = pending_lines(order)
    if not line_ids:
        return pending, True
    wanted = set(line_ids)
    chosen = [line for line in pending if line.id in wanted]
    if len(chosen) != len(wanted):
        raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
    return chosen, len(chosen) == len(pending)


def valuate(
    lines: list[OrderLine],
    *,
    discount_percent: Decimal,
    discount_amount: int,
    tax_included: bool,
    on: dt.date | None = None,
) -> pricing.Valuation:
    return pricing.value(
        [
            pricing.LineIn(
                key=index,
                unit_price=line.unit_price,
                ratio=ratio_of(line),
                tax_category_key=line.tax_category_key,
                line_percent=line.discount_percent,
                is_gift=line.is_gift,
                covered=line.voucher_session_id is not None,
                cost=line.cost,
                quantity=line.quantity,
                name=line.name,
            )
            for index, line in enumerate(lines)
        ],
        tax_included=tax_included,
        close=pricing.tax_closer(on),
        ticket_percent=discount_percent,
        ticket_amount=discount_amount,
        category_name=tax_category_name,
    )


def tax_category_name(key: str) -> str:
    """The name Taxes shows for the tax category ``key``, in the active language (a factory category's
    translated, one of the business's as typed); the key itself once no category has it (deleted in the Hub
    admin after the line was added). Read only when a line is refused for want of a rule."""
    category = TaxCategory.objects.filter(key=key).first()
    return category.display_name if category else key


def breakdown_rows(breakdown: list[dict]) -> list[dict]:
    """The valuation's breakdown as a sale keeps it: one row per fiscal key and component."""
    return [
        {
            "rate_pct": row["rate_pct"],
            "label": row["label"],
            "tax_type": str(row["tax_type"]),
            "regime": str(row["regime"]),
            "qualification": str(row["qualification"]),
            "exempt_reason": str(row["exempt_reason"]),
            "base": row["base"],
            "tax": row["tax"],
        }
        for row in breakdown
    ]


def operation_total(order: Order | None, closes: bool, valuation: pricing.Valuation, *, on: dt.date | None = None) -> int:
    """The whole operation the cash limit looks at (Ley 7/2012, art. 7.Uno.1, second paragraph: the
    payments a supply is split into add up). A check charged in parts is one operation: what it already
    charged (voided sales aside) plus all it has left, valued as the charge that would close it. A
    counter sale, or a charge that closes the check, adds its own total to what was charged before."""
    if order is None:
        return valuation.total
    charged = (
        Sale.objects.filter(order=order, status__in=[Sale.Status.COMPLETED, Sale.Status.REFUNDED])
        .aggregate(total=Sum("total"))["total"]
        or 0
    )
    if closes:
        return charged + valuation.total
    rest = valuate(
        charge_parts(pending_lines(order)),
        discount_percent=order.discount_percent,
        discount_amount=order.discount_amount,
        tax_included=current_settings().default_tax_included,
        on=on,
    )
    return charged + rest.total


def loose_lines(  # noqa: PLR0913
    ctx: OperationContext,
    lines: list,
    open_lines: list,
    service_lines: list = (),
    booking: Booking | None = None,
    *,
    hold: bool = False,
    combo_lines: Iterable = (),
) -> list[OrderLine]:
    """Unsaved rows for a counter sale: catalog lines frozen from Inventory, menus from Menus, services from
    Services (at the price ``booking`` booked, when a line brings it), then open-price ones. A write that adds
    them ``hold``s the departments of the open-price ones (``hold_departments``)."""
    frozen: list[OrderLine] = []
    if lines:
        units = inventory_units(ctx)
        frozen += [freeze_product_line(ctx, line, units) for line in lines]
    frozen += [freeze_combo_line(ctx, line) for line in combo_lines]
    frozen += [freeze_service_line(ctx, line, booking) for line in service_lines]
    priced = [freeze_open_line(ctx, line) for line in open_lines]
    if hold:
        hold_departments(zip(open_lines, priced, strict=True))
    frozen += priced
    for position, line in enumerate(frozen, start=1):
        line.position = position
    return frozen


@operation(
    "sale.checkout.preview",
    kind="query",
    permission="sale.view_sale",
    input=PreviewIn,
    output=PreviewOut,
    ai=AI(
        description="How much a charge would come to, WITHOUT charging nor writing anything: an open check (a table's: "
        "all of it, or some lines) or loose lines. Same arithmetic as the charge: total, taxable base, tax by rate, "
        "discounts and comps in cents, and each line.",
        asks={
            "en": (
                "how much would table 4 come to?",
                "what's the total with VAT if I charge just the drinks?",
            ),
            "es": (
                "¿cuánto les sale la mesa 4 si cobro ya?",
                "calcúlame el total con IVA solo de las bebidas",
            ),
        },
    ),
)
def preview(ctx: OperationContext, params: PreviewIn) -> dict:
    settings = current_settings()
    order = None
    closes = True
    if params.order_id is not None:
        order = find_order(params.order_id)
        if order.status != Order.Status.OPEN:
            raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
        lines, closes = lines_to_charge(order, params.line_ids)
        refresh_combos(ctx, lines)
        percent, amount = order.discount_percent, order.discount_amount if closes else 0
        version = order.version
    else:
        lines = loose_lines(
            ctx, params.lines, params.open_lines, params.service_lines, combo_lines=params.combo_lines
        )
        percent, amount, version = params.discount_percent, params.discount_amount, None
    parts = charge_parts(lines)
    valuation = valuate(
        parts,
        discount_percent=percent,
        discount_amount=amount,
        tax_included=settings.default_tax_included,
    )
    country = business_country()
    return {
        "order_id": params.order_id,
        "order_version": version,
        "lines_count": len(lines),
        "tax_included": settings.default_tax_included,
        "subtotal": valuation.subtotal,
        "tax_total": valuation.tax_total,
        "discount_amount": valuation.discount_amount,
        "discount_percent": percent,
        "ticket_discount_amount": valuation.ticket_discount_amount,
        "gift_total": valuation.gift_total,
        "total": valuation.total,
        "breakdown": breakdown_rows(valuation.breakdown),
        "lines": [
            {
                "order_line_id": line.origin.id if params.order_id else None,
                "name": line.name,
                "quantity": line.quantity,
                "unit": line.unit,
                "unit_price": line.unit_price,
                "discount_percent": line.discount_percent,
                "is_gift": line.is_gift,
                "service_id": line.service_id,
                "paid_by_voucher": line.paid_by_voucher,
                "voucher_name": line.voucher_name,
                "voucher_remaining": line.voucher_remaining,
                "tax_category_key": line.tax_category_key,
                "tax_rate": out.tax_rate,
                "net_amount": out.net_amount,
                "tax_amount": out.tax_amount,
                "line_total": out.line_total,
                "modifiers": [] if is_child(line) else folded_names(line),
                "is_child": is_child(line),
                "combo_name": combo_name(line),
                "components": [dish_name(dish) for dish in dishes_of(line) if getattr(line, "dish", None) is None],
            }
            for line, out in zip(parts, valuation.lines, strict=True)
        ],
        "operation_total": operation_total(order, closes, valuation),
        "cash_limit": CASH_LIMIT.get(country),
        "ticket_limit": TICKET_LIMIT.get(country),
        "limits_currency": LIMITS_CURRENCY,
    }
