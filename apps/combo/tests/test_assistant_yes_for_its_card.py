"""hub#1208 and hub#1217 in Menus: the yes to the card of a menu said by its name touches only what that card showed.

The platform holds a yes to what its card read (``base/tests/test_assistant_yes_for_its_card.py``). A write of Menus
whose record is the menu takes it by its id or by its name (``ComboRefIn``); said by its name, its card reads it by that
name as the write will find it (``names("combo.combo.get", by="combo")``) and the write checks it before any card
(``"check": "combo.combo.get"``), as Demo does (hub#1206): the card says the menu it found («Menú vegano» when the person
said «vegano»), a name two menus fit or none has draws no card, and a yes after another menu fits the name better runs
nothing and shows the new card (COMBO-F03, COMBO-F04, COMBO-F05, COMBO-F14, BASE-F97).
"""

import dataclasses
import json

import pytest
from live.operations import AI, registry

from apps.combo.models import Combo
from apps.combo.tests.conftest import ctx_for, make_combo, make_group
from apps.combo.tests.test_apps import CHECKED_BY_THE_MENU
from apps.combo.tests.test_assistant_card_records import fields_of, words
from base.schemas import names
from base.tests.test_assistant_yes_for_its_card import turn_as, yes_to_its_card
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

    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("error", "combo.combo_ambiguous")]
    assert json.loads(plan["append"][0]["content"])["error"]["code"] == "combo.combo_ambiguous"


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
    taking = {
        op.name
        for op in registry.values()
        if op.app_label == "combo"
        and op.kind == "command"
        and isinstance(op.ai_spec(), AI)
        and "combo" in op.input.model_fields
        and getattr(op.input.model_fields.get("id"), "json_schema_extra", None) == names("combo.combo.get")
    }
    assert taking == set(WRITES)
