"""«Only theirs or all» in Appointments: with «See the whole agenda» (``appointment.view_appointment``) a person reads
every professional's appointments and repeating appointments; with only «See their own agenda»
(``appointment.view_own_appointment``) they read and touch those of the staff record linked to their account, and
another's answers as one that does not exist: the same 404, never a 403 that tells it is there. A caller that is not
a person (an API key, an automation) has no agenda of its own: it reads all that its permission opens.

Over HTTP, as the screens, the assistant and the API ask.
"""

import pytest
from django.test import Client

from apps.appointment.models import Appointment, Recurring
from apps.flow.tests.test_api import get, post

from .conftest import HUB_DB, MONDAY, A, at, make_appointment, make_series, make_settings, run, wall

pytestmark = HUB_DB

EVERYONE = {"Ana López", "Bea Ruiz"}


@pytest.fixture
def two_agendas(salon):
    """An appointment and a repeating appointment of Ana's, and the same of Bea's."""
    return {
        "ana": make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00")),
        "bea": make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "11:00")),
        "ana_series": make_series(salon),
        "bea_series": make_series(salon, staff=salon.bea, day_of_week=1),
    }


def signed_in(client, make_user, role, member=None):
    user = make_user("bea", host=A.key, role=role)
    if member is not None:
        member.user = user.person
        member.save(update_fields=["user"])
    client.force_login(user)
    return client


def whose_are_read(client) -> tuple[set[str], set[str]]:
    """Whose appointments of the week and whose repeating appointments ``client`` lists."""
    appointments = get(client, "/appointment/appointments", date_from=MONDAY.isoformat()).json()["rows"]
    series = get(client, "/appointment/recurring").json()["rows"]
    return {row["staff_name"] for row in appointments}, {row["staff_name"] for row in series}


def opened(client, records) -> list[int]:
    """How Ana's appointment, its history and Ana's repeating appointment answer ``client``."""
    return [
        get(client, "/appointment/appointments/detail", id=str(records["ana"].id)).status_code,
        get(client, "/appointment/appointments/history", id=str(records["ana"].id)).status_code,
        get(client, "/appointment/recurring/detail", id=str(records["ana_series"].id)).status_code,
    ]


def test_the_manager_reads_and_opens_every_professionals_agenda(client, make_user, two_agendas):
    manager = signed_in(client, make_user, "hub_manager")
    assert whose_are_read(manager) == (EVERYONE, EVERYONE)
    assert opened(manager, two_agendas) == [200, 200, 200]


def test_an_employee_reads_only_their_own_and_a_colleagues_is_not_found(client, make_user, salon, two_agendas):
    employee = signed_in(client, make_user, "hub_employee", member=salon.bea)
    assert whose_are_read(employee) == ({"Bea Ruiz"}, {"Bea Ruiz"})
    own = get(employee, "/appointment/appointments/detail", id=str(two_agendas["bea"].id))
    assert (own.status_code, own.json()["staff_name"]) == (200, "Bea Ruiz")
    assert opened(employee, two_agendas) == [404, 404, 404]
    codes = {
        get(employee, "/appointment/appointments/detail", id=str(two_agendas["ana"].id)).json()["error"]["code"],
        get(employee, "/appointment/recurring/detail", id=str(two_agendas["ana_series"].id)).json()["error"]["code"],
    }
    assert codes == {"appointment.appointment_not_found", "appointment.recurring_not_found"}


def test_an_employee_cannot_touch_a_colleagues_appointment_nor_series_and_they_stay_as_they_were(
    client, make_user, salon, two_agendas
):
    employee = signed_in(client, make_user, "hub_employee", member=salon.bea)
    cancel = post(employee, "/appointment/appointments/cancel", {"id": str(two_agendas["ana"].id), "reason": "Ill"})
    pause = post(employee, "/appointment/recurring/deactivate", {"id": str(two_agendas["ana_series"].id)})
    assert [(answer.status_code, answer.json()["error"]["code"]) for answer in (cancel, pause)] == [
        (404, "appointment.appointment_not_found"),
        (404, "appointment.recurring_not_found"),
    ]
    assert Appointment.objects.get(pk=two_agendas["ana"].id).status == "confirmed"
    assert Recurring.objects.get(pk=two_agendas["ana_series"].id).is_active is True


def test_an_api_key_reads_every_appointment_its_permission_opens(client, make_user, two_agendas):
    admin = signed_in(client, make_user, "hub_admin")
    created = post(admin, "/keys", {"name": "Booking site", "rate_per_minute": 60, "scopes": {"*": ["read"]}})
    key = Client(HTTP_AUTHORIZATION=f"Bearer {created.json()['token']}")
    assert whose_are_read(key) == (EVERYONE, EVERYONE)
    assert opened(key, two_agendas) == [200, 200, 200]


# Telling that a time is taken opens no appointment: whose it is is told only to who may see that professional's
# agenda — a person's own, or everyone's with «See the whole agenda». A caller that is not a person, with only the
# permission of the free times, hears the time is taken and not by whom.


@pytest.mark.parametrize("actor", ["flow_run:0190a1b2", None])
def test_what_is_not_a_person_hears_a_time_is_taken_but_not_by_whom(salon, two_agendas, actor):
    make_settings(allow_overlapping=False)
    asked = {"staff_id": str(salon.ana.id), "start": wall(MONDAY, "10:00"), "duration_minutes": 30}
    blind = run("appointment.availability.check", asked, actor=actor, permissions={"appointment.view_schedule"})
    seeing = run(
        "appointment.availability.check",
        asked,
        actor=actor,
        permissions={"appointment.view_schedule", "appointment.view_appointment"},
    )
    assert (blind.code, blind.conflicts) == ("overlap", [])
    assert [one.number for one in seeing.conflicts] == [two_agendas["ana"].number]
