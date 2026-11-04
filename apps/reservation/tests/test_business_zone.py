"""Reservations on the clock of the business, not the deployment's (hub#687)."""

import datetime as dt

import pytest

from apps.reservation import queries
from base.models import Hub
from base.tenancy.context import use_hub

from .conftest import pin_clock, run

pytestmark = pytest.mark.django_db

CANARY = "Atlantic/Canary"


def test_the_settings_now_and_a_stay_are_on_the_businesss_clock(monkeypatch):
    pin_clock(monkeypatch, dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.UTC))
    with use_hub(Hub(slug="a", timezone=CANARY)):
        assert run("reservation.settings.get").timezone == CANARY
        assert queries.business_now() == dt.datetime(2026, 11, 2, 9, 0)
        assert queries.starts_at(dt.date(2026, 11, 2), dt.time(21, 30)) == dt.datetime(
            2026, 11, 2, 21, 30, tzinfo=dt.UTC
        )
