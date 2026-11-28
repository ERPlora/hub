"""The reactions to Customers' events read only the card's id from the payload and ignore the rest, never refuse it."""

import uuid

import pytest
from pydantic import ValidationError

from apps.online_booking.schemas.reactions import CustomerEventIn

from .schema_checks import fields_of


def test_a_customer_event_is_read_for_its_card_and_the_rest_is_ignored():
    card = uuid.uuid7()
    assert CustomerEventIn(id=str(card), name="Ana", phone="612345678").model_dump() == {"id": card}
    with pytest.raises(ValidationError) as error:
        CustomerEventIn(name="Ana")
    assert fields_of(error.value) == {"id"}
