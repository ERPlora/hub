"""The book's events (``reservation.<entity>.<fact>``), the contract Tables listens to, and the reactions to
Customers' events, run as the system through this app's operations."""

import pytest
from live.operations import NAME_RE

from apps.reservation import events
from apps.reservation.models import Reservation, WaitlistEntry
from apps.table import events as table_events

from .conftest import A, make_customer, make_entry, make_reservation


def test_every_event_is_named_app_entity_fact():
    assert events.ALL
    for name in events.ALL:
        assert NAME_RE.match(name), name
        assert name.startswith("reservation."), name
    assert len(set(events.ALL)) == len(events.ALL)


def test_tables_is_called_in_the_transaction_and_does_not_listen_to_this_apps_events():
    # TABLE-F25–F27: «Contrato con Reservas». With the relay running, one of the two ways went: the call inside
    # this app's transaction stays; the same event delivered later would replay a stale reservation.
    assert events.RESERVATION_STATUS_CHANGED not in table_events.REACTIONS
    assert events.RESERVATION_UPDATED not in table_events.REACTIONS


def test_the_reactions_are_the_two_of_customers():
    assert events.REACTIONS == {
        "customer.customer.merged": "reservation.customer.reassign",
        "customer.customer.erased": "reservation.customer.erase",
    }


@pytest.mark.django_db
def test_a_merge_delivered_moves_the_cards_bookings_as_the_system():
    survivor, absorbed = make_customer("Ana"), make_customer("Ana G.")
    reservation = make_reservation(customer_id=absorbed.id)
    entry = make_entry(customer_id=absorbed.id)
    payload = {
        "id": str(survivor.id),
        "absorbed_id": str(absorbed.id),
        "anything": "else",
    }
    assert events.react(A, "customer.customer.merged", payload).changed == 2
    assert Reservation.objects.get(pk=reservation.pk).customer_id == survivor.id
    assert WaitlistEntry.objects.get(pk=entry.pk).customer_id == survivor.id


@pytest.mark.django_db
def test_an_erasure_delivered_twice_changes_nothing_the_second_time():
    card = make_customer("Ana")
    make_reservation(customer_id=card.id, guest_phone="+34600111222")
    assert (
        events.react(A, "customer.customer.erased", {"id": str(card.id)}).changed == 1
    )
    assert (
        events.react(A, "customer.customer.erased", {"id": str(card.id)}).changed == 0
    )


def test_an_event_without_a_reaction_is_ignored():
    assert events.react(A, "sale.sale.completed", {}) is None
