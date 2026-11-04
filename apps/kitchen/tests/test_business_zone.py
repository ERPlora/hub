"""The kitchen's day on the clock of the business, not the deployment's (hub#687)."""

import datetime as dt

import pytest

from apps.kitchen import queries
from base.models import Hub
from base.tenancy.context import use_hub

from .conftest import run

pytestmark = pytest.mark.django_db

CANARY = "Atlantic/Canary"


def test_the_settings_and_the_day_are_on_the_businesss_clock():
    with use_hub(Hub(slug="a", timezone=CANARY)):
        assert run("kitchen.settings.get", {}).timezone == CANARY
        # 23:30 UTC of the 2nd is the 2nd in the Canaries, the 3rd in Madrid.
        assert queries.business_day(dt.datetime(2026, 11, 2, 23, 30, tzinfo=dt.UTC)) == dt.date(2026, 11, 2)
        assert queries.start_of(dt.date(2026, 11, 2)) == dt.datetime(2026, 11, 2, 0, 0, tzinfo=dt.UTC)
