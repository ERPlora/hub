"""What the schemas of the online booking app share: every input field says what it is (they are the JSON Schema of
the assistant's tools too) and an input refuses a field it does not declare."""

import pkgutil
from importlib import import_module

import pytest
from pydantic import ValidationError

from apps.online_booking import schemas
from apps.online_booking.schemas.bookings import BookingListIn
from apps.online_booking.schemas.fields import In

from .schema_checks import fields_of


def inputs() -> list[tuple[str, type[In]]]:
    modules = [import_module(f"{schemas.__name__}.{info.name}") for info in pkgutil.iter_modules(schemas.__path__)]
    return [
        (name, model)
        for module in modules
        for name, model in vars(module).items()
        if isinstance(model, type) and issubclass(model, In) and model is not In
    ]


def test_every_input_field_says_what_it_is():
    for name, model in inputs():
        for field, info in model.model_fields.items():
            assert info.description, f"{name}.{field}"


def test_an_input_refuses_a_field_it_does_not_declare():
    with pytest.raises(ValidationError) as error:
        BookingListIn(colour="red")
    assert fields_of(error.value) == {"colour"}
