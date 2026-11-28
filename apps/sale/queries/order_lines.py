"""Freezing a line of a product, a menu or an open price, as Inventory, Menus and Modifiers price it."""

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from apps.sale.models.orders import OrderLine
from apps.sale.queries.business import actor, missing_tax
from apps.sale.queries.departments import _department_refused, find_department, find_tax_category
from apps.sale.queries.line_parts import GRID_FALLBACK, WHOLE, check_grid, provisional_total
from apps.sale.queries.other_apps import call_app
from apps.sale.schemas.lines import ComboLineFields, LineFields, OpenLineFields, ProductLineIn
from base.allergens import in_order
from base.sensitive import recording_costs

PRODUCT_NOT_AVAILABLE = _(
    "A product of the ticket is no longer in the catalog. Remove the line and add it again."
)


#: Words of a person that fit no product of the catalog, said back as they were said.
NO_SUCH_PRODUCT = _("There is no product “%(said)s”. Say which one.")


PRODUCT_SOLD_OUT = _("«%(name)s» is sold out.")


OPEN_PRICE_PERMISSION = _(
    "Only someone who may sell at an open price can add this line: ask a manager."
)


def new_line(ctx: OperationContext, data: LineFields, **frozen) -> OrderLine:
    """An unsaved row: what ``frozen`` copies of its product, menu, service or price, what every line takes from its
    input (quantity, note, who serves it, comp) and its provisional total."""
    line = OrderLine(
        **frozen,
        quantity=data.quantity,
        notes=data.notes,
        staff_id=data.staff_id,
        is_gift=data.is_gift,
        gift_reason=data.gift_reason if data.is_gift else "",
        created_by=actor(ctx),
    )
    line.line_total = provisional_total(line)
    return line


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
#: What Menus takes of an option of Modifiers to price a dish's options (SALE-F42).
DISH_OPTION_FIELDS = ("option_id", "name", "kitchen_name", "price_delta", "tax_category_key", "own_line", "allergens")


def _dish_label(dish: dict) -> str:
    """A dish as the kitchen's text of the line names it: «2× Coffee», with its options' kitchen names («Steak (RARE)»)."""
    label = dish["product_name"] if dish["quantity"] == 1 else f"{dish['quantity']}× {dish['product_name']}"
    options = [option["kitchen_name"] for option in dish.get("options", [])]
    return f"{label} ({', '.join(options)})" if options else label


def _resolved_menu(ctx: OperationContext, request: dict) -> dict:
    """Menus' answer for a menu line (COMBO-F08), as JSON. Menus off or absent: 409
    ``sale.combo_unavailable``; its refusals (a course short, a dish sold out…) reach the seller as they are."""
    return call_app(ctx, COMBO_RESOLVE, request, "sale.combo_unavailable").model_dump(mode="json")


def _product(ctx: OperationContext, data: dict):
    return call_app(ctx, "inventory.product.get", data, "sale.catalog_unavailable")


def _with_allergens(ctx: OperationContext, menu: dict) -> dict:
    """Menus' answer with each dish carrying the allergens Inventory declares for its product today (SALE-F40) and those
    its options add (SALE-F42)."""
    for dish in menu["components"]:
        picked = [code for option in dish.get("options", []) for code in option["allergens"]]
        dish["allergens"] = in_order([*_product(ctx, {"id": dish["product_id"]}).allergens, *picked])
    return menu


def _options_by_dish(ctx: OperationContext, data: ComboLineFields, combo_id) -> dict[str, list]:
    """The options of Modifiers chosen for each dish, by its choice of Menus: a dish named by its product is found by
    Menus; two picks of one dish carry the options of both."""
    chosen: dict[str, list] = {}
    for choice in data.choices:
        if not choice.option_ids:
            continue
        option_id = choice.option_id
        if option_id is None:
            said = {"combo_id": combo_id, "group": choice.group, "product": choice.product}
            option_id = call_app(ctx, "combo.option.get", said, "sale.combo_unavailable").id
        chosen[str(option_id)] = [*chosen.get(str(option_id), []), *choice.option_ids]
    return chosen


def _dish_options(ctx: OperationContext, data: ComboLineFields, menu: dict) -> dict[str, list]:
    """The options of each dish of ``menu`` as Modifiers checks and values them for the dish's product (MODIFIER-F07),
    asked for every dish while Modifiers is on, so a required group left empty refuses the menu also through the API
    and the assistant (SALE-F42); none without Modifiers."""
    chosen = _options_by_dish(ctx, data, menu["combo_id"])
    valued = {}
    for dish in menu["components"]:
        picked = _options(ctx, dish["product_id"], chosen.get(str(dish["option_id"]), []))
        options = [pick.model_dump(mode="json") for pick in picked.picks] if picked else []
        valued[str(dish["option_id"])] = [{key: option[key] for key in DISH_OPTION_FIELDS} for option in options]
    return valued


def freeze_combo_line(ctx: OperationContext, data: ComboLineFields) -> OrderLine:
    """An unsaved row for a menu of Menus (SALE-F12): Menus checks the dishes picked and prices it; the line
    keeps its answer, and its amount as the price ordered. A menu is sold in whole units."""
    check_grid(data.quantity, WHOLE, "ud")
    answer = _resolved_menu(
        ctx,
        {
            "id": data.combo_id,
            "combo": data.combo,
            "choices": [choice.model_dump(exclude_none=True, exclude={"option_ids"}) for choice in data.choices],
        },
    )
    options = _dish_options(ctx, data, answer)
    if any(options.values()):
        # Menus prices the menu again, now with each dish's options.
        dishes = [
            {"option_id": dish["option_id"], "quantity": dish["quantity"], "options": options[str(dish["option_id"])]}
            for dish in answer["components"]
        ]
        answer = _resolved_menu(ctx, {"id": answer["combo_id"], "choices": dishes})
    return new_line(
        ctx,
        data,
        combo_id=answer["combo_id"],
        combo=_with_allergens(ctx, answer),
        name=answer["name"],
        unit="ud",
        increment=WHOLE,
        unit_price=answer["amount"],
        tax_category_key=answer["tax_category_key"] or "",
        kitchen_text=", ".join(_dish_label(dish) for dish in answer["components"])[:500],
    )


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
                        {"option_id": dish["option_id"], "quantity": dish["quantity"], "options": _frozen_options(dish)}
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


def _frozen_options(dish: dict) -> list[dict]:
    """The options a dish of a menu froze, as Menus takes them again to charge it; none on a dish ordered without."""
    return [{key: option[key] for key in DISH_OPTION_FIELDS} for option in dish.get("options", [])]


def _options(ctx: OperationContext, product_id, option_ids: list[UUID]) -> dict | None:
    """Modifiers' check and valuation of the options chosen for a product (MODIFIER-F07), always asked when
    Modifiers is on, also with none chosen (it refuses a required group left empty, which the API and the
    assistant do not go through the sheet for). Modifiers off or absent: ``None`` without options, 409
    ``sale.modifier_unavailable`` with them. Its refusals reach the seller as they are."""
    try:
        return call_app(
            ctx,
            MODIFIER_RESOLVE,
            {"product_id": product_id, "option_ids": option_ids},
            "sale.modifier_unavailable",
        )
    except Conflict as refused:
        if refused.code == "sale.modifier_unavailable" and not option_ids:
            return None
        raise


def _dish_allergens(product, chosen) -> list[str]:
    """The product's allergens and those of every option chosen, also one charged on a line of its own, once each and
    in the order of the list. An option adds allergens to the dish and never takes one away."""
    picked = [code for pick in chosen.picks for code in pick.allergens] if chosen else []
    return in_order([*product.allergens, *picked])


def catalog_product(ctx: OperationContext, data: ProductLineIn):
    """The product a new line names, as Inventory finds it for ``ctx``: by its id, or by the words of whoever asks.
    One named by an id is no longer in the catalog when it is gone; words that fit no product are a 422 on ``product``
    that says them back, so whoever asked looks it up or says which one (several that fit: Inventory's own 409)."""
    try:
        return _product(ctx, {"id": data.product_id, "product": data.product})
    except NotFound:
        if data.product_id is None:
            message = str(NO_SUCH_PRODUCT) % {"said": data.product}
            raise InvalidPayload(message, code="invalid_field", fields={"product": message}) from None
        raise Conflict(str(PRODUCT_NOT_AVAILABLE), code="sale.product_not_available") from None


def freeze_product_line(
    ctx: OperationContext, data: ProductLineIn, units: dict | None = None
) -> OrderLine:
    """An unsaved row for a product of Inventory: its price, unit and category frozen from the catalog. Only a
    new line goes through here, so an article sold out since it was ordered is still charged (COMBO-F08)."""
    # The line keeps the cost even when whoever sells does not see it (base.view_costs): it values the comps.
    product = catalog_product(recording_costs(ctx), data)
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
    chosen = _options(ctx, product.id, data.option_ids)
    picks = [pick.model_dump(mode="json") for pick in chosen.picks] if chosen else []
    return new_line(
        ctx,
        data,
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
        unit_price=product.price + (chosen.folded_delta if chosen else 0),
        cost=product.cost,
        tax_category_key=product.tax_category_key,
        modifiers=picks,
        modifier_lines=[own.model_dump(mode="json") for own in chosen.own_lines] if chosen else [],
        kitchen_text=chosen.kitchen_text[:500] if chosen else "",
        allergens=_dish_allergens(product, chosen),
    )


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
    return new_line(
        ctx,
        data,
        department=department,
        name=name,
        unit="ud",
        increment=GRID_FALLBACK,
        unit_price=data.unit_price,
        tax_category_key=category.key,
    )
