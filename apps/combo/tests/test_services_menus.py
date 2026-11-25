"""Writes of a menu: create it, change it, withdraw it (WORKBOOK COMBO-F02 to F04).

Each write is one transaction with its events in the outbox and only the fields sent change. Refusals about a field
carry it, so the screen puts them next to it.
"""

import pytest
from live.errors import InvalidPayload, NotFound, PermissionDenied

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from apps.combo.schemas.menus import ComboPatchIn
from apps.combo.services.menus import update_combo

from .conftest import (
    FOOD,
    HUB_DB,
    ctx_for,
    events,
    make_combo,
    make_group,
    make_option,
    make_product,
    run,
)

pytestmark = HUB_DB


def test_a_menu_eaten_in_is_created_with_its_tax_category():
    menu = run(
        "combo.combo.create",
        {
            "name": "Menu of the day",
            "kitchen_name": "MENU",
            "price": 1350,
            "tax_category_key": FOOD,
        },
        ctx_for(actor="marta"),
    )
    combo = Combo.objects.get(pk=menu.id)
    assert (
        combo.name,
        combo.kitchen_name,
        combo.price,
        combo.supply_kind,
        combo.tax_category.key,
    ) == (
        "Menu of the day",
        "MENU",
        1350,
        "service",
        FOOD,
    )
    assert (combo.created_by, combo.updated_by) == ("marta", "marta")
    assert (menu.sellable, menu.groups) == (False, [])
    assert events("combo.combo.created") == [
        {"id": str(combo.id), "name": "Menu of the day"}
    ]


def test_a_menu_eaten_in_without_a_tax_category_is_refused_on_the_field():
    with pytest.raises(InvalidPayload) as caught:
        run("combo.combo.create", {"name": "Menu of the day", "price": 1350})
    assert caught.value.fields == {
        "tax_category_key": "A menu eaten in needs its own VAT category: without it, it cannot be billed."
    }
    assert Combo.objects.count() == 0
    assert events("combo.combo.created") == []


def test_an_unknown_tax_category_is_refused_on_the_field():
    with pytest.raises(InvalidPayload) as caught:
        run("combo.combo.create", {"name": "x", "tax_category_key": "nope.nope"})
    assert caught.value.fields == {
        "tax_category_key": "That tax category does not exist in Taxes."
    }


def test_a_menu_to_take_away_needs_no_tax_category():
    menu = run(
        "combo.combo.create",
        {"name": "Sandwich pack", "price": 600, "supply_kind": "goods"},
    )
    assert (menu.supply_kind, menu.tax_category_key) == ("goods", None)


def test_only_a_manager_builds_menus():
    with pytest.raises(PermissionDenied):
        run(
            "combo.combo.create",
            {"name": "x", "supply_kind": "goods"},
            ctx_for("hub_employee"),
        )


def test_a_change_touches_only_what_is_sent():
    combo = make_combo(
        "Menu of the day",
        price=1350,
        kitchen_name="MENU",
        sort_order=3,
        is_active=False,
    )
    menu = run(
        "combo.combo.update",
        {"combo": "menu of the day", "price": 1400},
        ctx_for(actor="ana"),
    )
    combo.refresh_from_db()
    # The old module put it back on sale, at order 0 and without kitchen name: not any more.
    assert (combo.price, combo.is_active, combo.sort_order, combo.kitchen_name) == (
        1400,
        False,
        3,
        "MENU",
    )
    assert combo.updated_by == "ana"
    assert menu.price == 1400
    assert events("combo.combo.updated") == [
        {"id": str(combo.id), "name": "Menu of the day"}
    ]


def test_a_change_that_changes_nothing_says_nothing():
    combo = make_combo(price=1350)
    run("combo.combo.update", {"id": str(combo.id), "price": 1350})
    assert events("combo.combo.updated") == []


def test_eaten_in_needs_a_category_and_take_away_may_clear_it():
    pack = make_combo("Pack", supply_kind="goods")
    with pytest.raises(InvalidPayload) as caught:
        run("combo.combo.update", {"id": str(pack.id), "supply_kind": "service"})
    assert set(caught.value.fields) == {"tax_category_key"}
    menu = make_combo("Menu")
    run(
        "combo.combo.update",
        {"id": str(menu.id), "supply_kind": "goods", "tax_category_key": None},
    )
    menu.refresh_from_db()
    assert (menu.supply_kind, menu.tax_category) == ("goods", None)
    with pytest.raises(InvalidPayload):
        run(
            "combo.combo.update",
            {"id": str(menu.id), "supply_kind": "service", "tax_category_key": None},
        )


def test_withdrawing_a_menu_takes_its_courses_and_choices():
    combo = make_combo("Menu of the day")
    make_option(make_group(combo), make_product())
    assert run("combo.combo.delete", {"combo": "Menu of the day"}).id == combo.id
    assert (
        Combo.objects.count(),
        ChoiceGroup.objects.count(),
        ChoiceOption.objects.count(),
    ) == (0, 0, 0)
    assert events("combo.combo.deleted") == [
        {"id": str(combo.id), "name": "Menu of the day"}
    ]
    with pytest.raises(NotFound):
        run("combo.combo.delete", {"id": str(combo.id)})


def test_sending_the_tax_category_it_already_has_changes_nothing():
    combo = make_combo(price=1350)
    update_combo(ctx_for(), ComboPatchIn(id=combo.id, tax_category_key=FOOD))
    assert events("combo.combo.updated") == []
