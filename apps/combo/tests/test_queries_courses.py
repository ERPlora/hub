"""A course of a menu and one of its choices, as the assistant's card names them."""

from apps.combo.queries.courses import get_group
from apps.combo.schemas.references import GroupRefIn

from .conftest import ALCOHOL, HUB_DB, ctx_for, make_combo, make_group, make_option, make_product

pytestmark = HUB_DB


def test_a_course_to_take_away_says_whether_each_choice_has_a_rate_to_bill_it_at():
    course = make_group(make_combo("Sandwich pack", supply_kind="goods"))
    beer = make_option(course, make_product("Beer", tax=ALCOHOL), sort_order=2)
    box = make_option(course, make_product("Mystery box", tax=None), sort_order=1)
    found = get_group(ctx_for("hub_employee"), GroupRefIn(id=course.id))
    assert [(option.id, option.status) for option in found.options] == [(box.id, "untaxed"), (beer.id, "offered")]
