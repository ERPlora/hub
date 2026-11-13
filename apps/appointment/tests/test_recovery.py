"""What Appointments gives back from a separate copy of the business (hub#1284; BASE-F114, APPOINTMENT-F01).

The platform reads the copy (``base.tenancy.recovery``) through a direct, read-only connection: the copy is no
business, so it has no alias and the ORM never reaches it. Appointments answers it (``recoverable_from_copy`` on its
config) with its own read, by SQL over its models' names (``queries.appointments_in_copy``): each appointment of the
copy still to come and still booked (pending or confirmed, not charged), with what its create takes and the card of its
customer there. Then, in the business, which of those it lacks (``queries.appointments_not_in_business``): one it holds
(whatever became of it since) is not lacking, nor one booked again (the same customer at the same moment). Each lacking
one names the business's card of its customer (Customers' rule, ``card_in_business``) and the business's service of
each of its services (Services' rule, ``services_in_business``, hub#1341), and is created by
``appointment.appointment.create``, the agenda's own, which refuses with why what does not fit any more.
"""

import datetime as dt
import uuid

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from apps.appointment import queries
from apps.appointment.models import Appointment, Recurring, RecurringService
from apps.appointment.schemas import AppointmentCreateIn, RecurringCreateIn
from apps.appointment.tests.conftest import MONDAY, at, make_appointment, make_customer, make_series, make_service
from apps.service import queries as service_queries
from apps.service.models import Service
from apps.tax.models import TaxCategory
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import (
    ANA,
    APPOINTMENTS,
    Recoveries,
    Salon,
    a_monday_at,
    booked_events,
    fresh,
    run,
    run_in,
)

pytestmark = pytest.mark.django_db


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


def card(customer) -> dict:
    return {"id": customer.pk, "name": customer.name, "phone": customer.phone, "email": customer.email}


def test_the_copy_gives_each_appointment_still_to_come_and_booked_with_what_its_create_takes(salon):
    lucia, ana, bea, cut, colour = salon.lucia, salon.ana, salon.bea, salon.cut, salon.colour
    lucia.email = "lucia@example.com"
    lucia.save()
    # Booked later for an earlier time: they are read by their start.
    waiting = make_appointment(lucia, bea, [cut], at(MONDAY, "16:00"), status="pending", source="online")
    booked = make_appointment(
        lucia,
        ana,
        [colour, cut],
        at(MONDAY, "10:00"),
        duration=100,
        source="phone",
        notes="Bring the colour reference",
        internal_notes="Allergic to ammonia",
    )
    # Not to come, not booked any more, or charged already: none comes back.
    now = timezone.now()
    make_appointment(lucia, ana, [cut], now - dt.timedelta(hours=1))
    make_appointment(lucia, ana, [cut], at(MONDAY, "11:00"), status="cancelled")
    make_appointment(lucia, ana, [cut], at(MONDAY, "12:00"), status="no_show")
    make_appointment(lucia, ana, [cut], at(MONDAY, "13:00"), deleted_at=now)
    make_appointment(lucia, ana, [cut], at(MONDAY, "14:00"), charged_at=now)
    make_appointment(lucia, ana, [cut], at(MONDAY, "15:00"), sale_id=uuid.uuid7())

    read = queries.appointments_in_copy(direct())

    # Every service of the copy (Services' own read), each appointment's or not: what Services matches the
    # business's by, never a part of them (``services_in_business``).
    services = service_queries.services_in_copy(direct())
    assert {one["id"] for one in services} == {cut.pk, colour.pk}
    assert all(one.pop("services_in_copy") == services for one in read)
    assert read == [
        {
            "id": booked.pk,
            "customer_card": card(lucia),
            "staff_id": ana.pk,
            "services": [{"service_id": colour.pk}, {"service_id": cut.pk}],
            "start": booked.start,
            "duration_minutes": 100,
            "notes": "Bring the colour reference",
            "internal_notes": "Allergic to ammonia",
            "source": "phone",
        },
        {
            "id": waiting.pk,
            "customer_card": card(lucia),
            "staff_id": bea.pk,
            "services": [{"service_id": cut.pk}],
            "start": waiting.start,
            "duration_minutes": 30,
            "notes": "",
            "internal_notes": "",
            "source": "online",
        },
    ]


def test_a_customer_whose_card_the_copy_no_longer_has_live_is_named_as_the_appointment_kept_her(salon):
    gone = make_customer("Sara Gil", phone="+34600777888", email="sara@example.com")
    booked = make_appointment(gone, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    gone.deleted_at = timezone.now()
    gone.save()

    [read] = queries.appointments_in_copy(direct())

    assert read["id"] == booked.pk
    assert read["customer_card"] == {
        "id": gone.pk,
        "name": "Sara Gil",
        "phone": "+34600777888",
        "email": "sara@example.com",
    }


def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE appointment_appointment CASCADE")

    assert queries.appointments_in_copy(direct()) == []


def an_appointment_of_the_copy(
    customer_card: dict, salon, start: dt.datetime, appointment_id=None, services_in_copy: list[dict] | None = None
) -> dict:
    """An appointment as the copy gives it (``appointments_in_copy``): for a cut, with the copy's services as Services
    reads them (``services_in_copy``; the business's own when not given)."""
    return {
        "id": appointment_id or uuid.uuid7(),
        "customer_card": customer_card,
        "staff_id": salon.ana.pk,
        "services": [{"service_id": salon.cut.pk}],
        "start": start,
        "duration_minutes": 30,
        "notes": "",
        "internal_notes": "",
        "source": "counter",
        "services_in_copy": services_in_copy if services_in_copy is not None else service_queries.services_in_copy(
            direct()
        ),
    }


def test_the_business_lacks_what_it_does_not_hold_at_all_nor_booked_again(salon):
    lucia, now = salon.lucia, timezone.now()
    # Held, whatever became of it since (cancelled here, and at another time than in the copy): it stays as it is.
    held = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), status="cancelled")
    # Deleted from the agenda (APPOINTMENT-F11): still held, it comes back the same (``appointments_deleted_in_business``).
    deleted = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "11:00"), deleted_at=now)
    # Booked again by hand since (or brought back already): the same customer at the same moment.
    make_appointment(lucia, salon.bea, [salon.colour], at(MONDAY, "12:00"))
    again = an_appointment_of_the_copy(card(lucia), salon, at(MONDAY, "12:00"))
    gone = an_appointment_of_the_copy(card(lucia), salon, at(MONDAY, "13:00"))
    records = [
        an_appointment_of_the_copy(card(lucia), salon, at(MONDAY, "09:00"), held.pk),
        an_appointment_of_the_copy(card(lucia), salon, deleted.start, deleted.pk),
        again,
        gone,
    ]

    lacking = queries.appointments_not_in_business(records)

    assert [record["id"] for record in lacking] == [gone["id"]]


def test_the_business_holds_deleted_what_it_deleted_and_did_not_book_again(salon):
    lucia, now = salon.lucia, timezone.now()
    live = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"))
    deleted = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), deleted_at=now)
    # Deleted and booked again by hand since: the same customer at its moment. That one stays.
    rebooked = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "11:00"), deleted_at=now)
    make_appointment(lucia, salon.bea, [salon.colour], at(MONDAY, "11:00"))
    # Deleted, and its series booked its date again since. That one stays.
    series = make_series(salon)
    occurrence = make_appointment(
        lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), recurring=series, occurrence_date=MONDAY, deleted_at=now
    )
    make_appointment(lucia, salon.bea, [salon.cut], at(MONDAY, "15:00"), recurring=series, occurrence_date=MONDAY)
    records = [
        an_appointment_of_the_copy(card(lucia), salon, one.start, one.pk)
        for one in (live, rebooked, occurrence, deleted)
    ]
    gone = an_appointment_of_the_copy(card(lucia), salon, at(MONDAY, "13:00"))

    assert queries.appointments_deleted_in_business([gone, *records]) == [records[-1]]


def test_what_others_booked_since_never_holds_a_deleted_one_back(salon):
    """Booked again means its own customer at its moment, or its own series on its date: another customer at its time,
    another date of its series or another series on its date leave it to come back."""
    lucia, now = salon.lucia, timezone.now()
    marta = make_customer("Marta Ruiz", phone="+34600555666")
    alone = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), deleted_at=now)
    make_appointment(marta, salon.bea, [salon.cut], at(MONDAY, "10:00"))
    series, other = make_series(salon), make_series(salon, staff=salon.bea)
    occurrence = make_appointment(
        lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), recurring=series, occurrence_date=MONDAY, deleted_at=now
    )
    later = MONDAY + dt.timedelta(weeks=1)
    make_appointment(lucia, salon.ana, [salon.cut], at(later, "12:00"), recurring=series, occurrence_date=later)
    make_appointment(lucia, salon.bea, [salon.cut], at(MONDAY, "16:00"), recurring=other, occurrence_date=MONDAY)
    records = [an_appointment_of_the_copy(card(lucia), salon, one.start, one.pk) for one in (alone, occurrence)]

    assert queries.appointments_deleted_in_business(records) == records


def test_a_deleted_one_is_the_same_by_its_id_whatever_the_copy_says_of_its_time(salon):
    """Moved since the copy and deleted after: it is the same appointment, and whether it was booked again is read on
    its own time in the business, never on the copy's."""
    lucia, now = salon.lucia, timezone.now()
    moved = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "11:00"), deleted_at=now)
    make_appointment(lucia, salon.bea, [salon.colour], at(MONDAY, "09:00"))
    record = an_appointment_of_the_copy(card(lucia), salon, at(MONDAY, "09:00"), moved.pk)

    assert queries.appointments_deleted_in_business([record]) == [record]
    assert queries.appointments_not_in_business([record]) == []


def test_each_lacking_one_names_the_businesss_card_of_its_customer_and_is_what_its_create_takes(salon):
    now = timezone.now()
    # Deleted since the copy and made again (by hand, or brought back by Customers first): another id here.
    old = make_customer("Marta Ruiz", phone="+34600555666", email="marta@example.com", deleted_at=now)
    marta = make_customer("Marta Ruiz", phone="+34600555666", email="marta@example.com")
    # Deleted and never made again: the copy's card stays, and the create refuses it with why.
    sara = make_customer("Sara Gil", phone="+34600777888", deleted_at=now)
    start = at(MONDAY, "10:00")
    records = [
        an_appointment_of_the_copy(card(old), salon, start),
        an_appointment_of_the_copy(card(sara), salon, at(MONDAY, "11:00")),
    ]
    records[0] |= {"notes": "Bring the reference", "internal_notes": "Formula 7.1", "source": "whatsapp"}

    lacking = queries.appointments_not_in_business(records)

    assert [record["customer_id"] for record in lacking] == [marta.pk, sara.pk]
    first = lacking[0]
    assert first == {
        "id": records[0]["id"],
        "customer_id": marta.pk,
        "staff_id": salon.ana.pk,
        "services": [{"service_id": salon.cut.pk}],
        "start": start,
        "duration_minutes": 30,
        "notes": "Bring the reference",
        "internal_notes": "Formula 7.1",
        "source": "whatsapp",
    }
    payload = AppointmentCreateIn.model_validate({key: value for key, value in first.items() if key != "id"})
    assert (payload.customer_id, payload.staff_id, payload.start, payload.confirm_overlap) == (
        marta.pk,
        salon.ana.pk,
        start,
        False,
    )


def test_one_booked_again_for_the_card_its_customer_is_now_is_not_lacking(salon):
    """The match is on the business's card: one booked again for the card made again is the same appointment."""
    now = timezone.now()
    old = make_customer("Marta Ruiz", phone="+34600555666", email="marta@example.com", deleted_at=now)
    marta = make_customer("Marta Ruiz", phone="+34600555666", email="marta@example.com")
    make_appointment(marta, salon.ana, [salon.cut], at(MONDAY, "10:00"))

    assert queries.appointments_not_in_business([an_appointment_of_the_copy(card(old), salon, at(MONDAY, "10:00"))]) == []


def lost(*services) -> None:
    """``services`` gone from the business altogether, with the appointments booked for them (a line keeps its service:
    PROTECT); no operation deletes a service, a lost database does."""
    Appointment.objects.filter(lines__service__in=services).delete()
    Service.objects.filter(pk__in=[one.pk for one in services]).delete()


def comes_back_with(salon, copy: list[dict]) -> list[dict]:
    """The services a cut booked in the copy comes back with (``appointments_not_in_business``), ``copy`` being the
    copy's services (``services_in_copy``)."""
    [lacking] = queries.appointments_not_in_business(
        [an_appointment_of_the_copy(card(salon.lucia), salon, at(MONDAY, "10:00"), services_in_copy=copy)]
    )
    return lacking["services"]


def test_a_lacking_ones_service_made_again_since_is_the_one_it_is_booked_with(salon):
    """hub#1341: a service gone from the business and made again (the same name in the same category, by hand or
    brought back by Services first) is the one the appointment comes back with, as Services says
    (``services_in_business``)."""
    copy = service_queries.services_in_copy(direct())
    lost(salon.cut)
    again = make_service("  haircut ", tax=salon.tax)

    assert comes_back_with(salon, copy) == [{"service_id": again.pk}]


def test_a_lacking_ones_service_the_business_no_longer_has_stays_the_copys_for_its_create_to_refuse(salon):
    """Without one made again (another name, here), the copy's service stays: the create refuses it with why, and an
    appointment never comes back with a service the business does not have."""
    copy = service_queries.services_in_copy(direct())
    lost(salon.cut)
    make_service("Haircut and beard", tax=salon.tax)

    assert comes_back_with(salon, copy) == [{"service_id": salon.cut.pk}]


def test_with_two_made_again_the_oldest_is_the_one_it_is_booked_with(salon):
    copy = service_queries.services_in_copy(direct())
    lost(salon.cut)
    older = make_service("Haircut", tax=salon.tax)
    make_service("Haircut", tax=salon.tax)

    assert comes_back_with(salon, copy) == [{"service_id": older.pk}]


def test_a_service_the_copy_had_too_is_never_taken_for_the_lost_one_of_the_same_name(salon):
    """Service names are not unique: a cut the copy had too and the business kept is that one, never the lost one made
    again; so the match is by all of the copy's services, never by the appointment's alone."""
    kept = make_service("Haircut", tax=salon.tax)
    copy = service_queries.services_in_copy(direct())
    lost(salon.cut)

    assert comes_back_with(salon, copy) == [{"service_id": salon.cut.pk}]
    assert Service.objects.filter(pk=kept.pk).exists()


def test_a_copy_with_no_appointment_to_come_lacks_none():
    """The platform asks what is lacking even when the copy gave nothing (``base.tenancy.recovery._give_back``): with no
    appointment there is no list of the copy's services to match, and none is lacking."""
    assert queries.appointments_not_in_business([]) == []
    assert queries.appointments_deleted_in_business([]) == []


def test_the_app_declares_what_it_gives_back_its_appointments_first_then_its_series():
    """The series after the appointments: a deleted appointment of a series comes back before anything of its series
    does, and a series created anew books none of the dates its appointments came back on (hub#1327)."""
    appointments, series = apps.get_app_config("appointment").recoverable_from_copy()

    declared = [(one.read, one.missing, one.create, one.deleted, one.restore) for one in (appointments, series)]
    assert declared[0] == (
        queries.appointments_in_copy,
        queries.appointments_not_in_business,
        "appointment.appointment.create",
        queries.appointments_deleted_in_business,
        "appointment.appointment.restore",
    )
    assert declared[1] == (
        queries.series_in_copy,
        queries.series_not_in_business,
        "appointment.recurring.create",
        queries.series_deleted_in_business,
        "appointment.recurring.restore",
    )
    assert [str(one.label) for one in (appointments, series)] == ["Appointments", "Repeating appointments"]
    assert [one.reads_since for one in (appointments, series)] == ["0001_initial", "0001_initial"]


# ── Repeating appointments (hub#1327; APPOINTMENT-F12, APPOINTMENT-F15) ─────────────────────────────────────────────


def test_the_copy_gives_each_series_still_booking_with_what_its_create_takes(salon):
    lucia, ana, bea, cut, colour = salon.lucia, salon.ana, salon.bea, salon.cut, salon.colour
    lucia.email = "lucia@example.com"
    lucia.save()
    weekly = make_series(salon)
    RecurringService.objects.create(recurring=weekly, service=colour, position=1)
    monthly = make_series(
        salon,
        staff=bea,
        frequency="monthly",
        day_of_week=None,
        end_date=MONDAY + dt.timedelta(weeks=20),
        max_occurrences=5,
    )
    # Paused, deleted, without a professional or ended: none books anything, so none is lacking.
    make_series(salon, is_active=False)
    make_series(salon, deleted_at=timezone.now())
    Recurring.objects.filter(pk=make_series(salon).pk).update(staff=None, staff_name="")
    make_series(salon, start_date=MONDAY - dt.timedelta(weeks=8), end_date=timezone.localdate() - dt.timedelta(days=1))

    read = queries.series_in_copy(direct())

    services = service_queries.services_in_copy(direct())
    assert all(one.pop("services_in_copy") == services for one in read)
    assert read == [
        {
            "id": weekly.pk,
            "customer_card": card(lucia),
            "staff_id": ana.pk,
            "services": [{"service_id": cut.pk}, {"service_id": colour.pk}],
            "frequency": "weekly",
            "day_of_week": 0,
            "time": dt.time(10),
            "duration_minutes": 30,
            "start_date": MONDAY,
            "end_date": None,
            "max_occurrences": None,
        },
        {
            "id": monthly.pk,
            "customer_card": card(lucia),
            "staff_id": bea.pk,
            "services": [{"service_id": cut.pk}],
            "frequency": "monthly",
            "day_of_week": None,
            "time": dt.time(10),
            "duration_minutes": 30,
            "start_date": MONDAY,
            "end_date": MONDAY + dt.timedelta(weeks=20),
            "max_occurrences": 5,
        },
    ]


def test_a_series_whose_customer_the_copy_no_longer_has_live_is_named_as_the_series_kept_her(salon):
    gone = make_customer("Sara Gil", phone="+34600777888")
    series = make_series(salon)
    Recurring.objects.filter(pk=series.pk).update(customer=gone, customer_name="Sara Gil")
    gone.deleted_at = timezone.now()
    gone.save()

    [read] = queries.series_in_copy(direct())

    assert read["customer_card"] == {"id": gone.pk, "name": "Sara Gil", "phone": "", "email": ""}


def test_a_copy_without_the_series_table_gives_none():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE appointment_recurring CASCADE")

    assert queries.series_in_copy(direct()) == []


def a_series_of_the_copy(customer_card: dict, salon, series_id=None, **rule) -> dict:
    """A series as the copy gives it (``series_in_copy``): weekly on Mondays at 10:00, a cut with Ana."""
    return {
        "id": series_id or uuid.uuid7(),
        "customer_card": customer_card,
        "staff_id": salon.ana.pk,
        "services": [{"service_id": salon.cut.pk}],
        "frequency": "weekly",
        "day_of_week": 0,
        "time": dt.time(10),
        "duration_minutes": 30,
        "start_date": MONDAY,
        "end_date": None,
        "max_occurrences": None,
        "services_in_copy": service_queries.services_in_copy(direct()),
    } | rule


def test_the_business_holds_deleted_the_series_it_deleted_and_did_not_make_again(salon):
    """Made again means a live series of its customer that repeats the same way at the same time, whoever does it: that
    one stays, and the deleted one is not brought back next to it."""
    lucia, now = salon.lucia, timezone.now()
    live = make_series(salon)
    deleted = make_series(salon, day_of_week=1, deleted_at=now)
    made_again = make_series(salon, day_of_week=2, deleted_at=now)
    make_series(salon, staff=salon.bea, day_of_week=2)
    # Another customer, another day, another time or another repetition is not the same series.
    marta = make_customer("Marta Ruiz", phone="+34600555666")
    alone = make_series(salon, day_of_week=3, deleted_at=now)
    Recurring.objects.create(
        customer=marta, staff=salon.ana, frequency="weekly", day_of_week=3, time=dt.time(10), duration_minutes=30,
        start_date=MONDAY,
    )
    make_series(salon, day_of_week=3, frequency="biweekly")
    Recurring.objects.create(
        customer=lucia, staff=salon.ana, frequency="weekly", day_of_week=3, time=dt.time(11), duration_minutes=30,
        start_date=MONDAY,
    )
    records = [a_series_of_the_copy(card(lucia), salon, one.pk) for one in (live, made_again, deleted, alone)]
    gone = a_series_of_the_copy(card(lucia), salon)

    assert queries.series_deleted_in_business([gone, *records]) == records[2:]


def test_the_business_lacks_the_series_it_does_not_hold_at_all_nor_made_again(salon):
    now = timezone.now()
    held = make_series(salon, is_active=False)
    deleted = make_series(salon, day_of_week=1, deleted_at=now)
    make_series(salon, day_of_week=2)
    again = a_series_of_the_copy(card(salon.lucia), salon, day_of_week=2)
    gone = a_series_of_the_copy(card(salon.lucia), salon, day_of_week=4)
    records = [
        a_series_of_the_copy(card(salon.lucia), salon, held.pk),
        a_series_of_the_copy(card(salon.lucia), salon, deleted.pk, day_of_week=1),
        again,
        gone,
    ]

    assert [one["id"] for one in queries.series_not_in_business(records)] == [gone["id"]]


def test_each_lacking_series_names_the_businesss_card_and_services_and_is_what_its_create_takes(salon):
    now = timezone.now()
    # Deleted since the copy and made again (by hand, or brought back by Customers first): another id here.
    old = make_customer("Marta Ruiz", phone="+34600555666", email="marta@example.com", deleted_at=now)
    marta = make_customer("Marta Ruiz", phone="+34600555666", email="marta@example.com")
    copy = service_queries.services_in_copy(direct())
    lost(salon.cut)
    cut_again = make_service("Haircut", tax=salon.tax)
    record = a_series_of_the_copy(
        card(old), salon, frequency="biweekly", day_of_week=3, end_date=MONDAY + dt.timedelta(weeks=10),
        max_occurrences=4, services_in_copy=copy,
    )

    [lacking] = queries.series_not_in_business([record])

    assert lacking == {
        "id": record["id"],
        "customer_id": marta.pk,
        "staff_id": salon.ana.pk,
        "services": [{"service_id": cut_again.pk}],
        "frequency": "biweekly",
        "day_of_week": 3,
        "time": dt.time(10),
        "duration_minutes": 30,
        "start_date": MONDAY,
        "end_date": MONDAY + dt.timedelta(weeks=10),
        "max_occurrences": 4,
    }
    payload = RecurringCreateIn.model_validate({key: value for key, value in lacking.items() if key != "id"})
    assert (payload.customer_id, payload.staff_id, payload.frequency, payload.max_occurrences) == (
        marta.pk,
        salon.ana.pk,
        "biweekly",
        4,
    )


def test_a_copy_with_no_series_lacks_none():
    assert queries.series_not_in_business([]) == []
    assert queries.series_deleted_in_business([]) == []


# ── End to end: the business's own database and its copy (hub#1341) ─────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


SERVICE_CATEGORIES = APPOINTMENTS | {"app": "service", "label": "Service categories"}
SERVICES = APPOINTMENTS | {"app": "service", "label": "Services"}


def services_of(salon: Salon) -> list[list]:
    """The services of each of the business's live appointments, by their start."""
    return [services for (*_rest, services, _notes) in salon.live()]


@pytest.mark.usefixtures("no_test_fallback")
class TestTheServiceMadeAgain:
    def lost_with_its_cut(self, recoveries, every_app_on) -> tuple[Salon, object, str]:
        """A salon whose cut (taxed, as Services makes one) and its appointment, booked before a separate copy, are gone
        since from the business; and the key of the cut's tax category."""
        salon = Salon(recoveries, every_app_on, ANA)
        with use_hub(salon.hub):
            tax = TaxCategory.objects.filter(is_active=True).order_by("key").first()
            Service.objects.filter(pk=salon.cut).update(tax_category=tax)
        salon.book(salon.cards[0], "10:00", notes="Bring the colour reference")
        copy = recoveries.copy_of(salon.hub)
        with use_hub(salon.hub):
            lost(Service.objects.get(pk=salon.cut))
        return salon, copy, tax.key

    def test_an_appointment_whose_service_was_made_again_by_hand_comes_back_with_that_one(
        self, recoveries, every_app_on
    ):
        salon, copy, tax = self.lost_with_its_cut(recoveries, every_app_on)
        again = run_in(
            salon.hub, "service.service.create", name="Haircut", price=2200, duration_minutes=30, tax_category_key=tax
        ).id
        asked = recoveries.ask(copy, "appointment", "service")

        assert run() == 1

        assert services_of(salon) == [[again]]
        assert fresh(asked).results == [SERVICE_CATEGORIES, SERVICES, APPOINTMENTS | {"created": 1}]

    def test_an_appointment_whose_service_is_brought_back_in_the_same_recovery_comes_back_with_it(
        self, recoveries, every_app_on
    ):
        salon, copy, _tax = self.lost_with_its_cut(recoveries, every_app_on)
        asked = recoveries.ask(copy, "appointment", "service")

        assert run() == 1

        with use_hub(salon.hub):
            [back] = Service.objects.filter(name="Haircut").values_list("pk", flat=True)
        assert back != salon.cut
        assert services_of(salon) == [[back]]
        assert fresh(asked).results == [SERVICE_CATEGORIES, SERVICES | {"created": 1}, APPOINTMENTS | {"created": 1}]

    def test_an_appointment_whose_service_the_business_no_longer_has_does_not_come_back_and_says_why(
        self, recoveries, every_app_on
    ):
        salon, copy, tax = self.lost_with_its_cut(recoveries, every_app_on)
        # Another name is another service: none made again.
        run_in(
            salon.hub,
            "service.service.create",
            name="Haircut and beard",
            price=2500,
            duration_minutes=45,
            tax_category_key=tax,
        )
        asked = recoveries.ask(copy, "appointment")

        assert run() == 1

        assert salon.live() == []
        [result] = fresh(asked).results
        assert (result["created"], result["not_created"], result["refused"]) == (0, 1, "")
        [why] = result["reasons"]
        assert why["reason"].startswith("service.service_not_found: ")


def weekly_series_of(salon: Salon, card: uuid.UUID):
    """Three Mondays of ``card`` with Inés for a cut at 10:00, from a Monday one to two weeks ahead, by Repeating's own
    create: it books the three at once (APPOINTMENT-F12)."""
    return run_in(
        salon.hub,
        "appointment.recurring.create",
        customer_id=card,
        staff_id=salon.ines,
        services=[{"service_id": salon.cut}],
        frequency="weekly",
        start_date=a_monday_at("10:00")[:10],
        time="10:00",
        max_occurrences=3,
    ).recurring


@pytest.mark.usefixtures("no_test_fallback")
class TestTheSeriesComesBack:
    def test_a_deleted_series_comes_back_the_same_and_books_nothing_twice(self, recoveries, every_app_on):
        """hub#1327: the series the business deleted (APPOINTMENT-F15 keeps it and its appointments) comes back by
        Appointments' restore, the same one with the appointments it had booked; it books nothing by itself, and
        «Book» finds its dates already booked."""
        salon = Salon(recoveries, every_app_on, ANA)
        series = weekly_series_of(salon, salon.cards[0])
        then = salon.live()
        copy = recoveries.copy_of(salon.hub)
        run_in(salon.hub, "appointment.recurring.delete", id=series.id)
        asked = recoveries.ask(copy, "appointment")

        assert run() == 1

        assert len(then) == 3
        assert salon.live() == then
        with use_hub(salon.hub):
            back = Recurring.objects.get(pk=series.id)
            assert (back.deleted_at, back.is_active) == (None, True)
            assert Appointment.objects.filter(recurring_id=series.id, deleted_at__isnull=True).count() == 3
        assert booked_events(salon.hub, "appointment.recurring.restored") == 1
        assert fresh(asked).results == [APPOINTMENTS | {"restored": 1}]
        booked = run_in(salon.hub, "appointment.recurring.materialize", id=series.id)
        assert (booked.booked, booked.already_booked) == (0, 3)

    def test_a_series_gone_altogether_is_created_anew_without_booking_over_what_came_back(
        self, recoveries, every_app_on
    ):
        """One the business no longer has at all comes back by Repeating's create, after its appointments came back
        by the agenda's: its dates are theirs already, and it books none of them again."""
        salon = Salon(recoveries, every_app_on, ANA)
        series = weekly_series_of(salon, salon.cards[0])
        then = salon.live()
        copy = recoveries.copy_of(salon.hub)
        with use_hub(salon.hub):
            Appointment.objects.filter(recurring_id=series.id).delete()
            Recurring.objects.filter(pk=series.id).delete()
        asked = recoveries.ask(copy, "appointment")

        assert run() == 1

        assert salon.live() == then
        with use_hub(salon.hub):
            [anew] = Recurring.objects.all()
            assert anew.pk != series.id
            assert (anew.customer_id, anew.staff_id, anew.frequency, anew.time, anew.max_occurrences) == (
                salon.cards[0],
                salon.ines,
                "weekly",
                dt.time(10),
                3,
            )
            assert list(anew.lines.values_list("service_id", flat=True)) == [salon.cut]
        assert fresh(asked).results == [APPOINTMENTS | {"created": 4}]
