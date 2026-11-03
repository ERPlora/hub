"""The valuation of a charge: the arithmetic the preview and the checkout share, line for line.

Pure: it reads nothing. The money of a line is ``unit_price × ratio`` (the quantity in the unit the
price refers to, divided by its price quantity) with the line and ticket percents compounded, rounded
once, half up. ``discount_amount`` is every discount given (line and ticket); ``ticket_discount_amount`` is
the ticket's alone (its percent and its fixed amount): what the lines, each with its own discount, lose to it.
A comp is charged at 0 and keeps its cost;
a line a voucher pays (``covered``, SALE-F27) is worth 0, neither a discount nor a comp: the voucher was
taxed when it was sold. A fixed ticket amount comes off after the
percents, shared by weight (largest remainder, ties to the earlier line).

Each line's tax category is resolved to its rule by ``close`` — tax's ``calculate_tax`` in production
(``tax_closer``) — and the lines are grouped by **fiscal key** (tax, regime, qualification, exemption
cause and the rates of its components: what Invoicing's breakdown and VeriFactu's ``Desglose`` read).
Each key is then closed ONCE over the money of all its lines, whatever their categories, and its base
(with VAT included) or its quota (without it) is shared among them by weight, so every line squares
(base + tax = total), every entry of the breakdown squares, and the ticket and its invoice declare the
same base and quota to the cent (two categories at 10 % are one rounding, never two).
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

DEFAULT_TAX_KIND = "vat"
GENERAL_REGIME = "01"
SUBJECT = "subject"

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
    #: Paid with a voucher session (SALE-F27): worth 0, no discount and no comp.
    covered: bool = False
    #: Cost of one unit of the line's own (stock) unit, in cents.
    cost: int = 0
    #: The quantity in the line's own unit: what a comp's cost is multiplied by.
    quantity: Decimal = Decimal(1)
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
    #: What the ticket discount (percent and fixed amount) takes off the lines, already discounted each.
    ticket_discount_amount: int
    gift_total: int
    #: ``[{rate_pct, label, tax_type, regime, qualification, exempt_reason, base, tax}]`` in order of
    #: appearance: one entry per fiscal key and component.
    breakdown: list[dict]


def fiscal_key(closing: dict) -> tuple:
    """What a line is for the tax agency, from its rule (a ``CalculationOut``): tax, regime,
    qualification, exemption cause and its components' rates. Two lines with the same key are closed
    together and are one entry of the breakdown (Invoicing's ``FiscalKey``)."""
    return (
        closing.get("tax_kind") or DEFAULT_TAX_KIND,
        closing.get("tax_regime_key") or GENERAL_REGIME,
        closing.get("tax_operation_class") or SUBJECT,
        closing.get("tax_exempt_reason") or "",
        tuple(Decimal(component["rate_pct"]) for component in closing["components"]),
    )


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
        0
        if line.covered
        else line_amount(
            line.unit_price,
            line.ratio,
            line_percent=line.line_percent,
            ticket_percent=ticket_percent,
            is_gift=line.is_gift,
        )
        for line in lines
    ]
    # What each row paints: the line with its own discount only. The ticket's takes the rest off.
    listed = [
        0
        if line.covered
        else line_amount(line.unit_price, line.ratio, line_percent=line.line_percent, is_gift=line.is_gift)
        for line in lines
    ]
    # What the lines were worth before any discount (a comp is no discount: it is kept at cost; a line
    # a voucher pays is worth nothing to begin with).
    undiscounted = [
        0 if line.covered else line_amount(line.unit_price, line.ratio, is_gift=line.is_gift)
        for line in lines
    ]
    gift_total = sum(
        half_up(line.cost * Fraction(line.quantity))
        for line in lines
        if line.is_gift and not line.covered
    )

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
    ticket_discount_amount = sum(listed) - sum(amounts)

    outs = [
        LineOut(key=line.key, tax_category_key=line.tax_category_key) for line in lines
    ]
    # Each category resolved once to its rule (a closing of nothing); its lines go to the rule's key.
    rules: dict[str, dict] = {}
    groups: dict[tuple, list[int]] = {}
    for index, line in enumerate(lines):
        category = line.tax_category_key
        if category not in rules:
            rules[category] = _resolve(close, line, tax_included)
        groups.setdefault(fiscal_key(rules[category]), []).append(index)

    breakdown: list[dict] = []
    subtotal = tax_total = 0
    for key, members in groups.items():
        weights = [amounts[i] for i in members]
        # One closing for the whole key, by the rule of its first category: the money of a key only
        # depends on its rates.
        closing = close(lines[members[0]].tax_category_key, sum(weights), tax_included)
        components = closing["components"]
        if tax_included:
            # As Invoicing closes a charge (``fiscal.close_charged``): the key's base shared by weight,
            # each line's tax what is left of its amount; the main components' quotas by weight and the
            # last one takes what is left of the line's tax.
            bases = allocate(closing["base"], weights)
            shares = [allocate(component["tax"], weights) for component in components[:-1]]
            taxes = [amounts[i] - bases[position] for position, i in enumerate(members)]
            shares.append(
                [
                    tax - sum(share[position] for share in shares)
                    for position, tax in enumerate(taxes)
                ]
            )
        else:
            # Each component's quota, shared among the lines of the key by weight, on top.
            shares = [allocate(component["tax"], weights) for component in components]
        for position, i in enumerate(members):
            out, rule = outs[i], rules[lines[i].tax_category_key]
            line_tax = sum(share[position] for share in shares)
            if tax_included:
                out.line_total = amounts[i]
                out.net_amount = amounts[i] - line_tax
            else:
                out.net_amount = amounts[i]
                out.line_total = amounts[i] + line_tax
            out.tax_amount = line_tax
            out.tax_rate = Decimal(rule["tax_rate_pct"])
            out.tax_rule_id = rule["tax_rule_id"]
            out.tax_country_code = rule["tax_country_code"]
            out.tax_region_code = rule["tax_region_code"]
            out.tax_components = [
                {
                    "rule_id": component["rule_id"],
                    "label": component["label"],
                    "tax_type": component["tax_type"],
                    "rate_pct": Decimal(component["rate_pct"]),
                    "tax": share[position],
                }
                for component, share in zip(rule["components"], shares, strict=True)
            ]
        subtotal += closing["base"]
        tax_total += closing["tax"]
        tax_kind, regime, qualification, exempt_reason, _rates = key
        breakdown.extend(
            {
                "rate_pct": Decimal(component["rate_pct"]),
                "label": component["label"],
                "tax_type": component["tax_type"] or tax_kind,
                "regime": regime,
                "qualification": qualification,
                "exempt_reason": exempt_reason,
                "base": closing["base"],
                "tax": component["tax"],
            }
            for component in components
        )

    total = sum(out.line_total for out in outs)
    discount_amount = sum(undiscounted) - (total if tax_included else subtotal)
    return Valuation(
        lines=outs,
        total=total,
        subtotal=subtotal,
        tax_total=tax_total,
        discount_amount=discount_amount,
        ticket_discount_amount=ticket_discount_amount,
        gift_total=gift_total,
        breakdown=breakdown,
    )


def _resolve(close: Closer, line: LineIn, tax_included: bool) -> dict:
    """The rule of ``line``'s category (a closing of 0 cents); without one, 409 naming the line."""
    try:
        return close(line.tax_category_key, 0, tax_included)
    except Conflict as refusal:
        if refusal.code != "tax.no_rate":
            raise
        name = line.name or line.tax_category_key
        message = str(NO_TAX_RULE) % {"name": name, "category": line.tax_category_key}
        raise Conflict(message, code="sale.no_tax_rule") from None


def tax_closer(on=None) -> Closer:
    """``close`` on tax's own calculation, in the business's jurisdiction (its country and the region it
    keeps in Taxes, TAX-F11: no country named), on the business day ``on``."""
    from apps.tax.queries import calculate_tax

    def close(category_key: str, amount: int, tax_included: bool) -> dict:
        return calculate_tax(
            amount=amount, category_key=category_key, on=on, tax_included=tax_included
        )

    return close
