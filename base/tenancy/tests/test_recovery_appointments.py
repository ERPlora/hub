"""What Appointments brings back from a separate copy: a deleted appointment the same, one gone booked anew, and
why one is not. The databases are ``conftest.py``'s, the rest of what it runs on ``test_recovery``'s."""

import datetime as dt
import uuid

from live.models import OutboxEvent

from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import ANA, LUIS, MARTA, fresh, in_the_copy, run, run_in
from control.models.copies import CopyRecovery, RestoredCopy
from control.models.hubs import Hub


APPOINTMENTS = {
    "app": "appointment",
    "label": "Appointments",
    "restored": 0,
    "created": 0,
    "not_created": 0,
    "reasons": [],
    "refused": "",
}
#: What Appointments gives back after its appointments, its series (hub#1327): none in these tests of appointments.
SERIES = APPOINTMENTS | {"label": "Repeating appointments"}


def a_monday_at(hhmm: str) -> str:
    """A Monday one to two weeks ahead at ``hhmm`` on the business's wall clock: open (09:00–18:00 by default), inside
    the default advance and never in the past."""
    from django.utils import timezone

    today = timezone.localdate()
    monday = today + dt.timedelta(days=(0 - today.weekday()) % 7 + 7)
    return f"{monday.isoformat()}T{hhmm}"


class Salon:
    """A business with its cards (``Recoveries.business``), a professional who takes bookings and a cut."""

    def __init__(self, recoveries, every_app_on, *cards: dict):
        from apps.service.models import Service
        from apps.staff.models import Member

        self.recoveries = recoveries
        self.hub, self.cards = recoveries.business(every_app_on, *cards)
        with use_hub(self.hub):
            self.ines = Member.objects.create(first_name="Inés", last_name="Mora").pk
            self.cut = Service.objects.create(name="Haircut", price=2000, duration_minutes=30).pk

    def book(self, card: uuid.UUID, hhmm: str, **fields):
        """An appointment of ``card`` with Inés for a cut on Monday at ``hhmm``, booked by the agenda's create."""
        return run_in(
            self.hub,
            "appointment.appointment.create",
            customer_id=card,
            staff_id=self.ines,
            services=[{"service_id": self.cut}],
            start=a_monday_at(hhmm),
            **fields,
        )

    def lost_since_a_copy(self, *booked) -> RestoredCopy:
        """A separate copy of the business as it is now, then each of ``booked`` deleted from the agenda since."""
        copy = self.recoveries.copy_of(self.hub)
        for one in booked:
            run_in(self.hub, "appointment.appointment.delete", id=one.id)
        return copy

    def live(self) -> list[tuple]:
        """The business's live appointments: their customer's name, professional, start, minutes, services and notes."""
        from apps.appointment.models import Appointment

        with use_hub(self.hub):
            return [
                (
                    one.customer.name,
                    one.staff_id,
                    one.start,
                    one.duration_minutes,
                    [line.service_id for line in one.lines.all()],
                    one.notes,
                )
                for one in Appointment.objects.filter(deleted_at__isnull=True).order_by("start")
            ]


def booked_events(hub: Hub, name: str = "appointment.appointment.created") -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name=name).count()


def gone_from_the_agenda(hub: Hub, *appointments) -> None:
    """``appointments``' rows gone altogether from ``hub``, with what hangs from them: what the business no longer has
    (no operation destroys an appointment: a lost database does)."""
    from apps.appointment.models import Appointment

    with use_hub(hub):
        Appointment.objects.filter(pk__in=[one.id for one in appointments]).delete()


def the_one_not_booked(asked: CopyRecovery) -> dict:
    """Why the only appointment of ``asked`` that did not come back did not, the others having come back the same: a
    deleted one the restore refuses is never booked anew."""
    [appointments, series] = fresh(asked).results
    assert series == SERIES
    assert (appointments["restored"], appointments["created"], appointments["not_created"], appointments["refused"]) == (
        1,
        0,
        1,
        "",
    )
    [why] = appointments["reasons"]
    return why


class TestAppointmentsComeBack:
    def test_a_deleted_appointment_comes_back_the_same_and_one_gone_is_booked_anew(self, recoveries, every_app_on):
        """hub#1326: the one the business deleted (APPOINTMENT-F11 keeps it) comes back by Appointments' restore, with
        its number and its history; only the one it no longer has is booked again, by the agenda's create."""
        from apps.appointment.models import Appointment

        salon = Salon(recoveries, every_app_on, ANA, LUIS)
        ana, luis = salon.cards
        deleted = salon.book(ana, "10:00", notes="Bring the colour reference")
        lost = salon.book(luis, "11:00", duration_minutes=45)
        then = salon.live()
        copy = salon.lost_since_a_copy(deleted)
        gone_from_the_agenda(salon.hub, lost)
        asked = recoveries.ask(copy, "appointment")
        before = (booked_events(salon.hub), booked_events(salon.hub, "appointment.appointment.restored"))

        assert run() == 1

        assert salon.live() == then
        with use_hub(salon.hub):
            back = Appointment.objects.get(pk=deleted.id)
            assert (back.deleted_at, back.number) == (None, deleted.number)
            assert list(back.history.order_by("at", "id").values_list("action", flat=True)) == [
                "created",
                "deleted",
                "restored",
            ]
            [anew] = Appointment.objects.exclude(pk=deleted.id)
            assert (anew.pk, anew.number) != (lost.id, lost.number)
        assert (booked_events(salon.hub), booked_events(salon.hub, "appointment.appointment.restored")) == (
            before[0] + 1,
            before[1] + 1,
        )
        done = fresh(asked)
        assert (done.status, done.last_error) == ("done", "")
        assert done.results == [APPOINTMENTS | {"restored": 1, "created": 1}, SERIES]

    def test_asked_again_nothing_is_booked_twice(self, recoveries, every_app_on):
        salon = Salon(recoveries, every_app_on, ANA)
        copy = salon.lost_since_a_copy(salon.book(salon.cards[0], "10:00"))
        recoveries.ask(copy, "appointment")
        run()
        again = recoveries.ask(copy, "appointment")

        assert run() == 1

        assert len(salon.live()) == 1
        assert fresh(again).results == [APPOINTMENTS, SERIES]

    def test_one_gone_by_in_the_copy_does_not_come_back(self, recoveries, every_app_on):
        salon = Salon(recoveries, every_app_on, ANA)
        copy = salon.lost_since_a_copy(salon.book(salon.cards[0], "10:00"))
        in_the_copy(
            copy,
            "UPDATE appointment_appointment SET start = now() - interval '1 day', \"end\" = now() - interval '23 hours'",
        )
        asked = recoveries.ask(copy, "appointment")

        run()

        assert salon.live() == []
        assert fresh(asked).results == [APPOINTMENTS, SERIES]

    def test_its_customer_lost_too_comes_back_first_whatever_the_order_they_are_asked_in(self, recoveries, every_app_on):
        salon = Salon(recoveries, every_app_on, ANA)
        copy = salon.lost_since_a_copy(salon.book(salon.cards[0], "10:00"))
        run_in(salon.hub, "customer.customer.delete", id=salon.cards[0])
        # Asked appointments first: they need their customer, so Customers goes before (``requires``).
        asked = recoveries.ask(copy, "appointment", "customer")

        run()

        [(name, *_rest)] = salon.live()
        assert name == "Ana López"
        assert [result["app"] for result in fresh(asked).results] == ["customer", "appointment", "appointment"]
        assert fresh(asked).results[1:] == [APPOINTMENTS | {"restored": 1}, SERIES]

    def test_one_whose_time_was_taken_since_is_never_booked_over_and_says_why_and_the_others_come_back(
        self, recoveries, every_app_on
    ):
        salon = Salon(recoveries, every_app_on, ANA, LUIS, MARTA)
        ana, luis, marta = salon.cards
        taken = salon.book(ana, "10:00")
        copy = salon.lost_since_a_copy(taken, salon.book(luis, "11:00"))
        # Its time given to another customer since, with the same professional.
        salon.book(marta, "10:00")
        asked = recoveries.ask(copy, "appointment")

        run()

        assert [one[0] for one in salon.live()] == ["Marta Ruiz", "Luis Pérez"]
        why = the_one_not_booked(asked)
        assert why["id"] == str(taken.id)
        assert why["reason"].startswith("appointment.slot_taken: ")

    def test_one_whose_customer_the_business_no_longer_has_is_not_made_up_and_says_why(self, recoveries, every_app_on):
        salon = Salon(recoveries, every_app_on, ANA, LUIS)
        ana, luis = salon.cards
        lost = salon.book(ana, "10:00")
        copy = salon.lost_since_a_copy(lost, salon.book(luis, "11:00"))
        run_in(salon.hub, "customer.customer.erase", id=ana, reason="Asked under GDPR")
        asked = recoveries.ask(copy, "appointment")

        run()

        assert [one[0] for one in salon.live()] == ["Luis Pérez"]
        why = the_one_not_booked(asked)
        assert why["id"] == str(lost.id)
        assert why["reason"].startswith("customer.customer_unavailable: ")
