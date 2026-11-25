"""Writes of a course's choices (WORKBOOK COMBO-F06, F12) and the reaction to a product deleted in Inventory
(COMBO-F13). A choice is a product that can be sold by the unit; a new one goes last, a change keeps its place."""

import pytest
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from apps.combo.models import ChoiceOption
from apps.combo.schemas.choices import OptionBulkIn
from apps.combo.services.choices import bulk_create_options

from .conftest import (
    A,
    DRINK,
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
    # «0,37 € per 100 ud»: one pick would weigh a hundredth of what the catalogue says.
    from decimal import Decimal

    course = make_group(make_combo())
    napkins = make_product("Napkins", price=37, price_quantity=Decimal("100"))
    with pytest.raises(Conflict) as caught:
        run("combo.option.create", {"group_id": str(course.id), "product_id": str(napkins.id)})
    assert caught.value.code == "combo.product_not_by_unit"
    with pytest.raises(Conflict):
        run("combo.option.bulk_create", {"group_id": str(course.id), "product_ids": [str(napkins.id)]})


def test_several_choices_that_would_pass_forty_are_refused_together():
    course = make_group(make_combo())
    for n in range(39):
        make_option(course, make_product(f"Dish {n}"))
    extra = [make_product("One more").id, make_product("And another").id]
    with pytest.raises(Conflict) as caught:
        bulk_create_options(ctx_for(), OptionBulkIn(group_id=course.id, product_ids=extra))
    assert caught.value.code == "combo.too_many_options"
    assert course.options.count() == 39
