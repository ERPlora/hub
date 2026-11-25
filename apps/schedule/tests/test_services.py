"""Write operations of the schedule app: one operation = one transaction with its events in the outbox.

A refused command leaves no trace (no row, no event). Cases from the old module's WORKFLOW
(SCHEDULE-F02 … F08) and its handler and engine tests, plus the
corrections of the port (SCHEDULE-F13, freed dates).
"""

import datetime as dt

import pytest
from live.errors import PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.schedule.models import ScheduleSettings
from apps.schedule.schemas.fields import NoParamsIn
from apps.schedule.schemas.overrides import OverrideIn, OverridePatchIn, OverrideRefIn
from apps.schedule.schemas.settings import SettingsIn
from apps.schedule.schemas.special_days import BulkSpecialDayIn, SpecialDayIn, SpecialDayPatchIn, SpecialDayRefIn
from apps.schedule.schemas.week import SetDayIn

from base.tenancy.context import use_hub

from .conftest import HUB_DB, B, ctx_for, make_override, make_special_day

pytestmark = HUB_DB


def run(name, data, role="hub_admin", **ctx):
    return get(name)(ctx_for(role, **ctx), data)


def outbox():
    return list(
        OutboxEvent.objects.order_by("id").values_list("name", "scope_key", "payload")
    )


def names():
    return [name for name, _, _ in outbox()]


def t(value):
    return dt.time.fromisoformat(value)


def hours(*pairs):
    return [{"open_time": start, "close_time": end} for start, end in pairs]


def confirmed() -> bool:
    return ScheduleSettings.objects.filter(hours_confirmed=True).exists()


# ── Permissions ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "data", "permission"),
    [
        (
            "schedule.week.set_day",
            lambda: SetDayIn(weekday=0, is_closed=True),
            "schedule.change",
        ),
        ("schedule.week.confirm", lambda: NoParamsIn(), "schedule.change"),
        (
            "schedule.special_day.create",
            lambda: SpecialDayIn(date="2026-12-25", name="Christmas"),
            "schedule.add",
        ),
        (
            "schedule.special_day.bulk_create",
            lambda: BulkSpecialDayIn(
                special_days=[{"date": "2026-12-25", "name": "Christmas"}]
            ),
            "schedule.add",
        ),
        (
            "schedule.special_day.update",
            lambda: SpecialDayPatchIn(special_day="Christmas", notes="x"),
            "schedule.change",
        ),
        (
            "schedule.special_day.delete",
            lambda: SpecialDayRefIn(special_day="Christmas"),
            "schedule.delete",
        ),
        (
            "schedule.override.create",
            lambda: OverrideIn(
                start_date="2026-08-01", end_date="2026-08-02", reason="x"
            ),
            "schedule.add",
        ),
        (
            "schedule.override.update",
            lambda: OverridePatchIn(override="Holidays", reason="y"),
            "schedule.change",
        ),
        (
            "schedule.override.delete",
            lambda: OverrideRefIn(override="Holidays"),
            "schedule.delete",
        ),
        (
            "schedule.settings.update",
            lambda: SettingsIn(week_starts_on=7),
            "schedule.manage_settings",
        ),
    ],
)
def test_an_employee_only_looks_and_each_action_needs_its_permission(
    name, data, permission
):
    make_special_day("2026-12-24", "Christmas")
    make_override("2026-03-01", "2026-03-02", "Holidays")
    with pytest.raises(PermissionDenied):
        run(name, data(), "hub_employee")
    with pytest.raises(PermissionDenied):
        run(name, data(), permissions={"schedule.view"})
    assert outbox() == []
    run(name, data(), permissions={"schedule.view", permission})


# ── The live notice ────────────────────────────────────────────────────────────────────────────


def test_the_live_notice_goes_to_the_callers_scope_only(hub_b):
    with use_hub(hub_b):
        run("schedule.week.set_day", SetDayIn(weekday=1, is_closed=True), scope=B)
        assert outbox() == [("schedule.week.updated", B.key, {"weekday": 1})]
        assert set(OutboxEvent.objects.values_list("scope_kind", flat=True)) == {B.kind}
    assert outbox() == []
