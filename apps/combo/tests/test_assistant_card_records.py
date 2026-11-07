"""FIX-HUB-COMBO-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#669): the card of a write of Menus and combos says which
menu, course, choice or product it acts on by its name, read as whoever asks, never by its id, and leaves it out when
that person may not read it or it is not there. A menu and a course go by their name and a choice by its product's
name, as the builder's «Withdraw» and «Remove» dialogs say them; a product by its name, as Inventory says it. The
datum that names one by its id is titled with the screens' word for it («Menú», «Plato», «Elección»), never «Registro».
"""

import dataclasses
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import INTERNAL, get, registry

from apps.combo.tests.conftest import A, ctx_for, make_combo, make_group, make_option, make_product
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

FRONTEND = Path(apps.get_app_config("combo").path) / "frontend/locale"

#: Each write of Menus and combos and the datum of it that names a menu by its id.
ON_A_MENU = [
    ("combo.combo.delete", "id"),
    ("combo.combo.set_image", "id"),
    ("combo.combo.update", "id"),
    ("combo.group.create", "combo_id"),
    ("combo.group.delete", "combo_id"),
    ("combo.group.reorder", "id"),
    ("combo.group.update", "combo_id"),
    ("combo.option.bulk_create", "combo_id"),
    ("combo.option.create", "combo_id"),
    ("combo.option.delete", "combo_id"),
    ("combo.option.reorder", "combo_id"),
    ("combo.option.update", "combo_id"),
]
#: Each one that names a course by its id.
ON_A_COURSE = [
    ("combo.group.delete", "id"),
    ("combo.group.update", "id"),
    ("combo.option.bulk_create", "group_id"),
    ("combo.option.create", "group_id"),
    ("combo.option.delete", "group_id"),
    ("combo.option.reorder", "group_id"),
    ("combo.option.update", "group_id"),
]
#: Each one that names a choice by its id.
ON_A_CHOICE = [
    ("combo.option.delete", "id"),
    ("combo.option.update", "id"),
]
#: Each one that names a product of Inventory by its id.
ON_A_PRODUCT = [
    ("combo.option.create", "product_id"),
    ("combo.option.update", "new_product_id"),
]
#: Each one that names several of them by their ids, all of them, and what they are.
ON_SEVERAL = [
    ("combo.group.reorder", "group_ids", "courses"),
    ("combo.option.bulk_create", "product_ids", "products"),
    ("combo.option.reorder", "option_ids", "choices"),
]


def screens(language: str) -> dict:
    return json.loads((FRONTEND / f"{language}.json").read_text())["combo"]


def words(language: str) -> dict[str, str]:
    """What the Menus screens call each record, in ``language``: a menu as its list calls one, a course as its form's
    title, the choices and the courses as the builder's headings; a product as Inventory's screens and «Añadir varios»
    call it."""
    said = screens(language)
    return {
        "menu": said["menus"]["entity"]["one"].capitalize(),
        "course": said["courseForm"]["titleEdit"].split(" · ")[0],
        "choice": {"en": "Choice", "es": "Elección"}[language],
        "product": {"en": "Product", "es": "Producto"}[language],
        "new_product": {"en": "New product", "es": "Producto nuevo"}[language],
        "courses": said["courses"]["title"],
        "choices": said["choices"]["title"],
        "products": {"en": "Products", "es": "Productos"}[language],
    }


#: The word the card calls each datum by, as ``words`` names it.
TITLES = {
    **{case: "menu" for case in ON_A_MENU},
    **{case: "course" for case in ON_A_COURSE},
    **{case: "choice" for case in ON_A_CHOICE},
    ("combo.option.create", "product_id"): "product",
    ("combo.option.update", "new_product_id"): "new_product",
    **{(write, datum): kind for write, datum, kind in ON_SEVERAL},
}


@dataclasses.dataclass
class Menu:
    """A menu with a course and a choice in it, every datum that could name each one filled: the menu's kitchen name,
    the product's SKU, barcode and description, so the card that says a name says it by its name and no other datum."""

    combo: object
    course: object
    choice: object
    product: object


def make_menu(
    name: str = "Menú del día",
    course: str = "Primeros",
    dish: str = "Lentejas",
    code: str = "LEN-01",
    ean13: str = "8410000000017",
) -> Menu:
    product = make_product(dish, sku=code, ean13=ean13, description=f"{dish} de la casa")
    combo = make_combo(name, kitchen_name=f"COCINA {name.upper()}")
    group = make_group(combo, course)
    return Menu(combo, group, make_option(group, product), product)


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


def id_of(menu: Menu, write: str, datum: str) -> str:
    """The id ``datum`` of ``write`` names in ``menu``."""
    if (write, datum) in ON_A_MENU:
        return str(menu.combo.id)
    if (write, datum) in ON_A_COURSE:
        return str(menu.course.id)
    if (write, datum) in ON_A_CHOICE:
        return str(menu.choice.id)
    return str(menu.product.id)


def name_of(menu: Menu, write: str, datum: str) -> str:
    """What the card says for it: the menu's and the course's name, the product's name for a choice or a product."""
    if (write, datum) in ON_A_MENU:
        return menu.combo.name
    if (write, datum) in ON_A_COURSE:
        return menu.course.name
    return menu.product.name


# ── A menu, a course, a choice and a product by their names ───────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_MENU + ON_A_COURSE + ON_A_CHOICE + ON_A_PRODUCT)
def test_a_write_says_the_record_it_names_by_its_name(write, datum):
    """The case the issue names, «combo.combo.delete:id»: «Menu: Menú del día», never its id nor its kitchen name; a
    course by its name, a choice and a product by the product's name, never its SKU."""
    menu = make_menu()
    assert shown(write, {datum: id_of(menu, write, datum)})[datum] == name_of(menu, write, datum)


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names():
    """Each id names its own record, never another one of the business (the first, the last)."""
    menus = [make_menu(), make_menu("Menú infantil", "Segundos", "Croquetas", "CRO-02", "8410000000024")]
    for listed in (menus, list(reversed(menus))):
        for write, datum in ON_A_MENU + ON_A_COURSE + ON_A_CHOICE + ON_A_PRODUCT:
            said = [shown(write, {datum: id_of(menu, write, datum)})[datum] for menu in listed]
            assert said == [name_of(menu, write, datum) for menu in listed], f"{write}:{datum}"


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum", "kind"), ON_SEVERAL)
def test_the_records_a_write_puts_in_order_are_said_by_their_names_in_that_order(write, datum, kind):
    """«Courses: Segundos, Primeros»: each one by its name, in the order sent, said in words (``named``) — never «2
    items» of an empty line."""
    combo = make_combo("Menú del día", kitchen_name="COCINA MENU DIA")
    first, second = make_group(combo, "Primeros"), make_group(combo, "Segundos")
    lentils = make_product("Lentejas", sku="LEN-01", ean13="8410000000017", description="Lentejas de la casa")
    soup = make_product("Sopa", sku="SOP-02", ean13="8410000000031", description="Sopa de la casa")
    choices = [make_option(first, lentils), make_option(first, soup)]
    records = {
        "courses": ([second, first], ["Segundos", "Primeros"]),
        "choices": (list(reversed(choices)), ["Sopa", "Lentejas"]),
        "products": ([soup, lentils], ["Sopa", "Lentejas"]),
    }[kind]
    field = fields_of(write, {datum: [str(record.id) for record in records[0]]})[datum]
    assert (field["value"], field.get("named")) == (records[1], True)


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(("write", "datum"), list(TITLES))
def test_the_record_a_write_names_is_titled_with_the_screens_word_in_each_language(write, datum, language):
    """The datum that names a record goes under the screens' word for it, never «Record» nor «Id»: «Menú» for the menu
    a course is added to or withdrawn, «Plato» for a course, «Elección» for a choice."""
    menu = make_menu()
    several = {"group_ids": menu.course, "option_ids": menu.choice, "product_ids": menu.product}
    sent = [str(several[datum].id)] if datum in several else id_of(menu, write, datum)
    field = fields_of(write, {datum: sent}, language)[datum]
    assert field["label"] == words(language)[TITLES[(write, datum)]]


@pytest.mark.django_db
def test_a_change_keeps_saying_the_record_beside_what_it_changes():
    """The name is the record's as it is now, before the write runs: a rename says the old name under «Menu» and the
    new one under its own datum; a choice changed for another product says both."""
    menu = make_menu()
    assert shown("combo.combo.update", {"id": str(menu.combo.id), "name": "Menú de noche"}) == {
        "id": "Menú del día",
        "name": "Menú de noche",
    }
    soup = make_product("Sopa", sku="SOP-02", ean13="8410000000031", description="Sopa de la casa")
    assert shown("combo.option.update", {"id": str(menu.choice.id), "new_product_id": str(soup.id)}) == {
        "id": "Lentejas",
        "new_product_id": "Sopa",
    }


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_MENU + ON_A_COURSE + ON_A_CHOICE)
def test_a_menu_course_or_choice_is_left_out_for_whoever_may_not_see_the_menus(write, datum):
    """Whoever may not see the menus (``combo.view``) is told no menu, course nor choice, never its id."""
    menu = make_menu()
    arguments = {datum: id_of(menu, write, datum)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("combo.view"))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_PRODUCT)
def test_a_product_is_left_out_for_whoever_may_not_see_the_products(write, datum):
    """Whoever may not see Inventory's products (``inventory.view_product``) is told no product, never its id."""
    menu = make_menu()
    arguments = {datum: id_of(menu, write, datum)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("inventory.view_product"))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_MENU + ON_A_COURSE + ON_A_CHOICE + ON_A_PRODUCT)
def test_what_does_not_exist_is_left_out(write, datum):
    said = shown(write, {datum: A_MISSING_ID})
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_a_record_removed_meanwhile_is_left_out():
    """A choice, a course or a menu the builder removed is no longer there for the card either."""
    menu = make_menu()
    checks = [
        ("combo.option.delete", "id", menu.choice),
        ("combo.group.delete", "id", menu.course),
        ("combo.combo.delete", "id", menu.combo),
    ]
    for write, datum, record in checks:
        assert datum in shown(write, {datum: str(record.id)}), write  # positive control
    for write, datum, record in checks:
        record.delete()
        assert shown(write, {datum: str(record.id)}) == {}, write


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    menu = make_menu()
    card = assistant.card(get("combo.combo.update"), {"id": str(menu.combo.id), "name": "Menú de noche"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"name": "Menú de noche"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        menu = make_menu()
        records = [
            ("combo.combo.delete", "id", menu.combo),
            ("combo.group.delete", "id", menu.course),
            ("combo.option.delete", "id", menu.choice),
            ("combo.option.create", "product_id", menu.product),
        ]
        for write, datum, record in records:  # positive control
            assert datum in shown(write, {datum: str(record.id)}, ctx=in_a), write
    with use_hub(hub_b):
        for write, datum, record in records:
            assert datum not in shown(write, {datum: str(record.id)}, ctx=in_b), write


# ── The read that names a course ──────────────────────────────────────────────────────────────────────────────────────


def test_the_read_that_names_a_course_is_no_tool_route_nor_live_query():
    """``combo.group.get`` exists for the card alone: the model reads the courses with their menu, the screens and the
    API read the menu; so it is no tool of the assistant (``INTERNAL``) nor a route of the API."""
    read = registry["combo.group.get"]
    assert (read.kind, read.permission, read.ai, read.expose_api) == ("query", "combo.view", INTERNAL, False)


@pytest.mark.django_db
def test_the_read_that_names_a_course_finds_it_by_its_id_or_its_name_in_its_menu():
    menu, other = make_menu(), make_menu("Menú infantil", "Primeros", "Croquetas", "CRO-02", "8410000000024")
    read = get("combo.group.get")
    found = read(ctx_for("hub_employee"), read.input(id=menu.course.id))
    assert (found.id, found.combo_id, found.name) == (menu.course.id, menu.combo.id, "Primeros")
    assert [option.product_name for option in found.options] == ["Lentejas"]
    by_name = read(ctx_for(), read.input(combo="Menú infantil", group="Primeros"))
    assert by_name.id == other.course.id
