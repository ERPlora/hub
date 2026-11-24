"""Inputs of the rectifying invoices: one by hand, and the payloads of Sales that issue one by themselves."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from apps.invoice.schemas.rectifying import FromRefundIn, FromVoidIn, RectifyIn
from apps.invoice.tests.conftest import fields


def test_a_rectification_picks_r1_to_r4_and_needs_a_reason():
    ok = RectifyIn.model_validate(
        {"number": "F-1", "reason": " wrong price ", "rectification_type": "R4"}
    )
    assert (ok.reason, ok.rectification_type) == ("wrong price", "R4")
    with pytest.raises(ValidationError) as refused:
        RectifyIn.model_validate(
            {"number": "F-1", "reason": "x", "rectification_type": "R5"}
        )
    assert fields(refused.value) == {"rectification_type"}
    with pytest.raises(ValidationError) as refused:
        RectifyIn.model_validate({"number": "F-1", "reason": "  "})
    assert fields(refused.value) == {"reason"}


@pytest.mark.parametrize(("payload", "key"), [(FromRefundIn, "refund_id"), (FromVoidIn, "sale_id")])
def test_a_payload_of_sales_is_read_by_its_id_and_its_other_keys_are_ignored(payload, key):
    an_id = "01999999-0000-7000-8000-000000000000"
    data = payload.model_validate({key: an_id, "items": [{"x": 1}]})
    assert data.model_dump() == {key: UUID(an_id)}
    with pytest.raises(ValidationError) as refused:
        payload.model_validate({"items": [{"x": 1}]})
    assert fields(refused.value) == {key}
