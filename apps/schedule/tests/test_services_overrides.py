"""Temporary changes (SCHEDULE-F05, F06, F13): a range of dates with other hours or closed; two never cover the same
day."""

import datetime as dt

import pytest
from live.errors import Conflict, InvalidPayload, NotFound

from apps.schedule.models import Override
from apps.schedule.schemas.overrides import OverrideIn, OverridePatchIn, OverrideRefIn

from .conftest import HUB_DB, A, make_override
from .test_services import hours, outbox, run, t

pytestmark = HUB_DB


def test_a_temporary_change_with_its_intervals():
    summer = run(
        "schedule.override.create",
        OverrideIn(
            start_date="2026-08-01",
            end_date="2026-08-31",
            reason="Summer",
            is_closed=False,
            intervals=hours(("18:00", "21:00"), ("10:00", "13:30")),
        ),
    )
    row = Override.objects.get(pk=summer.id)
    assert (row.reason, row.is_closed) == ("Summer", False)
    assert [(i.position, i.open_time) for i in row.intervals.order_by("position")] == [
        (0, t("10:00")),
        (1, t("18:00")),
    ]
    assert outbox() == [
        (
            "schedule.override.created",
            A.key,
            {
                "id": str(summer.id),
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
            },
        )
    ]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-08-28", "2026-08-30"),
        ("2026-07-01", "2026-08-01"),
        ("2026-08-31", "2026-09-05"),
    ],
)
def test_two_temporary_changes_never_cover_the_same_day(start, end):
    make_override("2026-08-01", "2026-08-31", "Vacaciones")
    with pytest.raises(Conflict) as refused:
        run(
            "schedule.override.create",
            OverrideIn(start_date=start, end_date=end, reason="More holidays"),
        )
    assert refused.value.code == "schedule.override_overlaps"
    assert refused.value.fields == {
        "start_date": "Those dates overlap the temporary change “Vacaciones” (08/01/2026 – 08/31/2026)."
    }
    assert Override.objects.count() == 1 and outbox() == []


def test_touching_temporary_changes_are_fine():
    make_override("2026-08-01", "2026-08-15", "First half")
    run(
        "schedule.override.create",
        OverrideIn(
            start_date="2026-08-16", end_date="2026-08-31", reason="Second half"
        ),
    )
    assert Override.objects.count() == 2


def test_correcting_a_temporary_change():
    summer = make_override("2026-07-01", "2026-08-31", "Summer", ("10:00", "14:00"))
    make_override("2026-09-10", "2026-09-12", "Works")
    fixed = run(
        "schedule.override.update",
        OverridePatchIn(override="summer", end_date="2026-09-05"),
    )
    assert (fixed.start_date, fixed.end_date, fixed.reason, fixed.is_closed) == (
        dt.date(2026, 7, 1),
        dt.date(2026, 9, 5),
        "Summer",
        False,
    )
    assert outbox() == [
        (
            "schedule.override.updated",
            A.key,
            {
                "id": str(summer.id),
                "start_date": "2026-07-01",
                "end_date": "2026-09-05",
            },
        )
    ]
    # Over the next change: refused; its own range never clashes with itself.
    with pytest.raises(Conflict):
        run(
            "schedule.override.update",
            OverridePatchIn(id=summer.id, end_date="2026-09-10"),
        )
    with pytest.raises(InvalidPayload) as refused:
        run(
            "schedule.override.update",
            OverridePatchIn(id=summer.id, start_date="2026-09-06"),
        )
    assert refused.value.fields == {
        "end_date": "The end date cannot be before the start date."
    }
    run("schedule.override.update", OverridePatchIn(id=summer.id, is_closed=True))
    assert Override.objects.get(pk=summer.id).intervals.count() == 0


def test_deleting_a_temporary_change_by_a_date_it_covers():
    summer = make_override("2026-07-01", "2026-08-31", "Summer", ("10:00", "14:00"))
    run("schedule.override.delete", OverrideRefIn(override="2026-08-15"))
    assert not Override.objects.exists()
    assert outbox() == [("schedule.override.deleted", A.key, {"id": str(summer.id)})]
    with pytest.raises(NotFound):
        run("schedule.override.delete", OverrideRefIn(override="Summer"))
