"""The discounts of an open check and of its lines, within what the business allows."""

from fractions import Fraction

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, operation

from apps.sale import pricing
from apps.sale.models import Settings
from apps.sale.queries import authoriser, current_settings, provisional_total
from apps.sale.schemas import OrderOut, OrderSetDiscountIn, OrderSetLineDiscountIn
from apps.sale.services.orders import _guard_covered, _out, _pending_line, _still_open, _touch

DISCOUNTS_NOT_ALLOWED = _("This business does not allow discounts.")
DISCOUNT_OVER_LIMIT = _(
    "That discount is above what this business allows without a manager's approval."
)
DISCOUNT_OUT_OF_RANGE = _("That discount is bigger than what it comes off.")


def _cap(over_limit: bool, settings: Settings) -> int:
    return 100 if over_limit else settings.max_discount_percent


def _set_discount(
    ctx: OperationContext, data: OrderSetDiscountIn, *, over_limit: bool
) -> dict:
    order = _still_open(data.order_id)
    settings = current_settings()
    percent = data.discount_percent
    amount = (
        order.discount_amount if data.discount_amount is None else data.discount_amount
    )
    if (percent > 0 or amount > 0) and not settings.allow_discounts:
        raise Conflict(str(DISCOUNTS_NOT_ALLOWED), code="sale.discounts_not_allowed")
    lines = list(order.lines.live().unpaid())
    gross = sum(
        pricing.half_up(
            Fraction(line.line_total) * (1 - Fraction(percent) / 100)
        )
        for line in lines
        if not line.is_gift
    )
    if amount > gross:
        raise Conflict(
            str(DISCOUNT_OUT_OF_RANGE),
            code="sale.discount_out_of_range",
            fields={"discount_amount": str(DISCOUNT_OUT_OF_RANGE)},
        )
    cap = _cap(over_limit, settings)
    if cap < 100 and (percent > cap or amount > gross * cap // 100):
        raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")
    order.discount_percent = percent
    order.discount_amount = amount
    order.discount_approved_by = (
        authoriser(ctx) if over_limit and (percent > 0 or amount > 0) else ""
    )
    order.save(
        update_fields=[
            "discount_percent",
            "discount_amount",
            "discount_approved_by",
            "updated_at",
        ]
    )
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.set_discount",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderSetDiscountIn,
    output=OrderOut,
    ai=AI(
        description="Set the ticket discount of an open check: a percentage (0 removes it) and/or a fixed amount in cents. "
        "Above the business's cap it is refused: only a manager can (sale.order.set_discount_over_limit).",
        risk="high",
        asks={
            "en": (
                "give table 4 a 10% discount",
                "take 5 euros off the bill",
            ),
            "es": (
                "hazle un 10 % de descuento a la cuenta",
                "rebájale 5 € al total",
            ),
        },
    ),
)
def set_discount(ctx: OperationContext, data: OrderSetDiscountIn) -> dict:
    return _set_discount(ctx, data, over_limit=False)


@operation(
    "sale.order.set_discount_over_limit",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.discount_over_limit",
    input=OrderSetDiscountIn,
    output=OrderOut,
    ai=AI(
        description="The manager's door to the very same ticket discount, for one bigger than the business's cap; the check "
        "remembers who approved it. Never use it for a discount that fits under the cap.",
        risk="high",
        asks={
            "en": (
                "give them 50% off the whole check, I'm authorising it",
                "40% off the bill, above the usual cap",
            ),
            "es": (
                "hazles un 50 % en toda la cuenta, lo autorizo yo",
                "pasa del máximo y ponles un 40 % de descuento",
            ),
        },
    ),
)
def set_discount_over_limit(ctx: OperationContext, data: OrderSetDiscountIn) -> dict:
    return _set_discount(ctx, data, over_limit=True)


def _set_line_discount(
    ctx: OperationContext, data: OrderSetLineDiscountIn, *, over_limit: bool
) -> dict:
    order = _still_open(data.order_id)
    line = _pending_line(order, data.line_id)
    if data.discount_percent != line.discount_percent:
        _guard_covered(line)
    settings = current_settings()
    percent = data.discount_percent
    if percent > 0 and not settings.allow_discounts:
        raise Conflict(str(DISCOUNTS_NOT_ALLOWED), code="sale.discounts_not_allowed")
    if percent > _cap(over_limit, settings):
        raise Conflict(str(DISCOUNT_OVER_LIMIT), code="sale.discount_over_limit")
    line.discount_percent = percent
    line.discount_approved_by = authoriser(ctx) if over_limit and percent > 0 else ""
    line.line_total = provisional_total(line)
    line.save(
        update_fields=[
            "discount_percent",
            "discount_approved_by",
            "line_total",
            "updated_at",
        ]
    )
    _touch(ctx, order)
    return _out(order)


@operation(
    "sale.order.set_line_discount",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_sale",
    input=OrderSetLineDiscountIn,
    output=OrderOut,
    ai=AI(
        description="Set the discount (in %, 0 removes it) of a pending line of an open check. Above the business's cap it "
        "is refused: only a manager can (sale.order.set_line_discount_over_limit).",
        risk="high",
        asks={
            "en": (
                "a 20% discount on the haircut",
                "discount the wine by 10%",
            ),
            "es": (
                "ponle un 20 % de descuento al corte",
                "rebaja el vino un 10 %",
            ),
        },
    ),
)
def set_line_discount(ctx: OperationContext, data: OrderSetLineDiscountIn) -> dict:
    return _set_line_discount(ctx, data, over_limit=False)


@operation(
    "sale.order.set_line_discount_over_limit",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.discount_over_limit",
    input=OrderSetLineDiscountIn,
    output=OrderOut,
    ai=AI(
        description="The manager's door to the very same line discount, for one bigger than the business's cap; the line "
        "remembers who approved it.",
        risk="high",
        asks={
            "en": (
                "knock 60% off the wine, I'll approve it",
                "the dessert at half price even above the cap",
            ),
            "es": (
                "el vino con un 60 % de descuento, lo apruebo yo",
                "rebaja el postre un 50 % aunque pase del máximo",
            ),
        },
    ),
)
def set_line_discount_over_limit(
    ctx: OperationContext, data: OrderSetLineDiscountIn
) -> dict:
    return _set_line_discount(ctx, data, over_limit=True)
