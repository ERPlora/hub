"""base.system: what System's operations share and touches no database (APP-BASE-7)."""

import datetime as dt

from django.utils import translation

from base import system


def test_an_app_is_named_as_the_business_knows_it_in_its_language():
    with translation.override("es"):
        assert system.app_name("invoice") == "Facturación"
    with translation.override("en"):
        assert system.app_name("invoice") == "Invoicing"


def test_an_app_the_deployment_no_longer_has_keeps_its_label():
    assert system.app_name("oldapp") == "oldapp"


def test_the_release_date_in_utc_or_none_never_made_up():
    assert system.released_at("2026-10-23T20:50:00+02:00") == dt.datetime(2026, 10, 23, 18, 50, tzinfo=dt.UTC)
    assert system.released_at("") is None
    assert system.released_at("yesterday") is None
    assert system.released_at("2026-10-23T20:50:00") is None  # no offset: which time zone is unknown


def test_the_version_is_the_short_commit_or_dev():
    assert system.version("4da2a10c9e1f5b7d8a6c3e2f1b0a9d8c7e6f5a4b") == "4da2a10"
    assert system.version("") == "dev"
