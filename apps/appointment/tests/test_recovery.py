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
from apps.appointment.models import Appointment
from apps.appointment.schemas import AppointmentCreateIn
from apps.appointment.tests.conftest import MONDAY, at, make_appointment, make_customer, make_service
from apps.service import queries as service_queries
from apps.service.models import Service
from apps.tax.models import TaxCategory
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import (
    ANA,
    APPOINTMENTS,
    Recoveries,
    Salon,
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


def test_the_business_lacks_what_it_does_not_hold_nor_booked_again(salon):
    lucia, now = salon.lucia, timezone.now()
    # Held, whatever became of it since (cancelled here, and at another time than in the copy): it stays as it is.
    held = make_appointment(lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), status="cancelled")
    # Deleted from the agenda (APPOINTMENT-F11): lacking.
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


def test_the_app_declares_what_it_gives_back():
    [declared] = apps.get_app_config("appointment").recoverable_from_copy()

    assert (declared.read, declared.missing, declared.create) == (
        queries.appointments_in_copy,
        queries.appointments_not_in_business,
        "appointment.appointment.create",
    )
    assert str(declared.label) == "Appointments"
    assert declared.reads_since == "0001_initial"


# ── End to end: the business's own database and its copy (hub#1341) ─────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


SERVICES = APPOINTMENTS | {"app": "service"}


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
        assert fresh(asked).results == [SERVICES, APPOINTMENTS | {"created": 1}]

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
        assert fresh(asked).results == [SERVICES | {"created": 1}, APPOINTMENTS | {"created": 1}]

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
