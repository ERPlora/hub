"""One time off read whole: its reason and who approved it, by their name or their username; a terminated record's is gone."""

import uuid

import pytest
from django.utils import timezone
from live.errors import NotFound

from apps.staff.models import TimeOff
from apps.staff.queries.time_off_reads import load_time_off
from apps.staff.schemas.fields import ByIdIn

from .conftest import HUB_DB, TERMINATED, make_member, make_time_off, run

pytestmark = HUB_DB


def test_time_off_detail_with_its_reason_and_approver(make_user):
    boss = make_user("boss", first_name="Marta")
    leave = make_time_off(
        make_member(),
        "2026-10-12",
        reason="Surgery",
        notes="Back on Monday",
        status=TimeOff.Status.APPROVED,
        approved_by=boss.person,
        approved_at=timezone.now(),
    )
    detail = run("staff.time_off.detail", ByIdIn(id=leave.id), "hub_manager")
    assert (detail.reason, detail.notes, detail.approved_by_name, detail.approved_at) == (
        "Surgery",
        "Back on Monday",
        "Marta",
        leave.approved_at,
    )


def test_time_off_detail_names_an_approver_without_a_name_by_username(make_user):
    leave = make_time_off(make_member(), "2026-10-12", approved_by=make_user("saas:42").person)
    assert (
        run("staff.time_off.detail", ByIdIn(id=leave.id)).approved_by_name == "saas:42"
    )
    assert load_time_off(leave.id).approved_by_name == "saas:42"


def test_time_off_detail_of_a_missing_or_terminated_record_is_not_found():
    gone = make_time_off(make_member(status=TERMINATED), "2026-10-12")
    for time_off_id in (gone.id, uuid.uuid7()):
        with pytest.raises(NotFound):
            run("staff.time_off.detail", ByIdIn(id=time_off_id))
