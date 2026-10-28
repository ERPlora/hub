"""Models of the payment app: what the database itself refuses, the defaults and how a row reads."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.payment.models import Payment, PaymentCounter, PaymentMethod

from .conftest import make_method, make_payment

pytestmark = pytest.mark.django_db


def test_a_method_is_an_active_bank_transfer_by_default():
    method = PaymentMethod.objects.create(name="BBVA account")
    assert method.method_type == PaymentMethod.Type.TRANSFER
    assert method.is_active is True
    assert method.bank_account_ref == ""
    assert str(method) == "BBVA account"


def test_the_six_method_types_of_the_old_module():
    assert [value for value, _ in PaymentMethod.Type.choices] == [
        "cash",
        "transfer",
        "card",
        "sepa",
        "check",
        "other",
    ]


def test_two_methods_cannot_share_a_name_whatever_the_case():
    make_method("Cash drawer")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_method("CASH DRAWER", method_type="cash")


def test_methods_read_by_name():
    make_method("Zeta")
    make_method("Alpha")
    assert [m.name for m in PaymentMethod.objects.all()] == ["Alpha", "Zeta"]


def test_a_payment_is_a_draft_by_default():
    # Its currency has no default (test_business_currency.py): who records it says it.
    payment = make_payment()
    assert payment.status == Payment.Status.DRAFT
    assert payment.beneficiary_iban == ""
    assert payment.concept == ""
    assert payment.supplier_invoice_ref == ""
    assert payment.cancel_reason == ""
    # The trail of the ladder starts empty: who approved and when each step happened.
    assert (payment.approved_by, payment.approved_at) == ("", None)
    assert (payment.sent_at, payment.completed_at) == (None, None)
    assert (payment.cancelled_by, payment.cancelled_at) == ("", None)
    assert str(payment) == "PAY-20261014-0001"


def test_the_ladder_of_states():
    assert [value for value, _ in Payment.Status.choices] == [
        "draft",
        "approved",
        "sent",
        "completed",
        "cancelled",
    ]


@pytest.mark.parametrize("amount", [0, -1])
def test_the_database_refuses_an_amount_that_is_not_positive(amount):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_payment(amount=amount)


def test_the_database_refuses_an_unknown_status():
    with pytest.raises(IntegrityError), transaction.atomic():
        make_payment(status="lost")


def test_a_reference_is_never_repeated():
    method = make_method()
    make_payment(method, reference="PAY-20261014-0001")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_payment(method, reference="PAY-20261014-0001")


def test_a_method_used_by_a_payment_cannot_be_deleted():
    payment = make_payment()
    with pytest.raises(ProtectedError):
        payment.method.delete()


def test_payments_read_newest_payment_date_first():
    method = make_method()
    make_payment(method, reference="PAY-1", payment_date=dt.date(2026, 1, 5))
    make_payment(method, reference="PAY-2", payment_date=dt.date(2026, 3, 1))
    assert [p.reference for p in Payment.objects.all()] == ["PAY-2", "PAY-1"]


def test_one_counter_per_day():
    PaymentCounter.objects.create(day=dt.date(2026, 10, 14))
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentCounter.objects.create(day=dt.date(2026, 10, 14))
    assert PaymentCounter.objects.get().last == 0
