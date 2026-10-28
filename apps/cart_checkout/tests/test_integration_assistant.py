"""The assistant's confirmation card names each datum of a write of Cart & checkout by a name of the app's own
(FIX-HUB-CART_CHECKOUT-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title
pydantic makes up from the field («Item Id», «Order Id»), nor by a word another app's catalog happens to lend
(«Customer» → «Cliente», from Tables'). The card is base's (``base.assistant.card``); the names are cart_checkout's:
the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import gettext
import json
from pathlib import Path

from django.apps import apps
from django.utils.text import capfirst
from django.utils.translation import override
from live.operations import get, registry

from apps.cart_checkout.models import CartItem
from base import assistant
from base.tests.test_assistant import named_by_the_screen

APP = Path(apps.get_app_config("cart_checkout").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["cart_checkout"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["cart_checkout"]

#: The writes of Cart & checkout the assistant calls, by name.
TOOLS = sorted(
    name
    for name, op in registry.items()
    if op.app_label == "cart_checkout" and op.kind == "command" and assistant.is_tool(op)
)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def named_by_cart_checkout(op, name: str, title: str | None) -> bool:
    """Whether cart_checkout itself names the datum ``name`` of ``op``: by its schema's own title, by the
    ``verbose_name`` of one of its models, or by its own catalog. A title pydantic made up that another app's catalog
    happens to translate is not a name of Cart & checkout: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("cart_checkout", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_cart_checkout_reaches_a_spanish_card_by_its_technical_name():
    """Every write of cart_checkout the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up. By where the name comes from, not by the word: «SKU» is said the same in
    both languages and is its model's."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 13  # positive control: the registry has cart_checkout's writes
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_cart_checkout(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_the_customer_a_cart_is_found_by():
    """A cart said by its customer (their email or part of their name), as the app calls them: «Cliente»."""
    for name in ("cart_checkout.cart.clear", "cart_checkout.item.add", "cart_checkout.checkout.initiate"):
        assert labels(assistant.card(get(name), {"customer": "Ana"}, "es")) == ["Cliente"]
        assert labels(assistant.card(get(name), {"customer": "Ana"}, "en")) == ["Customer"]


def test_the_card_names_the_line_of_a_cart_as_its_model():
    """No screen shows a cart's lines: the card says the line as the app's model does («línea del carrito»)."""
    with override("es"):
        line = capfirst(str(CartItem._meta.verbose_name))
    assert line == "Línea del carrito"
    for name in ("cart_checkout.item.update", "cart_checkout.item.remove"):
        assert labels(assistant.card(get(name), {"item_id": "x"}, "es")) == [line]
        assert labels(assistant.card(get(name), {"item_id": "x"}, "en")) == ["Cart line"]


def test_the_card_names_the_order_as_the_orders_screen():
    for name in ("cart_checkout.order.mark_paid", "cart_checkout.order.complete", "cart_checkout.order.fail"):
        assert labels(assistant.card(get(name), {"order_id": "x"}, "es")) == [SCREENS["orders"]["columns"]["order"]]
        assert labels(assistant.card(get(name), {"order_id": "x"}, "en")) == [
            SCREENS_EN["orders"]["columns"]["order"]
        ]
