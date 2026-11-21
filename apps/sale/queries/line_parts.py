"""What a line of a check charges: its parts (the options of another tax category, the dishes of a split menu), the
grid of its quantity and its provisional total."""

from collections.abc import Iterable
from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from live.errors import Conflict

from apps.sale import pricing
from apps.sale.models import OrderLine

GRID_FALLBACK = Decimal("0.001")


QUANTITY_OFF_GRID = _(
    "The quantity does not fit the step of the product (%(step)s %(unit)s)."
)


#: A menu is sold in whole units.
WHOLE = Decimal("1")


def check_grid(quantity: Decimal, increment: Decimal, unit: str) -> None:
    if increment and quantity % increment != 0:
        message = str(QUANTITY_OFF_GRID) % {
            "step": f"{increment.normalize():f}",
            "unit": unit,
        }
        raise Conflict(
            message, code="sale.quantity_off_grid", fields={"quantity": message}
        )


def provisional_total(line: OrderLine) -> int:
    """What the row paints: its frozen price by its quantity, with its own discount, plus its options of
    another tax category (each charged on a child line); a comp, 0; a line a voucher pays, 0."""
    if line.voucher_session_id is not None:
        return 0
    return sum(
        pricing.line_amount(
            part.unit_price,
            ratio_of(part),
            line_percent=part.discount_percent,
            is_gift=part.is_gift,
        )
        for part in charge_parts([line])
    )


def charge_parts(lines: Iterable[OrderLine]) -> list[OrderLine]:
    """What a charge values and records, in order: each line of the check and, right after it, a child line
    per option of another tax category (SALE-F11, MODIFIER-F07) — unsaved, at the option's frozen price, with
    the dish's discount and comp, and its count per dish by the dish's quantity. A menu Menus splits (SALE-F12,
    COMBO-F09) is not a part itself: each of its dishes is, at its share of the amount and its own tax
    category, with no parent line carrying money, and right after it each option of the dish Menus gave a part of
    its own (SALE-F42). Each part keeps the check's line it comes from in ``origin`` (itself for the line)."""
    parts: list[OrderLine] = []
    for line in lines:
        line.origin = line
        if line.combo_id is not None and line.combo.get("split"):
            for dish in line.combo["components"]:
                parts += _dish_parts(line, dish)
            continue
        parts.append(line)
        for own in line.modifier_lines:
            child = OrderLine(
                order_id=line.order_id,
                position=line.position,
                name=own["name"],
                unit="ud",
                quantity=Decimal(own["quantity"]) * line.quantity,
                unit_price=own["price_delta"],
                tax_category_key=own["tax_category_key"],
                discount_percent=line.discount_percent,
                discount_approved_by=line.discount_approved_by,
                is_gift=line.is_gift,
                gift_reason=line.gift_reason,
                staff_id=line.staff_id,
            )
            child.origin = line
            parts.append(child)
    return parts


def _dish_parts(line: OrderLine, dish: dict) -> list[OrderLine]:
    """A dish of a split menu as a part of the charge, with the options inside it, and after it a part per option of a
    line of its own, under the dish's (``parent_part``): one each per menu of the line, at its share of one menu's
    amount and its tax category, with the menu's discount and comp."""
    part = _dish_part(line, dish)
    parts = [part]
    for option in dish.get("options", []):
        if option["amount"] is None:
            continue
        own = OrderLine(
            order_id=line.order_id,
            position=line.position,
            name=option["name"],
            unit="ud",
            increment=WHOLE,
            quantity=line.quantity,
            unit_price=option["amount"],
            tax_category_key=option["line_tax_category_key"],
            discount_percent=line.discount_percent,
            discount_approved_by=line.discount_approved_by,
            is_gift=line.is_gift,
            gift_reason=line.gift_reason,
            staff_id=line.staff_id,
        )
        own.origin = line
        own.parent_part = part
        parts.append(own)
    return parts


def _dish_part(line: OrderLine, dish: dict) -> OrderLine:
    part = OrderLine(
        order_id=line.order_id,
        position=line.position,
        combo_id=line.combo_id,
        product_id=dish["product_id"],
        name=dish["product_name"],
        sku=dish["sku"],
        is_service=dish["is_service"],
        category_id=dish["category_id"],
        unit="ud",
        increment=WHOLE,
        quantity=line.quantity,
        unit_price=dish["amount"],
        tax_category_key=dish["tax_category_key"],
        discount_percent=line.discount_percent,
        discount_approved_by=line.discount_approved_by,
        is_gift=line.is_gift,
        gift_reason=line.gift_reason,
        notes=line.notes,
        staff_id=line.staff_id,
        modifiers=inside(dish),
    )
    part.origin = line
    part.dish = dish
    return part


def is_child(part: OrderLine) -> bool:
    """A child line of an option, not a line of the check (nor a dish of a split menu)."""
    return getattr(part, "origin", part) is not part and getattr(part, "dish", None) is None


def combo_name(part: OrderLine) -> str:
    """The menu a part charges, or is a dish of: the receipt's header of its dishes."""
    origin = getattr(part, "origin", part)
    return origin.name if origin.combo_id is not None else ""


def dishes_of(part: OrderLine) -> list[dict]:
    """The dishes a part charges: all the menu's when it goes in one line, its own when it is a dish of a
    split menu, none otherwise."""
    if getattr(part, "dish", None) is not None:
        dishes = [part.dish]
    elif part.combo_id is not None and not is_child(part):
        dishes = part.combo["components"]
    else:
        return []
    return [
        {
            "product_id": dish["product_id"],
            "product_name": dish["product_name"],
            "quantity": dish["quantity"],
            "is_service": dish["is_service"],
            "category_id": dish["category_id"],
            "modifiers": [option["name"] for option in inside(dish)],
        }
        for dish in dishes
    ]


def inside(dish: dict) -> list[dict]:
    """The options of a dish of a menu charged inside the dish's line (SALE-F42): all of them unless Menus gave one a
    part of its own; none on a dish ordered without."""
    return [option for option in dish.get("options", []) if option.get("amount") is None]


def dish_name(dish: dict) -> str:
    """A dish of a menu as the bill names it: «Steak (Rare, Cheese)» with the options charged inside it."""
    names = dish.get("modifiers", [])
    return f"{dish['product_name']} ({', '.join(names)})" if names else dish["product_name"]


def folded_names(line: OrderLine) -> list[str]:
    """The options charged inside the line (the receipt prints them under it): not the child lines'."""
    return [pick["name"] for pick in line.modifiers if not pick.get("own_line")]


def ratio_of(line: OrderLine | object):
    return pricing.price_ratio(
        line.quantity,
        (line.unit_factor_num, line.unit_factor_den),
        (line.pricing_factor_num, line.pricing_factor_den),
        line.price_quantity,
    )
