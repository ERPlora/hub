"""The guest's phone is kept the way Customers keeps it (RESERVATION-F06, F08, F14, F16): in E.164, a number without
prefix read in the business's country, whether the card was chosen or found by the phone.

A reservation is how the inbox finds the guest's conversation (RESERVATION-F19, WHATSAPP_INBOX-F26): it looks for
exactly the international number, so a phone kept as typed («600111222») tells nobody. Taking, changing a
reservation and writing somebody on the waitlist read the typed phone with Customers' own rules
(``apps.customer.phones.to_e164``), as Appointments does when its phone is edited: a number of another country keeps
its own prefix, and one that is not a valid number of its country is refused with Customers' reason, on the phone
field, before any other check. The real Customers app; nothing is mocked.
"""

import pytest
from django.utils import translation
from live.errors import InvalidPayload
from live.models import OutboxEvent

from apps.customer.models import Customer
from apps.customer.services import PHONE_INVALID
from apps.reservation.models import Reservation, TimeSlot, WaitlistEntry

from .conftest import THURSDAY, TOMORROW, book, make_customer, make_reservation, make_slot, open_week, run

pytestmark = pytest.mark.django_db

LOCAL = "600111222"
LUCIA = "+34600111222"
UK = "+447911123456"  # Customers' own example (07700 900xxx is a fictional range: not a valid number)


@pytest.fixture(autouse=True)
def week(db):
    open_week()


@pytest.fixture
def lucia():
    """Lucía's card in Customers: her number, as Customers keeps it, is ``LUCIA``."""
    return make_customer("Lucía Pérez", phone=LOCAL)


def write_down(**data):
    """``reservation.waitlist.create`` for tomorrow at 21:00, two guests (override any field)."""
    payload = {"date": TOMORROW.isoformat(), "preferred_time": "21:00", "party_size": 2, **data}
    return run("reservation.waitlist.create", payload)


def refused(call) -> InvalidPayload:
    with pytest.raises(InvalidPayload) as caught:
        call()
    return caught.value


def assert_phone_refusal(error: InvalidPayload) -> None:
    assert error.code == "reservation.phone_invalid"
    assert error.fields == {"guest_phone": str(PHONE_INVALID)}
    assert error.message == str(PHONE_INVALID)


# ── RESERVATION-F06: taking a reservation ────────────────────────────────────────────────────────


def test_a_local_number_typed_with_a_chosen_card_is_kept_international(lucia):
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone=LOCAL)
    assert (out.customer_id, out.guest_phone) == (lucia.id, LUCIA)
    assert Reservation.objects.get(pk=out.id).guest_phone == LUCIA


def test_a_number_of_another_country_keeps_its_own_prefix(lucia):
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone="+44 7911 123456")
    assert out.guest_phone == UK
    alone = book(guest_name="John Smith", guest_phone=UK, date="2026-10-16")
    assert alone.guest_phone == UK
    assert Customer.objects.get(pk=alone.customer_id).phone == UK


def test_a_phone_that_is_not_a_number_of_its_country_books_nothing_and_says_it_on_the_phone_field(lucia):
    cards = Customer.objects.count()
    assert_phone_refusal(refused(lambda: book(customer_id=str(lucia.id), guest_name="", guest_phone="600111")))
    # Without a chosen card the same reason, and no card is made for a number that is not one.
    assert_phone_refusal(refused(lambda: book(guest_name="Luis", guest_phone="600111")))
    assert Reservation.objects.count() == 0
    assert Customer.objects.count() == cards
    assert not OutboxEvent.objects.filter(name__startswith="reservation.").exists()


def test_the_reason_is_customers_own_in_the_callers_language(lucia):
    english = str(PHONE_INVALID)
    with translation.override("es"):
        error = refused(lambda: book(customer_id=str(lucia.id), guest_name="", guest_phone="600111"))
        assert error.message == error.fields["guest_phone"] == str(PHONE_INVALID) != english


def test_a_bad_phone_with_a_chosen_card_is_said_before_a_full_slot_is_offered_to_overbook(lucia):
    TimeSlot.objects.all().delete()
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    make_reservation()
    assert_phone_refusal(refused(lambda: book(customer_id=str(lucia.id), guest_name="", guest_phone="600111")))


def test_an_empty_phone_with_a_chosen_card_still_takes_the_cards(lucia):
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone="")
    assert out.guest_phone == LUCIA


def test_the_book_finds_the_reservation_by_the_local_digits(lucia):
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone=LOCAL)
    by_column = run("reservation.reservation.list", {"guest_phone": LOCAL}).rows
    by_search = run("reservation.reservation.list", {"search": "600 111 222"}).rows
    assert [row.id for row in by_column] == [out.id]
    assert [row.id for row in by_search] == [out.id]


# ── RESERVATION-F08: changing a reservation ──────────────────────────────────────────────────────


def test_a_changed_phone_is_kept_international(lucia):
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone="")
    changed = run("reservation.reservation.update", {"id": str(out.id), "guest_phone": "611 222 333"})
    assert changed.guest_phone == "+34611222333"
    assert Reservation.objects.get(pk=out.id).guest_phone == "+34611222333"
    abroad = run("reservation.reservation.update", {"id": str(out.id), "guest_phone": UK})
    assert abroad.guest_phone == UK


def test_the_same_number_typed_another_way_is_no_change(lucia):
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone="")
    before = OutboxEvent.objects.filter(name="reservation.reservation.updated").count()
    run("reservation.reservation.update", {"id": str(out.id), "guest_phone": "600 11 12 22"})
    assert OutboxEvent.objects.filter(name="reservation.reservation.updated").count() == before
    assert Reservation.objects.get(pk=out.id).guest_phone == LUCIA


def test_a_bad_changed_phone_changes_nothing_and_is_said_before_the_gate(lucia):
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone="")
    # A full slot as well: the phone is said first, never after «Book anyway?».
    TimeSlot.objects.all().delete()
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    make_slot(THURSDAY, "13:00", "16:00", max_reservations=1)
    make_reservation(time="14:00")
    error = refused(
        lambda: run("reservation.reservation.update", {"id": str(out.id), "guest_phone": "600111", "time": "14:00"})
    )
    assert_phone_refusal(error)
    kept = Reservation.objects.get(pk=out.id)
    assert (kept.guest_phone, f"{kept.time:%H:%M}") == (LUCIA, "21:00")
    assert not OutboxEvent.objects.filter(name="reservation.reservation.updated").exists()


def test_clearing_the_phone_still_clears_it(lucia):
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone="")
    assert run("reservation.reservation.update", {"id": str(out.id), "guest_phone": ""}).guest_phone == ""


# ── RESERVATION-F14 and F16: the waitlist ────────────────────────────────────────────────────────


def test_a_waitlist_entry_with_a_chosen_card_keeps_the_number_international_and_its_reservation_too(lucia):
    entry = write_down(customer_id=str(lucia.id), guest_phone="600 111 222")
    assert (entry.customer_id, entry.guest_phone) == (lucia.id, LUCIA)
    converted = run("reservation.waitlist.convert", {"id": str(entry.id)})
    assert converted.reservation.guest_phone == LUCIA
    assert Reservation.objects.get(pk=converted.reservation.id).guest_phone == LUCIA


def test_a_waitlist_entry_of_another_country_keeps_its_prefix(lucia):
    assert write_down(customer_id=str(lucia.id), guest_phone=UK).guest_phone == UK


def test_a_bad_phone_writes_nobody_on_the_waitlist(lucia):
    cards = Customer.objects.count()
    assert_phone_refusal(refused(lambda: write_down(customer_id=str(lucia.id), guest_phone="600111")))
    assert_phone_refusal(refused(lambda: write_down(guest_name="Luis", guest_phone="600111")))
    assert WaitlistEntry.objects.count() == 0
    assert Customer.objects.count() == cards
    assert not OutboxEvent.objects.filter(name__startswith="reservation.").exists()


def test_a_bad_changed_phone_is_said_before_an_unknown_table(lucia):
    # RESERVATION-F08 takes F06's order: the phone's reason comes before any other check, a table that is not
    # there included (the assistant may say «mesa 99» and a wrong number in one breath).
    out = book(customer_id=str(lucia.id), guest_name="", guest_phone="")
    error = refused(
        lambda: run(
            "reservation.reservation.update",
            {"id": str(out.id), "guest_phone": "600111", "table_id": "0199f3a0-0000-7000-8000-000000000000"},
        )
    )
    assert_phone_refusal(error)
    assert Reservation.objects.get(pk=out.id).guest_phone == LUCIA
