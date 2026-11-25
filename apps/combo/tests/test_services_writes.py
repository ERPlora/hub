"""What the writes of menus, courses and choices share."""

import pytest
from live.errors import Conflict

from apps.combo.services.writes import _reordered

from .conftest import HUB_DB, make_combo, make_group

pytestmark = HUB_DB


def test_an_order_that_names_one_of_them_twice_is_refused():
    combo = make_combo()
    a, b = make_group(combo, "A"), make_group(combo, "B")
    with pytest.raises(Conflict) as caught:
        _reordered(combo.groups.all(), [a.id, a.id, b.id])
    assert caught.value.code == "combo.reorder_mismatch"
