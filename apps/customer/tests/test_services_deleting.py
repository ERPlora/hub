"""Deleting a card keeps its data (CUSTOMER-F07)."""

import uuid

import pytest
from live.errors import NotFound, PermissionDenied

from apps.customer import events
from apps.customer.models import OrderLink, Purchase
from apps.customer.schemas.fields import CustomerRefIn as RefIn, DeletedOut

from .conftest import HUB_DB, NOW, card, outbox, run

pytestmark = HUB_DB


# customer.customer.delete (CUSTOMER-F07; delete_guarded.pg)


def test_delete_keeps_the_data_and_announces_it():
    ana = card("Ana", email="ana@example.com")
    Purchase.objects.create(customer=ana, sale_id=uuid.uuid7(), amount=500)
    OrderLink.objects.create(order_id=uuid.uuid7(), customer=ana)
    assert run("customer.customer.delete", RefIn(id=ana.id)) == DeletedOut(id=ana.id)
    ana.refresh_from_db()
    assert ana.deleted_at is not None and ana.is_active is False
    assert (ana.email, ana.purchases.count(), ana.orders.count()) == (
        "ana@example.com",
        1,
        1,
    )
    assert outbox() == [(events.CUSTOMER_DELETED, {"id": str(ana.id)})]


def test_deleting_an_unknown_card_fails_and_announces_nothing():
    with pytest.raises(NotFound) as excinfo:
        run("customer.customer.delete", RefIn(id=uuid.uuid7()))
    assert excinfo.value.code == "customer.customer_unavailable"
    assert outbox() == []


def test_deleting_a_card_that_is_already_gone_answers_well_and_announces_again():
    gone = card("Gone", deleted_at=NOW)
    run("customer.customer.delete", RefIn(id=gone.id))
    gone.refresh_from_db()
    assert gone.deleted_at == NOW
    assert outbox() == [(events.CUSTOMER_DELETED, {"id": str(gone.id)})]


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_only_owner_and_admin_delete(role):
    ana = card("Ana")
    with pytest.raises(PermissionDenied):
        run("customer.customer.delete", RefIn(id=ana.id), role)
    assert run("customer.customer.delete", RefIn(id=ana.id), "hub_owner").id == ana.id
