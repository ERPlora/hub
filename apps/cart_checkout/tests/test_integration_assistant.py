"""The assistant's confirmation card names each datum of a write of Cart & checkout by a name of the app's own
(FIX-HUB-CART_CHECKOUT-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title
pydantic makes up from the field («Item Id», «Order Id»), nor by a word another app's catalog happens to lend
(«Customer» → «Cliente», from Tables'). The card is base's (``base.assistant.card``); the names are cart_checkout's:
the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog.

The record a write names by its id (FIX-HUB-CART_CHECKOUT-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's half is
hub#416): the cart by its session code, as the Carts list and «Delete the cart …?» name it; the line by its product; the
order by its number, as the Orders list. Read as whoever asks, in the hub they ask in — never by the id, and left out when
nobody, or somebody who may not see carts, is behind the request."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils.text import capfirst
from django.utils.translation import override
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get, registry

from apps.cart_checkout.models import CartItem
from base import assistant
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID

from .conftest import ctx_for

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


# ── The record a write names by its id, by its name ───────────────────────────────────────────────────────────────────

#: The writes that name a cart, a line or an order by its id, by the datum that does.
ON_A_CART = (
    "cart_checkout.cart.clear",
    "cart_checkout.cart.delete",
    "cart_checkout.cart.mark_abandoned",
    "cart_checkout.checkout.initiate",
    "cart_checkout.item.add",
)
ON_A_LINE = ("cart_checkout.item.update", "cart_checkout.item.remove")
ON_AN_ORDER = ("cart_checkout.order.mark_paid", "cart_checkout.order.fail", "cart_checkout.order.complete")
#: What each write sends besides the record, as the model would.
BESIDES = {
    "cart_checkout.item.add": {"product_ref": "p-9", "product_name": "Mascarilla", "quantity": "1", "unit_price": 900},
    "cart_checkout.item.update": {"quantity": "3"},
    "cart_checkout.order.fail": {"reason": "Tarjeta rechazada"},
}
#: The roles a business gives that may run every write of the app (cart_checkout.*): the manager is the least of them.
WRITERS = ("hub_manager", "hub_admin", "hub_owner")


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def no_id(card: dict) -> bool:
    return not AN_ID.search(json.dumps(card, ensure_ascii=False))


def in_hub(hub, role: str = "hub_manager", **ctx) -> OperationContext:
    return ctx_for(role, scope=Scope("host", hub.slug), **ctx)


def run(ctx: OperationContext, name: str, data: dict):
    op = get(name)
    return op(ctx, op.input.model_validate(data))


def shop(ctx: OperationContext, session: str = "sess_ana") -> dict:
    """A cart of Ana with two lines and an order initiated from it, made by the app's own writes: their ids."""
    cart = run(ctx, "cart_checkout.cart.create", {"session_token": session, "customer_name": "Ana García"})
    line = run(
        ctx,
        "cart_checkout.item.add",
        {"cart_id": str(cart.id), "product_ref": "p-1", "product_name": "Champú", "quantity": "2", "unit_price": 1250},
    ).item
    second = {"product_ref": "p-2", "product_name": "Acondicionador", "quantity": "1", "unit_price": 900}
    run(ctx, "cart_checkout.item.add", {"cart_id": str(cart.id), **second})
    order = run(ctx, "cart_checkout.checkout.initiate", {"cart_id": str(cart.id), "customer_email": "ana@example.com"})
    return {"cart_id": str(cart.id), "item_id": str(line.id), "order_id": str(order.id), "number": order.order_number}


@pytest.fixture
def no_fallback(monkeypatch):
    """As production: without ``use_hub`` a hub's model fails, nothing falls back on the shared database."""
    monkeypatch.setattr(context, "_test_fallback", None)


def cards(ctx: OperationContext, names: tuple[str, ...], datum: str, record: str, language: str = "es") -> dict:
    return {
        name: assistant.card(get(name), {datum: record, **BESIDES.get(name, {})}, language, ctx) for name in names
    }


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("role", WRITERS)
def test_a_write_on_a_cart_names_it_by_its_session_code(role, hub_a, no_fallback):
    """«Vacía el carrito», «bórralo», «abandónalo», «inicia su pedido», «añade una línea»: the card says which cart as
    the Carts list does, by its session code, never by its id."""
    with use_hub(hub_a):
        made = shop(in_hub(hub_a))
        said = cards(in_hub(hub_a, role), ON_A_CART, "cart_id", made["cart_id"])
    assert {name: values(card)["cart_id"] for name, card in said.items()} == dict.fromkeys(ON_A_CART, "sess_ana")
    assert all(no_id(card) for card in said.values())
    assert {name: card["fields"][0]["label"] for name, card in said.items()} == dict.fromkeys(ON_A_CART, "Carrito")


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("role", WRITERS)
def test_a_change_to_a_line_names_it_by_its_product(role, hub_a, no_fallback):
    """«Pon tres» or «quita esa línea»: no screen lists a cart's lines, so the card says the line by its product, as the
    cart's detail gives it, never by its id."""
    with use_hub(hub_a):
        made = shop(in_hub(hub_a))
        said = cards(in_hub(hub_a, role), ON_A_LINE, "item_id", made["item_id"])
    assert {name: values(card)["item_id"] for name, card in said.items()} == dict.fromkeys(ON_A_LINE, "Champú")
    assert all(no_id(card) for card in said.values())
    assert values(said["cart_checkout.item.update"])["quantity"] == "3"


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("role", WRITERS)
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_write_on_an_order_names_it_by_its_number(language, role, hub_a, no_fallback):
    """«Márcalo pagado», «falló», «complétalo» (the first two, dangerous): the card says which order as the Orders list
    does, by its number (OS-YYYYMMDD-NNNN), so a wrong one is seen before confirming."""
    with use_hub(hub_a):
        made = shop(in_hub(hub_a))
        said = cards(in_hub(hub_a, role), ON_AN_ORDER, "order_id", made["order_id"], language)
    assert made["number"].startswith("OS-")
    assert {name: values(card)["order_id"] for name, card in said.items()} == dict.fromkeys(ON_AN_ORDER, made["number"])
    assert all(no_id(card) for card in said.values())


def test_whoever_may_run_a_write_reads_the_record_its_card_names():
    """The read runs as the person: a role that may run a write and not read what its card names would get a card with
    nothing to recognise, just in the common case. Every role a business gives, every write that names a record."""
    configs = all_live_app_configs()
    unread: list[tuple[str, str]] = []
    checked = 0
    for role in ("hub_employee", *WRITERS):
        mine = OperationContext(scope=Scope("host", "a"), actor="x", permissions=permissions_for_role(configs, role))
        for name in (*ON_A_CART, *ON_A_LINE, *ON_AN_ORDER):
            op = get(name)
            if not mine.has(op.permission):
                continue
            for prop in assistant._schema(op).get("properties", {}).values():
                marked = assistant.refers_of(assistant._resolved(prop, assistant._schema(op).get("$defs", {})))
                if marked is not None:
                    checked += 1
                    if not mine.has(registry[marked["read"]].permission):
                        unread.append((role, name))
    assert checked >= 10 * len(WRITERS)  # positive control: every write's mark was found, for every writer
    assert unread == []


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_nobody_behind_the_request_reads_no_cart_line_or_order(hub_a, no_fallback):
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    with use_hub(hub_a):
        made = shop(in_hub(hub_a))
        for names, datum in ((ON_A_CART, "cart_id"), (ON_A_LINE, "item_id"), (ON_AN_ORDER, "order_id")):
            for name in names:
                card = assistant.card(get(name), {datum: made[datum], **BESIDES.get(name, {})}, "es")
                assert datum not in values(card) and no_id(card), name


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_who_may_not_see_carts_reads_none_of_them_on_the_card(hub_a, no_fallback):
    """Whoever asks without «view carts» (the write refuses them too) gets the record left out, never its id."""
    with use_hub(hub_a):
        made = shop(in_hub(hub_a))
        blind = in_hub(hub_a, permissions={"base.view_home"})
        said = {
            datum: cards(blind, names, datum, made[datum])
            for names, datum in ((ON_A_CART, "cart_id"), (ON_A_LINE, "item_id"), (ON_AN_ORDER, "order_id"))
        }
    for datum, by_write in said.items():
        for name, card in by_write.items():
            assert datum not in values(card) and no_id(card), name


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_deleted_cart_is_left_out_never_by_its_id(hub_a, no_fallback):
    """A deleted cart is never read (the write refuses it too): its card names none."""
    with use_hub(hub_a):
        ctx = in_hub(hub_a)
        made = shop(ctx)
        run(ctx, "cart_checkout.cart.delete", {"cart_id": made["cart_id"]})
        card = assistant.card(get("cart_checkout.cart.clear"), {"cart_id": made["cart_id"]}, "es", ctx)
    assert values(card) == {} and no_id(card)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_cart_of_hub_b_is_never_named_on_a_card_of_hub_a(hub_a, hub_b, no_fallback):
    """The read runs in the hub the person asks in: hub B's cart, line or order is nobody in hub A."""
    with use_hub(hub_b):
        of_b = shop(in_hub(hub_b), session="sess_bea")
    with use_hub(hub_a):
        in_a = {
            datum: assistant.card(get(name), {datum: of_b[datum], **BESIDES.get(name, {})}, "es", in_hub(hub_a))
            for name, datum in (
                ("cart_checkout.cart.clear", "cart_id"),
                ("cart_checkout.item.remove", "item_id"),
                ("cart_checkout.order.mark_paid", "order_id"),
            )
        }
    assert {datum: values(card) for datum, card in in_a.items()} == {"cart_id": {}, "item_id": {}, "order_id": {}}
    # Positive control: in hub B the same cards name them.
    with use_hub(hub_b):
        in_b = assistant.card(get("cart_checkout.cart.clear"), {"cart_id": of_b["cart_id"]}, "es", in_hub(hub_b))
    assert values(in_b) == {"cart_id": "sess_bea"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_the_card_names_the_line_of_a_cart_as_its_model(hub_a, no_fallback):
    """No screen shows a cart's lines: the card says the line as the app's model does («línea del carrito»). A line is
    named by its record (since hub#416 one the card cannot read is left out): a real one, read as its manager."""
    with override("es"):
        line = capfirst(str(CartItem._meta.verbose_name))
    assert line == "Línea del carrito"
    with use_hub(hub_a):
        item = shop(in_hub(hub_a))["item_id"]
        for name in ("cart_checkout.item.update", "cart_checkout.item.remove"):
            assert labels(assistant.card(get(name), {"item_id": item}, "es", in_hub(hub_a))) == [line]
            assert labels(assistant.card(get(name), {"item_id": item}, "en", in_hub(hub_a))) == ["Cart line"]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_the_card_names_the_order_as_the_orders_screen(hub_a, no_fallback):
    with use_hub(hub_a):
        order = shop(in_hub(hub_a))["order_id"]
        for name in ON_AN_ORDER:
            arguments = {"order_id": order, **BESIDES.get(name, {})}
            assert labels(assistant.card(get(name), arguments, "es", in_hub(hub_a)))[0] == SCREENS["orders"]["columns"][
                "order"
            ]
            assert labels(assistant.card(get(name), arguments, "en", in_hub(hub_a)))[0] == SCREENS_EN["orders"][
                "columns"
            ]["order"]


@pytest.mark.parametrize(("language", "label"), [("es", "Método de pago"), ("en", "Payment method")])
def test_the_card_says_the_payment_method_as_cart_checkout_does(language, label):
    """«Inicia el pedido y paga con tarjeta»: the payment method by cart_checkout's own word, not another app's («medio
    de pago», the till's)."""
    arguments = {"customer": "Ana", "payment_method": "card"}
    card = assistant.card(get("cart_checkout.checkout.initiate"), arguments, language)
    assert labels(card)[1] == label


# ── A line in the currency of its cart (BASE-F97) ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(
    ("currency", "money"),
    [("USD", {"currency": "USD", "decimals": 2}), ("JPY", {"currency": "JPY", "decimals": 0})],
    ids=["dollars", "yen"],
)
@pytest.mark.parametrize("datum", ["cart_id", "session_token", "customer"])
def test_a_line_added_to_a_cart_in_another_currency_is_priced_in_it(currency, money, datum, hub_a, no_fallback):
    """«Añade una mascarilla a 9 al carrito de Ana», a cart in dollars: the price goes in the minor unit of the cart's
    currency, and the card said it in the business's («9,00 €»). It reads the cart as the person, by what names it."""
    with use_hub(hub_a):
        ctx = in_hub(hub_a)
        cart = run(ctx, "cart_checkout.cart.create", {"session_token": "sess_ana", "customer_name": "Ana García", "currency": currency})
        which = {"cart_id": str(cart.id), "session_token": "sess_ana", "customer": "Ana García"}[datum]
        card = assistant.card(get("cart_checkout.item.add"), {datum: which, **BESIDES["cart_checkout.item.add"]}, "es", ctx)
    [price] = [field for field in card["fields"] if field["name"] == "unit_price"]
    assert {key: price[key] for key in ("kind", "value", "money") if key in price} == {"kind": "money", "value": 900, "money": money}
