"""Read operations of the schedule app: the week, the special days, the temporary changes, the settings,
«is it open?» and the hours of a range of days (the appointment book's contract)."""

import datetime as dt

import pytest
from live.errors import PermissionDenied
from live.operations import get

from apps.schedule.schemas.fields import NoParamsIn
from apps.schedule.schemas.hours import HoursRangeIn
from apps.schedule.schemas.is_open import IsOpenIn
from apps.schedule.schemas.overrides import OverrideListIn
from apps.schedule.schemas.special_days import SpecialDayListIn

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB


def run(name, data=None, role="hub_admin", **ctx):
    op = get(name)
    return get(name)(ctx_for(role, **ctx), data if data is not None else op.input())


def t(value):
    return dt.time.fromisoformat(value)


def is_open(when=None):
    return run("schedule.business.is_open", IsOpenIn(when=when))


# ── Permissions ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("schedule.week.get", NoParamsIn()),
        ("schedule.special_day.list", SpecialDayListIn()),
        ("schedule.override.list", OverrideListIn()),
        ("schedule.settings.get", NoParamsIn()),
        ("schedule.business.is_open", IsOpenIn()),
        ("schedule.hours.for_range", HoursRangeIn(date_from=dt.date(2026, 8, 17))),
    ],
)
def test_every_role_sees_the_hours_and_nobody_else(name, data):
    for role in ("hub_owner", "hub_admin", "hub_manager", "hub_employee"):
        run(name, data, role)
    with pytest.raises(PermissionDenied):
        run(name, data, permissions=set())
