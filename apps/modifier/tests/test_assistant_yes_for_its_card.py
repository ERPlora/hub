"""hub#1208 and hub#1218 in Modifiers: the yes to the card of a group said by its name touches only what it showed.

The platform holds a yes to what its card read (``base/tests/test_assistant_yes_for_its_card.py``). In Modifiers a group
is always found by its name alone (``find_group``: it belongs to nothing), so a write that takes it by its name reads it
on its card by that name, as the write will find it (``names("modifier.group.get", by="group")``), and checks its record
before any card (``check``): the group's own read when the group is the record, the option's or the link's when the
group said by its name finds them. The card says the group it found («Salsas picantes» when the person said «salsa»),
a name two groups fit or none has draws no card, and a yes after another group fits the name better runs nothing and
shows the new card, as Demo (hub#1206) and Menus (hub#1217) do (MODIFIER-F03, MODIFIER-F04, MODIFIER-F05,
BASE-F97). Adding an option to a group or applying it, which cannot check it, reads it the same way and says it as said
when two fit; an option said by its name is read with its group (hub#1245).
"""

import json

import pytest
from live.operations import get, registry

from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.modifier.tests.conftest import ctx_for, make_category, make_product, run
from apps.modifier.tests.test_integration_assistant import TITLES, modifier_writes
from base import assistant
from base.schemas import names
from base.tests.test_assistant_yes_for_its_card import turn_as, yes_to_its_card
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
    ``modifier.group_ambiguous`` and asks the person which one (BASE-G115: the data are checked before any card)."""
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
        (op.name, datum): op.input.model_fields[datum].json_schema_extra
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


# ── Not yet: a record that comes by its id with the name of another group beside it (hub#1250) ──────────────────────
# The write takes the record by its id and never looks at the name; the card reads that name all the same and says
# both groups under one word. The yes is still held to what the card read. Strict: once the card leaves out a name
# the write does not use, these pass and their mark goes.


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="hub#1250: the card reads a name the write does not use")
@pytest.mark.parametrize("write", ["modifier.group.delete", "modifier.group.update", "modifier.link.detach"])
def test_a_record_that_comes_by_its_id_names_no_other_group_said_beside_it(write):
    extras = a_group("Extras")
    a_group("Salsas picantes")
    record = extras.id if write.startswith("modifier.group.") else ModifierLink.objects.get(group_id=extras.id).id
    arguments = {**by_its_name("picantes")[write], "id": str(record)}
    arguments.pop("product", None)
    card = assistant.card(get(write), arguments, "es", as_admin())
    assert "Salsas picantes" not in [field["value"] for field in card["fields"]]
