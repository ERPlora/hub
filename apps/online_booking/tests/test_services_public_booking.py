"""The public booking: the page's checks and limits, the customer's card found by her mobile, and the booking in the
diary.

Every refusal leaves no trace: no appointment, no card, no link, no event.
"""

import datetime as dt

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, OperationError
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.appointment.models.appointments import Appointment, History
from apps.customer.models import Customer
from apps.online_booking.models import Booking
from apps.online_booking.queries.visitors import hash_token, visitor_key
from apps.online_booking.services import public_booking
from base.tenancy.context import use_hub

from .conftest import (
    HUB_DB,
    HUB_DB_COMMITTED,
    MONDAY,
    QUIET,
    TUESDAY,
    A,
    B,
    at,
    booking_data,
    events,
    make_appointment,
    make_customer,
    make_day,
    make_page,
    make_rules,
    make_service,
    no_rule_of_hours,
    noted_for,
    open_salon,
    public,
    public_ctx,
    received,
    run,
)

pytestmark = HUB_DB


def traces() -> tuple[int, int, int, int]:
    return (
        Appointment.objects.count(),
        Customer.objects.count(),
        Booking.objects.count(),
        OutboxEvent.objects.count(),
    )


def test_a_customer_books_and_the_appointment_lands_in_the_diary(salon):
    answer = public("book", booking_data(salon, "10:00", notes="First time here"))
    appointment = Appointment.objects.get(number=answer.number)
    assert appointment.source == "online"
    assert appointment.status == "confirmed"
    assert appointment.start == at(TUESDAY, "10:00")
    assert appointment.staff == salon.ana
    assert appointment.notes == "First time here"
    assert appointment.created_by == "online booking"
    assert (
        History.objects.get(appointment=appointment, action="created").by_customer
        is True
    )
    card = Customer.objects.get(pk=appointment.customer_id)
    assert (card.name, card.phone, card.email, card.source) == (
        "Marta Gil",
        "+34612345678",
        "marta@example.com",
        "website",
    )
    booking = Booking.objects.get(appointment=appointment)
    assert booking.token_hash == hash_token(answer.token)
    assert booking.requester == visitor_key(public_ctx())
    assert len(answer.token) >= 43
    assert (answer.status, answer.staff_name, answer.service_names) == (
        "confirmed",
        "Ana López",
        "Haircut",
    )
    assert answer.message == "Your booking is confirmed. See you soon!"
    assert events("online_booking.booking.created") == [
        {
            "appointment_id": str(appointment.id),
            "number": appointment.number,
            "customer_id": str(card.id),
            "start": appointment.start.isoformat(),
        }
    ]


def test_with_manual_confirmation_the_booking_waits_pending(salon):
    make_rules(auto_confirm_online=False, min_booking_notice=60)
    answer = public("book", booking_data(salon))
    assert answer.status == "pending"
    assert (
        answer.message
        == "We have received your booking. The business will confirm it shortly."
    )
    make_page(confirmation_message="Thanks! See you at the salon.")
    assert (
        public("book", booking_data(salon, "11:00", phone="699 000 111")).message
        == "Thanks! See you at the salon."
    )


def test_the_customer_is_recognised_by_her_mobile_and_her_card_is_never_changed(salon):
    marta = make_customer("Marta Gil", phone="+34612345678", email="old@example.com")
    make_customer("Pedro Gil", phone="+34612345678")
    answer = public("book", booking_data(salon, email="new@example.com"))
    appointment = Appointment.objects.get(number=answer.number)
    assert appointment.customer_id == marta.id
    marta.refresh_from_db()
    assert marta.email == "old@example.com"
    assert Customer.objects.count() == 3


def test_a_stranger_with_someone_elses_mobile_never_reads_her_name(salon):
    # Lucía's card has +34600111222: an anonymous visitor types it with another name. The booking goes on her
    # card (the market's recognition by mobile), but nothing public says who the card is (GDPR: no oracle
    # mobile → name).
    booked = public("book", booking_data(salon, "10:00", phone="600 111 222", name="x"))
    for answer in (
        booked,
        public("booking", {"token": booked.token}),
        public("cancel", {"token": booked.token}),
    ):
        dumped = answer.model_dump()
        assert "customer_name" not in dumped
        assert "Lucía" not in str(dumped)
        assert "Pérez" not in str(dumped)


def test_the_email_typed_for_a_card_without_one_stays_on_the_booking(salon):
    # Lucía's card has no email; the business asks for it: what she typed reaches the appointment's contact
    # (through the diary's own operation), and her card is not changed from the public page.
    make_page(require_email=True)
    booked = public("book", booking_data(salon, "10:00", phone="600 111 222", name="Lucía Pérez", email="lucia@new.example"))
    appointment = Appointment.objects.get(number=booked.number)
    assert appointment.customer_email == "lucia@new.example"
    salon.lucia.refresh_from_db()
    assert salon.lucia.email == ""


def test_a_card_with_an_email_keeps_it_on_the_booking(salon):
    salon.lucia.email = "lucia@salon.example"
    salon.lucia.save()
    booked = public("book", booking_data(salon, "10:00", phone="600 111 222", email="other@example.com"))
    assert Appointment.objects.get(number=booked.number).customer_email == "lucia@salon.example"


def test_the_chosen_professional_or_the_first_free_one(salon):
    by_bea = public("book", booking_data(salon, "10:00", staff_id=str(salon.bea.id)))
    assert by_bea.staff_name == "Bea Ruiz"
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "12:00"))
    anyone = public("book", booking_data(salon, "12:00", phone="699 000 111"))
    assert anyone.staff_name == "Bea Ruiz"


def test_when_nobody_is_free_the_time_is_taken_and_nothing_is_written(salon):
    for member in (salon.ana, salon.bea):
        make_appointment(salon.lucia, member, [salon.cut], at(TUESDAY, "10:00"))
    before = traces()
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "10:00"))
    assert error.value.code == "online_booking.time_taken"
    assert traces() == before


def test_a_rule_every_professional_breaks_is_said_as_such(salon):
    make_rules(min_booking_notice=24 * 60)
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "07:00"))
    assert error.value.code == "appointment.too_soon"
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "07:00", day=MONDAY - dt.timedelta(days=1)))
    assert error.value.code == "appointment.in_past"


def test_the_business_hours_are_the_diarys(salon):
    make_day(1, ("09:00", "13:00"))
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "15:00", staff_id=str(salon.ana.id)))
    assert error.value.code == "appointment.outside_schedule"


def test_what_the_page_does_not_allow_is_refused(salon):
    make_page(is_enabled=False)
    with pytest.raises(NotFound) as error:
        public("book", booking_data(salon))
    assert error.value.code == "online_booking.page_disabled"
    make_page(allow_staff_selection=False, allow_notes=False, require_email=True)
    shave = make_service("Shave", allow_online_booking=False)
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, service_ids=[str(shave.id)]))
    assert error.value.code == "online_booking.service_not_online"
    with pytest.raises(InvalidPayload) as error:
        public("book", booking_data(salon, staff_id=str(salon.ana.id)))
    assert set(error.value.fields) == {"staff_id"}
    with pytest.raises(InvalidPayload) as error:
        public("book", booking_data(salon, notes="Hi"))
    assert set(error.value.fields) == {"notes"}
    with pytest.raises(InvalidPayload) as error:
        public("book", booking_data(salon, email=""))
    assert error.value.code == "online_booking.email_required"
    assert set(error.value.fields) == {"email"}
    assert not Appointment.objects.exists()


def test_a_mobile_that_is_not_a_number_is_refused_under_its_field(salon):
    with pytest.raises(InvalidPayload) as error:
        public("book", booking_data(salon, phone="12"))
    assert set(error.value.fields) == {"phone"}
    assert not Customer.objects.filter(name="Marta Gil").exists()


# ── The limits ─────────────────────────────────────────────────────────────────────────────────


def test_one_device_books_at_most_five_times_an_hour(salon, clock):
    for index, hhmm in enumerate(("09:00", "09:30", "10:00", "10:30", "11:00")):
        public("book", booking_data(salon, hhmm, phone=f"61200000{index}"))
    with pytest.raises(OperationError) as error:
        public("book", booking_data(salon, "11:30", phone="612000009"))
    assert (error.value.status, error.value.code) == (
        429,
        "online_booking.too_many_bookings",
    )
    # Another device books; an hour later, the first one again.
    public("book", booking_data(salon, "11:30", phone="612000009"), ip="198.51.100.20")
    clock.set(at(MONDAY, "09:01"))
    public("book", booking_data(salon, "12:00", phone="612000008"))


def test_one_mobile_holds_at_most_its_upcoming_bookings(salon):
    make_page(max_upcoming_per_customer=2)
    public("book", booking_data(salon, "09:00"), ip="198.51.100.1")
    public("book", booking_data(salon, "10:00"), ip="198.51.100.2")
    with pytest.raises(Conflict) as error:
        public("book", booking_data(salon, "11:00"), ip="198.51.100.3")
    assert error.value.code == "online_booking.too_many_upcoming"
    # The public message never says how many bookings that mobile holds.
    assert error.value.message == (
        "This mobile already has upcoming bookings with this business: cancel one, or call the business to book more."
    )
    # A cancelled one no longer counts.
    Appointment.objects.filter(start=at(TUESDAY, "09:00")).update(status="cancelled")
    public("book", booking_data(salon, "11:00"), ip="198.51.100.3")


def test_a_flood_on_the_business_is_stopped(salon, monkeypatch):
    monkeypatch.setattr(public_booking, "BUSINESS_PER_HOUR", 2)
    public("book", booking_data(salon, "09:00", phone="612000001"), ip="198.51.100.1")
    public("book", booking_data(salon, "10:00", phone="612000002"), ip="198.51.100.2")
    with pytest.raises(OperationError) as error:
        public(
            "book", booking_data(salon, "11:00", phone="612000003"), ip="198.51.100.3"
        )
    assert (error.value.status, error.value.code) == (429, "online_booking.busy")


@HUB_DB_COMMITTED
def test_a_public_booking_in_hub_b_notifies_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        no_rule_of_hours()
        salon = open_salon()
        run("online_booking.public.book", booking_data(salon, "10:00"), ctx=public_ctx(scope=B))
        assert noted_for() == {(B.kind, B.key)}
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    names = {name for _, payload in notes for name in payload["events"]}
    assert {"online_booking.booking.created", "appointment.appointment.created", "customer.customer.created"} <= names
    assert received(on_a, timeout=QUIET) == []
    assert not OutboxEvent.objects.exists()
