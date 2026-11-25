"""Writes of a menu's courses (WORKBOOK COMBO-F05): a new course goes last, a change keeps its place, and reordering
takes the whole list at once."""

import pytest
from live.errors import Conflict, InvalidPayload

from apps.combo.models import ChoiceGroup, ChoiceOption
from apps.combo.schemas.courses import GroupPatchIn
from apps.combo.services.courses import update_group

from .conftest import (
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


def test_a_course_may_write_its_own_name_in_other_letters():
    course = make_group(make_combo(), "starters")
    out = update_group(ctx_for(), GroupPatchIn(id=course.id, name="Starters"))
    assert out.name == "Starters"
