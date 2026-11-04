"""The business's clock, one reading for all of the Hub (hub#687).

The SaaS keeps each business's time zone and pushes it to the registry (``control.Hub.timezone``); the assistant's card
read it, and every app and every text a person reads read the deployment's (``settings.TIME_ZONE``). So a business in
the Canaries (Settings › Business) read 9:00 on the card and 10:00 in the question of «Ask someone first», in the
WhatsApp and in the agenda. ``base.business.business_zone`` is the one place: the zone of the hub at work (``use_hub``,
as a request, the live executor and the worker enter it), the deployment's when it has none Python knows. These tests
use a zone that is not the deployment's; each app proves its own reading in its ``tests/test_business_zone.py``.
"""

from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from live.context import OperationContext, Scope
from live.operations import get

from base import assistant, business
from base.home import moment
from base.models import Hub
from base.permissions import VIEW_HOME
from base.tenancy.context import HubContextMissing, use_control, use_hub

CANARY = "Atlantic/Canary"
#: 10:00 on the deployment's clock, 9:00 on the Canaries': one hour apart all year round.
INSTANT = "2026-11-02T10:00:00+01:00"


def in_hub(zone: str, slug: str = "a"):
    return use_hub(Hub(slug=slug, timezone=zone))


def test_the_deployment_is_not_on_the_clock_these_tests_use():
    assert settings.TIME_ZONE == "Europe/Madrid"


def test_the_business_zone_is_the_hubs_and_not_the_deployments():
    with in_hub(CANARY):
        assert business.business_zone() == ZoneInfo(CANARY)
        assert business.zone_name() == CANARY


def test_each_hub_reads_its_own_zone_and_leaving_one_gives_the_other_back():
    with in_hub(CANARY):
        with in_hub("Asia/Tokyo", "b"):
            assert business.zone_name() == "Asia/Tokyo"
        assert business.zone_name() == CANARY


@pytest.mark.parametrize("name", ["", "Mars/Olympus", "America", "../etc"])
def test_a_hub_with_no_zone_python_knows_is_on_the_deployments_clock(name):
    with in_hub(name):
        assert business.zone_name() == settings.TIME_ZONE


def test_the_platform_is_on_the_deployments_clock():
    with use_control():
        assert business.zone_name() == settings.TIME_ZONE


def test_with_no_hub_nor_platform_at_work_it_fails_as_any_read_of_a_hub_does(no_test_fallback):
    """No hour is told on a clock nobody chose."""
    with pytest.raises(HubContextMissing):
        business.business_zone()


def test_a_zone_is_named_by_its_iana_name():
    assert business.zone_name(ZoneInfo("Asia/Tokyo")) == "Asia/Tokyo"
    assert business.zone_name(business.zone_of("Mars/Olympus")) == settings.TIME_ZONE


@pytest.mark.django_db
def test_settings_names_the_clock_every_app_reads():
    """Settings › Business names the zone the hours are really told in, not one that does not exist."""
    read = get("base.business.get")
    context = OperationContext(scope=Scope("host", "a"), actor="ana", permissions=frozenset({VIEW_HOME}), language="en")
    Hub.objects.update_or_create(slug="a", defaults={"timezone": CANARY})
    assert read(context, read.input()).timezone == CANARY
    Hub.objects.filter(slug="a").update(timezone="Mars/Olympus")
    assert read(context, read.input()).timezone == settings.TIME_ZONE


def test_a_card_says_the_businesss_hour_also_with_no_person_at_hand():
    """An automation's card has no person to read Settings › Business as: it is the same business, the same clock."""
    with in_hub(CANARY):
        card = assistant.card(get("appointment.appointment.create"), {"start": INSTANT}, "es")
    assert {field["name"]: field["value"] for field in card["fields"]}["start"] == "2 nov 2026, 9:00"


def test_an_instant_of_a_notice_is_read_on_the_businesss_clock():
    """``base.home.moment``: a notice of the Home's (``{at:%H:%M}``) and the words of an automation (``words_for``)."""
    with in_hub(CANARY):
        assert moment(INSTANT).hour == 9
    with in_hub("Europe/Madrid"):
        assert moment(INSTANT).hour == 10
