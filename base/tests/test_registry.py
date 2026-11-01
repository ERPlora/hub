"""base.registry: what the host gate and the apps read of the registry of hubs (plan 2026-10-17, §1.2)."""

import datetime as dt

import pytest
from django.utils import timezone

from base import registry
from base.models import Hub

pytestmark = pytest.mark.django_db

NOW = dt.datetime(2026, 10, 17, 12, 0, tzinfo=dt.UTC)


def test_a_slug_names_its_hub():
    acme = Hub.objects.create(slug="acme", status="ready")
    assert registry.hub_by_slug("acme") == acme


def test_a_slug_without_a_row_names_none():
    assert registry.hub_by_slug("nobody") is None


def test_only_a_demo_row_is_a_demo():
    Hub.objects.create(slug="demo-0000beef", status="ready", is_demo=True)
    Hub.objects.create(slug="acme", status="ready")
    assert registry.is_demo("demo-0000beef") is True
    assert registry.is_demo("acme") is False
    assert registry.is_demo("nobody") is False


@pytest.mark.parametrize("status", ["cancelled", "archiving", "expired", "dropping", "purged"])
def test_a_hub_that_ended_is_gone(status):
    assert registry.is_gone(Hub(slug="acme", status=status), NOW) is True


@pytest.mark.parametrize("status", ["requested", "creating", "migrating", "seeding", "ready", "failed"])
def test_a_hub_that_did_not_end_is_not_gone(status):
    assert registry.is_gone(Hub(slug="acme", status=status), NOW) is False


def test_a_demo_is_gone_from_the_minute_it_expires_even_before_the_reaper():
    demo = Hub(slug="demo-0000beef", status="ready", is_demo=True, expires_at=NOW)
    assert registry.is_gone(demo, NOW) is True
    assert registry.is_gone(demo, NOW - dt.timedelta(seconds=1)) is False


def test_an_expiry_on_a_hub_that_is_no_demo_means_nothing():
    assert registry.is_gone(Hub(slug="acme", status="ready", expires_at=NOW), NOW) is False


def test_now_is_the_clock_by_default():
    past = timezone.now() - dt.timedelta(minutes=1)
    assert registry.is_gone(Hub(slug="demo-0000beef", status="ready", is_demo=True, expires_at=past)) is True


@pytest.mark.parametrize(
    ("status", "preparing"),
    [
        ("requested", True),
        ("creating", True),
        ("migrating", True),
        ("seeding", True),
        ("failed", True),
        ("ready", False),
        ("cancelled", False),
    ],
)
def test_a_hub_is_preparing_until_it_is_ready(status, preparing):
    assert registry.is_preparing(Hub(slug="acme", status=status)) is preparing


@pytest.mark.parametrize(
    ("db_name", "status", "was_ready", "made"),
    [
        ("", "ready", True, False),  # a business of phase 1 not yet cut (S5): its database is still to be made
        ("hub_x", "ready", False, True),
        ("hub_x", "cancelled", True, True),  # cancelled after it was ready: its database stays
        ("hub_x", "archiving", True, True),
        ("hub_x", "cancelled", False, False),  # cancelled while it was being made
        ("hub_x", "failed", False, False),
        ("hub_x", "seeding", False, False),
        ("hub_x", "requested", False, False),
        ("hub_x", "purged", True, False),  # a demo whose database was dropped
        ("hub_x", "dropping", True, False),
    ],
)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_hub_database_is_made_once_it_was_ready_and_until_it_is_dropped(db_name, status, was_ready, made):
    hub = Hub(slug="acme", db_name=db_name, status=status, ready_at=timezone.now() if was_ready else None)
    assert registry.database_is_made(hub) is made


@pytest.mark.usefixtures("no_test_fallback")
def test_a_ready_business_without_its_own_database_is_not_served_until_its_cut():
    """S5: phase 1's shared database is gone; a business still on control's answers 503 until ``cut_shared_hubs``
    gives it its own (``base.tenancy.cut``), the maintenance one, as one moving to another cluster (W8)."""
    hub = Hub(slug="acme", db_name="", status="ready", ready_at=timezone.now())

    refused = registry.refusal(hub)

    assert (refused.status, refused.code) == (503, registry.HUB_MAINTENANCE)
    assert registry.refusal(Hub(slug="acme", db_name="hub_x", status="ready")) is None
    # One that ended is still gone, with or without a database.
    assert registry.refusal(Hub(slug="acme", db_name="", status="cancelled")).status == 410


def test_under_the_suite_s_fallback_a_business_without_its_own_database_is_served_on_control_s_test_database():
    hub = Hub(slug="acme", db_name="", status="ready", ready_at=timezone.now())

    assert registry.refusal(hub) is None
    assert registry.database_is_made(hub)
