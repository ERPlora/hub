"""Freezing a line of a product, a menu or an open price, as Inventory, Menus and Modifiers price it."""

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied

from apps.sale.models import OrderLine
from apps.sale.queries.business import actor, missing_tax
from apps.sale.queries.departments import _department_refused, find_department, find_tax_category
from apps.sale.queries.line_parts import GRID_FALLBACK, WHOLE, check_grid, provisional_total
from apps.sale.queries.other_apps import call_app
from apps.sale.schemas import ComboLineFields, OpenLineFields, ProductLineIn

PRODUCT_NOT_AVAILABLE = _(
    "A product of the ticket is no longer in the catalog. Remove the line and add it again."
)


PRODUCT_SOLD_OUT = _("«%(name)s» is sold out.")


OPEN_PRICE_PERMISSION = _(
    "Only someone who may sell at an open price can add this line: ask a manager."
)


def inventory_units(ctx: OperationContext) -> dict:
    """``{code: (factor_num, factor_den, increment)}`` of Inventory's units of measure."""
    page = call_app(ctx, "inventory.unit.list", {"limit": 100}, "sale.catalog_unavailable")
    return {
        unit.code: (unit.factor_num, unit.factor_den, Decimal(unit.increment))
        for unit in page.rows
    }


#: Modifiers' check and valuation of the options chosen for a product (MODIFIER-F07), asked by name.
MODIFIER_RESOLVE = "modifier.selection.resolve"
#: Menus' check and pricing of a menu line (COMBO-F08, F09), asked by name.
COMBO_RESOLVE = "combo.combo.resolve"


def _dish_label(dish: dict) -> str:
    return dish["product_name"] if dish["quantity"] == 1 else f"{dish['quantity']}× {dish['product_name']}"


def _resolved_menu(ctx: OperationContext, request: dict) -> dict:
    """Menus' answer for a menu line (COMBO-F08), as JSON. Menus off or absent: 409
    ``sale.combo_unavailable``; its refusals (a course short, a dish sold out…) reach the seller as they are."""
    return call_app(ctx, COMBO_RESOLVE, request, "sale.combo_unavailable").model_dump(mode="json")


def freeze_combo_line(ctx: OperationContext, data: ComboLineFields) -> OrderLine:
    """An unsaved row for a menu of Menus (SALE-F12): Menus checks the dishes picked and prices it; the line
    keeps its answer, and its amount as the price ordered. A menu is sold in whole units."""
    check_grid(data.quantity, WHOLE, "ud")
    answer = _resolved_menu(
        ctx,
        {
            "id": data.combo_id,
            "combo": data.combo,
            "choices": [choice.model_dump(exclude_none=True) for choice in data.choices],
        },
    )
    line = OrderLine(
        combo_id=answer["combo_id"],
        combo=answer,
        name=answer["name"],
        unit="ud",
        increment=WHOLE,
        quantity=data.quantity,
        unit_price=answer["amount"],
        tax_category_key=answer["tax_category_key"] or "",
        kitchen_text=", ".join(_dish_label(dish) for dish in answer["components"])[:500],
        notes=data.notes,
        staff_id=data.staff_id,
        is_gift=data.is_gift,
        gift_reason=data.gift_reason if data.is_gift else "",
        created_by=actor(ctx),
    )
    line.line_total = provisional_total(line)
    return line


def refresh_combos(ctx: OperationContext, lines: Iterable[OrderLine]) -> None:
    """Charging an open check asks Menus again for each of its menus with the amount ordered (COMBO-F08):
    it does not ask for the dishes to be on offer again, only checks the courses, the portions and the tax
    data, and splits that amount (or not, and at which tax category) as it says today. Only the charge's copy
    of each line changes: the line of the check keeps what it froze. A menu Menus no longer knows (withdrawn
    since) or Menus off since: the check charges what it froze, as a ticket already issued keeps its copy."""
    for line in lines:
        if line.combo_id is None:
            continue
        try:
            answer = _resolved_menu(
                ctx,
                {
                    "id": line.combo_id,
                    "choices": [
                        {"option_id": dish["option_id"], "quantity": dish["quantity"]}
                        for dish in line.combo["components"]
                    ],
                    "amount": line.unit_price,
                },
            )
        except Conflict as refused:
            if refused.code in ("combo.combo_missing", "sale.combo_unavailable"):
                continue
            raise
        line.combo = answer
        line.tax_category_key = answer["tax_category_key"] or ""


def _options(ctx: OperationContext, product, option_ids: list[UUID]) -> dict | None:
    """Modifiers' check and valuation of the options chosen for ``product`` (MODIFIER-F07), always asked when
    Modifiers is on, also with none chosen (it refuses a required group left empty, which the API and the
    assistant do not go through the sheet for). Modifiers off or absent: ``None`` without options, 409
    ``sale.modifier_unavailable`` with them. Its refusals reach the seller as they are."""
    try:
        return call_app(
            ctx,
            MODIFIER_RESOLVE,
            {"product_id": product.id, "option_ids": option_ids},
            "sale.modifier_unavailable",
        )
    except Conflict as refused:
        if refused.code == "sale.modifier_unavailable" and not option_ids:
            return None
        raise


def freeze_product_line(
    ctx: OperationContext, data: ProductLineIn, units: dict | None = None
) -> OrderLine:
    """An unsaved row for a product of Inventory: its price, unit and category frozen from the catalog. Only a
    new line goes through here, so an article sold out since it was ordered is still charged (COMBO-F08)."""
    try:
        product = call_app(
            ctx,
            "inventory.product.get",
            {"id": data.product_id, "product": data.product},
            "sale.catalog_unavailable",
        )
    except NotFound:
        raise Conflict(
            str(PRODUCT_NOT_AVAILABLE), code="sale.product_not_available"
        ) from None
    if not product.is_active:
        raise Conflict(str(PRODUCT_NOT_AVAILABLE), code="sale.product_not_available")
    # Sold out («86», INVENTORY-F29) stops only a new line: what was ordered before is still charged.
    if product.is_sold_out:
        raise Conflict(str(PRODUCT_SOLD_OUT) % {"name": product.name}, code="sale.product_sold_out")
    if product.needs_tax_setup or not product.tax_category_key:
        raise Conflict(
            missing_tax(product.name),
            code="sale.tax_category_missing",
        )
    units = units if units is not None else inventory_units(ctx)
    unit = units[product.unit]
    priced_in = units[product.pricing_unit]
    check_grid(data.quantity, unit[2], product.unit)
    chosen = _options(ctx, product, data.option_ids)
    picks = [pick.model_dump(mode="json") for pick in chosen.picks] if chosen else []
    line = OrderLine(
        product_id=product.id,
        name=product.name,
        sku=product.sku,
        is_service=product.product_type == "service",
        category_id=product.category_ids[0] if product.category_ids else None,
        unit=product.unit,
        unit_factor_num=unit[0],
        unit_factor_den=unit[1],
        increment=unit[2],
        price_quantity=product.price_quantity,
        pricing_unit=product.pricing_unit,
        pricing_factor_num=priced_in[0],
        pricing_factor_den=priced_in[1],
        quantity=data.quantity,
        unit_price=product.price + (chosen.folded_delta if chosen else 0),
        cost=product.cost,
        tax_category_key=product.tax_category_key,
        modifiers=picks,
        modifier_lines=[own.model_dump(mode="json") for own in chosen.own_lines] if chosen else [],
        kitchen_text=chosen.kitchen_text[:500] if chosen else "",
        notes=data.notes,
        staff_id=data.staff_id,
        is_gift=data.is_gift,
        gift_reason=data.gift_reason if data.is_gift else "",
        created_by=actor(ctx),
    )
    line.line_total = provisional_total(line)
    return line


def freeze_open_line(ctx: OperationContext, data: OpenLineFields) -> OrderLine:
    """An unsaved open-price row: the amount typed, the department's (or a category's) VAT."""
    if not ctx.has("sale.sell_open_price"):
        raise PermissionDenied(str(OPEN_PRICE_PERMISSION))
    department = None
    if data.department_id is not None or data.department is not None:
        try:
            department = find_department(data.department_id, data.department)
        except NotFound as missing:
            raise _department_refused(data, missing.message) from None
        category = department.tax_category
    else:
        category = find_tax_category(data.tax_category_key)
    with translation.override(ctx.language):
        name = data.name or (department.name if department else category.display_name)
    check_grid(data.quantity, GRID_FALLBACK, "ud")
    line = OrderLine(
        department=department,
        name=name,
        unit="ud",
        increment=GRID_FALLBACK,
        quantity=data.quantity,
        unit_price=data.unit_price,
        tax_category_key=category.key,
        notes=data.notes,
        staff_id=data.staff_id,
        is_gift=data.is_gift,
        gift_reason=data.gift_reason if data.is_gift else "",
        created_by=actor(ctx),
    )
    line.line_total = provisional_total(line)
    return line
