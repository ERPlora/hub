"""FIX-HUB-KITCHEN-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#671): the card of a write of Kitchen says which ticket,
dish, station, product, category, check or line of a check it acts on by its name, read as whoever asks, never by
its id, and leaves it out when that person may not read it or it is not there. A ticket goes by its number, as the
«Cancel ticket …?» dialog and the ticket's sheet say it; a dish and a station by their names, as the board and the
stations' «Delete …?» dialog say them; a product and a category by their names, as Inventory says them; a check of
Sales by its title (else its amount) and its line by the dish on it, as Sales says them. The type of a ticket sent
or received is said by its label («Para llevar»), never by its code.
"""

import dataclasses
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import INTERNAL, get, registry

from apps.kitchen.tests.conftest import A, add_line, ctx_for, make_station, open_check, run
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

FRONTEND = Path(apps.get_app_config("kitchen").path) / "frontend/locale"

#: Each write of Kitchen that names a ticket by its id.
ON_A_TICKET = [
    (write, "ticket_id")
    for write in (
        "kitchen.item.bump",
        "kitchen.item.recall",
        "kitchen.ticket.cancel",
        "kitchen.ticket.delete",
        "kitchen.ticket.ready",
        "kitchen.ticket.recall",
        "kitchen.ticket.reprint",
        "kitchen.ticket.serve",
        "kitchen.ticket.set_rush",
        "kitchen.ticket.start",
    )
]
#: Each one that names a station by its id.
ON_A_STATION = [
    ("kitchen.routing.set", "station_id"),
    ("kitchen.station.delete", "station_id"),
    ("kitchen.station.update", "station_id"),
]
#: Each one that names a product of Inventory by its id.
ON_A_PRODUCT = [("kitchen.routing.clear", "product_id"), ("kitchen.routing.set", "product_id")]
#: Each one that names a category of Inventory by its id.
ON_A_CATEGORY = [("kitchen.routing.clear", "category_id"), ("kitchen.routing.set", "category_id")]
#: Each one that names a check of Sales by its id.
ON_A_CHECK = [("kitchen.ticket.receive", "order_id"), ("kitchen.ticket.send", "order_id")]
#: Each one that names dishes of a ticket by their ids.
ON_DISHES = [("kitchen.item.bump", "item_ids"), ("kitchen.item.recall", "item_ids")]
ON_ONE = ON_A_TICKET + ON_A_STATION + ON_A_PRODUCT + ON_A_CATEGORY + ON_A_CHECK


def screens(language: str) -> dict:
    return json.loads((FRONTEND / f"{language}.json").read_text())["kitchen"]


def words(language: str) -> dict[str, str]:
    """What the Kitchen screens call each record, in ``language``: a ticket and a station as their lists call one, the
    dishes as the ticket's form; a check, a product and a category as Sales and Inventory call them."""
    said = screens(language)
    return {
        "ticket": said["tickets"]["entity"]["one"].capitalize(),
        "station": said["stations"]["entity"]["one"].capitalize(),
        "dishes": said["form"]["dishes"],
        "check": {"en": "Check", "es": "Cuenta"}[language],
        "product": {"en": "Product", "es": "Producto"}[language],
        "category": {"en": "Category", "es": "Categoría"}[language],
    }


#: The word the card calls each datum by, as ``words`` names it.
TITLES = {
    **{case: "ticket" for case in ON_A_TICKET},
    **{case: "station" for case in ON_A_STATION},
    **{case: "product" for case in ON_A_PRODUCT},
    **{case: "category" for case in ON_A_CATEGORY},
    **{case: "check" for case in ON_A_CHECK},
    **{case: "dishes" for case in ON_DISHES},
    ("kitchen.ticket.create", "items"): "dishes",
    ("kitchen.ticket.receive", "items"): "dishes",
}


@dataclasses.dataclass
class Kitchen:
    """A ticket made by hand with two dishes, a station, a product and a category routed to it, and an open check of
    Sales with a line: every datum that could name each one filled (the ticket's label and notes, each dish's note,
    the station's printer, the product's SKU, barcode and description), so the card that says a name says it by its
    name and no other datum."""

    ticket: object
    dishes: list
    station: object
    product: object
    category: object
    check: object
    line: object


def make_kitchen(
    label: str = "Mesa 4",
    dish: str = "Tortilla",
    station: str = "Plancha",
    product: str = "Hamburguesa",
    code: str = "HAM-01",
    ean13: str = "8410000000017",
    category: str = "Principales",
    check: str = "Terraza 2",
) -> Kitchen:
    system = ctx_for()
    found = run("inventory.category.create", {"name": category}, system)
    made = run(
        "inventory.product.create",
        {
            "name": product,
            "sku": code,
            "ean13": ean13,
            "description": f"{product} de la casa",
            "price": 1200,
            "tax_category_key": "restaurant.food",
        },
        system,
    )
    grill = make_station(station, printer_name=f"Impresora {station}", color="#F97316")
    ticket = run(
        "kitchen.ticket.create",
        {
            "label": label,
            "notes": f"Notas de {label}",
            "items": [
                {"name": dish, "notes": f"{dish} sin cebolla"},
                {"product_id": str(made.id), "notes": f"{product} poco hecha", "quantity": "2"},
            ],
        },
        system,
    )
    order = open_check(check)
    line = add_line(order.id, made).lines[-1]
    return Kitchen(ticket, list(ticket.items), grill, made, found, order, line)


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or ctx_for())
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def without(permission: str, scope: Scope = A) -> OperationContext:
    """An admin of ``scope`` without ``permission``: a combination no role has."""
    ctx = ctx_for(scope=scope)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - {permission})


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


def id_of(kitchen: Kitchen, write: str, datum: str) -> str:
    """The id ``datum`` of ``write`` names in ``kitchen``."""
    record = {
        "ticket_id": kitchen.ticket,
        "station_id": kitchen.station,
        "product_id": kitchen.product,
        "category_id": kitchen.category,
        "order_id": kitchen.check,
    }[datum]
    return str(record.id)


def name_of(kitchen: Kitchen, write: str, datum: str) -> str:
    """What the card says for it: the ticket's number, the station's, product's and category's names, the check's
    title."""
    return {
        "ticket_id": kitchen.ticket.number,
        "station_id": kitchen.station.name,
        "product_id": kitchen.product.name,
        "category_id": kitchen.category.name,
        "order_id": kitchen.check.label,
    }[datum]


# ── A ticket, a station, a product, a category and a check by their names ────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_ONE)
def test_a_write_says_the_record_it_names_by_its_name(write, datum):
    """The case the issue names, «kitchen.item.bump:ticket_id»: «Ticket: 20261014-0001», never its id nor its label;
    a station, a product and a category by their names, never the printer or the SKU; a check by its title."""
    kitchen = make_kitchen()
    assert shown(write, {datum: id_of(kitchen, write, datum)})[datum] == name_of(kitchen, write, datum)


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names():
    """Each id names its own record, never another one of the business (the first, the last)."""
    kitchens = [
        make_kitchen(),
        make_kitchen("Barra", "Croquetas", "Postres", "Tarta", "TAR-02", "8410000000024", "Postres", "Salón 1"),
    ]
    for listed in (kitchens, list(reversed(kitchens))):
        for write, datum in ON_ONE:
            said = [shown(write, {datum: id_of(kitchen, write, datum)})[datum] for kitchen in listed]
            assert said == [name_of(kitchen, write, datum) for kitchen in listed], f"{write}:{datum}"
        for write, datum in ON_DISHES:
            said = [shown(write, {datum: [str(kitchen.dishes[0].id)]})[datum] for kitchen in listed]
            assert said == [[kitchen.dishes[0].name] for kitchen in listed], f"{write}:{datum}"


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_DISHES)
def test_the_dishes_a_write_marks_are_said_by_their_names_in_that_order(write, datum):
    """«Dishes: Hamburguesa, Tortilla»: each one by its name, in the order sent, said in words (``named``), never its
    note — never «2 items» of an empty line."""
    kitchen = make_kitchen()
    tortilla, burger = kitchen.dishes
    field = fields_of(write, {datum: [str(burger.id), str(tortilla.id)]})[datum]
    assert (field["value"], field.get("named")) == (["Hamburguesa", "Tortilla"], True)


@pytest.mark.django_db
def test_the_dishes_of_a_round_sent_are_said_by_the_dish_on_each_line_of_the_check():
    """The round Sales fired, received by the kitchen: its check by its title and each line by the dish on it."""
    kitchen = make_kitchen()
    salad = run(
        "inventory.product.create",
        {"name": "Ensalada", "sku": "ENS-03", "price": 900, "tax_category_key": "restaurant.food"},
        ctx_for(),
    )
    salad = add_line(kitchen.check.id, salad).lines[-1]
    items = [{"order_item_id": str(salad.id)}, {"order_item_id": str(kitchen.line.id)}]
    field = fields_of("kitchen.ticket.receive", {"order_id": str(kitchen.check.id), "items": items})
    assert field["order_id"]["value"] == "Terraza 2"
    assert (field["items"]["value"], field["items"].get("named")) == (
        [{"order_item_id": "Ensalada"}, {"order_item_id": "Hamburguesa"}],
        True,
    )


@pytest.mark.django_db
def test_a_dish_made_by_hand_from_the_catalogue_is_said_by_its_product_beside_how_many():
    """A ticket made by hand: a product of the catalogue by its name, beside its quantity (hub#970), never its id."""
    kitchen = make_kitchen()
    field = fields_of("kitchen.ticket.create", {"items": [{"product_id": str(kitchen.product.id), "quantity": "2"}]})
    assert (field["items"]["value"], field["items"].get("named")) == ([{"product_id": "Hamburguesa", "quantity": "2"}], True)


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(("write", "datum"), list(TITLES))
def test_the_record_a_write_names_is_titled_with_the_screens_word_in_each_language(write, datum, language):
    """The datum that names a record goes under the screens' word for it, never «Record» nor «Id»: «Comanda» for a
    ticket, «Estación» for a station, «Platos» for its dishes, «Cuenta» for a check of Sales."""
    kitchen = make_kitchen()
    sent = {
        ("kitchen.ticket.create", "items"): [{"product_id": str(kitchen.product.id), "quantity": "2"}],
        ("kitchen.ticket.receive", "items"): [{"order_item_id": str(kitchen.line.id)}],
    }.get((write, datum))
    if sent is None:
        sent = [str(kitchen.dishes[0].id)] if datum == "item_ids" else id_of(kitchen, write, datum)
    field = fields_of(write, {datum: sent}, language)[datum]
    assert field["label"] == words(language)[TITLES[(write, datum)]]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "title", "types"),
    [
        ("en", "Ticket type", ["Dine in", "Takeaway", "Delivery"]),
        ("es", "Tipo de comanda", ["En sala", "Para llevar", "A domicilio"]),
    ],
)
@pytest.mark.parametrize("write", ["kitchen.ticket.send", "kitchen.ticket.receive"])
def test_the_type_of_a_round_is_said_by_its_label_never_its_code(write, language, title, types):
    """«Tipo de comanda: Para llevar», as the ticket's card and the till say it, never «takeaway»."""
    kitchen = make_kitchen()
    for code, said in zip(("dine_in", "takeaway", "delivery"), types, strict=True):
        field = fields_of(write, {"order_id": str(kitchen.check.id), "channel": code}, language)["channel"]
        assert (field["label"], field["value"]) == (title, said)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "said"), [("en", ["Normal", "Rush", "VIP"]), ("es", ["Normal", "Urgente", "VIP"])]
)
def test_the_priority_of_a_round_received_is_said_by_its_label_never_its_code(language, said):
    """The round Sales fired, urgent or not: «Prioridad: Urgente», as the ticket's card says it, never «rush»."""
    kitchen = make_kitchen()
    for code, label in zip(("normal", "rush", "vip"), said, strict=True):
        arguments = {"order_id": str(kitchen.check.id), "priority": code}
        assert shown("kitchen.ticket.receive", arguments, language)["priority"] == label


@pytest.mark.django_db
def test_a_change_keeps_saying_the_record_beside_what_it_changes():
    """The name is the record's as it is now, before the write runs: a rename says the old name under «Station» and the
    new one under its own datum."""
    kitchen = make_kitchen()
    assert shown("kitchen.station.update", {"station_id": str(kitchen.station.id), "name": "Horno"}) == {
        "station_id": "Plancha",
        "name": "Horno",
    }


# ── A round of Sales the kitchen has not saved yet ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_round_not_saved_yet_is_said_by_its_number_and_its_dishes_by_their_names(product):
    """A round the till just fired, before the kitchen saved it: the board already shows it, so the card names it by
    the number it will have and each dish by its name, as the board does."""
    from apps.kitchen.tests.conftest import fire

    order = open_check("Mesa 9")
    add_line(order.id, product("Paella", sku="PAE-01"))
    fire(order.id)
    board = run("kitchen.ticket.board", {})
    (view,) = [ticket for ticket in board.cooking if ticket.label == "Mesa 9"]
    assert view.saved is False  # positive control: the round is not saved yet
    said = shown("kitchen.item.bump", {"ticket_id": str(view.id), "item_ids": [str(view.items[0].id)]})
    assert said == {"ticket_id": view.number, "item_ids": ["Paella"]}


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


#: The permission without which the card says nothing of each kind of record.
READ_BY = {
    "ticket_id": "kitchen.view_ticket",
    "station_id": "kitchen.view_ticket",
    "product_id": "inventory.view_product",
    "category_id": "inventory.view_category",
    "order_id": "sale.view_sale",
}


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_ONE)
def test_a_record_is_left_out_for_whoever_may_not_read_it(write, datum):
    """Whoever may not see the tickets (``kitchen.view_ticket``), Inventory's products or categories, or Sales' checks
    is told no record, never its id."""
    kitchen = make_kitchen()
    arguments = {datum: id_of(kitchen, write, datum)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without(READ_BY[datum]))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_the_dishes_are_left_out_for_whoever_may_not_see_the_tickets_and_a_line_for_whoever_may_not_see_the_sales():
    kitchen = make_kitchen()
    dishes = {"item_ids": [str(kitchen.dishes[0].id)]}
    lines = {"items": [{"order_item_id": str(kitchen.line.id)}]}
    assert shown("kitchen.item.bump", dishes)["item_ids"] == ["Tortilla"]  # positive control
    assert shown("kitchen.ticket.receive", lines)["items"] == [{"order_item_id": "Hamburguesa"}]  # positive control
    for write, arguments, permission, name in (
        ("kitchen.item.bump", dishes, "kitchen.view_ticket", "Tortilla"),
        ("kitchen.ticket.receive", lines, "sale.view_sale", "Hamburguesa"),
    ):
        said = shown(write, arguments, ctx=without(permission))
        assert no_id(said), write
        assert name not in str(said), write


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_ONE)
def test_what_does_not_exist_is_left_out(write, datum):
    said = shown(write, {datum: A_MISSING_ID})
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_a_dish_that_does_not_exist_is_left_out():
    """The list still says how many it carries; the dish it cannot name is none of them."""
    assert shown("kitchen.item.bump", {"item_ids": [A_MISSING_ID]}) == {"item_ids": [None]}


@pytest.mark.django_db
def test_a_record_removed_meanwhile_is_left_out():
    """A ticket or a station deleted is no longer there for the card either, nor the dishes of that ticket."""
    kitchen = make_kitchen()
    ticket, station = str(kitchen.ticket.id), str(kitchen.station.id)
    dish = [str(kitchen.dishes[0].id)]
    assert shown("kitchen.ticket.serve", {"ticket_id": ticket}) == {"ticket_id": kitchen.ticket.number}  # control
    assert shown("kitchen.station.delete", {"station_id": station}) == {"station_id": "Plancha"}  # control
    assert shown("kitchen.item.bump", {"item_ids": dish}) == {"item_ids": ["Tortilla"]}  # control
    run("kitchen.ticket.delete", {"ticket_id": ticket})
    run("kitchen.station.delete", {"station_id": station})
    assert shown("kitchen.ticket.serve", {"ticket_id": ticket}) == {}
    assert shown("kitchen.station.delete", {"station_id": station}) == {}
    assert shown("kitchen.item.bump", {"item_ids": dish}) == {"item_ids": [None]}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    kitchen = make_kitchen()
    card = assistant.card(get("kitchen.station.update"), {"station_id": str(kitchen.station.id), "name": "Horno"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"name": "Horno"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        ticket = run("kitchen.ticket.create", {"label": "Mesa 4", "items": [{"name": "Tortilla"}]}, in_a)
        station = make_station("Plancha")
        records = [
            ("kitchen.ticket.serve", "ticket_id", str(ticket.id), ticket.number),
            ("kitchen.station.delete", "station_id", str(station.id), "Plancha"),
            ("kitchen.item.bump", "item_ids", [str(ticket.items[0].id)], ["Tortilla"]),
        ]
        for write, datum, sent, name in records:  # positive control
            assert shown(write, {datum: sent}, ctx=in_a)[datum] == name, write
    with use_hub(hub_b):
        for write, datum, sent, _ in records:
            assert no_id(shown(write, {datum: sent}, ctx=in_b)), write
            assert shown(write, {datum: sent}, ctx=in_b).get(datum) in (None, [None]), write


# ── The reads that name a station and a dish ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["kitchen.station.get", "kitchen.item.get"])
def test_the_reads_that_name_a_station_or_a_dish_are_no_tool_route_nor_live_query(name):
    """They exist for the card alone: the model reads the stations from their list and the dishes with their ticket,
    the screens and the API too; so they are no tool of the assistant (``INTERNAL``) nor a route of the API."""
    read = registry[name]
    assert (read.kind, read.permission, read.ai, read.expose_api) == ("query", "kitchen.view_ticket", INTERNAL, False)


@pytest.mark.django_db
def test_the_read_that_names_a_station_finds_it_by_its_id_or_its_name():
    grill, oven = make_station("Plancha"), make_station("Horno")
    read = get("kitchen.station.get")
    for station in (grill, oven, grill):
        found = read(ctx_for("hub_employee"), read.input(station_id=station.id))
        assert (found.id, found.name) == (station.id, station.name)
    assert read(ctx_for(), read.input(station="horno")).id == oven.id


@pytest.mark.django_db
def test_the_read_that_names_a_dish_finds_the_one_its_id_names():
    kitchens = [make_kitchen(), make_kitchen("Barra", "Croquetas", "Postres", "Tarta", "TAR-02", "8410000000024")]
    read = get("kitchen.item.get")
    for kitchen in (*kitchens, *reversed(kitchens)):
        for dish in kitchen.dishes:
            found = read(ctx_for("hub_employee"), read.input(id=dish.id))
            assert (found.id, found.name, found.notes) == (dish.id, dish.name, dish.notes)
