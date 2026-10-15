"""Writes of the combo app: menus, courses and choices (WORKBOOK COMBO-F02 to F06, F12, F13).

Each write is one transaction with its events in the outbox; only the fields sent change; a new
course or choice goes last; reordering takes the whole list at once. Refusals about a field carry it,
so the screen puts them next to it.
"""

import pytest
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo

from .conftest import (
    A,
    DRINK,
    FOOD,
    ctx_for,
    make_combo,
    make_group,
    make_option,
    make_product,
    run,
)

pytestmark = pytest.mark.django_db


def events(name: str) -> list[dict]:
    return [
        event.payload
        for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")
    ]


# Menus (COMBO-F02, F03, F04)


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


# Courses (COMBO-F05)


def test_a_course_goes_last_in_its_menu():
    combo = make_combo("Menu of the day")
    make_group(combo, "Starters", sort_order=7)
    course = run(
        "combo.group.create",
        {
            "combo": "menu of the day",
            "name": "Mains",
            "min_choices": 1,
            "max_choices": 2,
        },
    )
    assert (
        course.name,
        course.sort_order,
        course.min_choices,
        course.max_choices,
        course.options,
    ) == (
        "Mains",
        8,
        1,
        2,
        [],
    )
    assert events("combo.group.created") == [
        {"id": str(course.id), "combo_id": str(combo.id)}
    ]


def test_two_courses_with_the_same_name_in_one_menu_are_refused():
    combo = make_combo()
    make_group(combo, "Starters")
    with pytest.raises(Conflict) as caught:
        run("combo.group.create", {"combo_id": str(combo.id), "name": "STARTERS"})
    assert caught.value.code == "combo.group_exists"
    assert caught.value.fields == {"name": "That menu already has a course “STARTERS”."}


def test_a_menu_holds_twenty_courses_at_most():
    combo = make_combo()
    for n in range(20):
        make_group(combo, f"Course {n}")
    with pytest.raises(Conflict) as caught:
        run("combo.group.create", {"combo_id": str(combo.id), "name": "One more"})
    assert (caught.value.code, caught.value.message) == (
        "combo.too_many_groups",
        "A menu holds 20 courses at most.",
    )


def test_a_course_change_keeps_its_place_and_what_is_not_sent():
    combo = make_combo("Menu of the day")
    course = make_group(
        combo, "Starters", sort_order=4, min_choices=1, max_choices=2, allow_repeat=True
    )
    out = run(
        "combo.group.update",
        {"combo": "Menu of the day", "group": "starters", "min_choices": 2},
    )
    course.refresh_from_db()
    # The old module sent it to the top and back to 1 and 1.
    assert (
        course.sort_order,
        course.min_choices,
        course.max_choices,
        course.allow_repeat,
    ) == (4, 2, 2, True)
    assert out.min_choices == 2
    assert events("combo.group.updated") == [
        {"id": str(course.id), "combo_id": str(combo.id)}
    ]


def test_a_course_change_checks_the_ceiling_against_what_it_keeps():
    course = make_group(make_combo(), "Mains", min_choices=1, max_choices=1)
    with pytest.raises(InvalidPayload) as caught:
        run("combo.group.update", {"id": str(course.id), "min_choices": 3})
    assert caught.value.fields == {
        "min_choices": "The maximum (1) is below the minimum (3): nobody could ever satisfy this course."
    }


def test_renaming_a_course_to_a_name_in_use_is_refused():
    combo = make_combo()
    make_group(combo, "Starters")
    mains = make_group(combo, "Mains")
    with pytest.raises(Conflict) as caught:
        run("combo.group.update", {"id": str(mains.id), "name": "starters"})
    assert caught.value.code == "combo.group_exists"


def test_withdrawing_a_course_takes_its_choices():
    course = make_group(make_combo())
    make_option(course, make_product())
    assert run("combo.group.delete", {"id": str(course.id)}).id == course.id
    assert (ChoiceGroup.objects.count(), ChoiceOption.objects.count()) == (0, 0)
    assert events("combo.group.deleted") == [
        {"id": str(course.id), "combo_id": str(course.combo_id)}
    ]


def test_reordering_courses_saves_the_whole_order_at_once():
    combo = make_combo()
    a, b, c = (make_group(combo, name) for name in ("A", "B", "C"))
    menu = run(
        "combo.group.reorder",
        {"id": str(combo.id), "group_ids": [str(c.id), str(a.id), str(b.id)]},
    )
    assert [g.name for g in menu.groups] == ["C", "A", "B"]
    assert [g.sort_order for g in menu.groups] == [0, 1, 2]
    assert events("combo.group.reordered") == [{"combo_id": str(combo.id)}]


def test_reordering_needs_every_course_of_the_menu_and_nothing_else():
    combo = make_combo()
    a, b = make_group(combo, "A"), make_group(combo, "B")
    other = make_group(make_combo("Other"), "X")
    for ids in ([a.id], [a.id, b.id, other.id], [a.id, other.id]):
        with pytest.raises(Conflict) as caught:
            run(
                "combo.group.reorder",
                {"id": str(combo.id), "group_ids": [str(i) for i in ids]},
            )
        assert caught.value.code == "combo.reorder_mismatch"


# Choices (COMBO-F06, F12)


def test_a_choice_is_a_product_named_as_said_and_goes_last():
    combo = make_combo("Menu of the day")
    course = make_group(combo, "Mains")
    make_option(course, make_product("Chicken"), sort_order=5)
    hake = make_product("Hake", price=1400, sku="HAK")
    option = run(
        "combo.option.create",
        {
            "combo": "Menu of the day",
            "group": "mains",
            "product": "hak",
            "price_delta": 200,
        },
    )
    assert (
        option.product_id,
        option.product_name,
        option.catalog_price,
        option.price_delta,
        option.sort_order,
    ) == (
        hake.id,
        "Hake",
        1400,
        200,
        6,
    )
    assert option.status == "offered"
    assert events("combo.option.created") == [
        {
            "id": str(option.id),
            "group_id": str(course.id),
            "combo_id": str(combo.id),
            "product_id": str(hake.id),
        }
    ]


def test_the_same_product_twice_in_a_course_is_refused():
    course = make_group(make_combo())
    lentils = make_product("Lentils")
    make_option(course, lentils)
    with pytest.raises(Conflict) as caught:
        run(
            "combo.option.create",
            {"group_id": str(course.id), "product_id": str(lentils.id)},
        )
    assert caught.value.code == "combo.option_exists"
    assert caught.value.fields == {
        "product_id": "This course already offers that product. To let it be picked twice, switch on "
        "«the same choice may be picked more than once»."
    }


def test_a_product_that_cannot_be_sold_is_refused():
    course = make_group(make_combo())
    with pytest.raises(Conflict) as inactive:
        run(
            "combo.option.create",
            {
                "group_id": str(course.id),
                "product_id": str(make_product("Old", is_active=False).id),
            },
        )
    assert inactive.value.code == "combo.product_inactive"
    with pytest.raises(Conflict) as by_weight:
        run(
            "combo.option.create",
            {
                "group_id": str(course.id),
                "product_id": str(make_product("Ham", unit="kg").id),
            },
        )
    assert by_weight.value.code == "combo.product_not_by_unit"
    gone = make_product("Gone", is_deleted=True)
    with pytest.raises(InvalidPayload) as deleted:
        run(
            "combo.option.create",
            {"group_id": str(course.id), "product_id": str(gone.id)},
        )
    assert set(deleted.value.fields) == {"product_id"}
    with pytest.raises(InvalidPayload) as unknown:
        run(
            "combo.option.create",
            {"group_id": str(course.id), "product": "nothing like it"},
        )
    assert set(unknown.value.fields) == {"product"}


def test_a_course_holds_forty_choices_at_most():
    course = make_group(make_combo())
    for n in range(40):
        make_option(course, make_product(f"Dish {n}"))
    with pytest.raises(Conflict) as caught:
        run(
            "combo.option.create",
            {
                "group_id": str(course.id),
                "product_id": str(make_product("One more").id),
            },
        )
    assert caught.value.code == "combo.too_many_options"


def test_several_choices_go_in_at_once_in_the_order_ticked():
    course = make_group(make_combo())
    make_option(course, make_product("First"))
    b, c = make_product("B"), make_product("C")
    out = run(
        "combo.option.bulk_create",
        {"group_id": str(course.id), "product_ids": [str(c.id), str(b.id)]},
    )
    assert [(o.product_name, o.sort_order, o.price_delta) for o in out.options] == [
        ("First", 0, 0),
        ("C", 1, 0),
        ("B", 2, 0),
    ]
    assert len(events("combo.option.created")) == 2


def test_several_choices_are_all_or_nothing():
    course = make_group(make_combo())
    lentils = make_product("Lentils")
    make_option(course, lentils)
    fresh = make_product("Fresh")
    with pytest.raises(Conflict) as caught:
        run(
            "combo.option.bulk_create",
            {
                "group_id": str(course.id),
                "product_ids": [str(fresh.id), str(lentils.id)],
            },
        )
    assert caught.value.code == "combo.option_exists"
    assert "Lentils" in caught.value.message
    assert course.options.count() == 1


def test_a_choice_change_keeps_its_place_and_what_is_not_sent():
    combo = make_combo("Menu of the day")
    course = make_group(combo, "Mains")
    option = make_option(course, make_product("Hake"), price_delta=200, sort_order=3)
    run(
        "combo.option.update",
        {"combo": "Menu of the day", "product": "hake", "is_available": False},
    )
    option.refresh_from_db()
    # The old module set the supplement to 0 and sent it to the top.
    assert (option.is_available, option.price_delta, option.sort_order) == (
        False,
        200,
        3,
    )
    assert events("combo.option.updated") == [
        {
            "id": str(option.id),
            "group_id": str(course.id),
            "combo_id": str(combo.id),
            "product_id": str(option.product_id),
        }
    ]


def test_a_choice_may_change_its_product_and_keep_its_place():
    course = make_group(make_combo())
    option = make_option(course, make_product("Hake"), sort_order=2)
    taken = make_product("Chicken")
    make_option(course, taken)
    sole = make_product("Sole", sku="SOL")
    out = run("combo.option.update", {"id": str(option.id), "new_product": "SOL"})
    assert (out.product_id, out.sort_order) == (sole.id, 2)
    with pytest.raises(Conflict) as caught:
        run(
            "combo.option.update",
            {"id": str(option.id), "new_product_id": str(taken.id)},
        )
    assert caught.value.code == "combo.option_exists"
    assert set(caught.value.fields) == {"new_product_id"}


def test_removing_a_choice():
    option = make_option(make_group(make_combo()), make_product())
    assert run("combo.option.delete", {"id": str(option.id)}).id == option.id
    assert ChoiceOption.objects.count() == 0
    assert events("combo.option.deleted")[0]["id"] == str(option.id)


def test_reordering_choices_saves_the_whole_order_at_once():
    course = make_group(make_combo())
    a, b = (
        make_option(course, make_product("A")),
        make_option(course, make_product("B")),
    )
    out = run(
        "combo.option.reorder",
        {"group_id": str(course.id), "option_ids": [str(b.id), str(a.id)]},
    )
    assert [(o.product_name, o.sort_order) for o in out.options] == [("B", 0), ("A", 1)]
    assert events("combo.option.reordered") == [
        {"group_id": str(course.id), "combo_id": str(course.combo_id)}
    ]
    with pytest.raises(Conflict) as caught:
        run(
            "combo.option.reorder",
            {"group_id": str(course.id), "option_ids": [str(b.id)]},
        )
    assert caught.value.code == "combo.reorder_mismatch"


# The reaction to a deleted product (COMBO-F13)


def test_a_deleted_product_leaves_every_menu_once():
    flan = make_product("Flan", sku="FLAN")
    day, kids = make_combo("Menu of the day"), make_combo("Kids menu")
    first = make_option(make_group(day, "Dessert"), flan)
    second = make_option(make_group(kids, "Dessert"), flan)
    kept = make_option(make_group(day, "Mains"), make_product("Hake"))
    payload = {"id": str(flan.id), "sku": "FLAN", "name": "Flan"}
    assert run("combo.option.drop_product", payload, system_context(A)).dropped == 2
    assert list(ChoiceOption.objects.all()) == [kept]
    dropped = events("combo.option.deleted")
    assert {event["id"] for event in dropped} == {str(first.id), str(second.id)}
    assert {event["reason"] for event in dropped} == {"product_deleted"}
    # The same notice twice changes nothing.
    assert run("combo.option.drop_product", payload, system_context(A)).dropped == 0


def test_no_person_runs_the_reaction():
    with pytest.raises(PermissionDenied):
        run(
            "combo.option.drop_product",
            {"id": str(make_product().id)},
            ctx_for("hub_owner"),
        )


def test_choices_of_two_menus_do_not_mix():
    course = make_group(make_combo("Menu of the day"), "Drink")
    make_option(course, make_product("Water", tax=DRINK))
    other = make_group(make_combo("Kids menu"), "Drink")
    with pytest.raises(NotFound):
        run(
            "combo.option.update",
            {"combo": "Kids menu", "product": "Water", "is_available": False},
        )
    assert other.options.count() == 0


def test_a_product_priced_per_several_units_is_not_a_portion():
    # «0,37 € per 100 ud»: one pick would weigh a hundredth of what the catalogue says (review 9).
    from decimal import Decimal

    course = make_group(make_combo())
    napkins = make_product("Napkins", price=37, price_quantity=Decimal("100"))
    with pytest.raises(Conflict) as caught:
        run("combo.option.create", {"group_id": str(course.id), "product_id": str(napkins.id)})
    assert caught.value.code == "combo.product_not_by_unit"
    with pytest.raises(Conflict):
        run("combo.option.bulk_create", {"group_id": str(course.id), "product_ids": [str(napkins.id)]})
