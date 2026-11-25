"""What an input of the tax operations refuses before anything is read (a 422 per field)."""

import pydantic
import pytest

RULE = {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"}


def invalid_fields(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo:
        schema(**data)
    return {
        ".".join(str(part) for part in error["loc"]) for error in excinfo.value.errors()
    }


def message(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo:
        schema(**data)
    [error] = excinfo.value.errors()
    return str(error["ctx"]["error"])
