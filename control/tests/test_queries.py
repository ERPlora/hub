"""What the worker's metrics read of the registry (hub#488; PLAN-AWS §8, PLAN-DB §6 and §8): one aggregate of control.

``registry_health(now)`` answers, in one query: since when the oldest hub still being prepared waits (requested,
creating, migrating, seeding, or failed and retried), how many hubs failed, and since when the oldest demo that ended
waits to be dropped (its time up but still open, expired or dropping; never purged). A demo whose time is up is no
sign-up still being prepared: it is an ended demo, the reaper's.
"""

import datetime as dt

import pytest
from django.utils import timezone

from control.models import Hub
from control.queries import RegistryHealth, registry_health

pytestmark = pytest.mark.django_db


def make(slug: str, status: str, *, created: dt.datetime, **more) -> Hub:
    """A registry row in ``status`` created at ``created`` (``created_at`` is ``auto_now_add``: set after the insert)."""
    hub = Hub.objects.create(slug=slug, status=status, **more)
    Hub.objects.filter(pk=hub.pk).update(created_at=created, **({"updated_at": more["updated_at"]} if "updated_at" in more else {}))
    return hub


def test_with_every_hub_ready_nothing_waits_and_none_failed():
    """The suite's local hubs ``a`` and ``b`` are ready (``conftest.local_hubs``)."""
    assert registry_health(timezone.now()) == RegistryHealth(oldest_preparing_since=None, failed=0, oldest_ended_demo_since=None)


@pytest.mark.parametrize("status", ["requested", "creating", "migrating", "seeding", "failed"])
def test_a_hub_still_being_prepared_waits_since_it_was_created(status):
    now = timezone.now()
    make("acme", status, created=now - dt.timedelta(minutes=12))

    assert registry_health(now).oldest_preparing_since == now - dt.timedelta(minutes=12)


def test_the_oldest_of_the_hubs_being_prepared_is_the_one_read():
    now = timezone.now()
    make("young", "creating", created=now - dt.timedelta(minutes=2))
    make("old", "requested", created=now - dt.timedelta(minutes=40))
    make("middle", "failed", created=now - dt.timedelta(minutes=20))

    assert registry_health(now).oldest_preparing_since == now - dt.timedelta(minutes=40)


@pytest.mark.parametrize("status", ["ready", "cancelled", "archiving", "expired", "dropping", "purged"])
def test_a_hub_no_longer_being_prepared_never_waits(status):
    now = timezone.now()
    make("acme", status, created=now - dt.timedelta(days=3))

    assert registry_health(now).oldest_preparing_since is None


def test_a_demo_whose_time_is_up_is_an_ended_demo_not_a_sign_up_still_being_prepared():
    now = timezone.now()
    make("demo-x", "creating", created=now - dt.timedelta(hours=3), is_demo=True, expires_at=now - dt.timedelta(minutes=5))
    make("demo-y", "creating", created=now - dt.timedelta(minutes=7), is_demo=True, expires_at=now + dt.timedelta(hours=1))

    health = registry_health(now)

    assert health.oldest_preparing_since == now - dt.timedelta(minutes=7)
    assert health.oldest_ended_demo_since == now - dt.timedelta(minutes=5)


def test_the_failed_hubs_are_counted_but_a_demo_whose_time_is_up():
    now = timezone.now()
    make("one", "failed", created=now)
    make("two", "failed", created=now)
    make("three", "creating", created=now)
    make("demo-x", "failed", created=now, is_demo=True, expires_at=now - dt.timedelta(seconds=1))

    assert registry_health(now).failed == 2


@pytest.mark.parametrize("status", ["requested", "creating", "migrating", "seeding", "failed", "ready"])
def test_an_open_demo_whose_time_is_up_waits_to_be_dropped_since_it_ended(status):
    now = timezone.now()
    make("demo-x", status, created=now - dt.timedelta(days=1), is_demo=True, expires_at=now - dt.timedelta(minutes=31))

    assert registry_health(now).oldest_ended_demo_since == now - dt.timedelta(minutes=31)


@pytest.mark.parametrize("status", ["expired", "dropping"])
def test_an_expired_or_dropping_demo_waits_to_be_dropped_since_it_ended(status):
    now = timezone.now()
    make("demo-x", status, created=now - dt.timedelta(days=1), is_demo=True, expires_at=now - dt.timedelta(minutes=45))

    assert registry_health(now).oldest_ended_demo_since == now - dt.timedelta(minutes=45)


def test_an_expired_demo_without_its_end_waits_since_it_last_changed():
    now = timezone.now()
    make("demo-x", "expired", created=now - dt.timedelta(days=1), is_demo=True, updated_at=now - dt.timedelta(minutes=50))

    assert registry_health(now).oldest_ended_demo_since == now - dt.timedelta(minutes=50)


def test_the_oldest_ended_demo_is_the_one_read():
    now = timezone.now()
    make("demo-x", "expired", created=now, is_demo=True, expires_at=now - dt.timedelta(minutes=3))
    make("demo-y", "dropping", created=now, is_demo=True, expires_at=now - dt.timedelta(minutes=90))

    assert registry_health(now).oldest_ended_demo_since == now - dt.timedelta(minutes=90)


def test_a_demo_still_open_a_purged_one_and_a_business_that_left_wait_for_no_drop():
    now = timezone.now()
    make("demo-x", "ready", created=now, is_demo=True, expires_at=now + dt.timedelta(minutes=1))
    make("demo-y", "purged", created=now, is_demo=True, expires_at=now - dt.timedelta(days=2))
    make("gone", "cancelled", created=now, expires_at=now - dt.timedelta(days=2))
    make("old", "expired", created=now, expires_at=now - dt.timedelta(days=2))

    assert registry_health(now).oldest_ended_demo_since is None


def test_one_query_reads_it_all(django_assert_num_queries):
    now = timezone.now()
    make("acme", "failed", created=now)

    with django_assert_num_queries(1):
        registry_health(now)
