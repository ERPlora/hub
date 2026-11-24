"""How a menu is read with its courses and choices, and what its row says."""

import pytest
from django.db import connections
from django.test.utils import CaptureQueriesContext

from apps.combo.queries.rows import combo_row
from base import images
from base.tenancy.context import current_alias

from .conftest import HUB_DB, A, make_combo, make_group, make_option, make_product, run

pytestmark = HUB_DB


@pytest.mark.parametrize("name", ["combo.combo.get", "combo.combo.resolve"])
def test_a_menu_is_read_with_its_tree_in_as_many_queries_however_big(name):
    # The menu comes with its courses and choices in the read that finds it: one more course or choice
    # is never one more query (nor a second read of the menu, see test_concurrency.py).
    def queries(courses: int, choices: int) -> int:
        combo = make_combo(f"Menu {courses}x{choices}")
        picks = []
        for c in range(courses):
            course = make_group(combo, f"Course {c}", min_choices=1)
            options = [make_option(course, make_product(f"Dish {c}.{n}")) for n in range(choices)]
            picks.append({"option_id": str(options[0].id)})
        data = {"id": str(combo.id)} | ({"choices": picks} if name == "combo.combo.resolve" else {})
        with CaptureQueriesContext(connections[current_alias()]) as read:
            run(name, data)
        return len(read)

    queries(1, 1)  # the business's first read also fills what base keeps per business (its apps off)
    assert queries(3, 3) == queries(1, 1)


def test_a_menu_billed_per_dish_has_no_tax_category_on_its_row():
    row = combo_row(make_combo("Sandwich pack", supply_kind="goods"), 0, images.Urls(A))
    assert (row["tax_category_key"], row["tax_category_name"]) == (None, None)
