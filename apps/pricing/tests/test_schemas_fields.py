"""Input schemas of the pricing app: what a caller may send, and the 422 per field of what it may not (``errors``, which
the tests of every schema module read). Here, the page every list reads."""

import pytest
from pydantic import ValidationError

from apps.pricing.schemas.fields import PageIn
from apps.pricing.schemas.price_lists import PriceListListIn


def errors(schema, **data) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return {".".join(str(p) for p in e["loc"]): e["type"] for e in caught.value.errors()}


def test_a_page_asks_for_at_most_100_rows_and_refuses_an_unknown_filter():
    assert (PageIn().limit, PageIn().offset) == (50, 0)
    assert "limit" in errors(PageIn, limit=101)
    assert "offset" in errors(PageIn, offset=-1)
    assert errors(PriceListListIn, colour="red") == {"colour": "extra_forbidden"}
