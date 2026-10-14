"""The valuation of a charge: the arithmetic the preview and the checkout share, line for line.

Pure: it reads nothing. The money of a line is ``unit_price × ratio`` (the quantity in the unit the
price refers to, divided by its price quantity) with the line and ticket percents compounded, rounded
once, half up. ``discount_amount`` is every discount given (line and ticket). A comp is charged at 0 and keeps its cost; a fixed ticket amount comes off after the
percents, shared by weight (largest remainder, ties to the earlier line). Each tax category is then
closed ONCE by ``close`` — tax's ``calculate_tax`` in production (``tax_closer``) — and its base (with
VAT included) or its quota (without it) is shared among its lines by weight, so every line squares
(base + tax = total), every rate of the breakdown squares, and what is charged and what is declared
never drift apart.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any

from django.utils.translation import gettext_lazy as _
from live.errors import Conflict

EMPTY_SALE = _("There is nothing to charge: the check has no lines.")
DISCOUNT_OUT_OF_RANGE = _("That discount is bigger than what it comes off.")
NO_TAX_RULE = _(
    "«%(name)s» cannot be charged: no tax rule applies to its tax category («%(category)s») here."
)

#: ``close(category_key, amount, tax_included)`` → a ``CalculationOut`` of tax.
Closer = Callable[[str, int, bool], dict]

_HUNDRED = Fraction(100)


def half_up(value: Fraction) -> int:
    """To the cent, a half away from zero (money here is never negative)."""
    if value < 0:
        return -half_up(-value)
    return int((value * 2 + 1) // 2)


def allocate(total: int, weights: list[int]) -> list[int]:
    """``total`` cents shared by ``weights``: floors, then one cent each to the largest remainders
    (ties to the earlier position). A weight of 0 never gets anything; Σ parts == total."""
    whole = sum(weights)
    if whole <= 0 or total == 0:
        return [0] * len(weights)
    parts = [total * weight // whole for weight in weights]
    remainders = [(total * weight) % whole for weight in weights]
    left = total - sum(parts)
    ranked = sorted(
        (i for i, weight in enumerate(weights) if weight > 0),
        key=lambda i: (-remainders[i], i),
    )
    for i in ranked[:left]:
        parts[i] += 1
    return parts


def price_ratio(
    quantity: Decimal,
    unit_factor: tuple[int, int],
    pricing_factor: tuple[int, int],
    price_quantity: Decimal,
) -> Fraction:
    """How many «price quantities» ``quantity`` is: in the reference unit of its kind (× the unit's
    exact factor), in the unit the price refers to (÷ that unit's factor), over the price quantity."""
    in_reference = Fraction(quantity) * Fraction(*unit_factor)
    return in_reference / Fraction(*pricing_factor) / Fraction(price_quantity)


def _keep(percent: Decimal) -> Fraction:
    return 1 - Fraction(percent) / _HUNDRED


def line_amount(
    unit_price: int,
    ratio: Fraction,
    *,
    line_percent: Decimal = Decimal(0),
    ticket_percent: Decimal = Decimal(0),
    is_gift: bool = False,
) -> int:
    """What a line is worth: one rounding of price × ratio with both percents compounded; a comp, 0."""
    if is_gift:
        return 0
    return half_up(unit_price * ratio * _keep(line_percent) * _keep(ticket_percent))


@dataclass(frozen=True)
class LineIn:
    """A line to value: its frozen price and the ratio of its quantity to the price's."""

    key: Any
    unit_price: int
    ratio: Fraction
    tax_category_key: str
    line_percent: Decimal = Decimal(0)
    is_gift: bool = False
    cost: int = 0
    name: str = ""


@dataclass
class LineOut:
    key: Any
    tax_category_key: str
    net_amount: int = 0
    tax_amount: int = 0
    line_total: int = 0
    tax_rate: Decimal = Decimal(0)
    tax_rule_id: Any = None
    tax_country_code: str = ""
    tax_region_code: str | None = None
    #: ``[{rule_id, label, tax_type, rate_pct, tax}]``: this line's share of each component.
    tax_components: list[dict] = field(default_factory=list)


@dataclass
class Valuation:
    lines: list[LineOut]
    total: int
    subtotal: int
    tax_total: int
    discount_amount: int
    gift_total: int
    #: ``[{rate_pct, label, base, tax}]`` in order of appearance; one entry per rate.
    breakdown: list[dict]


def value(
    lines: list[LineIn],
    *,
    tax_included: bool,
    close: Closer,
    ticket_percent: Decimal = Decimal(0),
    ticket_amount: int = 0,
) -> Valuation:
    if not lines:
        raise Conflict(str(EMPTY_SALE), code="sale.empty_sale")
    amounts = [
        line_amount(
            line.unit_price,
            line.ratio,
            line_percent=line.line_percent,
            ticket_percent=ticket_percent,
            is_gift=line.is_gift,
        )
        for line in lines
    ]
    # What the lines were worth before any discount (a comp is no discount: it is kept at cost).
    undiscounted = [
        line_amount(line.unit_price, line.ratio, is_gift=line.is_gift) for line in lines
    ]
    gift_total = sum(half_up(line.cost * line.ratio) for line in lines if line.is_gift)

    if ticket_amount:
        payable = sum(amounts)
        if ticket_amount > payable:
            raise Conflict(
                str(DISCOUNT_OUT_OF_RANGE),
                code="sale.discount_out_of_range",
                fields={"discount_amount": str(DISCOUNT_OUT_OF_RANGE)},
            )
        shares = allocate(ticket_amount, amounts)
        amounts = [
            max(0, amount - share)
            for amount, share in zip(amounts, shares, strict=True)
        ]

    outs = [
        LineOut(key=line.key, tax_category_key=line.tax_category_key) for line in lines
    ]
    breakdown: dict[Decimal, dict] = {}
    subtotal = tax_total = 0
    groups: dict[str, list[int]] = {}
    for index, line in enumerate(lines):
        groups.setdefault(line.tax_category_key, []).append(index)

    for category, members in groups.items():
        weights = [amounts[i] for i in members]
        gross = sum(weights)
        try:
            closing = close(category, gross, tax_included)
        except Conflict as refusal:
            if refusal.code != "tax.no_rate":
                raise
            name = lines[members[0]].name or category
            message = str(NO_TAX_RULE) % {"name": name, "category": category}
            raise Conflict(message, code="sale.no_tax_rule") from None
        components = closing["components"]
        # Each component's quota, shared among the lines of the category by weight.
        shares = [allocate(component["tax"], weights) for component in components]
        for position, i in enumerate(members):
            out = outs[i]
            line_tax = sum(share[position] for share in shares)
            if tax_included:
                out.line_total = amounts[i]
                out.net_amount = amounts[i] - line_tax
            else:
                out.net_amount = amounts[i]
                out.line_total = amounts[i] + line_tax
            out.tax_amount = line_tax
            out.tax_rate = Decimal(closing["tax_rate_pct"])
            out.tax_rule_id = closing["tax_rule_id"]
            out.tax_country_code = closing["tax_country_code"]
            out.tax_region_code = closing["tax_region_code"]
            out.tax_components = [
                {
                    "rule_id": component["rule_id"],
                    "label": component["label"],
                    "tax_type": component["tax_type"],
                    "rate_pct": Decimal(component["rate_pct"]),
                    "tax": share[position],
                }
                for component, share in zip(components, shares, strict=True)
            ]
        subtotal += closing["base"]
        tax_total += closing["tax"]
        for component in components:
            rate = Decimal(component["rate_pct"])
            entry = breakdown.setdefault(
                rate,
                {"rate_pct": rate, "label": component["label"], "base": 0, "tax": 0},
            )
            entry["base"] += closing["base"]
            entry["tax"] += component["tax"]

    total = sum(out.line_total for out in outs)
    discount_amount = sum(undiscounted) - (total if tax_included else subtotal)
    return Valuation(
        lines=outs,
        total=total,
        subtotal=subtotal,
        tax_total=tax_total,
        discount_amount=discount_amount,
        gift_total=gift_total,
        breakdown=list(breakdown.values()),
    )


def tax_closer(on=None) -> Closer:
    """``close`` on tax's own calculation, in the business's country, on the business day ``on``."""
    from apps.tax.queries import calculate_tax

    def close(category_key: str, amount: int, tax_included: bool) -> dict:
        return calculate_tax(
            amount=amount, category_key=category_key, on=on, tax_included=tax_included
        )

    return close
