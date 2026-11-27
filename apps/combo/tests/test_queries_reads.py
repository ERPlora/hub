"""How a menu, a course and a choice are named (COMBO-F01, F05, F06): by the id, or as a person says it."""

import pytest
from live.errors import Conflict, NotFound

from apps.combo.queries.reads import find_combo

from .conftest import HUB_DB, make_combo, run

pytestmark = HUB_DB


def test_a_menu_is_named_by_its_name_as_said():
    combo = make_combo("Menu of the day")
    make_combo("Kids menu")
    assert run("combo.combo.get", {"combo": "menu of the DAY"}).id == combo.id
    # Part of the name, when only one menu has it.
    assert run("combo.combo.get", {"combo": "day"}).id == combo.id
    with pytest.raises(Conflict) as caught:
        run("combo.combo.get", {"combo": "menu"})
    assert caught.value.code == "combo.combo_ambiguous"
    assert (
        "Kids menu" in caught.value.message
        and "Menu of the day" in caught.value.message
    )
    with pytest.raises(NotFound) as missing:
        run("combo.combo.get", {"combo": "brunch"})
    assert missing.value.message == "That menu does not exist in this business."


def test_a_name_said_whole_wins_over_the_names_that_contain_it():
    day = make_combo("Day")
    make_combo("Menu of the day")
    assert find_combo(None, "DAY") == day


def test_a_menu_said_without_its_accents_is_found():
    day = make_combo("Menú del día QA")
    make_combo("Kids menu")
    assert run("combo.combo.get", {"combo": "menu del dia QA"}).id == day.id
    assert run("combo.combo.get", {"combo": "menu del día qa"}).id == day.id
