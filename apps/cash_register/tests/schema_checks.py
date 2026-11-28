"""What a caller (screen, assistant, API key) may send to the cash register app: the fields an input refuses."""

import pydantic
import pytest


def refused(schema, **data) -> list[str]:
    with pytest.raises(pydantic.ValidationError) as caught:
        schema.model_validate(data)
    return [".".join(str(p) for p in error["loc"]) for error in caught.value.errors()]
