"""What an input of the combo operations refuses before anything is read (a 422 per field)."""

import uuid

import pytest
from pydantic import ValidationError

ID = str(uuid.uuid7())


def fields_of(error: ValidationError) -> dict[str, str]:
    return {".".join(map(str, e["loc"])): e["msg"] for e in error.errors()}


def refused(schema, data) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return fields_of(caught.value)
