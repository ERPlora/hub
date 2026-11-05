"""The public web's «today» reads the one place the Hub reads a zone from (hub#687)."""

import datetime as dt

from django.utils import timezone

from apps.website.render import local_day

#: Monday in Madrid and in the Canaries, still Sunday in New York.
MOMENT = dt.datetime(2026, 10, 19, 2, 30, tzinfo=dt.UTC)


def test_a_hub_with_no_zone_it_knows_is_on_the_deployments_clock():
    with timezone.override("America/New_York"):
        assert local_day("", MOMENT) == "sun"
        assert local_day("Mars/Olympus", MOMENT) == "sun"
        assert local_day("Atlantic/Canary", MOMENT) == "mon"
