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
