"""The assistant's card for a write of modifier (FIX-HUB-MODIFIER-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Modifiers screens give it, never by the title pydantic makes
up from the field («Option», «Tax Category Key»). The card is base's (``base.assistant.card``); the names are
modifier's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import get, registry

from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID, unnamed

from .conftest import GENERIC, ctx_for, run

FRONTEND = Path(apps.get_app_config("modifier").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["modifier"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["modifier"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def modifier_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "modifier" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_modifier_reaches_a_spanish_card_by_its_technical_name():
    """Every write of modifier the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = modifier_writes()
    assert len(writes) >= 8  # positive control: the registry has modifier's writes (not the platform's own)
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_option_said_by_its_name_as_the_group_sheet_does():
    """Changing or deleting an option the person names («Sin cebolla»): «Opción», as «Borrar opción» says it."""
    for name in ("modifier.option.update", "modifier.option.delete"):
        assert labels(assistant.card(get(name), {"option": "Sin cebolla"}, "es")) == ["Opción"]
        assert labels(assistant.card(get(name), {"option": "No onion"}, "en")) == ["Option"]


def test_the_card_names_the_own_tax_category_of_an_option_as_its_form_does():
    """An option that taxes differently from the dish: the option form's «Categoría fiscal propia»."""
    tax, tax_en = SCREENS["options"]["form"]["tax"], SCREENS_EN["options"]["form"]["tax"]
    for name in ("modifier.option.create", "modifier.option.update"):
        arguments = {"tax_category_key": "product.generic"}
        assert labels(assistant.card(get(name), arguments, "es")) == [tax]
        assert labels(assistant.card(get(name), arguments, "en")) == [tax_en]


# ── The records a write names by their id (hub#672) ──────────────────────────────────────────────────────────────────

#: What each write of modifier names by its id, and which record that is.
NAMED = {
    "modifier.group.update": {"id": "group"},
    "modifier.group.delete": {"id": "group"},
    "modifier.option.create": {"group_id": "group"},
    "modifier.option.update": {"id": "option", "group_id": "group"},
    "modifier.option.delete": {"id": "option", "group_id": "group"},
    "modifier.link.attach": {"group_id": "group", "product_id": "product", "category_id": "category"},
    "modifier.link.detach": {"id": "link", "group_id": "group", "product_id": "product", "category_id": "category"},
}
#: How the card names each record of ``a_menu``.
SAID = {
    "group": "Salsas",
    "option": "Ali oli (Salsas)",
    "link": "Salsas · Hamburguesa",
    "product": "Hamburguesa",
    "category": "Entrantes",
}
TITLES = {
    "es": {"group": "Grupo", "option": "Opción", "link": "Se aplica a", "product": "Producto", "category": "Categoría"},
    "en": {"group": "Group", "option": "Option", "link": "Applies to", "product": "Product", "category": "Category"},
}
#: The roles a business gives that run modifier's writes.
ROLES = ("hub_manager", "hub_admin", "hub_owner")


def references(op) -> set[str]:
    """The data of ``op``'s input its schema declares an id of (``format: uuid``)."""
    schema = op.input.model_json_schema()
    props = schema.get("properties", {})
    return {name for name, prop in props.items() if assistant._resolved(prop, schema.get("$defs", {})).get("format") == "uuid"}


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def no_id(card: dict) -> bool:
    return not AN_ID.search(json.dumps(card, ensure_ascii=False))


def in_hub(hub, role: str = "hub_admin", language: str = "es") -> OperationContext:
    return ctx_for(role, scope=Scope("host", hub.slug), language=language)


def a_menu(hub) -> dict:
    """What the Modifiers screens of a restaurant show: the group «Salsas», its option «Ali oli», applied to the product
    «Hamburguesa», and the category «Entrantes». Made with each app's own operations."""
    admin = in_hub(hub)
    product = run(
        "inventory.product.create", {"name": "Hamburguesa", "sku": "HAM", "price": 800, "tax_category_key": GENERIC}, ctx=admin
    )
    category = run("inventory.category.create", {"name": "Entrantes"}, ctx=admin)
    group = run("modifier.group.create", {"name": "Salsas"}, ctx=admin)
    option = run("modifier.option.create", {"group_id": str(group.id), "name": "Ali oli"}, ctx=admin)
    link = run("modifier.link.attach", {"group_id": str(group.id), "product_id": str(product.id)}, ctx=admin)
    return {"group": group.id, "option": option.id, "link": link.id, "product": product.id, "category": category.id}


def cards(menu: dict, ctx: OperationContext | None, language: str = "es") -> dict:
    """The card of each write of ``NAMED`` naming every record it names by its id, as ``ctx``'s person would confirm it."""
    return {
        write: assistant.card(get(write), {datum: str(menu[kind]) for datum, kind in data.items()}, language, ctx)
        for write, data in NAMED.items()
    }


def named_as_the_screens() -> dict:
    return {write: {datum: SAID[kind] for datum, kind in data.items()} for write, data in NAMED.items()}


def left_out() -> dict:
    return dict.fromkeys(NAMED, {})


def test_every_record_a_write_of_modifier_names_by_its_id_is_listed_here():
    """Positive control of the tests below: a new reference of a write of modifier comes in here, with its name."""
    assert {op.name: references(op) for op in modifier_writes() if references(op)} == {
        write: set(data) for write, data in NAMED.items()
    }
    assert {op.name: unnamed(op)[0] for op in modifier_writes() if unnamed(op)[0]} == {}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_write_of_modifier_names_each_record_as_its_screens_do(language, hub_a, no_fallback):
    """«Borra el grupo», «quita ese suplemento de la hamburguesa»: the card says which group, option, link, product or
    category by its name, in the person's language, never by its id."""
    with use_hub(hub_a):
        shown = cards(a_menu(hub_a), in_hub(hub_a, language=language), language)
    assert {write: values(card) for write, card in shown.items()} == named_as_the_screens()
    assert [write for write, card in shown.items() if not no_id(card)] == []


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_each_record_is_titled_as_the_screens_title_it(language, hub_a, no_fallback):
    """«Grupo: Salsas», «Opción: Ali oli (Salsas)», never «Id: Salsas»: the mark alone would name it under its field."""
    with use_hub(hub_a):
        shown = cards(a_menu(hub_a), in_hub(hub_a, language=language), language)
    assert {write: {field["name"]: field["label"] for field in card["fields"]} for write, card in shown.items()} == {
        write: {datum: TITLES[language][kind] for datum, kind in data.items()} for write, data in NAMED.items()
    }


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_nobody_behind_the_request_reads_no_record_of_modifier(hub_a, no_fallback):
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    with use_hub(hub_a):
        shown = cards(a_menu(hub_a), None)
    assert {write: values(card) for write, card in shown.items()} == left_out()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_who_may_not_see_them_reads_none_of_them_on_the_card(hub_a, no_fallback):
    """Whoever may keep the modifiers but see neither them nor the catalogue (a key that only writes, say) gets every
    record left out, never its id."""
    writes_only = OperationContext(
        scope=Scope("host", hub_a.slug), actor="key", permissions=frozenset({"modifier.manage"}), language="es"
    )
    with use_hub(hub_a):
        shown = cards(a_menu(hub_a), writes_only)
    assert {write: values(card) for write, card in shown.items()} == left_out()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_that_is_not_there_is_left_out_never_by_its_id(hub_a, no_fallback):
    gone = {kind: uuid.uuid7() for kind in SAID}
    with use_hub(hub_a):
        shown = cards(gone, in_hub(hub_a))
    assert {write: values(card) for write, card in shown.items()} == left_out()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_of_hub_b_is_never_named_on_a_card_of_hub_a(hub_a, hub_b, no_fallback):
    """The read runs in the hub the person asks in: hub B's group, option, link, product or category is nobody in hub A."""
    with use_hub(hub_b):
        theirs = a_menu(hub_b)
        named_in_b = cards(theirs, in_hub(hub_b))
    with use_hub(hub_a):
        shown = cards(theirs, in_hub(hub_a))
    assert {write: values(card) for write, card in shown.items()} == left_out()
    assert all(no_id(card) for card in shown.values())
    # Positive control: in hub B the same cards name them.
    assert {write: values(card) for write, card in named_in_b.items()} == named_as_the_screens()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_two_options_with_one_name_are_told_apart_by_their_group(hub_a, no_fallback):
    """«Grande» of the drinks and «Grande» of the chips: whoever confirms deleting one sees which, as the question the
    assistant asks when the name alone is not enough says it."""
    with use_hub(hub_a):
        admin = in_hub(hub_a)
        drinks = run("modifier.group.create", {"name": "Bebidas"}, ctx=admin)
        chips = run("modifier.group.create", {"name": "Patatas"}, ctx=admin)
        of_drinks = run("modifier.option.create", {"group_id": str(drinks.id), "name": "Grande"}, ctx=admin)
        of_chips = run("modifier.option.create", {"group_id": str(chips.id), "name": "Grande"}, ctx=admin)
        said = [
            values(assistant.card(get("modifier.option.delete"), {"id": str(option.id)}, "es", admin))["id"]
            for option in (of_drinks, of_chips)
        ]
    assert said == ["Grande (Bebidas)", "Grande (Patatas)"]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_link_to_a_category_is_named_by_its_group_and_that_category(hub_a, no_fallback):
    with use_hub(hub_a):
        admin = in_hub(hub_a)
        category = run("inventory.category.create", {"name": "Postres"}, ctx=admin)
        group = run("modifier.group.create", {"name": "Toppings"}, ctx=admin)
        link = run("modifier.link.attach", {"group_id": str(group.id), "category_id": str(category.id)}, ctx=admin)
        card = assistant.card(get("modifier.link.detach"), {"id": str(link.id)}, "es", admin)
    assert values(card) == {"id": "Toppings · Postres"}


def test_whoever_may_run_a_write_reads_the_record_its_card_names():
    """The read runs as the person: a role that may run a write and not read what its card names would get a card with
    nothing to recognise, just in the common case. Every role a business gives, every write that names a record."""
    unread: list[tuple[str, str, str]] = []
    checked = 0
    for role in ROLES:
        mine = ctx_for(role)
        for name, data in NAMED.items():
            op = get(name)
            assert mine.has(op.permission)
            schema = op.input.model_json_schema()
            for datum in data:
                checked += 1
                marked = assistant.refers_of(assistant._resolved(schema["properties"][datum], schema.get("$defs", {})))
                if marked is None or not mine.has(registry[marked["read"]].permission):
                    unread.append((role, name, datum))
    # Positive control: 3 roles over the 14 records of ``NAMED``.
    assert checked == 3 * sum(len(data) for data in NAMED.values())
    assert unread == []
