"""hub#670: the card of a write of Demo says which item it acts on by its name, read as whoever asks, never by its id,
and leaves it out when that person may not read it or it is not there. An item goes by its name, as its list and its
«Delete» dialog say it; its status by its label in each language, as the list's «Open» / «Done».
"""

import dataclasses
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import get, registry

from apps.demo.models import Item
from apps.demo.schemas import AN_ITEM_BY_NAME
from apps.demo.tests.conftest import A, ctx_for
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import technical_names
from base.tests.test_assistant_card_values import AN_ID
from base.tests.test_assistant_yes_for_its_card import unless_marked, yes_to_its_card
from base.tests.test_services_assistant import asked, call

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"
SCREENS = {
    language: json.loads((Path(apps.get_app_config("demo").path) / f"frontend/locale/{language}.json").read_text())[
        "demo"
    ]
    for language in ("en", "es")
}

#: Each write of Demo and the datum of it that names an item by its id.
ON_AN_ITEM = [
    ("demo.item.add_line", "id"),
    ("demo.item.delete", "id"),
    ("demo.item.update", "id"),
]


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


def demo_writes() -> list:
    return [op for _, op in sorted(registry.items()) if op.app_label == "demo" and assistant.is_tool(op)
            and op.kind == "command"]


@pytest.fixture
def named(monkeypatch):
    """Every item a write names by its id comes out named, as a person who may read it sees it: these tests are about
    what the card calls each datum, and an item nobody names is left out of it."""
    monkeypatch.setattr(assistant, "_reference", lambda value, prop, words: "Mesa 4")


# ── An item by its name, titled as its screen calls one ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_AN_ITEM)
def test_a_write_on_an_item_says_it_by_its_name(write, datum):
    """The case the issue names, «demo.item.delete:id»: «Item: Mesa 4», never its id nor its note."""
    item = Item.objects.create(name="Mesa 4", note="By the window")
    assert shown(write, {datum: str(item.id)})[datum] == "Mesa 4"


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_case_of_the_issue_reads_item_and_its_name_in_each_language(language):
    """Deleting an item, a dangerous write: its name under the word its screen calls one («Elemento», «Item»)."""
    item = Item.objects.create(name="Mesa 4")
    field = fields_of("demo.item.delete", {"id": str(item.id)}, language)["id"]
    assert (field["value"], field["label"]) == ("Mesa 4", SCREENS[language]["detail"]["title"])


@pytest.mark.parametrize(("write", "datum"), ON_AN_ITEM)
def test_the_card_names_the_item_of_a_write_as_its_screen_calls_one(named, write, datum):
    """The item a write acts on, titled with the word its screen calls one in each language («Elemento», «Item»):
    never «Id» nor «Registro»."""
    for language in ("es", "en"):
        label = fields_of(write, {datum: A_MISSING_ID}, language)[datum]["label"]
        assert label == SCREENS[language]["detail"]["title"], (write, language)


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names():
    """Each id names its own item, never another of the list (the first, the last)."""
    items = [Item.objects.create(name="Mesa 4"), Item.objects.create(name="Barra")]
    for write, datum in ON_AN_ITEM:
        for listed in (items, list(reversed(items))):
            said = [shown(write, {datum: str(item.id)})[datum] for item in listed]
            assert said == [item.name for item in listed], write


@pytest.mark.django_db
def test_a_change_keeps_saying_the_item_beside_what_it_changes():
    """The name is the item's as it is now, before the write runs: a rename says the old name under «Item» and the new
    one under its own datum; a new line says the item it goes on beside its text."""
    item = Item.objects.create(name="Mesa 4")
    renamed = shown("demo.item.update", {"id": str(item.id), "name": "Mesa 5"})
    assert renamed == {"id": "Mesa 4", "name": "Mesa 5"}
    line = shown("demo.item.add_line", {"id": str(item.id), "text": "Café"})
    assert line == {"id": "Mesa 4", "text": "Café"}


# ── Its status by its label ───────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("write", ["demo.item.create", "demo.item.update"])
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_status_of_an_item_is_said_by_its_label_in_each_language(write, language):
    """The closed list of an item's status says each value as the list says it («Abierto» / «Hecho», «Open» / «Done»),
    never the code it is sent as."""
    for status in ("open", "done"):
        field = fields_of(write, {"status": status}, language)["status"]
        assert field["value"] == SCREENS[language]["status"][status], (write, language, status)


def test_no_datum_of_a_write_of_demo_reaches_a_spanish_card_by_its_technical_name(named):
    """Every write of Demo the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up. None of its data is written alike in both languages, so the set is empty."""
    writes = demo_writes()
    assert [op.name for op in writes] == [
        "demo.item.add_line", "demo.item.create", "demo.item.delete", "demo.item.update",
    ]  # positive control: the registry has demo's writes
    assert technical_names(writes) == {}


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_AN_ITEM)
def test_what_the_person_may_not_read_is_left_out_never_said_by_its_id(write, datum):
    """Whoever may not see the items (``demo.view``) is told no item."""
    item = Item.objects.create(name="Mesa 4")
    arguments = {datum: str(item.id)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("demo.view"))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_an_employee_who_sees_the_items_is_told_which_one():
    """An employee sees every item (``demo.view``): the line they ask for, with a manager's approval, names its item."""
    item = Item.objects.create(name="Mesa 4")
    assert shown("demo.item.add_line", {"id": str(item.id)}, ctx=ctx_for("hub_employee")) == {"id": "Mesa 4"}


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_AN_ITEM)
def test_what_does_not_exist_is_left_out(write, datum):
    said = shown(write, {datum: A_MISSING_ID})
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_an_item_deleted_meanwhile_is_left_out():
    item = Item.objects.create(name="Mesa 4")
    arguments = {"id": str(item.id)}
    assert shown("demo.item.delete", arguments) == {"id": "Mesa 4"}  # positive control
    item.delete()
    assert shown("demo.item.delete", arguments) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_item():
    """An automation's card (no person at hand) names no item: nothing is read for anybody."""
    item = Item.objects.create(name="Mesa 4")
    card = assistant.card(get("demo.item.update"), {"id": str(item.id), "name": "Mesa 5"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"name": "Mesa 5"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_an_item_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        item = Item.objects.create(name="Mesa 4")
        assert shown("demo.item.delete", {"id": str(item.id)}, ctx=in_a) == {"id": "Mesa 4"}  # positive control
    with use_hub(hub_b):
        assert shown("demo.item.delete", {"id": str(item.id)}, ctx=in_b) == {}


# ── An item said by its name (hub#1162) ───────────────────────────────────────────────────────────────────────────────

#: Each write of Demo and the datum of it that names an item by its name, when its id is not known.
BY_ITS_NAME = [
    ("demo.item.add_line", {"text": "Café", "qty": 1}),
    ("demo.item.delete", {}),
    ("demo.item.update", {"status": "done"}),
]
#: The request of the issue, the owner's probe of layer 2 (``qa20261108.owner.es.demo.item.delete``): the item said by
#: its own name alone, with no word that says it is an item of Demo.
DELETE_BY_ITS_NAME = "elimina Ejemplo QA junto con todas sus líneas; entiendo que no se puede deshacer"


def owner_in(language: str = "es") -> OperationContext:
    return dataclasses.replace(ctx_for("hub_owner"), language=language)


def turn_of(ctx: OperationContext, said: str, write: dict, decision: dict | None = None) -> dict:
    """``base.assistant.turn`` after the model asked for ``write`` on the person's request ``said``."""
    op = get("base.assistant.turn")
    data = {"messages": [{"role": "user", "content": said}, asked(write)], "pending": [write], "decision": decision}
    return op(ctx, op.input.model_validate(data)).model_dump(mode="json")


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "rest"), BY_ITS_NAME)
def test_a_write_on_an_item_said_by_its_name_says_the_item_it_finds(write, rest):
    """The card reads the item by what was said, as the write will find it: the item's own name, even when only part
    of it was said, under the word its screen calls one."""
    Item.objects.create(name="Mesa 4")
    Item.objects.create(name="Barra")
    for language in ("es", "en"):
        field = fields_of(write, {"called": "mesa", **rest}, language)["called"]
        assert (field["value"], field["label"]) == ("Mesa 4", SCREENS[language]["detail"]["title"]), (write, language)


@pytest.mark.django_db
def test_an_employee_who_sees_the_items_is_told_which_one_by_its_name():
    Item.objects.create(name="Mesa 4")
    assert shown("demo.item.add_line", {"called": "Mesa 4"}, ctx=ctx_for("hub_employee")) == {"called": "Mesa 4"}
    assert shown("demo.item.add_line", {"called": "Mesa 4"}, ctx=without("demo.view")) == {}


@pytest.mark.django_db
def test_the_item_of_the_issue_said_by_its_own_name_alone_gets_its_card_and_goes_with_the_yes():
    """«elimina Ejemplo QA junto con todas sus líneas»: the model sends the name it heard, never asks for the UUID; the
    card says «Elemento: Ejemplo QA» and nothing is deleted until the person types the word."""
    item = Item.objects.create(name="Ejemplo QA")
    write = call("demo.item.delete", {"called": "Ejemplo QA"})

    plan = turn_of(owner_in(), DELETE_BY_ITS_NAME, write)

    card = plan["confirm"]
    assert (card["operation"], card["risk"]) == ("demo.item.delete", "high")
    assert [(field["name"], field["label"], field["value"]) for field in card["fields"]] == [
        ("called", SCREENS["es"]["detail"]["title"], "Ejemplo QA")
    ]
    [waiting] = plan["pending"]
    assert ({key: waiting[key] for key in write}, plan["executed"]) == (write, [])
    assert Item.objects.filter(pk=item.pk).exists()

    yes = {"call_id": "c1", "accepted": True, "typed": card["confirm_word"]}
    done = turn_of(owner_in(), DELETE_BY_ITS_NAME, waiting, decision=yes)

    assert done["executed"][0]["outcome"] == "ok"
    assert not Item.objects.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_the_yes_deletes_only_the_item_its_card_showed_although_another_fits_the_name_better_meanwhile():
    """hub#1208: «elimina mesa» shows «Mesa 4»; somebody creates «Mesa» before the yes. The yes, with the call as the
    turn gave it back (the panel's way), deletes nothing: the card now says «Mesa», and only its yes deletes it."""
    shown = Item.objects.create(name="Mesa 4")
    plan = turn_of(owner_in(), "elimina mesa", call("demo.item.delete", {"called": "mesa"}))
    assert [(field["name"], field["value"]) for field in plan["confirm"]["fields"]] == [("called", "Mesa 4")]
    other = Item.objects.create(name="Mesa")
    [waiting] = plan["pending"]
    yes = {"call_id": "c1", "accepted": True, "typed": plan["confirm"]["confirm_word"]}

    again = turn_of(owner_in(), "elimina mesa", waiting, decision=yes)

    assert again["executed"] == []
    assert [(field["name"], field["value"]) for field in again["confirm"]["fields"]] == [("called", "Mesa")]
    assert Item.objects.filter(pk=shown.pk).exists() and Item.objects.filter(pk=other.pk).exists()
    [waiting] = again["pending"]
    done = turn_of(owner_in(), "elimina mesa", waiting, decision=yes)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert list(Item.objects.values_list("pk", flat=True)) == [shown.pk]


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "rest"), BY_ITS_NAME)
def test_a_name_two_items_share_draws_no_card_and_the_model_hears_it(write, rest):
    """Two items called the same: no card that would act on either; the model hears ``demo.item_ambiguous`` and asks
    the person which one (the data are checked before any card is drawn)."""
    Item.objects.create(name="Ejemplo QA")
    Item.objects.create(name="Ejemplo QA", note="the other one")
    asked_for = call(write, {"called": "Ejemplo QA", **rest})

    plan = turn_of(owner_in(), DELETE_BY_ITS_NAME, asked_for)

    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert (plan["executed"][0]["outcome"], plan["executed"][0]["code"]) == ("error", "demo.item_ambiguous")
    assert json.loads(plan["append"][0]["content"])["error"]["code"] == "demo.item_ambiguous"
    assert Item.objects.count() == 2


@pytest.mark.django_db
def test_a_name_no_item_has_draws_no_card():
    Item.objects.create(name="Barra")
    plan = turn_of(owner_in(), DELETE_BY_ITS_NAME, call("demo.item.delete", {"called": "Ejemplo QA"}))
    assert (plan["confirm"], plan["executed"][0]["code"]) == (None, "not_found")
    assert Item.objects.count() == 1


# ── An item that comes by its id with the name of another one beside it (hub#1272) ────────────────────────────────────
# Each write of Demo takes its item by its id when it comes (``find_item``) and never looks at the name said beside it:
# the card neither reads nor shows that name (``unless``, hub#1250), never «Elemento: Terraza» beside «Elemento: Mesa
# 4».

#: Beside which data each write of Demo takes its item by them and not by the name said beside them.
UNLESS = {(write, "called"): {"id"} for write, _ in BY_ITS_NAME}


def test_the_name_is_left_unread_beside_the_id_its_write_takes_the_item_by_instead():
    assert unless_marked(demo_writes(), AN_ITEM_BY_NAME) == UNLESS


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "rest"), BY_ITS_NAME)
def test_an_item_that_comes_by_its_id_names_no_other_one_said_beside_it(write, rest):
    item = Item.objects.create(name="Mesa 4")
    Item.objects.create(name="Terraza")
    for language in ("es", "en"):
        said = shown(write, {"id": str(item.id), "called": "terraza", **rest}, language)
        assert (said["id"], "called" in said, "Terraza" in said.values()) == ("Mesa 4", False, False), (write, language)


def everything_of(item: Item) -> tuple:
    """``item`` and its lines, as the writes of Demo change them."""
    row = Item.objects.filter(pk=item.pk).values_list("name", "status", "note", "updated_at").first()
    return row, sorted(item.lines.values_list("text", "qty"))


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "rest"), BY_ITS_NAME)
def test_the_yes_to_an_item_that_comes_by_its_id_runs_on_it_whatever_name_is_said_beside_it(write, rest):
    """Control of the above: the write acts on the item of the id, never on the one the name beside it fits."""
    item = Item.objects.create(name="Mesa 4")
    other = Item.objects.create(name="Terraza")
    before = everything_of(other), everything_of(item)
    done = yes_to_its_card(owner_in(), write, {"id": str(item.id), "called": "terraza", **rest})
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert (everything_of(other), everything_of(item) != before[1]) == (before[0], True)
