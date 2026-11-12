"""What Appointments gives back from a separate copy of the business (hub#1284; BASE-F114, APPOINTMENT-F01).

The platform reads the copy (``base.tenancy.recovery``) through a direct, read-only connection: the copy is no
business, so it has no alias and the ORM never reaches it. Appointments answers it (``recoverable_from_copy`` on its
config) with its own read, by SQL over its models' names (``queries.appointments_in_copy``): each appointment of the
copy still to come and still booked (pending or confirmed, not charged), with what its create takes and the card of its
customer there. Then, in the business, which of those it lacks (``queries.appointments_not_in_business``): one it holds
(whatever became of it since) is not lacking, nor one booked again (the same customer at the same moment). Each lacking
one names the business's card of its customer (Customers' rule, ``card_in_business``) and is created by
``appointment.appointment.create``, the agenda's own, which refuses with why what does not fit any more.
"""

import datetime as dt
import uuid

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from apps.appointment import queries
from apps.appointment.schemas import AppointmentCreateIn
from apps.appointment.tests.conftest import MONDAY, at, make_appointment, make_customer

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


def an_appointment_of_the_copy(customer_card: dict, salon, start: dt.datetime, appointment_id=None) -> dict:
    """An appointment as the copy gives it (``appointments_in_copy``)."""
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
    }


def test_the_business_lacks_what_it_does_not_hold_nor_booked_again(salon):
    lucia, now = salon.lucia, timezone.now()
    # Held, whatever became of it since (cancelled here): it stays as it is.
    held = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), status="cancelled")
    # Deleted from the agenda (APPOINTMENT-F11): lacking.
    deleted = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "11:00"), deleted_at=now)
    # Booked again by hand since (or brought back already): the same customer at the same moment.
    make_appointment(lucia, salon.bea, [salon.colour], at(MONDAY, "12:00"))
    again = an_appointment_of_the_copy(card(lucia), salon, at(MONDAY, "12:00"))
    gone = an_appointment_of_the_copy(card(lucia), salon, at(MONDAY, "13:00"))
    records = [
        an_appointment_of_the_copy(card(lucia), salon, held.start, held.pk),
        an_appointment_of_the_copy(card(lucia), salon, deleted.start, deleted.pk),
        again,
        gone,
    ]

    lacking = queries.appointments_not_in_business(records)

    assert [record["id"] for record in lacking] == [deleted.pk, gone["id"]]


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


def test_the_app_declares_what_it_gives_back():
    [declared] = apps.get_app_config("appointment").recoverable_from_copy()

    assert (declared.read, declared.missing, declared.create) == (
        queries.appointments_in_copy,
        queries.appointments_not_in_business,
        "appointment.appointment.create",
    )
    assert str(declared.label) == "Appointments"
    assert declared.reads_since == "0001_initial"
