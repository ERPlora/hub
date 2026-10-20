"""Two hosts at once (RESERVATION-F06, F16): real sessions in threads, real row locks.

Two reservations for the same table and time leave one (the old module did not check it); the last place
of a slot goes to one reservation (the old gate's promise), also when a conversion from the waitlist races
a new booking. The losers get their reason and write nothing.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError

from django.contrib.auth import get_user_model
from django.test import Client
from live.context import system_context

from apps.customer.models import Customer
from apps.customer.tests.conftest import card_deleted_on_screen, card_protected, reads, writes
from apps.reservation.models import Reservation, WaitlistEntry

from .conftest import (
    THURSDAY,
    TOMORROW,
    A,
    book,
    ctx_for,
    make_customer,
    make_entry,
    make_slot,
    make_table,
    open_week,
    run,
    set_rules,
)

pytestmark = pytest.mark.django_db(transaction=True)

EMPLOYEE = "hub_employee"


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except OperationError as error:
            results[index] = error
        except (
            Exception
        ) as error:  # an unexpected failure (a deadlock…) is reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def codes(results) -> list:
    return sorted(getattr(result, "code", "ok") for result in results)


@pytest.fixture(autouse=True)
def saved_rules(db):
    """The book's settings row exists before the race: creating it would serialize the writers by itself
    (its unique index), and hide whether the lock does."""
    set_rules()


def as_host(**data):
    return lambda: book(ctx=ctx_for(EMPLOYEE), **data)


def test_two_reservations_for_the_same_table_and_time_leave_one():
    open_week()
    table = make_table("5")
    results = at_once(
        *(
            as_host(
                table_id=str(table.id),
                guest_name=f"Guest {n}",
                guest_phone=f"60011122{n}",
            )
            for n in range(4)
        )
    )
    assert codes(results) == [
        "ok",
        "reservation.table_taken",
        "reservation.table_taken",
        "reservation.table_taken",
    ]
    assert Reservation.objects.filter(table=table).count() == 1
    # The losers left no card behind either: their whole transaction rolled back.
    assert Customer.objects.count() == 1


def test_the_last_place_of_a_slot_goes_to_one_reservation():
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    results = at_once(
        *(
            as_host(guest_name=f"Guest {n}", guest_phone=f"60011122{n}")
            for n in range(3)
        )
    )
    assert codes(results) == [
        "ok",
        "reservation.no_capacity",
        "reservation.no_capacity",
    ]
    assert Reservation.objects.count() == 1


def test_a_conversion_and_a_new_booking_racing_for_the_last_place_leave_one():
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    entry = make_entry()
    results = at_once(
        as_host(guest_name="Ana", guest_phone="600111222"),
        lambda: run(
            "reservation.waitlist.convert", {"id": str(entry.id)}, ctx_for(EMPLOYEE)
        ),
    )
    assert codes(results) == ["ok", "reservation.no_capacity"]
    assert Reservation.objects.count() == 1


# ── The Hub admin's «Delete» of the guest's card while a write links it ──────────────────────────
#
# A reservation and a waitlist entry find the guest's card (the one named, or the one with the guest's phone) and
# then write the row that points at it. The Hub admin's «Delete» of that card between the two found nothing
# protecting it and deleted it: the write then failed at its COMMIT (an IntegrityError, a 500). The write locks
# the card when it finds it, as the deletion does: the deletion waits for it and answers «Cannot delete», since
# the new row protects the card; a write that comes second waits for the deletion, and finds the card gone (404)
# or, by phone, makes a new one.

HOW = ["page", "list"]


def _reserve(card, by: str):
    who = {"customer_id": str(card.id)} if by == "id" else {"guest_name": card.name, "guest_phone": card.phone}
    return book(**who)


def _wait(card, by: str):
    who = {"customer_id": str(card.id)} if by == "id" else {"guest_name": card.name, "guest_phone": card.phone}
    data = {"date": TOMORROW.isoformat(), "preferred_time": "21:00", "party_size": 2, **who}
    return run("reservation.waitlist.create", data)


#: The writes that link a guest's card, and the table of the row that points at it.
CARD_LINKS = {"reservation": (_reserve, "reservation_reservation"), "waitlist": (_wait, "reservation_waitlistentry")}


def _ana():
    open_week()
    return Customer.objects.get(pk=make_customer("Ana García", phone="600111222").id)


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("by", ["id", "phone"])
@pytest.mark.parametrize("write", sorted(CARD_LINKS))
def test_the_hub_admin_cannot_delete_a_card_a_reservation_links_meanwhile(write, by, how):
    ana = _ana()
    link, table = CARD_LINKS[write]
    with card_deleted_on_screen(ana, how, writes(table)) as answers:
        link(ana, by)
    [answer] = answers
    assert card_protected(answer)
    model = Reservation if write == "reservation" else WaitlistEntry
    assert model.objects.get().customer_id == ana.id


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(CARD_LINKS))
def test_a_reservation_whose_card_the_hub_admin_deletes_first_is_told_it_is_gone(write, how):
    ana = _ana()
    link, _ = CARD_LINKS[write]
    with card_deleted_on_screen(ana, how, reads("customer_customer")) as answers:
        with pytest.raises(OperationError) as refused:
            link(ana, "id")
    [answer] = answers
    assert answer.status_code == 302
    assert (refused.value.status, refused.value.code) == (404, "customer.customer_unavailable")
    assert not Customer.objects.exists()
    assert not Reservation.objects.exists() and not WaitlistEntry.objects.exists()


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(CARD_LINKS))
def test_a_reservation_by_the_phone_of_a_card_the_hub_admin_deletes_first_makes_a_new_card(write, how):
    ana = _ana()
    link, _ = CARD_LINKS[write]
    with card_deleted_on_screen(ana, how, reads("customer_customer")) as answers:
        link(ana, "phone")
    [answer] = answers
    assert answer.status_code == 302
    model = Reservation if write == "reservation" else WaitlistEntry
    [card] = Customer.objects.all()
    assert card.id != ana.id
    assert model.objects.get().customer_id == card.id


# The merge of two cards moves the absorbed card's reservations and waitlist entries to the card that stays, later,
# as a reaction: the Hub admin may have deleted that card in between (nothing protected it), or delete it while the
# reaction moves them. The reaction locks the card that stays first: gone, nothing moves (they keep the card they
# were booked with) instead of failing for ever at its COMMIT; there, the deletion waits and answers «Cannot delete».


def _merged_into_marta():
    ana = _ana()
    booked = Reservation.objects.get(pk=_reserve(ana, "id").id)
    entry = make_entry(customer=ana)
    marta = Customer.objects.get(pk=make_customer("Marta Gil", phone="600999888").id)
    data = {"id": str(marta.id), "absorbed_id": str(ana.id)}
    return ana, booked, entry, marta, lambda: run("reservation.customer.reassign", data, system_context(A))


@pytest.mark.parametrize("how", HOW)
def test_the_hub_admin_cannot_delete_the_card_a_merge_moves_the_reservations_to_meanwhile(how):
    _, booked, entry, marta, move = _merged_into_marta()
    with card_deleted_on_screen(marta, how, writes("reservation_reservation")) as answers:
        move()
    [answer] = answers
    assert card_protected(answer)
    booked.refresh_from_db()
    entry.refresh_from_db()
    assert (booked.customer_id, entry.customer_id) == (marta.id, marta.id)


@pytest.mark.parametrize("how", HOW)
def test_a_merge_into_a_card_the_hub_admin_deleted_moves_no_reservation(how):
    ana, booked, entry, marta, move = _merged_into_marta()
    staff = get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")
    client = Client()
    client.force_login(staff)
    if how == "page":
        url, data = f"/admin/customer/customer/{marta.pk}/delete/", {"post": "yes"}
    else:
        url, data = "/admin/customer/customer/", {"action": "delete_selected", "_selected_action": [str(marta.pk)], "post": "yes"}
    assert client.post(url, data, HTTP_HOST="hubs.localhost", HTTP_ACCEPT_LANGUAGE="en").status_code == 302
    assert move().changed == 0
    booked.refresh_from_db()
    entry.refresh_from_db()
    assert (booked.customer_id, entry.customer_id) == (ana.id, ana.id)
