"""Services with the real Customers app: the owner of a voucher is a customer.Customer card.

Customers' own operations create, merge, delete and erase the cards; the merge event is handed to
``events.react`` from the outbox, as the relay will.
"""

import pytest
from live.models import OutboxEvent
from live.operations import get

from apps.service import events
from apps.service.models import Grant

from .conftest import A, ctx_for, make_package, make_service, make_tax

pytestmark = pytest.mark.django_db


def run(name, data, role="hub_admin"):
    op = get(name)
    return op(ctx_for(role), op.input.model_validate(data))


@pytest.fixture
def bono():
    return make_package(
        "Bono 5 cortes",
        [make_service("Cut", tax=make_tax())],
        max_uses=5,
        validity_days=180,
    )


def test_a_voucher_is_granted_to_a_card_named_by_its_phone_and_listed_by_its_name(bono):
    lucia = run(
        "customer.customer.create", {"name": "Lucía Pérez", "phone": "600 111 222"}
    )
    granted = run(
        "service.grant.create",
        {"package": "Bono 5 cortes", "customer": "+34600111222", "amount": 9000},
    )
    assert (granted.customer_id, granted.customer_name) == (lucia.id, "Lucía Pérez")
    [row] = run("service.grant.list", {"customer": "Lucía Pérez"}).rows
    assert (row.id, row.remaining) == (granted.id, 5)


def test_two_cards_merged_in_customers_take_the_vouchers_to_the_one_that_stays(bono):
    lucia = run("customer.customer.create", {"name": "Lucía Pérez"})
    duplicate = run("customer.customer.create", {"name": "Lucia P."})
    first = run(
        "service.grant.create",
        {"package_id": str(bono.id), "customer_id": str(duplicate.id)},
    )
    run("service.grant.redeem", {"id": str(first.id)})

    run(
        "customer.customer.merge",
        {"id": str(lucia.id), "absorbed_id": str(duplicate.id)},
    )
    event = OutboxEvent.objects.filter(name="customer.customer.merged").latest("id")
    events.react(A, event.name, event.payload)

    [row] = run("service.grant.list", {"customer_id": str(lucia.id)}).rows
    assert (row.id, row.used, row.remaining, row.customer_name) == (
        first.id,
        1,
        4,
        "Lucía Pérez",
    )
    assert run("service.grant.list_orphans", {}).total == 0


def test_a_card_deleted_or_erased_in_customers_leaves_its_vouchers_without_a_customer(
    bono,
):
    gone = run("customer.customer.create", {"name": "Marta Gil"})
    erased = run("customer.customer.create", {"name": "Eva Sanz"})
    for card in (gone, erased):
        run(
            "service.grant.create",
            {"package": "Bono 5 cortes", "customer_id": str(card.id)},
        )

    run("customer.customer.delete", {"id": str(gone.id)})
    run("customer.customer.erase", {"id": str(erased.id), "reason": "GDPR request"})

    orphans = run("service.grant.list_orphans", {}).rows
    assert {row.customer_id for row in orphans} == {gone.id, erased.id}
    assert all(row.remaining == 5 for row in orphans)
    names = {
        row.customer_id: row.customer_name
        for row in run("service.grant.list", {"package": "Bono 5 cortes"}).rows
    }
    assert names == {gone.id: None, erased.id: None}
    # The voucher still says whose it was: the reference is what matches it with the sale that paid it.
    assert set(Grant.objects.values_list("customer_id", flat=True)) == {
        gone.id,
        erased.id,
    }


def test_who_may_not_read_customers_sees_the_voucher_without_the_name(bono):
    lucia = run("customer.customer.create", {"name": "Lucía Pérez"})
    run(
        "service.grant.create",
        {"package": "Bono 5 cortes", "customer_id": str(lucia.id)},
    )
    op = get("service.grant.list")
    ctx = ctx_for(permissions={"service.view_package_balance"})
    [row] = op(ctx, op.input.model_validate({"package": "Bono 5 cortes"})).rows
    assert (row.customer_id, row.customer_name) == (lucia.id, None)


def test_a_card_erased_in_customers_empties_the_free_texts_of_its_vouchers(bono):
    lucia = run("customer.customer.create", {"name": "Lucía Pérez"})
    granted = run("service.grant.create", {"package": "Bono 5 cortes", "customer_id": str(lucia.id), "amount": 9000, "note": "Lucía, cash"})
    run("service.grant.redeem", {"id": str(granted.id), "note": "Lucía came on Friday"})
    run("service.grant.adjust", {"id": str(granted.id), "uses_delta": 1, "reason": "Lucía was ill"})

    run("customer.customer.erase", {"id": str(lucia.id), "reason": "GDPR request"})
    event = OutboxEvent.objects.filter(name="customer.customer.erased").latest("id")
    events.react(A, event.name, event.payload)

    grant = Grant.objects.get()
    assert (grant.note, grant.amount, grant.customer_id) == ("", 9000, lucia.id)
    assert list(grant.adjustments.values_list("reason", "uses_delta")) == [("", 1)]
    assert list(grant.redemptions.values_list("note", flat=True)) == [""]
    [row] = run("service.grant.list_orphans", {}).rows
    assert (row.id, row.remaining) == (granted.id, 5)
