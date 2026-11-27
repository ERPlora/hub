"""An employee who asks the assistant for a colleague in the time clock, or for one of her days, hears that she can only
see her own (hub#2688).

Without the team's shifts a person and a day are read only by whoever they belong to, and the read answers that they do
not exist. Told nothing more, the model says the colleague is not in the time clock."""

import json

import pytest
from live.operations import get

from base import assistant
from base.only_theirs import ONLY_THEIRS

from .conftest import HUB_DB, ctx_for, day, make_member

pytestmark = HUB_DB


def answered(ctx, name: str, row) -> dict:
    return json.loads(assistant.tools.run(ctx, get(name), json.dumps({"id": str(row.id)})).content)


@pytest.fixture
def bea_with_a_day():
    bea = make_member("Bea", "Ruiz")
    return {"attendance.person.detail": bea, "attendance.record.detail": day(bea, "2026-10-05T07:00", "2026-10-05T15:00")}


@pytest.mark.parametrize("name", ["attendance.person.detail", "attendance.record.detail"])
def test_ana_asking_for_a_colleagues_person_or_day_hears_she_reads_only_her_own(name, person, bea_with_a_day):
    _, ana = person()
    answer = answered(ana, name, bea_with_a_day[name])
    assert answer["error"]["code"] == "not_found"
    assert answer[ONLY_THEIRS]


@pytest.mark.parametrize("name", ["attendance.person.detail", "attendance.record.detail"])
def test_whoever_sees_the_team_hears_nothing_of_the_kind(name, bea_with_a_day):
    assert ONLY_THEIRS not in answered(ctx_for("hub_manager"), name, bea_with_a_day[name])


def test_her_own_day_is_answered_whole(person):
    ana, ctx = person()
    answer = answered(ctx, "attendance.record.detail", day(ana, "2026-10-05T07:00", "2026-10-05T15:00"))
    assert answer["clock_in_at"]
    assert ONLY_THEIRS not in answer
