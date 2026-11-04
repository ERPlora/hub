"""The cut-off of the till on the clock of the business, not the deployment's (hub#687)."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict

from apps.cash_register.models import Session
from apps.cash_register.queries import last_cut_off
from apps.cash_register.tests.conftest import open_session, run
from base.models import Hub
from base.tenancy.context import use_hub

pytestmark = pytest.mark.django_db

CANARY = "Atlantic/Canary"


def in_canary():
    return use_hub(Hub(slug="a", timezone=CANARY))


def test_the_last_cut_off_is_at_its_hour_on_the_businesss_clock():
    with in_canary():
        cut = last_cut_off(dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.UTC), dt.time(4, 0))
    assert cut == dt.datetime(2026, 11, 2, 4, 0, tzinfo=dt.UTC)


def test_the_refusal_past_the_cut_off_says_the_hour_the_business_set():
    with in_canary():
        open_session(10000)
        Session.objects.update(opened_at=timezone.now() - dt.timedelta(days=2))
        run("cash_register.settings.update", {"auto_close_enabled": True, "auto_close_time": "04:00"})
        with pytest.raises(Conflict) as refused:
            run("cash_register.session.closing_summary", {"closing_balance": 10000})
    assert refused.value.code == "cash_register.session_auto_close_due"
    assert "04:00" in str(refused.value)
