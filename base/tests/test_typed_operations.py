"""``ts_fields`` reads a hand-written type of a page's operations (``frontend/operations.d.ts``) the way vue-tsc does:
its own fields, the optional ones too, and the ones it inherits."""

import pytest

from base.tests.typed_operations import ts_fields

OPERATIONS = """\
export interface PageIn {
  limit?: number;
  offset?: number;
}

export interface ItemListIn extends PageIn {
  cart_id: string;
  search?: string;
}

export interface ItemDetailOut extends ItemListIn {
  label: string;
}
"""


@pytest.fixture
def operations_ts(tmp_path):
    path = tmp_path / "operations.d.ts"
    path.write_text(OPERATIONS)
    return path


def test_a_type_has_its_own_fields_optional_ones_included(operations_ts):
    assert ts_fields("PageIn", operations_ts) == {"limit", "offset"}


def test_a_type_has_the_fields_it_inherits_down_the_chain(operations_ts):
    assert ts_fields("ItemListIn", operations_ts) == {"cart_id", "search", "limit", "offset"}
    assert ts_fields("ItemDetailOut", operations_ts) == {"label", "cart_id", "search", "limit", "offset"}


def test_a_type_that_is_not_declared_fails_by_its_name(operations_ts):
    with pytest.raises(AssertionError, match="ItemOut is not in"):
        ts_fields("ItemOut", operations_ts)
