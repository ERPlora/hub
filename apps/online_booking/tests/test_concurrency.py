"""Two customers booking the same time at once: real sessions in threads, real row locks.

Citas locks the professional's staff record before judging the time, so two online bookings of the same
professional at the same time wait for each other: one enters, the other sees it and is refused. The public
bookings of the business wait for each other on the page's settings row, so one mobile booking twice at once keeps
its limit of upcoming bookings.

Two saves of the settings, a merge of the card a booking is made on and two cancellations with the same link each
wait for the row the other one holds.

A booking's detail that a deletion lands in the middle of answers what it read or 404, never a 500.
"""

import pytest
from live.errors import OperationError

from apps.appointment.models import Appointment, History
from apps.appointment.tests.test_concurrency import deleted_after_the_first_read_of
from apps.customer.tests.conftest import reads, writes
from apps.online_booking.models import Booking, Settings
from base.tenancy.tests.concurrency import at_once, meanwhile

from .conftest import (
    HUB_DB_COMMITTED,
    TUESDAY,
    at,
    booking_data,
    make_appointment,
    make_customer,
    make_page,
    public,
    run,
)

#: Several sessions of business A at once, on a plan with room for them: on Free's one transaction at a time the second
#: booking would wait for its turn, never for the first one's lock.
pytestmark = [HUB_DB_COMMITTED, pytest.mark.usefixtures("plan_with_room")]


def codes(results) -> list[str]:
    """Each call's refusal code, or «ok» for an answer: an error with no code, or a call that never ended, is said as
    itself and fails the comparison."""
    return sorted(
        getattr(result, "code", repr(result)) if result is None or isinstance(result, Exception) else "ok"
        for result in results
    )


def book(salon, ip: str, phone: str, **fields):
    return lambda: public(
        "book", booking_data(salon, "10:00", phone=phone, **fields), ip=ip
    )


def test_two_customers_and_the_same_professional_at_the_same_time_one_wins(salon):
    ana = str(salon.ana.id)
    results = at_once(
        book(salon, "198.51.100.1", "612000001", staff_id=ana),
        book(salon, "198.51.100.2", "612000002", staff_id=ana),
    )
    assert codes(results) == ["appointment.slot_taken", "ok"]
    assert Appointment.objects.filter(staff=salon.ana).count() == 1


def test_with_anyone_and_one_professional_free_one_wins(salon):
    salon.bea.is_bookable = False
    salon.bea.save()
    results = at_once(
        book(salon, "198.51.100.1", "612000001"),
        book(salon, "198.51.100.2", "612000002"),
    )
    assert codes(results) == ["ok", "online_booking.time_taken"]
    assert Appointment.objects.count() == 1


def test_with_anyone_two_professionals_take_two_customers(salon):
    results = at_once(
        book(salon, "198.51.100.1", "612000001"),
        book(salon, "198.51.100.2", "612000002"),
    )
    assert codes(results) == ["ok", "ok"]
    assert sorted(Appointment.objects.values_list("staff_name", flat=True)) == [
        "Ana López",
        "Bea Ruiz",
    ]


def test_one_mobile_twice_at_once_keeps_its_limit(salon):
    make_page(max_upcoming_per_customer=1)
    results = at_once(
        book(salon, "198.51.100.1", "600111222", staff_id=str(salon.ana.id)),
        book(salon, "198.51.100.2", "600111222", staff_id=str(salon.bea.id)),
    )
    assert codes(results) == ["ok", "online_booking.too_many_upcoming"]


def test_a_new_mobile_twice_at_once_is_one_card_and_keeps_its_limit(salon):
    from apps.customer.models import Customer

    make_page(max_upcoming_per_customer=1)
    results = at_once(
        book(salon, "198.51.100.1", "699 555 444", staff_id=str(salon.ana.id)),
        book(salon, "198.51.100.2", "699 555 444", staff_id=str(salon.bea.id)),
    )
    assert codes(results) == ["ok", "online_booking.too_many_upcoming"]
    assert Customer.objects.filter(phone="+34699555444").count() == 1


def test_one_device_six_times_at_once_five_enter(salon):
    ana = str(salon.ana.id)
    calls = [
        (lambda hhmm=hhmm, n=n: public("book", booking_data(salon, hhmm, phone=f"61200000{n}", staff_id=ana), ip="198.51.100.9"))
        for n, hhmm in enumerate(("09:00", "09:30", "10:00", "10:30", "11:00", "11:30"))
    ]
    results = at_once(*calls)
    assert codes(results) == ["ok"] * 5 + ["online_booking.too_many_bookings"]
    assert Appointment.objects.count() == 5


# ── A second write that starts right after the first one read its row ──────────────────────────


def save_settings(fields: dict):
    return lambda: run("online_booking.settings.update", fields)


def test_two_saves_of_the_settings_at_once_keep_what_each_one_sent(salon):
    with meanwhile(reads("online_booking_settings"), save_settings({"allow_notes": False})) as other:
        save_settings({"require_email": True})()
    assert codes(other) == ["ok"]
    saved = Settings.objects.get()
    assert (saved.require_email, saved.allow_notes) == (True, False)


def test_a_booking_on_a_card_customers_merges_meanwhile_ends_on_the_kept_card(salon, worker_loop):
    duplicate = make_customer("Lucia P.", phone="+34699999999")

    def merge():
        return run("customer.customer.merge", {"id": str(salon.lucia.id), "absorbed_id": str(duplicate.id)})

    with meanwhile(reads("customer_customer"), merge) as merged:
        booked = public("book", booking_data(salon, "10:00", phone="699 999 999", name="Lucia P."))
    assert codes(merged) == ["ok"]

    worker_loop()

    assert run("online_booking.booking.get", {"number": booked.number}).customer_id == salon.lucia.id


def test_a_booking_that_arrives_while_customers_merges_its_card_is_made_on_the_kept_card(salon):
    duplicate = make_customer("Lucia P.", phone=salon.lucia.phone)

    def book():
        return public("book", booking_data(salon, "10:00", phone="600 111 222", name="Lucia P."))

    with meanwhile(writes("customer_customer"), book) as booked:
        run("customer.customer.merge", {"id": str(salon.lucia.id), "absorbed_id": str(duplicate.id)})
    assert codes(booked) == ["ok"]

    assert Appointment.objects.get(number=booked[0].number).customer_id == salon.lucia.id


def test_two_cancellations_at_once_with_the_same_link_cancel_once_and_refuse_the_other(salon):
    booked = public("book", booking_data(salon, "10:00"))

    def cancel():
        return public("cancel", {"token": booked.token})

    with meanwhile(reads("appointment_appointment"), cancel) as other:
        try:
            first = cancel()
        except OperationError as error:
            first = error
    assert codes([first, *other]) == ["appointment.cannot_cancel", "ok"]
    appointment = Appointment.objects.get(number=booked.number)
    assert appointment.status == "cancelled"
    assert History.objects.filter(appointment=appointment, action="cancelled").count() == 1


# ── A deletion that lands in the middle of a booking's detail ────────────────────────────────────
#
# The detail found the booking and then loaded it again by its id: a deletion committed between the two reads
# raised DoesNotExist (a 500) when the Hub admin deleted it (the row goes). In one read it is the booking as it
# was read; what the deletion's event runs next says it is not found.

#: How a booking is taken away, and whether it still has its page link: the Hub admin's «Delete» from the
#: appointment's page or with the list's «Delete selected» (the row goes with its lines; only once no link
#: protects it), or the business's «Delete» in the inbox (the row is marked).
DELETIONS = {"delete_model": False, "delete_queryset": False, "operation": True}

#: How the detail is asked for: by id, by number, or as a person says it (the customer and the day, or her next).
REFS = {
    "id": lambda booked: {"id": str(booked.id)},
    "number": lambda booked: {"number": booked.number.lower()},
    "customer and day": lambda booked: {"customer": "Lucía", "date": TUESDAY.isoformat()},
    "customer's next": lambda booked: {"customer": "Lucía"},
}


@pytest.mark.parametrize("how", sorted(DELETIONS))
@pytest.mark.parametrize("ref", sorted(REFS))
def test_a_booking_deleted_while_its_detail_is_read_is_never_a_server_error(salon, ref, how):
    via_page = DELETIONS[how]
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "10:00"))
    if via_page:
        Booking.objects.create(appointment=booked, token_hash="a" * 64)
    with deleted_after_the_first_read_of(booked, how, "online_booking.booking.delete") as deletions:
        shown = run("online_booking.booking.get", REFS[ref](booked))
    assert deletions == [None]
    assert (shown.id, shown.number, shown.customer_name, shown.status, shown.via_page) == (
        booked.id,
        booked.number,
        "Lucía Pérez",
        "confirmed",
        via_page,
    )
    # What the deletion's event runs next: not found, and the open sheet closes.
    try:
        gone = run("online_booking.booking.get", REFS[ref](booked))
    except OperationError as error:
        gone = error
    assert isinstance(gone, OperationError), gone
    assert (gone.status, gone.code) == (404, "online_booking.booking_not_found")
