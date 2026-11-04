"""The schedule on the clock of the business, not the deployment's (hub#687; SCHEDULE-F09, F10)."""

import datetime as dt

import pytest
from django.utils import timezone
from live.operations import get

from base.models import Hub
from base.tenancy.context import use_hub

from .conftest import ctx_for

pytestmark = pytest.mark.django_db

CANARY = "Atlantic/Canary"


def run(name):
    op = get(name)
    return op(ctx_for(), op.input())


def test_the_settings_and_the_verdict_are_on_the_businesss_clock(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.UTC))
    with use_hub(Hub(slug="a", timezone=CANARY)):
        settings, verdict = run("schedule.settings.get"), run("schedule.business.is_open")
    assert settings.timezone == verdict.timezone == CANARY
    assert verdict.current_time == "09:00"
