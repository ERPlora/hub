"""The inputs of a table: named by its number and its zone, seats and a shape, a box on the plan, and many at once."""

import pytest

from apps.table.schemas.tables import TableBulkIn, TableIn, TableMoveIn, TableRefIn

from .test_schemas_fields import ID, bad


def test_a_table_is_named_by_its_number_and_its_zone_when_said_aloud():
    ref = TableRefIn.model_validate({"table": " 4 ", "zone": "Terrace"})
    assert (ref.id, ref.table, ref.zone) == (None, "4", "Terrace")


def test_a_new_table_takes_the_factory_values_and_its_number_may_be_left_out():
    table = TableIn.model_validate({"zone_id": str(ID)})
    assert (
        table.number,
        table.capacity,
        table.shape,
        table.position_x,
        table.width,
    ) == (
        None,
        4,
        "square",
        None,
        None,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("capacity", 0),
        ("capacity", 101),
        ("shape", "oval"),
        ("number", "x" * 21),
        ("width", 10),
    ],
)
def test_a_table_seats_one_to_a_hundred_with_a_known_shape_and_a_real_box(field, value):
    assert bad(TableIn, zone_id=str(ID), **{field: value})


def test_many_tables_are_one_to_a_hundred():
    assert bad(TableBulkIn, zone_id=str(ID), count=0)
    assert bad(TableBulkIn, zone_id=str(ID), count=101)
    bulk = TableBulkIn.model_validate({"zone": "Terrace", "count": 12, "prefix": "T"})
    assert (bulk.start_number, bulk.capacity, bulk.shape) == (1, 4, "square")


def test_a_move_stays_on_the_plan():
    assert bad(TableMoveIn, id=str(ID), position_x=-1, position_y=0)
    assert bad(TableMoveIn, id=str(ID), position_x=0, position_y=10_001)
