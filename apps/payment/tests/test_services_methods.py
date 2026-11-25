"""Writes of the payment methods: create, edit, deactivate and activate (PAYMENT-F01, F08). A name is unique whatever
the case, and a refusal says why and records no event."""

import uuid

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.payment.models import PaymentMethod

from .conftest import HUB_DB, make_method
from .test_services import bank, business_today, events, payload, run

#: The fixtures these tests take from test_services.py: the method a test starts from and the business's day.
__all__ = ["bank", "business_today"]

pytestmark = HUB_DB


# ── Methods (PAYMENT-F01, F08) ────────────────────────────────────────────────────────────────


def test_creating_a_method(bank):
    method = run(
        "payment.method.create",
        {"name": "Cash  drawer", "method_type": "cash", "bank_account_ref": ""},
        actor="Ana",
    )
    assert (method.name, method.method_type, method.is_active) == (
        "Cash drawer",
        "cash",
        True,
    )
    stored = PaymentMethod.objects.get(pk=method.id)
    assert (stored.created_by, stored.updated_by) == ("Ana", "Ana")
    assert events() == ["payment.method.created"]
    assert payload("payment.method.created") == {
        "id": str(method.id),
        "name": "Cash drawer",
    }


def test_a_method_name_is_unique_whatever_the_case(bank):
    with pytest.raises(Conflict) as caught:
        run("payment.method.create", {"name": "bbva ACCOUNT"})
    assert caught.value.code == "payment.method_exists"
    assert caught.value.fields == {
        "name": "There is already a payment method with that name. Pick another name."
    }
    assert events() == []


def test_editing_a_method_changes_only_what_is_sent(bank):
    method = run(
        "payment.method.update",
        {"method": "bbva", "bank_account_ref": "ES91…1332"},
        actor="Bea",
    )
    assert (method.name, method.method_type, method.bank_account_ref) == (
        "BBVA account",
        "transfer",
        "*****1332",
    )
    assert PaymentMethod.objects.get(pk=bank.pk).bank_account_ref == "ES91…1332"
    assert PaymentMethod.objects.get(pk=bank.pk).updated_by == "Bea"
    assert events() == ["payment.method.updated"]
    assert payload("payment.method.updated") == {
        "id": str(bank.id),
        "name": "BBVA account",
        "changed": ["bank_account_ref"],
    }


def test_editing_a_method_with_nothing_new_records_nothing(bank):
    run("payment.method.update", {"id": str(bank.id), "name": "BBVA account"})
    assert events() == []


def test_renaming_a_method_to_another_ones_name_is_refused(bank):
    make_method("Cash drawer", method_type="cash")
    with pytest.raises(Conflict) as caught:
        run("payment.method.update", {"id": str(bank.id), "name": "CASH drawer"})
    assert caught.value.code == "payment.method_exists"
    assert "name" in caught.value.fields
    # Its own name in another case is not «another one's».
    assert (
        run("payment.method.update", {"id": str(bank.id), "name": "Bbva Account"}).name
        == "Bbva Account"
    )


def test_a_method_that_does_not_exist(bank):
    with pytest.raises(NotFound) as caught:
        run("payment.method.update", {"id": str(uuid.uuid7()), "name": "X"})
    assert caught.value.code == "payment.method_not_found"


def test_deactivating_and_activating_a_method(bank):
    assert run("payment.method.deactivate", {"id": str(bank.id)}).is_active is False
    with pytest.raises(Conflict) as again:
        run("payment.method.deactivate", {"id": str(bank.id)})
    assert again.value.code == "payment.method_already_inactive"
    assert run("payment.method.activate", {"method": "BBVA account"}).is_active is True
    with pytest.raises(Conflict) as active:
        run("payment.method.activate", {"id": str(bank.id)})
    assert active.value.code == "payment.method_already_active"
    assert events() == ["payment.method.deactivated", "payment.method.activated"]


def test_only_who_records_payments_manages_the_methods(bank):
    for name, data in [
        ("payment.method.create", {"name": "Card"}),
        ("payment.method.update", {"id": str(bank.id), "name": "Y"}),
        ("payment.method.deactivate", {"id": str(bank.id)}),
    ]:
        with pytest.raises(PermissionDenied):
            run(name, data, role="hub_employee")
