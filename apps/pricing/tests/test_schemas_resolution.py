"""Input schema of the price of a line: what a caller may send, and the 422 per field of what it may not."""

import datetime as dt
import uuid
from decimal import Decimal

from apps.pricing.schemas.resolution import ResolveIn

from .test_schemas_fields import errors


def test_the_price_of_a_line_names_one_article_and_a_moment_with_its_zone():
    data = ResolveIn(product="Shampoo")
    assert (data.quantity, data.when, data.customer, data.price_list) == (Decimal("1"), None, None, None)
    assert errors(ResolveIn) == {"product": "value_error"}
    assert errors(ResolveIn, product="a", service_id=uuid.uuid7()) == {"product": "value_error"}
    assert "quantity" in errors(ResolveIn, product="a", quantity="0")
    assert "when" in errors(ResolveIn, product="a", when="2026-07-15T10:00:00")
    assert ResolveIn(product="a", when="2026-07-15T10:00:00+02:00").when.utcoffset() == dt.timedelta(hours=2)
