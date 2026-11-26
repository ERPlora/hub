"""An employee who asks the assistant for a colleague's appointments hears that she can only see her own (hub#2688).

Without «See the whole agenda» the list gives Bea only hers, as her agenda does. Told nothing more, the model read the
empty answer as a fact and said «Ana has no appointments either» when Ana had two."""

import json

import pytest
from live.operations import get

from base import assistant
from base.only_theirs import ONLY_THEIRS

from .conftest import HUB_DB, MONDAY, at, ctx_for, employee_linked_to, make_appointment, make_customer, make_member
from .conftest import make_service

pytestmark = HUB_DB

LIST = "appointment.appointment.list"
WEEK = {"date_from": str(MONDAY), "date_to": str(MONDAY)}


@pytest.fixture
def team():
    """Ana with two appointments on Monday and Bea with none."""
    ana, bea, cut = make_member("Ana", "Ruiz"), make_member("Bea", "Gil"), make_service("Corte de mujer")
    make_appointment(make_customer("Lucía Pérez"), ana, [cut], at(MONDAY, "10:00"))
    make_appointment(make_customer("Carmen Ruiz", phone="+34600444555"), ana, [cut], at(MONDAY, "12:00"))
    return ana, bea


def answered(ctx, data: dict) -> dict:
    outcome = assistant.tools.run(ctx, get(LIST), json.dumps(data))
    assert outcome.outcome == "ok", outcome.content
    return json.loads(outcome.content)


def test_bea_asking_for_anas_appointments_hears_the_answer_holds_only_her_own(team, make_user):
    # flow: APPOINTMENT-F27 (el empleado ve la suya)
    ana, bea = team
    answer = answered(employee_linked_to(bea, make_user), {**WEEK, "staff": "Ana"})
    assert answer["rows"] == []
    assert answer[ONLY_THEIRS]


def test_whoever_sees_the_whole_agenda_hears_nothing_of_the_kind(team):
    answer = answered(ctx_for("hub_owner"), {**WEEK, "staff": "Ana"})
    assert len(answer["rows"]) == 2
    assert ONLY_THEIRS not in answer
