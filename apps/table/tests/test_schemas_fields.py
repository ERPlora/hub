"""The table app's input schemas: what a screen, the assistant or an integration may send (``bad``, which the
tests of every schema module read).

Every input refuses a field it does not declare; a record is named by its id or as a person says it
(«table 4», «the terrace»); lists page at 100 at most.
"""

import uuid

import pytest
from pydantic import ValidationError

from apps.table.schemas.sessions import SessionListIn, SessionRefIn
from apps.table.schemas.tables import TableListIn, TableRefIn
from apps.table.schemas.zones import ZoneListIn, ZoneRefIn

ID = uuid.uuid7()


def bad(schema, **data) -> bool:
    try:
        schema.model_validate(data)
    except ValidationError:
        return True
    return False


def test_an_input_refuses_a_field_it_does_not_declare():
    assert bad(ZoneListIn, colour="red")
    assert bad(TableListIn, hub_id="x")


def test_a_list_pages_at_a_hundred_at_most():
    assert bad(TableListIn, limit=101)
    assert bad(SessionListIn, limit=0)
    assert ZoneListIn.model_validate({}).limit == 50


@pytest.mark.parametrize("schema", [ZoneRefIn, TableRefIn, SessionRefIn])
def test_a_reference_says_which_one(schema):
    assert bad(schema)
