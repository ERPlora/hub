"""The book's reactions to Customers: the merge of two cards and the erasure of one."""

import pytest
from live.context import system_context
from live.errors import PermissionDenied

from apps.reservation.models import Reservation, WaitlistEntry

from .conftest import A, HUB_DB, TOMORROW, events, make_entry, make_reservation, run

pytestmark = HUB_DB


def test_a_merge_moves_the_absorbed_cards_reservations_and_entries_and_repeats_harmlessly():
    from .conftest import make_customer

    survivor, absorbed, other = (
        make_customer("Ana"),
        make_customer("Ana G."),
        make_customer("Luis"),
    )
    mine = make_reservation(customer_id=absorbed.id, guest_name="Ana G.")
    entry = make_entry(customer_id=absorbed.id)
    theirs = make_reservation(customer_id=other.id)
    data = {"id": str(survivor.id), "absorbed_id": str(absorbed.id)}
    assert run("reservation.customer.reassign", data, system_context(A)).changed == 2
    assert Reservation.objects.get(pk=mine.pk).customer_id == survivor.id
    assert Reservation.objects.get(pk=mine.pk).guest_name == "Ana G."
    assert WaitlistEntry.objects.get(pk=entry.pk).customer_id == survivor.id
    assert Reservation.objects.get(pk=theirs.pk).customer_id == other.id
    assert run("reservation.customer.reassign", data, system_context(A)).changed == 0
    assert events() == ["reservation.customer.reassigned"]


def test_an_erasure_empties_the_personal_data_and_keeps_the_booking():
    from .conftest import make_customer

    card = make_customer("Ana")
    reservation = make_reservation(
        customer_id=card.id,
        guest_phone="+34600111222",
        guest_email="ana@x.es",
        notes="Allergic",
        internal_notes="Wheelchair",
        cancellation_reason="Ill",
        party_size=4,
    )
    entry = make_entry(customer_id=card.id, notes="x", is_deleted=True)
    assert (
        run(
            "reservation.customer.erase", {"id": str(card.id)}, system_context(A)
        ).changed
        == 2
    )
    reservation.refresh_from_db()
    assert (
        reservation.guest_name,
        reservation.guest_phone,
        reservation.guest_email,
        reservation.notes,
        reservation.internal_notes,
        reservation.cancellation_reason,
    ) == ("", "", "", "", "", "")
    assert (reservation.party_size, reservation.customer_id, reservation.date) == (
        4,
        card.id,
        TOMORROW,
    )
    entry.refresh_from_db()
    assert (entry.guest_name, entry.guest_phone, entry.notes) == ("", "", "")
    assert (
        run(
            "reservation.customer.erase", {"id": str(card.id)}, system_context(A)
        ).changed
        == 0
    )
    assert events() == ["reservation.customer.erased"]


def test_the_reactions_are_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run("reservation.customer.erase", {"id": None})
    assert run("reservation.customer.erase", {}, system_context(A)).changed == 0
