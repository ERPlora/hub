"""The input schemas of the kitchen app: what they accept, what they refuse (422 per field) and how a
person names a record (assistant, voice). Here, what every input shares: the closed input, the page and
naming a ticket; ``refuses``, which the tests of every schema module read."""

import uuid

from pydantic import ValidationError

from apps.kitchen.schemas.fields import TicketRefIn
from apps.kitchen.schemas.history import LogListIn
from apps.kitchen.schemas.stations import StationIn
from apps.kitchen.schemas.tickets import TicketListIn


def refuses(schema, **data) -> bool:
    try:
        schema.model_validate(data)
    except ValidationError:
        return True
    return False


def test_every_input_refuses_a_field_it_does_not_declare():
    assert refuses(TicketListIn, colour="red")
    assert refuses(StationIn, name="Grill", fire=True)


def test_a_page_is_one_to_a_hundred_rows():
    assert TicketListIn.model_validate({}).limit == 50
    assert refuses(TicketListIn, limit=101)
    assert refuses(TicketListIn, limit=0)
    assert refuses(LogListIn, offset=-1)


def test_a_ticket_is_named_by_its_id_or_as_a_person_says_it():
    by_id = TicketRefIn.model_validate({"ticket_id": str(uuid.uuid7())})
    said = TicketRefIn.model_validate({"ticket": "  Table 4 "})
    assert by_id.ticket_id and said.ticket == "Table 4"
    assert refuses(TicketRefIn)
