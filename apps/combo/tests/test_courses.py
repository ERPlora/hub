"""The inputs of a course: how many picks it asks for, which menu it is in and the order of the courses."""

from apps.combo.schemas.courses import GroupIn, GroupPatchIn, GroupReorderIn

from .schema_checks import ID, refused


def test_a_course_defaults_to_one_compulsory_pick():
    course = GroupIn.model_validate({"combo": "Menu of the day", "name": "Starters"})
    assert (course.min_choices, course.max_choices, course.allow_repeat) == (
        1,
        1,
        False,
    )


def test_a_course_ceiling_below_its_floor_is_refused_on_the_maximum():
    fields = refused(
        GroupIn, {"combo_id": ID, "name": "Mains", "min_choices": 2, "max_choices": 1}
    )
    assert fields["max_choices"].endswith(
        "The maximum (1) is below the minimum (2): nobody could ever satisfy this course."
    )
    assert (
        GroupIn.model_validate(
            {"combo_id": ID, "name": "Drinks", "min_choices": 2, "max_choices": 0}
        ).max_choices
        == 0
    )


def test_a_course_asks_for_fifty_at_most():
    assert "min_choices" in refused(
        GroupIn, {"combo_id": ID, "name": "x", "min_choices": 51, "max_choices": 0}
    )
    assert "max_choices" in refused(
        GroupIn, {"combo_id": ID, "name": "x", "max_choices": 51}
    )


def test_a_course_belongs_to_a_menu_named_by_id_or_name():
    assert refused(GroupIn, {"name": "Starters"})


def test_a_course_change_checks_its_own_ceiling_when_both_are_sent():
    assert "max_choices" in refused(
        GroupPatchIn, {"id": ID, "min_choices": 3, "max_choices": 2}
    )
    assert GroupPatchIn.model_validate(
        {"id": ID, "max_choices": 2}
    ).model_fields_set == {"id", "max_choices"}


def test_reordering_courses_names_each_once():
    assert refused(GroupReorderIn, {"id": ID, "group_ids": [ID, ID]})
    assert refused(GroupReorderIn, {"id": ID, "group_ids": []})
