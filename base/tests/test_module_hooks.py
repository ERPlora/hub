"""The row a step reads, as the old hub's ``setup_status.rs`` had it: the cases are those of its tests
(``crates/runtime/src/setup_status.rs`` at ``9dd38215``).
"""

import pytest

from base import home


@pytest.mark.parametrize(
    ("result", "row"),
    [
        ({"rows": [{"a": 1}, {"a": 2}], "total": 2}, {"a": 1}),
        ({"items": [{"b": 1}]}, {"b": 1}),
        ({"rows": [], "total": 0}, None),
        ({"items": []}, None),
        ({"count": 3}, {"count": 3}),  # a single object is its own row (``*.status``, ``count_to_confirm``)
        ({"configured": False, "series": 0}, {"configured": False, "series": 0}),
    ],
)
def test_the_first_row_of_a_result(result, row):
    assert home.module_hooks.first_row(result) == row
