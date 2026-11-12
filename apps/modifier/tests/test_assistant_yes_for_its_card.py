"""hub#1208 and hub#1218 in Modifiers: the yes to the card of a group said by its name touches only what it showed.

The platform holds a yes to what its card read (``base/tests/test_assistant_yes_for_its_card.py``). In Modifiers a group
is always found by its name alone (``find_group``: it belongs to nothing), so a write that takes it by its name reads it
on its card by that name, as the write will find it (``names("modifier.group.get", by="group")``), and checks its record
before any card (``check``): the group's own read when the group is the record, the option's or the link's when the
group said by its name finds them. The card says the group it found («Salsas picantes» when the person said «salsa»),
a name two groups fit or none has draws no card, and a yes after another group fits the name better runs nothing and
shows the new card, as Demo (hub#1206) and Menus (hub#1217) do (MODIFIER-F03, MODIFIER-F04, MODIFIER-F05,
BASE-F97). Adding an option to a group or applying it, which cannot check it, reads it the same way and says it as said
when two fit; an option said by its name is read with its group (hub#1245). A record that comes by its id names no other
group said beside it (hub#1250), nor another group, product or category whose id comes beside a link's (hub#1278). A
product or a category said by its name, when a group is applied or let go, is read as the write finds it, and left
unread beside the id the write takes its record by instead (hub#1291).
"""

import json

import pytest
from live.context import Scope
from live.operations import get, registry

from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.modifier.tests.conftest import GENERIC, ctx_for, make_category, make_product, run
from apps.modifier.tests.test_integration_assistant import TITLES, modifier_writes
from base import assistant
from base.schemas import names
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_yes_for_its_card import (
    read_as,
    said,
    turn_as,
    unless_by_id,
    unless_marked,
    unless_of,
    yes_to_its_card,
)
from base.tests.test_services_assistant import call

pytestmark = pytest.mark.django_db

BY_ITS_NAME = ("modifier.group.delete", {"group": "salsa"})

#: The writes of Modifiers that take a group by its name, and the read each one checks its record with before its
#: card: the group's own when the group is the record; the option's or the link's, which find theirs in that group
#: (their ``id`` is the option or the link: ``modifier.group.get`` would read it as a group's).
CHECKS = {
    "modifier.group.delete": "modifier.group.get",
    "modifier.group.update": "modifier.group.get",
    "modifier.link.detach": "modifier.link.get",
    "modifier.option.delete": "modifier.option.get",
    "modifier.option.update": "modifier.option.get",
}
WRITES = sorted(CHECKS)
#: The writes that take a group by its name with no read whose input fits theirs to check it with (``base.E012``:
#: ``modifier.group.get`` takes an ``id``, which adding an option or applying a group has not): their card reads the
#: group by its name all the same, so the yes holds to it, and says it as said when two fit (hub#1245).
UNCHECKED = ("modifier.link.attach", "modifier.option.create")
#: How the card reads a group and an option said by their names: an option inside its group, when it is told.
A_GROUP_SAID = names("modifier.group.get", by="group", as_said=True)
AN_OPTION_SAID = names("modifier.option.get", by="option", within=("group_id", "group"), name=("label",), as_said=True)


def by_its_name(said: str) -> dict[str, dict]:
    """The data of each write of Modifiers that takes a group by its name, with the group said as ``said``; the rest
    as every group of ``a_group`` has it (its option «Alioli», applied to «Hamburguesa»)."""
    return {
        "modifier.group.delete": {"group": said},
        "modifier.group.update": {"group": said, "max_choices": 3},
        "modifier.link.attach": {"group": said, "category": "Entrantes"},
        "modifier.link.detach": {"group": said, "product": "Hamburguesa"},
        "modifier.option.create": {"group": said, "name": "Brava"},
        "modifier.option.delete": {"group": said, "option": "Alioli"},
        "modifier.option.update": {"group": said, "option": "Alioli", "price_delta": 50},
    }


def burger():
    """«Hamburguesa» of Inventory, made once through its own operation."""
    from apps.inventory.models import Product

    return Product.objects.filter(sku="HAM").first() or make_product("Hamburguesa", "HAM")


def a_group(name: str):
    """The group ``name`` as a restaurant's Modifiers screens show it: its option «Alioli», applied to
    «Hamburguesa»; the category «Entrantes» to apply it to. Made with each app's own operations."""
    group = run("modifier.group.create", {"name": name})
    run("modifier.option.create", {"group_id": str(group.id), "name": "Alioli"})
    run("modifier.link.attach", {"group_id": str(group.id), "product_id": str(burger().id)})
    if not _has_category("Entrantes"):
        make_category("Entrantes")
    return group


def _has_category(name: str) -> bool:
    from apps.inventory.models import Category

    return Category.objects.filter(name=name).exists()


def as_admin(language: str = "es"):
    return ctx_for("hub_admin", language=language)


def group_on(plan: dict) -> list[tuple[str, object]]:
    return [(field["name"], field["value"]) for field in plan["confirm"]["fields"] if field["name"] == "group"]


def fields_of(write: str, arguments: dict, language: str) -> dict:
    card = assistant.card(get(write), arguments, language, as_admin(language))
    return {field["name"]: field for field in card["fields"]}


def yes_after_salsa_comes(write: str) -> tuple[dict, tuple]:
    """«salsa» said to ``write`` while only «Salsas picantes» fits; somebody creates «Salsa», with its own «Alioli» on
    «Hamburguesa», before the yes. → the yes's turn, and every group, option and link as they were just before it."""
    a_group("Salsas picantes")
    before = {}

    def meanwhile():
        a_group("Salsa")
        before["state"] = state()

    done = yes_to_its_card(as_admin(), write, by_its_name("salsa")[write], meanwhile=meanwhile)
    return done, before["state"]


def state() -> tuple:
    """Every group, option and link, with what the writes above change."""
    return (
        sorted(ModifierGroup.objects.values_list("name", "max_choices")),
        sorted(ModifierOption.objects.values_list("group__name", "name", "price_delta")),
        sorted(ModifierLink.objects.values_list("group__name", "product__name", "category__name")),
    )


def test_the_yes_to_the_card_of_a_group_said_by_its_name_runs_on_it():
    """Control: nothing changed between the card and the yes."""
    shown = ModifierGroup.objects.create(name="Salsas picantes")
    done = yes_to_its_card(ctx_for("hub_admin"), *BY_ITS_NAME)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert not ModifierGroup.objects.filter(pk=shown.pk).exists()


def test_the_yes_touches_only_the_group_its_card_showed_although_another_fits_the_name_better_meanwhile():
    """The case of the issue: «borra la salsa» shows «Salsas picantes»; somebody creates «Salsa» before the yes
    (the same name wins over one that holds it): the yes deletes neither, and the card it shows now says «Salsa»."""
    ModifierGroup.objects.create(name="Salsas picantes")
    assert group_on(turn_as(as_admin(), call(*BY_ITS_NAME))) == [("group", "Salsas picantes")]

    done = yes_to_its_card(as_admin(), *BY_ITS_NAME, meanwhile=lambda: ModifierGroup.objects.create(name="Salsa"))

    assert done["executed"] == []
    assert group_on(done) == [("group", "Salsa")]
    assert sorted(ModifierGroup.objects.values_list("name", flat=True)) == ["Salsa", "Salsas picantes"]


@pytest.mark.parametrize("write", WRITES)
def test_a_write_on_a_group_said_by_its_name_says_the_group_it_finds(write):
    """The card reads the group by what was said, as the write will find it: its own name, even when only part of
    it was said, under the word its screens call one («Grupo: Salsas picantes»), never the words said («salsa»)."""
    a_group("Salsas picantes")
    a_group("Extras")
    for language in ("es", "en"):
        field = fields_of(write, by_its_name("salsa")[write], language)["group"]
        found = (field["value"], field["label"])
        assert found == ("Salsas picantes", TITLES[language]["group"]), (write, language)


@pytest.mark.parametrize("write", WRITES)
def test_the_yes_runs_nothing_when_another_group_fits_the_name_better_before_it(write):
    """«salsa» shows «Salsas picantes»; somebody creates «Salsa» before the yes: the yes runs nothing on either, and
    the card it shows now says «Salsa»."""
    done, before = yes_after_salsa_comes(write)
    assert done["executed"] == []
    assert group_on(done) == [("group", "Salsa")]
    assert state() == before


@pytest.mark.parametrize("write", WRITES)
def test_a_name_two_groups_fit_draws_no_card_and_the_model_hears_it(write):
    """«salsas» fits «Salsas picantes» and «Salsas dulces»: no card that would act on either; the model hears
    ``modifier.group_ambiguous`` and asks the person which one (the data are checked before any card)."""
    a_group("Salsas picantes")
    a_group("Salsas dulces")

    plan = turn_as(as_admin(), call(write, by_its_name("salsas")[write]))

    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("error", "modifier.group_ambiguous")]
    assert json.loads(plan["append"][0]["content"])["error"]["code"] == "modifier.group_ambiguous"


@pytest.mark.parametrize("write", WRITES)
def test_a_name_no_group_has_draws_no_card(write):
    a_group("Salsas picantes")
    before = state()
    plan = turn_as(as_admin(), call(write, by_its_name("postres")[write]))
    assert (plan["confirm"], [row["code"] for row in plan["executed"]]) == (None, ["not_found"])
    assert state() == before


def test_every_write_of_modifiers_that_takes_a_group_by_its_name_is_here():
    """No assistant write that takes a group by its name (``group``) escapes these cases: it checks it, or it is one of
    those that cannot yet (hub#1245)."""
    taking = {op.name for op in modifier_writes() if "group" in op.input.model_fields}
    assert taking == set(CHECKS) | set(UNCHECKED)
    assert set(by_its_name("salsa")) == taking


def test_only_the_writes_that_take_a_group_by_its_name_check_their_record():
    """Ratchet: a check is a read before the card, which a write that takes no group by its name does not need (and
    whose refusal would hide its card): exactly these, each with the read of its own record."""
    declared = {op.name: assistant.check_of(op) for op in registry.values() if op.app_label == "modifier"}
    assert {name: read for name, read in declared.items() if read is not None} == CHECKS


def test_every_write_that_takes_a_group_or_an_option_by_its_name_reads_it_and_says_it_as_said_when_it_cannot():
    """With or without a check before it, a group said by its name is read on its card, and stays on it as said when it
    cannot be read (two fit): never off it. An option, with its group."""
    marks = {
        (op.name, datum): read_as(op.input.model_fields[datum].json_schema_extra)
        for op in modifier_writes()
        for datum in ("group", "option")
        if datum in op.input.model_fields
    }
    assert {key for key, mark in marks.items() if key[1] == "group" and mark == A_GROUP_SAID} == {
        (name, "group") for name in [*CHECKS, *UNCHECKED]
    }
    assert {key for key, mark in marks.items() if key[1] == "option" and mark == AN_OPTION_SAID} == {
        ("modifier.option.delete", "option"),
        ("modifier.option.update", "option"),
    }
    assert {key for key, mark in marks.items() if mark not in (A_GROUP_SAID, AN_OPTION_SAID)} == set()


@pytest.mark.parametrize("write", UNCHECKED)
def test_a_group_two_fit_stays_on_the_card_of_a_write_that_cannot_check_it(write):
    """Adding an option or applying a group: «salsas» fits two groups and the card still says «salsas», as said."""
    a_group("Salsas picantes")
    a_group("Salsas dulces")
    assert fields_of(write, by_its_name("salsas")[write], "es")["group"]["value"] == "salsas"


# ── A group added to or applied by its name, and an option said by its name (hub#1245) ───────────────────────────────
# Adding an option to a group or applying a group, said by its name, has no read whose input fits to check it with: its
# card reads the group by its name all the same, so the group it found goes in its fingerprint and the yes holds to it.
# An option said by its name is read with its group (``within``), as the write finds it.


@pytest.mark.parametrize("write", UNCHECKED)
def test_the_yes_to_adding_or_applying_touches_only_the_group_its_card_showed(write):
    """«salsa» shows «salsa»; somebody creates «Salsa» before the yes: the yes adds or applies nothing."""
    done, before = yes_after_salsa_comes(write)
    assert done["executed"] == []
    assert state() == before


@pytest.mark.parametrize("write", UNCHECKED)
def test_a_write_that_cannot_check_it_says_the_group_it_finds(write):
    a_group("Salsas picantes")
    assert fields_of(write, by_its_name("salsa")[write], "es")["group"]["value"] == "Salsas picantes"


@pytest.mark.parametrize("write", ["modifier.option.delete", "modifier.option.update"])
def test_the_card_says_the_option_it_finds(write):
    a_group("Salsas picantes")
    arguments = {**by_its_name("salsa")[write], "option": "ali"}
    assert fields_of(write, arguments, "es")["option"]["value"] == "Alioli (Salsas picantes)"


@pytest.mark.parametrize("write", ["modifier.option.delete", "modifier.option.update"])
def test_the_card_says_the_option_of_the_group_said_beside_it(write):
    """«ali» of «dulces», though «Salsas picantes» has its «Alioli» too: the option is read with its group."""
    a_group("Salsas picantes")
    a_group("Salsas dulces")
    arguments = {**by_its_name("dulces")[write], "option": "ali"}
    assert fields_of(write, arguments, "es")["option"]["value"] == "Alioli (Salsas dulces)"


@pytest.mark.parametrize("write", ["modifier.option.delete", "modifier.option.update"])
def test_an_option_two_groups_have_stays_on_the_card_as_said(write):
    """«ali» with no group: «Alioli» of «Salsas picantes» and of «Salsas dulces» fit, and the card says «ali»."""
    a_group("Salsas picantes")
    a_group("Salsas dulces")
    arguments = {key: value for key, value in by_its_name("salsa")[write].items() if key != "group"}
    assert fields_of(write, {**arguments, "option": "ali"}, "es")["option"]["value"] == "ali"


# ── A link to something Inventory deleted, until MODIFIER-F09 lets it go ─────────────────────────────────────────────


def test_a_link_to_a_product_deleted_meanwhile_draws_no_card_and_its_id_still_lets_it_go():
    """Between the deletion of a product and the reaction that drops its links (MODIFIER-F09), the link is in no read
    (``LIVE_LINK``), so the check of ``modifier.link.detach`` refuses it before any card, by its id or by its group
    and product: the assistant cannot let go what it cannot see. The operation itself still takes it by its id."""
    group = a_group("Extras")
    link = ModifierLink.objects.get(group_id=group.id)
    run("inventory.product.delete", {"id": str(link.product_id)})
    assert ModifierLink.objects.filter(pk=link.pk).exists()

    for arguments in ({"id": str(link.id)}, {"group": "extras", "product_id": str(link.product_id)}):
        plan = turn_as(as_admin(), call("modifier.link.detach", arguments))
        refused = [row["code"] for row in plan["executed"]]
        assert (plan["confirm"], refused) == (None, ["not_found"]), arguments
    assert ModifierLink.objects.filter(pk=link.pk).exists()

    run("modifier.link.detach", {"id": str(link.id)})
    assert not ModifierLink.objects.filter(pk=link.pk).exists()


# ── A record that comes by its id with the name of another group beside it (hub#1250) ────────────────────────────────
# The write takes the record by its id and never looks at the name beside it: the card neither reads nor shows it
# (``unless``). An option that comes by its id is the exception: the write looks for it in the group said beside it,
# so that group is read.

#: Beside which data each write of Modifiers takes its group by them and not by its name, and its option.
UNLESS = {
    **{(name, "group"): {"id"} for name in ("modifier.group.delete", "modifier.group.update")},
    ("modifier.link.attach", "group"): {"group_id"},
    ("modifier.link.detach", "group"): {"id", "group_id"},
    ("modifier.option.create", "group"): {"group_id"},
    **{(name, "group"): {"group_id"} for name in ("modifier.option.delete", "modifier.option.update")},
    **{(name, "option"): {"id"} for name in ("modifier.option.delete", "modifier.option.update")},
}


def test_a_name_is_left_unread_beside_each_datum_its_write_takes_its_record_by_instead():
    marked = {
        (op.name, datum): unless_of(op.input.model_fields[datum].json_schema_extra)
        for op in modifier_writes()
        for datum in ("group", "option")
        if datum in op.input.model_fields
    }
    assert marked == UNLESS


def by_its_id_beside_picantes(write: str) -> dict:
    """The data of ``write`` with «Extras» (or its link) by its id and, beside it, «picantes», which only «Salsas
    picantes» fits."""
    extras = a_group("Extras")
    a_group("Salsas picantes")
    record = extras.id if write.startswith("modifier.group.") else ModifierLink.objects.get(group_id=extras.id).id
    arguments = {**by_its_name("picantes")[write], "id": str(record)}
    arguments.pop("product", None)
    return arguments


@pytest.mark.parametrize("write", ["modifier.group.delete", "modifier.group.update", "modifier.link.detach"])
def test_a_record_that_comes_by_its_id_names_no_other_group_said_beside_it(write):
    card = assistant.card(get(write), by_its_id_beside_picantes(write), "es", as_admin())
    assert "Salsas picantes" not in [field["value"] for field in card["fields"]]


@pytest.mark.parametrize("write", ["modifier.group.delete", "modifier.link.detach"])
def test_the_yes_to_a_record_that_comes_by_its_id_runs_on_it_whatever_group_is_said_beside_it(write):
    """Control of the above: the write acts on «Extras» (or its link), never on «Salsas picantes»."""
    arguments = by_its_id_beside_picantes(write)
    picantes = ModifierGroup.objects.get(name="Salsas picantes")

    def of_picantes() -> tuple[int, int]:
        return ModifierGroup.objects.filter(pk=picantes.pk).count(), ModifierLink.objects.filter(group=picantes).count()

    before = of_picantes()
    done = yes_to_its_card(as_admin(), write, arguments)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert of_picantes() == before


@pytest.mark.parametrize("write", ["modifier.option.delete", "modifier.option.update"])
def test_an_option_that_comes_by_its_id_is_still_looked_for_in_the_group_said_beside_it(write):
    """The write looks for the option of the id in the group said: the card reads that group, as the write uses it."""
    extras = a_group("Extras")
    option = ModifierOption.objects.get(group_id=extras.id)
    arguments = {**by_its_name("extras")[write], "id": str(option.id)}
    arguments.pop("option", None)
    assert fields_of(write, arguments, "es")["group"]["value"] == "Extras"


# ── A link that comes by its id with the id of another group, product or category beside it (hub#1278) ───────────────
# Letting a group go by the link's id never looks at the group, the product or the category whose id comes beside it:
# the card neither reads nor shows them (``unless``), as when the id comes alone. Everywhere else an id of a group, a
# product or a category is what the write takes (the group an option gets or a link hangs, what it applies to, the
# group an option by its id is looked for in): it is read.

#: Beside which data each write of Modifiers takes its record by them and not by each id it reads.
UNLESS_BY_ID = {
    **{(name, "id"): set() for name in ("modifier.group.delete", "modifier.group.update")},
    **{(name, "id"): set() for name in ("modifier.option.delete", "modifier.option.update")},
    **{
        (name, "group_id"): set() for name in ("modifier.option.create", "modifier.option.delete", "modifier.option.update")
    },
    **{("modifier.link.attach", datum): set() for datum in ("group_id", "product_id", "category_id")},
    ("modifier.link.detach", "id"): set(),
    **{("modifier.link.detach", datum): {"id"} for datum in ("group_id", "product_id", "category_id")},
}


def test_an_id_is_left_unread_beside_each_datum_its_write_takes_its_record_by_instead():
    assert unless_by_id(modifier_writes()) == UNLESS_BY_ID


def extras_link_beside(datum: str) -> dict:
    """The data to let «Extras» go from «Hamburguesa» by the link's id with, beside it, the id of «Salsas picantes»,
    of «Pizza» or of «Entrantes», which the write does not use."""
    from apps.inventory.models import Category

    extras = a_group("Extras")
    others = {
        "group_id": a_group("Salsas picantes").id,
        "product_id": make_product("Pizza", "PIZ").id,
        "category_id": Category.objects.get(name="Entrantes").id,
    }
    return {"id": str(ModifierLink.objects.get(group_id=extras.id).id), datum: str(others[datum])}


@pytest.mark.parametrize("datum", ["category_id", "group_id", "product_id"])
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_link_that_comes_by_its_id_names_no_group_product_or_category_whose_id_comes_beside_it(datum, language):
    shown = fields_of("modifier.link.detach", extras_link_beside(datum), language)
    assert {name: field["value"] for name, field in shown.items()} == {"id": "Extras · Hamburguesa"}


@pytest.mark.parametrize("datum", ["category_id", "group_id", "product_id"])
def test_the_yes_to_a_link_that_comes_by_its_id_lets_only_it_go_whatever_id_comes_beside_it(datum):
    """Control of the above: the write lets «Extras» go from «Hamburguesa», and keeps every other link."""
    arguments = extras_link_beside(datum)
    done = yes_to_its_card(as_admin(), "modifier.link.detach", arguments)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert state()[2] == [("Salsas picantes", "Hamburguesa", None)]


# ── A product or a category said by its name, when a group is applied or let go (hub#1291) ───────────────────────────
# Applying a group or letting it go finds a product by its id, else by its SKU or its name, and a category by its id,
# else by its name (``services._target``): the card reads them by what was said, as the write will find them, and
# says them as said when it cannot. Beside the id the write takes its record by instead (the product's or the
# category's or, letting a group go, the link's), the card neither reads nor shows the name, which the write does not
# use.

#: How the card reads a product and a category said by their names: as Inventory's detail and Modifiers' own read of a
#: category find them, the same finders the write uses.
A_PRODUCT_SAID = names("inventory.product.get", by="product", as_said=True)
A_CATEGORY_SAID = names("modifier.category.get", by="category", as_said=True)
#: Beside which data each write of Modifiers takes its product or its category by them and not by its name.
UNLESS_OF_A_TARGET = {
    ("modifier.link.attach", "product"): {"product_id"},
    ("modifier.link.attach", "category"): {"category_id"},
    ("modifier.link.detach", "product"): {"id", "product_id"},
    ("modifier.link.detach", "category"): {"id", "category_id"},
}


def test_a_product_or_a_category_said_by_its_name_is_read_as_its_write_finds_it_and_unread_beside_its_id():
    """Found by the mark, not by the datum's name (``unless_marked``): every write that takes a product or a category
    by its name reads it as the write finds it, and leaves it unread beside each id it takes its record by instead."""
    writes = modifier_writes()
    marked = {**unless_marked(writes, A_PRODUCT_SAID), **unless_marked(writes, A_CATEGORY_SAID)}
    assert marked == UNLESS_OF_A_TARGET
    taking = {(op.name, datum) for op in writes for datum in ("product", "category") if datum in op.input.model_fields}
    assert taking == set(UNLESS_OF_A_TARGET)


def extras_everywhere() -> dict:
    """«Extras» applied to «Hamburguesa», to «Pizza» and to the categories «Entrantes» and «Postres»; «Salsas», applied
    to nothing. Made with each app's own operations."""
    from apps.inventory.models import Category

    extras = a_group("Extras")
    entrantes = Category.objects.get(name="Entrantes")
    run("modifier.link.attach", {"group_id": str(extras.id), "category_id": str(entrantes.id)})
    run("modifier.link.attach", {"group_id": str(extras.id), "product_id": str(make_product("Pizza", "PIZ").id)})
    run("modifier.link.attach", {"group_id": str(extras.id), "category_id": str(make_category("Postres").id)})
    run("modifier.group.create", {"name": "Salsas"})
    return {
        "id": ModifierLink.objects.get(group_id=extras.id, product=burger()).id,
        "product_id": burger().id,
        "category_id": entrantes.id,
    }


#: The name of another product or category that comes beside the id: «Pizza» and «Postres», which «Extras» hangs from.
ANOTHER = {"product": "Pizza", "category": "Postres"}
#: Each write with, beside the name of another product or category, the id it takes its record by instead: letting
#: «Extras» go by the link's id, or by «Extras» and the id of «Hamburguesa» or «Entrantes»; applying «Salsas» to the
#: product or the category of the id. → what the card says: the record of the id, never the name beside it.
SAID_BY_ITS_ID = {
    ("modifier.link.detach", "id", "product"): {"id": "Extras · Hamburguesa"},
    ("modifier.link.detach", "id", "category"): {"id": "Extras · Hamburguesa"},
    ("modifier.link.detach", "product_id", "product"): {"group": "Extras", "product_id": "Hamburguesa"},
    ("modifier.link.detach", "category_id", "category"): {"group": "Extras", "category_id": "Entrantes"},
    ("modifier.link.attach", "product_id", "product"): {"group": "Salsas", "product_id": "Hamburguesa"},
    ("modifier.link.attach", "category_id", "category"): {"group": "Salsas", "category_id": "Entrantes"},
}
#: The links of ``extras_everywhere``, and the one each yes of ``SAID_BY_ITS_ID`` lets go or makes: of the id's
#: record, never of the name beside it.
LINKS = [
    ("Extras", None, "Entrantes"),
    ("Extras", None, "Postres"),
    ("Extras", "Hamburguesa", None),
    ("Extras", "Pizza", None),
]
TOUCHED_BY_ITS_ID = {
    ("modifier.link.detach", "id"): ("Extras", "Hamburguesa", None),
    ("modifier.link.detach", "product_id"): ("Extras", "Hamburguesa", None),
    ("modifier.link.detach", "category_id"): ("Extras", None, "Entrantes"),
    ("modifier.link.attach", "product_id"): ("Salsas", "Hamburguesa", None),
    ("modifier.link.attach", "category_id"): ("Salsas", None, "Entrantes"),
}


def beside_another_name(write: str, by: str, kind: str) -> dict:
    """The data of a case of ``SAID_BY_ITS_ID``."""
    ids = extras_everywhere()
    group = {} if by == "id" else {"group": "extras" if write == "modifier.link.detach" else "salsas"}
    return {**group, by: str(ids[by]), kind: ANOTHER[kind]}


def by_name(rows) -> list[tuple]:
    """``rows`` of (group, product, category) in order, a link to a category before one to a product."""
    return sorted(rows, key=lambda row: tuple(value or "" for value in row))


def links() -> list[tuple]:
    return by_name(ModifierLink.objects.values_list("group__name", "product__name", "category__name"))


@pytest.mark.parametrize("case", sorted(SAID_BY_ITS_ID))
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_product_or_a_category_named_beside_the_id_its_write_takes_is_not_on_the_card(case, language):
    shown = fields_of(case[0], beside_another_name(*case), language)
    assert {name: field["value"] for name, field in shown.items()} == SAID_BY_ITS_ID[case]


@pytest.mark.parametrize("case", sorted(SAID_BY_ITS_ID))
def test_the_yes_beside_the_name_of_another_product_or_category_touches_only_the_record_of_the_id(case):
    """Control of the above: the write lets go the link of the id, or applies «Salsas» to the product or the category
    of the id; nothing of «Pizza» or «Postres» changes."""
    write, by, _ = case
    done = yes_to_its_card(as_admin(), write, beside_another_name(*case))
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    touched = TOUCHED_BY_ITS_ID[(write, by)]
    expected = [row for row in LINKS if row != touched] if write == "modifier.link.detach" else [*LINKS, touched]
    assert links() == by_name(expected)


#: A product or a category said in part, with no id: the card says the one the write finds.
SAID_IN_PART = {
    ("modifier.link.attach", "product"): ({"group": "salsas", "product": "pizz"}, "Pizza"),
    ("modifier.link.attach", "category"): ({"group": "salsas", "category": "postr"}, "Postres"),
    ("modifier.link.detach", "product"): ({"group": "extras", "product": "pizz"}, "Pizza"),
    ("modifier.link.detach", "category"): ({"group": "extras", "category": "postr"}, "Postres"),
}


@pytest.mark.parametrize("case", sorted(SAID_IN_PART))
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_product_or_a_category_said_by_its_name_is_on_the_card_as_the_write_finds_it(case, language):
    """«pizz» shows «Pizza» and «postr», «Postres», under the word the screens call one, never the words said."""
    extras_everywhere()
    arguments, found = SAID_IN_PART[case]
    field = fields_of(case[0], arguments, language)[case[1]]
    assert (field["value"], field["label"]) == (found, TITLES[language][case[1]])


@pytest.mark.parametrize("kind", ["product", "category"])
def test_a_product_or_a_category_two_fit_stays_on_the_card_of_applying_a_group_as_said(kind):
    """«pizz» fits «Pizza» and «Pizza grande»; «postr», «Postres» and «Postres caseros»: applying a group, which cannot
    check it, still says it as said, and the write asks which."""
    extras_everywhere()
    make_product("Pizza grande", "PIG")
    make_category("Postres caseros")
    arguments = SAID_IN_PART[("modifier.link.attach", kind)][0]
    assert fields_of("modifier.link.attach", arguments, "es")[kind]["value"] == arguments[kind]


#: What somebody creates before the yes that fits better what was said (the same name wins over one that holds it).
FITS_BETTER = {
    "product": ("Pizz", lambda: make_product("Pizz", "PZZ")),
    "category": ("Postr", lambda: make_category("Postr")),
}


@pytest.mark.parametrize("kind", sorted(FITS_BETTER))
def test_the_yes_to_applying_a_group_touches_only_the_product_or_the_category_its_card_showed(kind):
    """«pizz» shows «Pizza»; somebody creates «Pizz» before the yes: the yes applies the group to neither, and the card
    it shows now says «Pizz». The same with «postr», «Postres» and «Postr»."""
    extras_everywhere()
    arguments = SAID_IN_PART[("modifier.link.attach", kind)][0]
    better, create = FITS_BETTER[kind]
    before = {}

    def meanwhile():
        create()
        before["links"] = links()

    done = yes_to_its_card(as_admin(), "modifier.link.attach", arguments, meanwhile=meanwhile)
    assert done["executed"] == []
    assert [value for name, value in said(done) if name == kind] == [better]
    assert links() == before["links"]



#: Words and the product each one names: by its SKU before a name that holds it, by its same name before one that
#: holds it, else the only one that holds it; a deleted product is nobody.
PRODUCTS_SAID = [("piz", "Calzone"), ("pizza", "Pizza"), ("grande", "Pizza grande"), ("calz", "Calzone")]


def products_to_find() -> None:
    """«Calzone» (SKU «PIZ»), «Pizza», «Pizza grande» and a deleted «Pizza fría»; «Salsas», applied to nothing."""
    make_product("Calzone", "PIZ")
    make_product("Pizza", "PZA")
    make_product("Pizza grande", "PZG")
    run("inventory.product.delete", {"id": str(make_product("Pizza fría", "PZF").id)})
    run("modifier.group.create", {"name": "Salsas"})


@pytest.mark.parametrize(("said", "product"), PRODUCTS_SAID)
def test_the_read_the_card_names_a_product_by_finds_the_one_the_write_applies_a_group_to(said, product):
    """The trap of hub#1291: Inventory's detail finds a product with its rows ready (``_products``), the write with
    ``find_product`` alone. Both look for it among the same live products, so they find the same one."""
    products_to_find()
    read = run("inventory.product.get", {"product": said})
    applied = run("modifier.link.attach", {"group": "salsas", "product": said})
    assert (read.name, applied.product_name) == (product, product)


@pytest.mark.parametrize(("said", "product"), PRODUCTS_SAID)
def test_the_card_says_the_product_the_yes_applies_the_group_to(said, product):
    products_to_find()
    arguments = {"group": "salsas", "product": said}
    assert fields_of("modifier.link.attach", arguments, "es")["product"]["value"] == product
    done = yes_to_its_card(as_admin(), "modifier.link.attach", arguments)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert ModifierLink.objects.get().product.name == product


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_words_that_fit_a_product_or_a_category_of_another_business_are_said_as_said(hub_a, hub_b, no_fallback):
    """Each business in its own database: «pizz» and «postr» name «Pizza» and «Postres» in A, nothing in B."""
    in_a = ctx_for("hub_admin", scope=Scope("host", hub_a.slug), language="es")
    in_b = ctx_for("hub_admin", scope=Scope("host", hub_b.slug), language="es")

    def shown(ctx) -> dict:
        return {
            kind: {
                field["name"]: field["value"]
                for field in assistant.card(get(write), arguments, "es", ctx)["fields"]
            }[kind]
            for (write, kind), (arguments, _) in SAID_IN_PART.items()
            if write == "modifier.link.attach"
        }

    with use_hub(hub_a):
        product = {"name": "Pizza", "sku": "PIZ", "price": 800, "tax_category_key": GENERIC}
        run("inventory.product.create", product, ctx=in_a)
        run("inventory.category.create", {"name": "Postres"}, ctx=in_a)
        assert shown(in_a) == {"product": "Pizza", "category": "Postres"}  # positive control
    with use_hub(hub_b):
        assert shown(in_b) == {"product": "pizz", "category": "postr"}
