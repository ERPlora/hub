"""What an input of the modifier operations refuses before anything is read (a 422 per field)."""

import pytest
from pydantic import ValidationError


def fields_of(error: ValidationError) -> set[str]:
    return {
        ".".join(str(part) for part in item["loc"]) or "__all__"
        for item in error.errors()
    }


def refused(schema, **data) -> set[str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return fields_of(caught.value)
