"""The assistant's card for a line added to a cart (``ai={"summary": item_card.summary}``): the product, how many and the
price of one, as the line will keep them, right after the cart. A normal card's line shows only its first three data,
and in Cart & checkout the quantity and the price are whoever asks says, not the catalog's."""

from babel.numbers import format_decimal
from django.utils import translation
from django.utils.text import capfirst
from live.context import OperationContext
from pydantic import ValidationError

from apps.cart_checkout.models import CartItem
from apps.cart_checkout.schemas import CartRefIn, ItemAddIn
from base.business import babel_locale

LINE = ("product_name", "quantity", "unit_price")


def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The cart, then the line. Data the write refuses, or a cart whose currency this person cannot read (none found,
    several), keep the card as they came: no price in a currency made up."""
    try:
        data = ItemAddIn.model_validate(arguments)
    except ValidationError:
        return fields
    price = next((field for field in fields if field["name"] == "unit_price"), {})
    if price.get("kind") != "money":
        return fields
    quantity = format_decimal(data.quantity, locale=babel_locale(translation.get_language()))
    line = {
        "name": "item",
        "label": capfirst(str(CartItem._meta.verbose_name)),
        "kind": "object",
        "value": {
            "product_name": data.product_name,
            "quantity": quantity,
            "unit_price": {key: price[key] for key in ("kind", "value", "money") if key in price},
        },
    }
    cart = [field for field in fields if field["name"] in CartRefIn.model_fields]
    rest = [field for field in fields if field["name"] not in {*CartRefIn.model_fields, *LINE}]
    return [*cart, line, *rest]
