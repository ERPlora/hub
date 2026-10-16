"""The online booking app's writes: the inbox's actions (done by the diary), the settings (the page's and the
diary's rules, all or nothing), the public booking and cancelling by link, and the reaction to an erasure.

Every refusal leaves no trace: no appointment, no card, no link, no event.
"""

import datetime as dt

import pytest
from live.errors import (
    Conflict,
    InvalidPayload,
    NotFound,
    OperationError,
    PermissionDenied,
)
from live.models import OutboxEvent

from apps.appointment.models import Appointment, History
from apps.appointment.models import Settings as Rules
from apps.customer.models import Customer
from apps.online_booking import services
from apps.online_booking.models import Booking, Settings
from apps.online_booking.queries import hash_token, visitor_key

from .conftest import (
    MONDAY,
    TUESDAY,
    at,
    booking_data,
    ctx_for,
    make_appointment,
    make_customer,
    make_day,
    make_page,
    make_rules,
    make_service,
    public,
    public_ctx,
    run,
)

pytestmark = pytest.mark.django_db


def events(name: str) -> list[dict]:
    return [
        event.payload for event in OutboxEvent.objects.filter(name=name).order_by("id")
    ]


def traces() -> tuple[int, int, int, int]:
    return (
        Appointment.objects.count(),
        Customer.objects.count(),
        Booking.objects.count(),
        OutboxEvent.objects.count(),
    )


@pytest.fixture
def pending(salon):
    """Lucía's pending online booking of Tuesday 10:00 with Ana."""
    return make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "10:00"),
        status="pending",
        number="APT-1",
    )


# ── The inbox: the diary does it ───────────────────────────────────────────────────────────────


def test_confirming_a_booking_confirms_the_appointment(pending):
    answer = run("online_booking.booking.confirm", {"number": "APT-1"})
    assert answer.status == "confirmed"
    pending.refresh_from_db()
    assert pending.status == "confirmed"
    assert History.objects.filter(appointment=pending, action="confirmed").exists()
    assert [event["id"] for event in events("appointment.appointment.confirmed")] == [
        str(pending.id)
    ]


def test_a_booking_is_confirmed_as_a_person_says_it(pending):
    answer = run(
        "online_booking.booking.confirm",
        {"customer": "Lucía", "date": TUESDAY.isoformat()},
    )
    assert answer.number == "APT-1"


def test_confirming_twice_is_the_diarys_refusal(pending):
    run("online_booking.booking.confirm", {"number": "APT-1"})
    with pytest.raises(Conflict) as error:
        run("online_booking.booking.confirm", {"number": "APT-1"})
    assert error.value.code == "appointment.cannot_confirm"


def test_the_inbox_actions_need_this_apps_right_and_the_diarys(pending):
    with pytest.raises(PermissionDenied):
        run("online_booking.booking.confirm", {"number": "APT-1"}, role="hub_employee")
    with pytest.raises(PermissionDenied):
        run(
            "online_booking.booking.confirm",
            {"number": "APT-1"},
            permissions={"online_booking.confirm_booking", "appointment.view_appointment"},
        )
    assert Appointment.objects.get(pk=pending.pk).status == "pending"


def test_completing_marking_a_no_show_and_cancelling(salon, pending, clock):
    run("online_booking.booking.confirm", {"number": "APT-1"})
    assert (
        run(
            "online_booking.booking.complete", {"number": "APT-1"}, role="hub_manager"
        ).status
        == "completed"
    )

    other = make_appointment(
        salon.lucia, salon.bea, [salon.cut], at(TUESDAY, "11:00"), number="APT-2"
    )
    with pytest.raises(Conflict) as error:
        run("online_booking.booking.no_show", {"number": "APT-2"})
    assert error.value.code == "appointment.no_show_too_early"
    clock.set(at(TUESDAY, "11:30"))
    assert (
        run("online_booking.booking.no_show", {"number": "APT-2"}).status == "no_show"
    )

    third = make_appointment(
        salon.lucia, salon.bea, [salon.cut], at(TUESDAY, "15:00"), number="APT-3"
    )
    cancelled = run(
        "online_booking.booking.cancel",
        {"number": "APT-3", "reason": "Fully booked that day"},
    )
    assert (
        cancelled.status,
        cancelled.cancellation_reason,
        cancelled.cancelled_by_customer,
    ) == (
        "cancelled",
        "Fully booked that day",
        False,
    )
    assert other.pk and third.pk


def test_deleting_is_the_owners_and_archives_the_appointment(pending):
    with pytest.raises(PermissionDenied):
        run("online_booking.booking.delete", {"number": "APT-1"}, role="hub_manager")
    answer = run("online_booking.booking.delete", {"number": "APT-1"}, role="hub_owner")
    assert (answer.id, answer.deleted) == (pending.id, True)
    pending.refresh_from_db()
    assert pending.deleted_at is not None
    with pytest.raises(NotFound):
        run("online_booking.booking.get", {"number": "APT-1"})


def test_an_appointment_that_is_not_online_is_not_the_inboxs(salon):
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "10:00"),
        number="APT-C",
        source="counter",
    )
    with pytest.raises(NotFound) as error:
        run("online_booking.booking.cancel", {"number": "APT-C"})
    assert error.value.code == "online_booking.booking_not_found"
    assert Appointment.objects.get(number="APT-C").status == "confirmed"


# ── Settings ───────────────────────────────────────────────────────────────────────────────────


def test_saving_the_page_settings_keeps_what_changed_and_says_so(db):
    answer = run(
        "online_booking.settings.update",
        {"is_enabled": True, "page_title": "Salón Lucía"},
    )
    assert (answer.is_enabled, answer.page_title, answer.require_email) == (
        True,
        "Salón Lucía",
        False,
    )
    saved = Settings.objects.get()
    assert (saved.is_enabled, saved.page_title, saved.updated_by) == (
        True,
        "Salón Lucía",
        "tester",
    )
    assert len(events("online_booking.settings.updated")) == 1
    run("online_booking.settings.update", {"page_title": "Salón Lucía"})
    assert len(events("online_booking.settings.updated")) == 1


def test_the_rules_are_saved_in_the_diary_with_the_page_all_or_nothing(db):
    answer = run(
        "online_booking.settings.update",
        {"allow_notes": False, "min_booking_notice": 120, "auto_confirm_online": False},
    )
    assert (
        answer.allow_notes,
        answer.min_booking_notice,
        answer.auto_confirm_online,
    ) == (False, 120, False)
    rules = Rules.objects.get()
    assert (rules.min_booking_notice, rules.auto_confirm_online) == (120, False)
    assert len(events("appointment.settings.updated")) == 1
    # Without the diary's settings right, nothing of the page is saved either.
    allowed = {"online_booking.manage_settings", "appointment.view_own_appointment"}
    with pytest.raises(PermissionDenied):
        run(
            "online_booking.settings.update",
            {"allow_notes": True, "slot_interval": 30},
            permissions=allowed,
        )
    assert Settings.objects.get().allow_notes is False
    assert Rules.objects.get().slot_interval == 15


def test_the_settings_are_the_owners_and_the_admins(db):
    with pytest.raises(PermissionDenied):
        run("online_booking.settings.update", {"is_enabled": True}, role="hub_manager")
    assert not Settings.objects.exists()


# ── The public booking ─────────────────────────────────────────────────────────────────────────


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
    monkeypatch.setattr(services, "BUSINESS_PER_HOUR", 2)
    public("book", booking_data(salon, "09:00", phone="612000001"), ip="198.51.100.1")
    public("book", booking_data(salon, "10:00", phone="612000002"), ip="198.51.100.2")
    with pytest.raises(OperationError) as error:
        public(
            "book", booking_data(salon, "11:00", phone="612000003"), ip="198.51.100.3"
        )
    assert (error.value.status, error.value.code) == (429, "online_booking.busy")


# ── Cancelling by the link ─────────────────────────────────────────────────────────────────────


def test_the_customer_cancels_with_her_link_within_the_policy(salon):
    booked = public("book", booking_data(salon, "10:00"))
    answer = public("cancel", {"token": booked.token, "reason": "Something came up"})
    assert (answer.status, answer.can_cancel) == ("cancelled", False)
    appointment = Appointment.objects.get(number=booked.number)
    assert (
        appointment.status,
        appointment.cancelled_by_customer,
        appointment.cancellation_reason,
    ) == (
        "cancelled",
        True,
        "Something came up",
    )
    assert (
        History.objects.get(appointment=appointment, action="cancelled").by_customer
        is True
    )


def test_the_link_keeps_the_cancellation_policy(salon):
    booked = public("book", booking_data(salon, "10:00"))
    make_rules(cancellation_notice_hours=48)
    with pytest.raises(Conflict) as error:
        public("cancel", {"token": booked.token})
    assert error.value.code == "appointment.cancellation_notice_required"
    make_rules(allow_customer_cancellation=False)
    with pytest.raises(Conflict) as error:
        public("cancel", {"token": booked.token})
    assert error.value.code == "appointment.customer_cancellation_disabled"
    assert Appointment.objects.get(number=booked.number).status == "confirmed"


def test_a_wrong_link_cancels_nothing(salon):
    with pytest.raises(NotFound) as error:
        public("cancel", {"token": "x" * 43})
    assert error.value.code == "online_booking.booking_not_found"


# ── Reactions ──────────────────────────────────────────────────────────────────────────────────


def test_erasing_a_customer_revokes_her_links_and_forgets_her_device(salon):
    booked = public("book", booking_data(salon, "10:00"))
    other = public("book", booking_data(salon, "11:00", phone="699 000 111"))
    card = Appointment.objects.get(number=booked.number).customer
    system = ctx_for(permissions={"*"})
    assert (
        run("online_booking.customer.erase", {"id": str(card.id)}, ctx=system).changed
        == 1
    )
    booking = Booking.objects.get(appointment__number=booked.number)
    assert (booking.token_hash, booking.requester) == (None, "")
    with pytest.raises(NotFound):
        public("booking", {"token": booked.token})
    assert public("booking", {"token": other.token}).number == other.number
    assert (
        run("online_booking.customer.erase", {"id": str(card.id)}, ctx=system).changed
        == 0
    )


def test_only_the_platform_runs_the_reaction(salon):
    with pytest.raises(PermissionDenied):
        run(
            "online_booking.customer.erase",
            {"id": str(salon.lucia.id)},
            role="hub_admin",
        )


# ── Scopes: writing in hub B never notifies A (CLAUDE.md «Tests») ────────────────────────────────


WAIT = 1.0
QUIET = 0.3


@pytest.fixture
def listen(db_dsn):
    import psycopg
    from live.outbox import channel_for

    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    import json

    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


@pytest.mark.django_db(transaction=True)
def test_a_public_booking_in_hub_b_notifies_b_only(listen, salon):
    from live.outbox import channel_for

    from .conftest import A, B

    on_a, on_b = listen(A), listen(B)
    run("online_booking.public.book", booking_data(salon, "10:00"), ctx=public_ctx(scope=B))
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    names = {name for _, payload in notes for name in payload["events"]}
    assert {"online_booking.booking.created", "appointment.appointment.created", "customer.customer.created"} <= names
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_saving_the_settings_in_hub_b_notifies_b_only(listen):
    from live.outbox import channel_for

    from .conftest import A, B

    on_a, on_b = listen(A), listen(B)
    run("online_booking.settings.update", {"is_enabled": True}, scope=B)
    assert received(on_b) == [(channel_for(B), {"events": ["online_booking.settings.updated"]})]
    assert received(on_a, timeout=QUIET) == []
