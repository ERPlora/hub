"""Input schemas of the payment app: what an operation refuses before it touches the database.

The amount cases come from the old module's handler (Rust, `create_payment`): money travels in whole
minor units and a payment of 0 or less is refused; the currency of a payment is a real ISO 4217 code,
uppercased; and the old «no IBAN validation» is gone (python-stdnum checks it).
"""

import datetime as dt
import uuid

import pytest
from django.utils import translation
from pydantic import ValidationError

from apps.payment.schemas import (
    AMOUNT_NOT_POSITIVE,
    CURRENCY_UNKNOWN,
    IBAN_INVALID,
    MAX_AMOUNT,
    REASON_REQUIRED,
    SAY_WHICH_METHOD,
    SAY_WHICH_PAYMENT,
    CancelIn,
    MethodIn,
    MethodListIn,
    MethodPatchIn,
    MethodRefIn,
    PaymentIn,
    PaymentListIn,
    PaymentRefIn,
)

METHOD = uuid.uuid7()


def payment_in(**fields) -> PaymentIn:
    data = {
        "method_id": METHOD,
        "payment_date": "2026-10-14",
        "amount": 1250,
        "beneficiary_name": "Proveedor Norte SL",
    } | fields
    return PaymentIn(**data)


def messages(error: ValidationError) -> dict[str, str]:
    return {
        ".".join(str(part) for part in item["loc"]): str(
            (item.get("ctx") or {}).get("error") or item["msg"]
        )
        for item in error.errors()
    }


# Payments


def test_a_payment_in_minor_units_with_the_optional_fields_empty():
    data = payment_in()
    assert data.amount == 1250
    assert data.payment_date == dt.date(2026, 10, 14)
    assert data.currency is None
    assert data.beneficiary_iban == ""
    assert data.concept == ""
    assert data.supplier_invoice_ref == ""


@pytest.mark.parametrize("amount", [0, -5])
def test_an_amount_of_zero_or_less_is_refused_with_its_reason(amount):
    with pytest.raises(ValidationError) as caught:
        payment_in(amount=amount)
    assert messages(caught.value) == {"amount": str(AMOUNT_NOT_POSITIVE)}


def test_an_amount_with_cents_after_the_minor_unit_is_refused():
    # The schema is integer minor units: 12.5 cents is not an amount (the old handler rounded it).
    with pytest.raises(ValidationError):
        payment_in(amount=12.5)


def test_an_amount_above_the_ceiling_is_refused():
    assert payment_in(amount=MAX_AMOUNT).amount == MAX_AMOUNT
    with pytest.raises(ValidationError):
        payment_in(amount=MAX_AMOUNT + 1)


def test_the_beneficiary_is_kept_trimmed_and_cannot_be_blank():
    assert payment_in(beneficiary_name="  Ana  ").beneficiary_name == "Ana"
    with pytest.raises(ValidationError) as caught:
        payment_in(beneficiary_name="   ")
    assert "beneficiary_name" in messages(caught.value)


def test_the_date_is_a_calendar_day():
    with pytest.raises(ValidationError):
        payment_in(payment_date="14/10/2026")


def test_the_method_is_said_by_its_id_or_its_name():
    assert payment_in(method_id=None, method="Cash drawer").method == "Cash drawer"
    with pytest.raises(ValidationError) as caught:
        payment_in(method_id=None)
    assert str(SAY_WHICH_METHOD) in messages(caught.value).values()


def test_the_currency_is_an_iso_code_uppercased():
    assert payment_in(currency="usd").currency == "USD"
    assert payment_in(currency=" jpy ").currency == "JPY"
    # Blank counts as absent: the business's currency (the old payments#38).
    assert payment_in(currency="  ").currency is None
    with pytest.raises(ValidationError) as caught:
        payment_in(currency="XYZ")
    assert messages(caught.value) == {"currency": str(CURRENCY_UNKNOWN)}


def test_a_valid_iban_is_kept_compact_and_uppercase():
    assert (
        payment_in(beneficiary_iban="es91 2100 0418 4502 0005 1332").beneficiary_iban
        == "ES9121000418450200051332"
    )


@pytest.mark.parametrize(
    "iban", ["ES9121000418450200051333", "XX00", "not an iban", "ES91 2100"]
)
def test_an_invalid_iban_is_refused_with_its_reason(iban):
    with pytest.raises(ValidationError) as caught:
        payment_in(beneficiary_iban=iban)
    assert messages(caught.value) == {"beneficiary_iban": str(IBAN_INVALID)}


def test_the_attempt_key_is_a_uuid_and_optional():
    # payments#8: a caller that may send twice (a retry, a double tap) says which attempt it is.
    key = "0192f0a4-6f43-7b4e-9a8e-2f1c3d4b5a69"
    assert str(payment_in(idempotency_key=key).idempotency_key) == key
    assert payment_in().idempotency_key is None
    with pytest.raises(ValidationError) as caught:
        payment_in(idempotency_key="twice")
    assert list(messages(caught.value)) == ["idempotency_key"]


def test_an_unknown_field_is_refused():
    with pytest.raises(ValidationError):
        payment_in(status="approved")


def test_a_payment_is_said_by_its_id_or_its_reference():
    assert (
        PaymentRefIn(reference=" pay-20261014-0001 ").reference == "PAY-20261014-0001"
    )
    with pytest.raises(ValidationError) as caught:
        PaymentRefIn()
    assert str(SAY_WHICH_PAYMENT) in messages(caught.value).values()


def test_cancelling_needs_a_reason():
    assert CancelIn(reference="PAY-1", reason="  duplicated  ").reason == "duplicated"
    with pytest.raises(ValidationError) as caught:
        CancelIn(reference="PAY-1", reason="   ")
    assert messages(caught.value) == {"reason": str(REASON_REQUIRED)}
    with pytest.raises(ValidationError):
        CancelIn(reference="PAY-1")


def test_the_list_pages_up_to_a_hundred_newest_payment_date_first():
    params = PaymentListIn()
    assert (params.limit, params.offset, params.sort) == (50, 0, "-payment_date")
    with pytest.raises(ValidationError):
        PaymentListIn(limit=101)
    with pytest.raises(ValidationError):
        PaymentListIn(sort="beneficiary_iban")
    with pytest.raises(ValidationError):
        PaymentListIn(f_status="draft")


# Methods


def test_a_new_method_is_a_bank_transfer_unless_said():
    data = MethodIn(name="  BBVA   account ")
    assert (data.name, data.method_type, data.bank_account_ref) == (
        "BBVA account",
        "transfer",
        "",
    )
    with pytest.raises(ValidationError):
        MethodIn(name="Cash", method_type="crypto")
    with pytest.raises(ValidationError):
        MethodIn(name="  ")


def test_a_method_is_said_by_its_id_or_its_name():
    assert MethodRefIn(method="Cash").method == "Cash"
    with pytest.raises(ValidationError) as caught:
        MethodRefIn()
    assert str(SAY_WHICH_METHOD) in messages(caught.value).values()
    patch = MethodPatchIn(id=METHOD, bank_account_ref="ES91…1332")
    assert patch.model_fields_set == {"id", "bank_account_ref"}


def test_the_method_list_filters_by_type_and_state():
    params = MethodListIn(method_type="cash", is_active=False)
    assert (params.method_type, params.is_active, params.sort) == (
        "cash",
        False,
        "name",
    )


def test_the_messages_read_in_spanish():
    with translation.override("es"):
        assert (
            str(AMOUNT_NOT_POSITIVE)
            == "El importe de un pago tiene que ser mayor que 0."
        )
        assert str(IBAN_INVALID) == (
            "Ese IBAN no es válido: revisa el país, los dígitos de control y la longitud."
        )
