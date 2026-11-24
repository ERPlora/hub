"""A refund of the Sales app as Invoicing names it: asked for by its id, answered with its sale, its money and its label."""

import pytest
from pydantic import ValidationError

from apps.invoice.schemas.refunds import RefundGetIn, RefundOut
from apps.invoice.tests.conftest import fields

REFUND = {
    "id": "01999999-0000-7000-8000-000000000001",
    "sale_id": "01999999-0000-7000-8000-000000000002",
    "sale_number": "20261014-0003",
    "total": 500,
    "currency": "EUR",
    "currency_decimals": 2,
    "invoice_number": "",
    "label": "20261014-0003 · €5.00",
}


@pytest.mark.parametrize("wrong", [{}, {"refund_id": "20261014-0003"}])
def test_a_refund_is_asked_for_by_its_id(wrong):
    with pytest.raises(ValidationError) as refused:
        RefundGetIn.model_validate(wrong)
    assert fields(refused.value) == {"refund_id"}


def test_a_refund_is_answered_with_its_sale_its_money_and_its_label():
    assert RefundOut.model_validate(REFUND).model_dump(mode="json") == REFUND


@pytest.mark.parametrize("missing", ["sale_id", "total", "currency_decimals", "label"])
def test_an_answer_without_a_datum_its_card_says_is_refused(missing):
    with pytest.raises(ValidationError) as refused:
        RefundOut.model_validate({key: value for key, value in REFUND.items() if key != missing})
    assert fields(refused.value) == {missing}


def test_its_total_is_read_as_money():
    # The mark the assistant's card reads to say an amount in its currency, never in minor units.
    assert RefundOut.model_json_schema()["properties"]["total"]["money"] is True
