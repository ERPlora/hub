"""The assistant's card for a write of pricing (FIX-HUB-PRICING-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Price lists screens give it, never by the title pydantic
makes up from the field («Customer Group», «Rule»). The card is base's (``base.assistant.card``); the names are
pricing's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import dataclasses
import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.errors import AppInactive
from live.operations import get, registry

from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID, card_title

from .conftest import ctx_for, make_item, make_list, make_product

FRONTEND = Path(apps.get_app_config("pricing").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["pricing"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["pricing"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def pricing_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "pricing" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_pricing_reaches_a_spanish_card_by_its_technical_name():
    """Every write of pricing the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = pricing_writes()
    assert len(writes) > 10  # positive control: the registry has pricing's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_customer_group_said_by_its_name_as_the_forms_do():
    """A price list or a rule for a group the person names («los socios»): the forms' «Customer group»."""
    group, group_en = SCREENS["lists"]["form"]["group"], SCREENS_EN["lists"]["form"]["group"]
    assert SCREENS["rules"]["form"]["group"] == group
    for name in ("pricing.price_list.create", "pricing.price_list.update", "pricing.rule.create", "pricing.rule.update"):
        assert labels(assistant.card(get(name), {"customer_group": "Socios"}, "es")) == [group]
        assert labels(assistant.card(get(name), {"customer_group": "Socios"}, "en")) == [group_en]


def test_the_card_names_the_rule_it_changes_as_the_discount_rules_screen_does():
    """Editing, deactivating or activating a rule named by its code or name: «Regla de descuento», never «Rule»."""
    for name in ("pricing.rule.update", "pricing.rule.deactivate", "pricing.rule.activate"):
        assert labels(assistant.card(get(name), {"rule": "VERANO"}, "es")) == ["Regla de descuento"]
        assert labels(assistant.card(get(name), {"rule": "VERANO"}, "en")) == ["Discount rule"]


# ── A price in the currency of its list (BASE-F97) ────────────────────────────────────────────────────────────────────


def priced(card: dict) -> dict:
    """The price the card shows, as the screen paints it: its kind, its figure and its currency when it is not the
    business's."""
    [price] = [field for field in card["fields"] if field["name"] == "price"]
    return {key: price[key] for key in ("kind", "value", "money") if key in price}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("currency", "money"),
    [("USD", {"currency": "USD", "decimals": 2}), ("PLN", {"currency": "PLN", "decimals": 2})],
    ids=["dollars", "zlotys"],
)
@pytest.mark.parametrize("named", ["price_list_id", "price_list"], ids=["by its id", "by its code"])
def test_a_price_added_to_a_list_in_another_currency_is_said_in_that_currency(currency, money, named):
    """«Pon el champú a 15 en la lista de dólares»: the price goes in the minor unit of the list's currency, and the
    card said it in the business's («15,00 €»). It reads the list as the person, by what the write names it. A list
    is always in a currency with two decimals (``D_CURRENCY``): none in yen."""
    price_list = make_list("DOLARES", currency=currency)
    product = make_product("Shampoo", "SH-1")
    which = {"price_list_id": str(price_list.id), "price_list": "DOLARES"}[named]
    arguments = {named: which, "product_id": str(product.id), "price": 1500}
    card = assistant.card(get("pricing.price_item.add"), arguments, "es", ctx_for(language="es"))
    assert priced(card) == {"kind": "money", "value": 1500, "money": money}


@pytest.mark.django_db
def test_a_price_on_a_list_that_is_not_there_is_said_as_sent():
    """No currency made up: the write refuses a list that does not exist, and the card does not paint a price in one."""
    card = assistant.card(get("pricing.price_item.add"), {"price_list": "NADA", "product": "Shampoo", "price": 1500}, "es", ctx_for(language="es"))
    assert priced(card) == {"kind": "text", "value": 1500}


#: The roles a business gives that change prices (``pricing.manage``): the manager is the least of them.
WRITERS = ("hub_manager", "hub_admin", "hub_owner")


def in_hub(hub, role: str = "hub_manager", **ctx) -> OperationContext:
    return ctx_for(role, scope=Scope("host", hub.slug), language="es", **ctx)


def a_price(currency: str = "USD"):
    """A price of the shampoo in the list DOLARES, in ``currency``: what «cambia el precio del champú» names by its id."""
    return make_item(make_list("DOLARES", currency=currency), make_product("Shampoo", "SH-1"), price=1200)


def price_change(item, ctx: OperationContext | None) -> dict:
    return assistant.card(get("pricing.price_item.update"), {"id": str(item.id), "price": 1500}, "es", ctx)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("role", WRITERS)
@pytest.mark.parametrize(
    ("currency", "money"),
    [("USD", {"currency": "USD", "decimals": 2}), ("PLN", {"currency": "PLN", "decimals": 2}), ("EUR", {"currency": "EUR", "decimals": 2})],
    ids=["dollars", "zlotys", "the business's"],
)
def test_a_price_changed_on_a_list_in_another_currency_is_said_in_that_currency(currency, money, role, hub_a, no_fallback):
    """«Pon el champú a 15 en la lista de dólares», a price named by its id: it goes in the minor unit of its list's
    currency, and the card said it in the business's («15,00 €»), never «1500». It reads the price as the person who
    changes it, every role that may."""
    with use_hub(hub_a):
        card = price_change(a_price(currency), in_hub(hub_a, role))
    assert priced(card) == {"kind": "money", "value": 1500, "money": money}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_price_of_another_business_is_said_as_sent_never_in_its_currency(hub_a, hub_b, no_fallback):
    """The id of another business's price names none of this one (the write refuses it): no currency made up, neither
    the other's nor this business's."""
    with use_hub(hub_b):
        theirs = a_price()
    with use_hub(hub_a):
        card = price_change(theirs, in_hub(hub_a))
    assert priced(card) == {"kind": "text", "value": 1500}
    with use_hub(hub_b):  # positive control: in its own business, in dollars
        assert priced(price_change(theirs, in_hub(hub_b)))["money"] == {"currency": "USD", "decimals": 2}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_nobody_behind_the_request_reads_no_price_for_its_card(hub_a, no_fallback):
    """An automation's card (no person at hand) reads nothing for anybody: the price as sent."""
    with use_hub(hub_a):
        card = price_change(a_price(), None)
    assert priced(card) == {"kind": "text", "value": 1500}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_who_may_not_see_prices_reads_none_on_the_card(hub_a, no_fallback):
    """Whoever asks without «view prices» (the write refuses them too) reads no list's currency: the price as sent."""
    with use_hub(hub_a):
        card = price_change(a_price(), in_hub(hub_a, permissions={"base.view_home"}))
    assert priced(card) == {"kind": "text", "value": 1500}


# ── The record a write names by its id, by its name (FIX-HUB-PRICING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's half
# is hub#416) ──
# Since hub#416 the card leaves out an id its schema does not mark: «desactiva la tarifa», «quita el precio del champú» or
# «crea una regla para el grupo VIP» said no list, no price and no group. Now each record is named as the Price lists
# screens show it: a list and a rule by their name, a price by its article and its list, a product, a service, a category
# and a customer group by their names. Read as whoever asks, in the hub they ask in: never by the id, and left out when
# nobody, or somebody who may not see prices, is behind the request.

#: Every record a write of pricing names by its id: the data that name one, by write.
NAMED = {
    "pricing.price_item.add": ("price_list_id", "product_id", "service_id"),
    "pricing.price_item.remove": ("id", "price_list_id", "product_id", "service_id"),
    "pricing.price_item.update": ("id",),
    "pricing.price_list.activate": ("id",),
    "pricing.price_list.create": ("customer_group_id",),
    "pricing.price_list.deactivate": ("id",),
    "pricing.price_list.set_default": ("id",),
    "pricing.price_list.update": ("id", "customer_group_id"),
    "pricing.rule.activate": ("id",),
    "pricing.rule.create": ("category_id", "product_id", "service_id", "customer_group_id"),
    "pricing.rule.deactivate": ("id",),
    "pricing.rule.update": ("id", "category_id", "product_id", "service_id", "customer_group_id"),
}
#: Services is no requirement of pricing, and its tables stay out of a hub's database until each hub has its own staff
#: (``base/tenancy/tests/hubs.py``, ``portable_apps``): in a hub, every record but the service; the service, apart.
IN_A_HUB = {write: tuple(datum for datum in data if datum != "service_id") for write, data in NAMED.items()}
WITH_A_SERVICE = {write: ("service_id",) for write, data in NAMED.items() if "service_id" in data}
#: What each write sends besides its records, as the model would.
BESIDES = {"pricing.price_item.add": {"price": 1500}, "pricing.price_item.update": {"price": 1500}}
#: How the card titles each of those data in Spanish, as the screens do (the screen's own word for one it knows by its
#: name, ``id``, only when the schema titles it).
TITLED = {
    "price_list_id": "Tarifa",
    "product_id": "Producto",
    "service_id": "Servicio",
    "category_id": "Categoría",
    "customer_group_id": "Grupo de clientes",
}
TITLED_ID = {"price_list": "Tarifa", "price_item": "Precio", "rule": "Regla de descuento"}
#: How the card names each record of ``a_business``, as the Price lists screens show it.
SAID = {
    "price_list": "Mayoristas",
    "price_item": "Champú · Mayoristas",
    "rule": "Verano",
    "product_id": "Champú",
    "service_id": "Corte de pelo",
    "category_id": "Cuidado del cabello",
    "customer_group_id": "VIP",
}


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def no_id(card: dict) -> bool:
    return not AN_ID.search(json.dumps(card, ensure_ascii=False))


def references(op) -> set[str]:
    """The data of ``op``'s input its schema declares an id of (``format: uuid``)."""
    schema = op.input.model_json_schema()
    props = schema.get("properties", {})
    return {name for name, prop in props.items() if assistant._resolved(prop, schema.get("$defs", {})).get("format") == "uuid"}


def a_business(*, service: bool = False) -> dict:
    """What a salon's Price lists screens show: the list «Mayoristas» with a price of the shampoo, the rule «Verano», the
    product, the category «Cuidado del cabello», the customer group «VIP» and, with ``service``, the service «Corte de
    pelo»."""
    from .conftest import make_category, make_group, make_rule, make_service

    wholesale = make_list("MAYOR", "Mayoristas")
    shampoo = make_product("Champú", "CH-1")
    return {
        "price_list": wholesale,
        "price_item": make_item(wholesale, shampoo, price=1200),
        "rule": make_rule("VERANO", name="Verano"),
        "product_id": shampoo,
        "category_id": make_category("Cuidado del cabello"),
        "customer_group_id": make_group("VIP"),
        **({"service_id": make_service("Corte de pelo")} if service else {}),
    }


def whose(write: str, datum: str) -> str:
    """The record of ``a_business`` the datum ``datum`` of ``write`` names: its own (``id``) or another one."""
    return write.split(".")[1] if datum == "id" else "price_list" if datum == "price_list_id" else datum


def cards(business: dict, ctx, named: dict = IN_A_HUB, language: str = "es") -> dict:
    """The card of each write of ``named`` naming every record it names by its id, as ``ctx``'s person would confirm
    it."""
    return {
        write: assistant.card(
            get(write),
            {**{datum: str(business[whose(write, datum)].id) for datum in data}, **BESIDES.get(write, {})},
            language,
            ctx,
        )
        for write, data in named.items()
    }


def named_as_the_screens(named: dict = IN_A_HUB) -> dict:
    return {write: {**{datum: SAID[whose(write, datum)] for datum in data}, **BESIDES.get(write, {})} for write, data in named.items()}


def left_out(named: dict = IN_A_HUB) -> dict:
    return {write: BESIDES.get(write, {}) for write in named}


def test_every_record_a_write_of_pricing_names_by_its_id_is_listed_here():
    """Positive control of the tests below: a new reference of a write of pricing comes in here, with its name."""
    assert {op.name: references(op) for op in pricing_writes() if references(op)} == {
        write: set(data) for write, data in NAMED.items()
    }


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("role", WRITERS)
def test_a_write_of_pricing_names_each_record_as_the_price_lists_screens_do(role, hub_a, no_fallback):
    """«Desactiva la tarifa», «quita el precio del champú», «crea una regla para el grupo VIP»: the card says which list,
    price, rule, product, category or group as the Price lists screens show it, never by its id — for every role that
    may run the write."""
    with use_hub(hub_a):
        said = cards(a_business(), in_hub(hub_a, role))
    assert {write: values(card) for write, card in said.items()} == named_as_the_screens()
    assert [write for write, card in said.items() if not no_id(card)] == []


@pytest.mark.django_db
@pytest.mark.parametrize("role", WRITERS)
def test_a_write_of_pricing_names_the_service_as_services_does(role):
    """«Pon el corte de pelo a 15 en Mayoristas», «crea una regla del 10 % en el corte»: the service by the name Services
    gives it, read through Services' own read as the person (Services is no requirement of pricing)."""
    said = cards(a_business(service=True), ctx_for(role, language="es"), WITH_A_SERVICE)
    assert {write: values(card) for write, card in said.items()} == named_as_the_screens(WITH_A_SERVICE)
    assert all(no_id(card) for card in said.values())


@pytest.mark.django_db
def test_each_record_is_titled_as_its_screen_titles_it():
    """«Tarifa: Mayoristas», «Precio: Champú · Mayoristas», «Regla de descuento: Verano», never «Registro» or «Id»."""
    said = cards(a_business(service=True), ctx_for(language="es"), NAMED)
    assert {
        write: {field["name"]: card_title(field) for field in card["fields"] if field["name"] in NAMED[write]}
        for write, card in said.items()
    } == {
        write: {datum: TITLED_ID[write.split(".")[1]] if datum == "id" else TITLED[datum] for datum in data}
        for write, data in NAMED.items()
    }


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(("language", "from_ten"), [("es", "Champú · Mayoristas · desde 10"), ("en", "Champú · Mayoristas · from 10")])
def test_a_price_from_a_quantity_on_is_named_with_it(language, from_ten, hub_a, no_fallback):
    """The shampoo has two prices in «Mayoristas», by quantity: the card names the one it changes by its «Desde»."""
    with use_hub(hub_a):
        business = a_business()
        by_ten = make_item(business["price_list"], business["product_id"], price=1000, min_quantity="10")
        card = assistant.card(get("pricing.price_item.update"), {"id": str(by_ten.id), "price": 900}, language, ctx_for("hub_manager", scope=Scope("host", hub_a.slug), language=language))
    assert values(card)["id"] == from_ten


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_price_named_by_its_id_is_said_by_its_name_and_in_its_list_s_currency(hub_a, no_fallback):
    """Both marks on the price's id: the card names the price and says the new one in the currency of its list."""
    with use_hub(hub_a):
        card = price_change(a_price("USD"), in_hub(hub_a))
    assert values(card)["id"] == "Shampoo · DOLARES prices"
    assert priced(card) == {"kind": "money", "value": 1500, "money": {"currency": "USD", "decimals": 2}}


@pytest.fixture(params=["off", "absent"])
def services_unavailable(request, monkeypatch):
    """Services, which pricing does not require, off in the business or not installed."""
    if request.param == "absent":
        monkeypatch.delitem(registry, "service.service.get")
    else:

        def off(ctx, data):
            raise AppInactive("Services is off.")

        monkeypatch.setitem(registry, "service.service.get", dataclasses.replace(registry["service.service.get"], fn=off))


@pytest.mark.django_db
def test_without_services_the_card_leaves_the_service_out_and_names_the_rest(services_unavailable):
    business = a_business(service=True)
    said = cards(business, ctx_for(language="es"), {"pricing.price_item.add": NAMED["pricing.price_item.add"]})
    assert values(said["pricing.price_item.add"]) == {"price_list_id": "Mayoristas", "product_id": "Champú", "price": 1500}
    assert no_id(said["pricing.price_item.add"])


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_nobody_behind_the_request_reads_no_record_of_pricing(hub_a, no_fallback):
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    with use_hub(hub_a):
        said = cards(a_business(), None)
    assert {write: values(card) for write, card in said.items()} == left_out()
    assert all(no_id(card) for card in said.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_who_may_not_see_prices_reads_none_of_them_on_the_card(hub_a, no_fallback):
    """Whoever asks without «view prices» (a key that only changes them, say) gets every record left out, never its id;
    the product too, without Inventory's «view products»."""
    with use_hub(hub_a):
        said = cards(a_business(), in_hub(hub_a, permissions={"pricing.manage"}))
    assert {write: values(card) for write, card in said.items()} == left_out()
    assert all(no_id(card) for card in said.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_that_is_not_there_is_left_out_never_by_its_id(hub_a, no_fallback):
    with use_hub(hub_a):
        gone = {
            write: assistant.card(get(write), {**dict.fromkeys(data, str(uuid.uuid7())), **BESIDES.get(write, {})}, "es", in_hub(hub_a))
            for write, data in IN_A_HUB.items()
        }
    assert {write: values(card) for write, card in gone.items()} == left_out()
    assert all(no_id(card) for card in gone.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_of_hub_b_is_never_named_on_a_card_of_hub_a(hub_a, hub_b, no_fallback):
    """The read runs in the hub the person asks in: hub B's list, price, rule, product, category or group is nobody in
    hub A."""
    with use_hub(hub_b):
        theirs = a_business()
        named_in_b = cards(theirs, in_hub(hub_b))
    with use_hub(hub_a):
        said = cards(theirs, in_hub(hub_a))
    assert {write: values(card) for write, card in said.items()} == left_out()
    assert all(no_id(card) for card in said.values())
    # Positive control: in hub B the same cards name them.
    assert {write: values(card) for write, card in named_in_b.items()} == named_as_the_screens()


def test_whoever_may_run_a_write_reads_the_record_its_card_names():
    """The read runs as the person: a role that may run a write and not read what its card names would get a card with
    nothing to recognise, just in the common case. Every role a business gives, every write that names a record, and
    Services' read behind a service (pricing reads it as the person)."""
    unread: list[tuple[str, str, str]] = []
    checked = 0
    for role in ("hub_employee", *WRITERS):
        mine = ctx_for(role)
        for name, data in NAMED.items():
            op = get(name)
            if not mine.has(op.permission):
                continue
            schema = op.input.model_json_schema()
            for datum in data:
                checked += 1
                marked = assistant.refers_of(assistant._resolved(schema["properties"][datum], schema.get("$defs", {})))
                reads = [marked["read"], *(["service.service.get"] if datum == "service_id" else [])] if marked else []
                if not reads or not all(mine.has(registry[read].permission) for read in reads):
                    unread.append((role, name, datum))
    # Positive control: the employee runs none of them; the manager, the admin and the owner every one of the 25.
    assert checked == 25 * 3
    assert unread == []
