"""A course of a menu and one of its choices, as the assistant's card names them."""

from apps.combo.queries.courses import get_group
from apps.combo.schemas.references import GroupRefIn

from .conftest import HUB_DB, ctx_for, make_combo, make_group, make_option, make_product

pytestmark = HUB_DB


def test_a_course_is_read_with_its_choices_in_their_order():
    course = make_group(make_combo())
    last = make_option(course, make_product("Salad"), sort_order=2)
    first = make_option(course, make_product("Lentils"), sort_order=1)
    found = get_group(ctx_for("hub_employee"), GroupRefIn(id=course.id))
    assert [option.id for option in found.options] == [first.id, last.id]
