"""hub#1208, hub#1217 and hub#1231 in Menus: the yes to the card of a record said by its name touches only what that
card showed.

The platform holds a yes to what its card read (``base/tests/test_assistant_yes_for_its_card.py``). A write of Menus
whose record is the menu takes it by its id or by its name (``ComboRefIn``); said by its name, its card reads it by that
name as the write will find it (``names("combo.combo.get", by="combo")``) and the write checks it before any card
(``"check": "combo.combo.get"``), as Demo does (hub#1206): the card says the menu it found («Menú vegano» when the person
said «vegano»), a name two menus fit or none has draws no card, and a yes after another menu fits the name better runs
nothing and shows the new card (COMBO-F03, COMBO-F04, COMBO-F05, COMBO-F14, BASE-F97). A write whose record is a course
or a choice checks it with its own read (``combo.group.get``, ``combo.option.get``) and reads its menu by its name the
same way (hub#1231; COMBO-F05, COMBO-F06).
"""

import dataclasses
import json

import pytest
from live.operations import AI, registry

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from apps.combo.schemas import A_CHOICE, A_COURSE, A_MENU
from apps.combo.tests.conftest import ctx_for, make_combo, make_group, make_option, make_product
from apps.combo.tests.test_apps import CHECKED_BY_THE_MENU
from apps.combo.tests.test_assistant_card_records import fields_of, words
from base.schemas import names
from base.tests.test_assistant_yes_for_its_card import read_as, turn_as, unless_of, yes_to_its_card
from base.tests.test_services_assistant import call

pytestmark = pytest.mark.django_db

DELETE_BY_ITS_NAME = ("combo.combo.delete", {"combo": "menú"})


def by_its_name(said: str, combo: Combo) -> dict[str, dict]:
    """The data of each write of Menus whose record is the menu, an assistant tool, with the menu said as ``said``;
    the rest as ``combo`` (the menu the name finds) takes them. ``combo.combo.upload_image`` is no assistant tool (it
    takes the photo picked in the menu's form): no card ever shows it."""
    return {
        "combo.combo.delete": {"combo": said},
        "combo.combo.set_image": {"combo": said, "image": ""},
        "combo.combo.update": {"combo": said, "price": 1190},
        "combo.group.reorder": {"combo": said, "group_ids": [str(g.id) for g in combo.groups.order_by("-sort_order")]},
    }


WRITES = sorted(CHECKED_BY_THE_MENU)


def vegan_menu() -> Combo:
    """«Menú vegano», with two courses so its courses can be put in another order."""
    combo = make_combo("Menú vegano")
    make_group(combo, "Primeros")
    make_group(combo, "Segundos")
    return combo


def as_admin(language: str = "es"):
    return dataclasses.replace(ctx_for("hub_admin"), language=language)


def assistant_writes() -> list:
    """The writes of Menus that are assistant tools."""
    return [
        op
        for op in registry.values()
        if op.app_label == "combo" and op.kind == "command" and isinstance(op.ai_spec(), AI)
    ]


def id_mark(op) -> dict | None:
    """How the assistant's card names the record ``op``'s ``id`` says: as a menu, a course or a choice."""
    return getattr(op.input.model_fields.get("id"), "json_schema_extra", None)


def no_card_but_the_model_hears(plan: dict, code: str) -> None:
    """No card that would act on anything: the model hears ``code`` and asks the person which one."""
    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("error", code)]
    assert json.loads(plan["append"][0]["content"])["error"]["code"] == code


def said_on(plan: dict) -> list[tuple[str, object]]:
    return [(field["name"], field["value"]) for field in plan["confirm"]["fields"] if field["name"] == "combo"]


def test_the_yes_to_the_card_of_a_menu_said_by_its_name_runs_on_it():
    """Control: nothing changed between the card and the yes."""
    shown = make_combo("Menú vegano")
    done = yes_to_its_card(ctx_for("hub_admin"), *DELETE_BY_ITS_NAME)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert not Combo.objects.filter(pk=shown.pk).exists()


def test_the_yes_touches_only_the_menu_its_card_showed_although_another_fits_the_name_better_meanwhile():
    make_combo("Menú vegano")
    done = yes_to_its_card(ctx_for("hub_admin"), *DELETE_BY_ITS_NAME, meanwhile=lambda: make_combo("Menú"))
    assert done["executed"] == []
    assert Combo.objects.count() == 2


@pytest.mark.parametrize("write", WRITES)
def test_a_write_on_a_menu_said_by_its_name_says_the_menu_it_finds(write):
    """The card reads the menu by what was said, as the write will find it: the menu's own name, even when only part of
    it was said, under the word its screens call one («Menú: Menú vegano»), never the words said («vegano»)."""
    combo = vegan_menu()
    make_combo("Menú infantil")
    for language in ("es", "en"):
        field = fields_of(write, by_its_name("vegano", combo)[write], language, as_admin(language))["combo"]
        assert (field["value"], field["label"]) == ("Menú vegano", words(language)["menu"]), (write, language)


@pytest.mark.parametrize("write", WRITES)
def test_the_yes_runs_nothing_when_another_menu_fits_the_name_better_before_it(write):
    """«menú» shows «Menú vegano»; somebody creates «Menú» before the yes (the same name wins over one that holds it):
    the yes runs nothing on either, and the card it shows now says «Menú»."""
    combo = vegan_menu()
    before = Combo.objects.values().get(pk=combo.pk)
    order = list(combo.groups.order_by("sort_order").values_list("id", flat=True))

    done = yes_to_its_card(as_admin(), write, by_its_name("menú", combo)[write], meanwhile=lambda: make_combo("Menú"))

    assert done["executed"] == []
    assert said_on(done) == [("combo", "Menú")]
    assert Combo.objects.values().get(pk=combo.pk) == before
    assert list(combo.groups.order_by("sort_order").values_list("id", flat=True)) == order
    assert Combo.objects.count() == 2


@pytest.mark.parametrize("write", WRITES)
def test_a_name_two_menus_fit_draws_no_card_and_the_model_hears_it(write):
    """«vegano» fits «Menú vegano» and «Menú vegano sin gluten»: no card that would act on either; the model hears
    ``combo.combo_ambiguous`` and asks the person which one (BASE-G115: the data are checked before any card)."""
    combo = vegan_menu()
    make_combo("Menú vegano sin gluten")

    plan = turn_as(as_admin(), call(write, by_its_name("vegano", combo)[write]))

    no_card_but_the_model_hears(plan, "combo.combo_ambiguous")


@pytest.mark.parametrize("write", WRITES)
def test_a_name_no_menu_has_draws_no_card(write):
    combo = vegan_menu()
    plan = turn_as(as_admin(), call(write, by_its_name("infantil", combo)[write]))
    assert (plan["confirm"], [row["code"] for row in plan["executed"]]) == (None, ["not_found"])
    assert Combo.objects.count() == 1


def test_every_assistant_write_of_menus_that_takes_a_menu_by_its_name_is_here():
    """No write whose record is the menu, said by its name, escapes these cases: each tool of Menus whose input names
    the menu itself by its id (``id``, marked as a menu) or by its name (``combo``): not a course's or a choice's, whose
    ``combo`` is the menu they belong to."""
    taking = {op.name for op in assistant_writes() if "combo" in op.input.model_fields and id_mark(op) == A_MENU}
    assert taking == set(WRITES)




# ── A course or a choice said by its name, and the menu it belongs to (hub#1231) ──────────────────────────────────────
# A write whose record is a course or a choice takes it by its id or by its name inside its menu (``GroupRefIn``,
# ``OptionRefIn``): it checks it with that record's own read before its card (``combo.group.get``,
# ``combo.option.get``), and its card reads the menu it belongs to by the name said. The yes holds to the course or the
# choice the check found (its id goes in the card's fingerprint, hub#1208).

#: Each such write, an assistant tool: the datum that says its record by its name — a course by its own, a choice by
#: its product's — and the rest of its data.
BY_NAME = {
    "combo.group.delete": ("group", {}),
    "combo.group.update": ("group", {"max_choices": 2}),
    "combo.option.delete": ("product", {}),
    "combo.option.update": ("product", {"is_available": False}),
}
COURSE_OR_CHOICE_WRITES = sorted(BY_NAME)
#: What is said of each record («postres», «flan»), the one it finds, one that fits it better (the same name wins over
#: one that holds it), another that holds it as well, and a name none has.
SAID = {"group": "postres", "product": "flan"}
FOUND = {"group": "Postres caseros", "product": "Flan de la casa"}
BETTER = {"group": "Postres", "product": "Flan"}
ALSO = {"group": "Postres de temporada", "product": "Flan de huevo"}
NONE_HAS = {"group": "helados", "product": "tarta"}


def vegan_desserts(name: str = "Menú vegano") -> Combo:
    """A menu whose course «Postres caseros» offers «Flan de la casa»."""
    combo = make_combo(name)
    make_option(make_group(combo, FOUND["group"]), make_product(FOUND["product"]))
    return combo


def another(datum: str, combo: Combo, name: str) -> None:
    """Somebody adds to ``combo`` a course called ``name``, or a choice of a product called ``name`` to its desserts."""
    if datum == "group":
        make_group(combo, name)
    else:
        make_option(combo.groups.get(name=FOUND["group"]), make_product(name))


def course_or_choice(write: str, menu: str, said: str | None = None) -> dict:
    """The data of ``write`` with the menu said as ``menu`` and its course or its choice as ``said``."""
    datum, rest = BY_NAME[write]
    return {"combo": menu, datum: said or SAID[datum], **rest}


def everything() -> list[dict]:
    """Every course and every choice of every menu, as they are now."""
    return [*ChoiceGroup.objects.order_by("id").values(), *ChoiceOption.objects.order_by("id").values()]


def unchanged_after(change):
    """``change`` (what happens between the card and the yes), which keeps how everything was right after it."""
    seen = {}

    def meanwhile():
        change()
        seen["after"] = everything()

    return meanwhile, seen


def test_the_yes_touches_only_the_course_its_card_showed_although_another_fits_the_name_better_meanwhile():
    combo = make_combo("Menú vegano")
    make_group(combo, "Postres caseros")
    done = yes_to_its_card(
        as_admin(), "combo.group.delete", {"combo": "Menú vegano", "group": "postres"},
        meanwhile=lambda: make_group(combo, "Postres"),
    )
    assert done["executed"] == []
    assert sorted(combo.groups.values_list("name", flat=True)) == ["Postres", "Postres caseros"]


def test_the_yes_touches_only_the_course_of_the_menu_its_card_showed_although_another_menu_fits_the_name_better_meanwhile():
    make_group(make_combo("Menú vegano"), "Postres")
    done = yes_to_its_card(
        as_admin(), "combo.group.delete", {"combo": "menú", "group": "postres"},
        meanwhile=lambda: make_group(make_combo("Menú"), "Postres"),
    )
    assert done["executed"] == []
    assert Combo.objects.filter(groups__name="Postres").count() == 2


@pytest.mark.parametrize("write", COURSE_OR_CHOICE_WRITES)
def test_the_yes_to_the_card_of_a_course_or_a_choice_said_by_its_name_runs_on_it(write):
    """Control: nothing changed between the card and the yes."""
    vegan_desserts()
    before = everything()
    done = yes_to_its_card(as_admin(), write, course_or_choice(write, "vegano"))
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert everything() != before


@pytest.mark.parametrize("write", COURSE_OR_CHOICE_WRITES)
def test_the_yes_runs_nothing_when_another_course_or_choice_fits_the_name_better_before_it(write):
    """«postres» finds «Postres caseros» («flan», «Flan de la casa»); somebody adds «Postres» («Flan») to the same menu
    before the yes: it runs nothing on either."""
    combo = vegan_desserts()
    datum, _ = BY_NAME[write]
    meanwhile, seen = unchanged_after(lambda: another(datum, combo, BETTER[datum]))
    done = yes_to_its_card(as_admin(), write, course_or_choice(write, "Menú vegano"), meanwhile=meanwhile)
    assert done["executed"] == []
    assert everything() == seen["after"]


@pytest.mark.parametrize("write", COURSE_OR_CHOICE_WRITES)
def test_the_yes_runs_nothing_on_a_course_or_a_choice_when_another_menu_fits_the_name_better_before_it(write):
    """«menú» finds «Menú vegano»; somebody creates «Menú», with the same course and choice, before the yes: it runs
    nothing on either menu, and the card it shows now says «Menú»."""
    vegan_desserts()
    meanwhile, seen = unchanged_after(lambda: vegan_desserts("Menú"))
    done = yes_to_its_card(as_admin(), write, course_or_choice(write, "menú"), meanwhile=meanwhile)
    assert done["executed"] == []
    assert said_on(done) == [("combo", "Menú")]
    assert everything() == seen["after"]


@pytest.mark.parametrize("write", COURSE_OR_CHOICE_WRITES)
def test_a_write_on_a_course_or_a_choice_says_the_menu_it_belongs_to_as_it_finds_it(write):
    """The card reads the menu said by its name as the write will find it: «Menú: Menú vegano» when «vegano» was
    said, never the words said."""
    vegan_desserts()
    make_combo("Menú infantil")
    for language in ("es", "en"):
        field = fields_of(write, course_or_choice(write, "vegano"), language, as_admin(language))["combo"]
        assert (field["value"], field["label"]) == ("Menú vegano", words(language)["menu"]), (write, language)


@pytest.mark.parametrize("write", COURSE_OR_CHOICE_WRITES)
def test_a_name_two_courses_or_choices_fit_draws_no_card_and_the_model_hears_it(write):
    """«postres» fits «Postres caseros» and «Postres de temporada» («flan», two flans): no card that would act on
    either; the model hears which ones and asks the person (BASE-G115: the data are checked before any card)."""
    combo = vegan_desserts()
    datum, _ = BY_NAME[write]
    another(datum, combo, ALSO[datum])
    code = f"combo.{'group' if datum == 'group' else 'option'}_ambiguous"

    plan = turn_as(as_admin(), call(write, course_or_choice(write, "Menú vegano")))

    no_card_but_the_model_hears(plan, code)


@pytest.mark.parametrize("write", COURSE_OR_CHOICE_WRITES)
def test_a_name_no_course_or_choice_has_draws_no_card(write):
    vegan_desserts()
    datum, _ = BY_NAME[write]
    plan = turn_as(as_admin(), call(write, course_or_choice(write, "Menú vegano", NONE_HAS[datum])))
    assert (plan["confirm"], [row["code"] for row in plan["executed"]]) == (None, ["not_found"])


@pytest.mark.parametrize("write", COURSE_OR_CHOICE_WRITES)
def test_a_menu_two_fit_draws_no_card_rather_than_one_without_the_menu(write):
    """«vegano» fits «Menú vegano» and «Menú vegano sin gluten», each with the course and the choice: no card at all,
    never one that leaves the menu out (a read by the name that fails leaves it out, rv-1232); the model hears
    ``combo.combo_ambiguous`` and asks which one."""
    vegan_desserts()
    vegan_desserts("Menú vegano sin gluten")
    plan = turn_as(as_admin(), call(write, course_or_choice(write, "vegano")))
    no_card_but_the_model_hears(plan, "combo.combo_ambiguous")


def test_every_assistant_write_of_menus_that_takes_a_course_or_a_choice_by_its_name_is_here():
    """No write whose record is a course (``id`` marked as a course) or a choice (marked as a choice) escapes these
    cases."""
    assert {op.name for op in assistant_writes() if id_mark(op) in (A_COURSE, A_CHOICE)} == set(BY_NAME)


# ── Every write reads what it takes by its name, and says it as said when it cannot (hub#1245) ────────────────────────
# The card reads a course by its name with its menu, a choice by its product with its menu and its course, and the
# menu and Inventory's product by their names, in every write, with or without a check before it: what it finds goes
# in the card's fingerprint, so the yes holds to it; what it cannot read (two fit, none does) it says as said, never
# leaving it off the card (base.schemas ``names(…, within=…, as_said=True)``).


def mark_of(op, name: str) -> dict | None:
    """How the card reads the datum ``name`` of ``op``'s input — the mark that names its record, but for the data
    beside which it is left unread (``unless``, below) —, or ``None``."""
    field = op.input.model_fields.get(name)
    mark = field.json_schema_extra if field is not None else None
    return read_as(mark)["refers"] if mark else None


#: How the card reads each datum a write of Menus takes by its name.
SAID_BY_NAME = {
    "combo": names("combo.combo.get", by="combo", as_said=True),
    "group": names("combo.group.get", by="group", within=("combo_id", "combo"), as_said=True),
}


@pytest.mark.parametrize("datum", sorted(SAID_BY_NAME))
def test_every_write_that_takes_a_menu_or_a_course_by_its_name_reads_it_and_says_it_as_said_when_it_cannot(datum):
    """With or without a check before it: a course with its menu, never alone (it would never be found)."""
    taking = {op.name: mark_of(op, datum) for op in assistant_writes() if datum in op.input.model_fields}
    assert taking
    assert all(mark == SAID_BY_NAME[datum]["refers"] for mark in taking.values()), taking


def test_a_choice_is_read_by_its_product_with_its_menu_and_its_course_and_a_product_of_inventory_by_its_name():
    choice = names(
        "combo.option.get", by="product", within=("combo_id", "combo", "group_id", "group"), name=("product_name",),
        as_said=True,
    )["refers"]
    product = names("inventory.product.get", by="product", as_said=True)["refers"]
    marks = {
        (op.name, datum): mark_of(op, datum)
        for op in assistant_writes()
        for datum in ("product", "new_product")
        if datum in op.input.model_fields
    }
    assert marks == {
        ("combo.option.create", "product"): product,
        ("combo.option.delete", "product"): choice,
        ("combo.option.update", "product"): choice,
        ("combo.option.update", "new_product"): product,
    }


#: The writes of Menus that take their menu, or their course, by its name and have no read whose input fits theirs to
#: check it with (``base.E012``: adding or ordering courses and choices).
UNCHECKED = {
    "combo.group.create": lambda combo: {"combo": "vegano", "name": "Bebidas"},
    "combo.option.create": lambda combo: {"combo": "vegano", "group": "postres", "product": "flan"},
    "combo.option.bulk_create": lambda combo: {
        "combo": "vegano", "group": "postres", "product_ids": [str(make_product("Natillas").id)],
    },
    "combo.option.reorder": lambda combo: {
        "combo": "vegano", "group": "postres",
        "option_ids": [str(option.id) for option in ChoiceOption.objects.filter(group__combo=combo)],
    },
}
UNCHECKED_COURSE = sorted(name for name in UNCHECKED if name != "combo.group.create")


@pytest.mark.parametrize("write", sorted(UNCHECKED))
def test_a_menu_two_fit_stays_on_the_card_of_a_write_that_cannot_check_it(write):
    """Adding or ordering courses and choices: «vegano» fits two menus and the card still says «vegano», as said."""
    combo = vegan_desserts()
    vegan_desserts("Menú vegano sin gluten")
    assert fields_of(write, UNCHECKED[write](combo), "es", as_admin())["combo"]["value"] == "vegano"


@pytest.mark.parametrize("write", UNCHECKED_COURSE)
def test_a_course_two_fit_stays_on_the_card_of_a_write_that_cannot_check_it(write):
    """«postres» fits «Postres caseros» and «Postres de temporada»: the card still says «postres», as said."""
    combo = vegan_desserts()
    another("group", combo, ALSO["group"])
    assert fields_of(write, UNCHECKED[write](combo), "es", as_admin())["group"]["value"] == "postres"


@pytest.mark.parametrize("write", sorted(UNCHECKED))
def test_a_write_that_cannot_check_it_says_the_menu_and_the_course_it_finds(write):
    combo = vegan_desserts()
    fields = fields_of(write, UNCHECKED[write](combo), "es", as_admin())
    assert fields["combo"]["value"] == "Menú vegano"
    if "group" in fields:
        assert fields["group"]["value"] == FOUND["group"]


@pytest.mark.parametrize("write", COURSE_OR_CHOICE_WRITES)
def test_the_card_says_the_course_or_the_choice_it_finds(write):
    vegan_desserts()
    datum, _ = BY_NAME[write]
    assert fields_of(write, course_or_choice(write, "Menú vegano"), "es", as_admin())[datum]["value"] == FOUND[datum]


@pytest.mark.parametrize("write", sorted(UNCHECKED))
def test_the_yes_to_adding_or_ordering_touches_only_the_menu_its_card_showed_although_another_fits_the_name_better(
    write,
):
    """«vegano» shows «Menú vegano»; somebody creates «Vegano», with the same course, before the yes: it adds or
    orders nothing in either."""
    combo = vegan_desserts()
    meanwhile, seen = unchanged_after(lambda: vegan_desserts("Vegano"))
    done = yes_to_its_card(as_admin(), write, UNCHECKED[write](combo), meanwhile=meanwhile)
    assert done["executed"] == []
    assert everything() == seen["after"]


@pytest.mark.parametrize(
    ("write", "arguments", "datum"),
    [
        ("combo.option.create", {"combo": "Menú vegano", "group": "postres", "product": "natillas"}, "product"),
        ("combo.option.update", {"combo": "Menú vegano", "product": "flan", "new_product": "natillas"}, "new_product"),
    ],
)
def test_the_card_says_the_product_of_inventory_it_finds_or_as_said_when_two_fit(write, arguments, datum):
    vegan_desserts()
    make_product("Natillas caseras")
    assert fields_of(write, arguments, "es", as_admin())[datum]["value"] == "Natillas caseras"
    make_product("Natillas de chocolate")
    assert fields_of(write, arguments, "es", as_admin())[datum]["value"] == "natillas"


# ── A record that comes by its id with a name the write does not use beside it (hub#1250) ────────────────────────────
# The write takes the menu, the course or the choice by its id (or its course's, or its menu's) and never looks at the
# name beside it; the card neither reads nor shows that name (``unless``), as when the id comes alone: never another
# menu, course, choice or product of Inventory.

#: Beside which data each write of Menus takes its record by them and not by the name: the datum's own id, and the id
#: of the record that holds it (a course's menu is the course's own).
UNLESS = {
    **{(name, "combo"): {"id"} for name in CHECKED_BY_THE_MENU},
    ("combo.group.create", "combo"): {"combo_id"},
    **{(name, "combo"): {"combo_id", "group_id"} for name in UNCHECKED_COURSE},
    **{(name, "combo"): {"id", "combo_id"} for name in ("combo.group.delete", "combo.group.update")},
    **{(name, "combo"): {"id", "combo_id", "group_id"} for name in ("combo.option.delete", "combo.option.update")},
    **{(name, "group"): {"id"} for name in ("combo.group.delete", "combo.group.update")},
    **{(name, "group"): {"group_id"} for name in UNCHECKED_COURSE},
    **{(name, "group"): {"id", "group_id"} for name in ("combo.option.delete", "combo.option.update")},
    ("combo.option.create", "product"): {"product_id"},
    **{(name, "product"): {"id"} for name in ("combo.option.delete", "combo.option.update")},
    ("combo.option.update", "new_product"): {"new_product_id"},
}


def test_a_name_is_left_unread_beside_each_datum_its_write_takes_its_record_by_instead():
    marked = {
        (op.name, datum): unless_of(op.input.model_fields[datum].json_schema_extra)
        for op in assistant_writes()
        for datum in ("combo", "group", "product", "new_product")
        if datum in op.input.model_fields
    }
    assert marked == UNLESS


def infantil() -> Combo:
    """«Menú infantil», whose course «Postres infantiles» offers «Flan infantil»: a name only it fits."""
    combo = make_combo("Menú infantil")
    make_option(make_group(combo, "Postres infantiles"), make_product("Flan infantil"))
    return combo


def beside_an_id() -> dict[str, dict]:
    """The data of a write with its record by its id and, beside it, a name only «Menú infantil» or what it holds
    fits; «Menú vegano» and its «Postres caseros» with «Flan de la casa» are the records of the ids."""
    combo = vegan_desserts()
    infantil()
    course = combo.groups.get(name=FOUND["group"])
    choice = course.options.get()
    natillas = make_product("Natillas")
    return {
        "combo.combo.delete": {"id": str(combo.id), "combo": "infantil"},
        "combo.group.update": {"id": str(course.id), "combo": "infantil", "group": "infantiles", "max_choices": 2},
        "combo.group.create": {"combo_id": str(combo.id), "combo": "infantil", "name": "Bebidas"},
        "combo.option.create": {
            "group_id": str(course.id), "combo": "infantil", "group": "infantiles",
            "product_id": str(natillas.id), "product": "flan infantil",
        },
        "combo.option.update": {
            "id": str(choice.id), "combo": "infantil", "group": "infantiles", "product": "flan infantil",
            "new_product_id": str(natillas.id), "new_product": "flan infantil",
        },
        "combo.option.delete": {"group_id": str(course.id), "combo": "infantil", "product": "flan"},
    }


OF_THE_OTHER = {"Menú infantil", "Postres infantiles", "Flan infantil"}


@pytest.mark.parametrize(
    "write",
    ["combo.combo.delete", "combo.group.create", "combo.group.update", "combo.option.create",
     "combo.option.delete", "combo.option.update"],
)
def test_a_record_that_comes_by_its_id_names_no_other_one_said_beside_it(write):
    shown = fields_of(write, beside_an_id()[write], "es", as_admin())
    assert OF_THE_OTHER.isdisjoint(field["value"] for field in shown.values()), shown


def test_a_choice_that_comes_by_its_course_s_id_is_named_by_its_product_in_that_course():
    """«flan» beside the course's id is how the write finds the choice: the card reads it there, never the menu."""
    shown = fields_of("combo.option.delete", beside_an_id()["combo.option.delete"], "es", as_admin())
    assert (shown["product"]["value"], "combo" in shown) == (FOUND["product"], False)


@pytest.mark.parametrize("write", ["combo.combo.delete", "combo.group.update", "combo.option.update"])
def test_the_yes_to_a_record_that_comes_by_its_id_runs_on_it_whatever_name_is_said_beside_it(write):
    """Control: the write acts on the record of the id, never on what the name beside it fits."""
    arguments = beside_an_id()[write]
    other = Combo.objects.get(name="Menú infantil")
    before = (Combo.objects.values().get(pk=other.pk), list(ChoiceGroup.objects.filter(combo=other).values()),
              list(ChoiceOption.objects.filter(group__combo=other).values()))
    done = yes_to_its_card(as_admin(), write, arguments)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert (Combo.objects.values().get(pk=other.pk), list(ChoiceGroup.objects.filter(combo=other).values()),
            list(ChoiceOption.objects.filter(group__combo=other).values())) == before
