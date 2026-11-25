"""What each hub used and did, day by day, and the nights it was measured."""

import pytest
from django.db import IntegrityError, transaction

from control.models.hubs import Hub

pytestmark = pytest.mark.django_db


def test_a_day_of_use_is_one_row_per_hub_and_day():
    from control.models.usage import HubUsageDaily

    hub = Hub.objects.create(slug="acme", db_name="hub_test_usage")
    HubUsageDaily.objects.create(hub=hub, day="2026-10-30", db_bytes=1, measured_at="2026-10-31T00:15Z")

    with pytest.raises(IntegrityError), transaction.atomic():
        HubUsageDaily.objects.create(hub=hub, day="2026-10-30", db_bytes=2, measured_at="2026-10-31T00:16Z")
    row = HubUsageDaily.objects.get()
    assert (row.s3_bytes, row.active_users_1d, row.active_users_30d) == (0, 0, 0)


def test_a_person_counts_once_a_day_on_a_hub():
    from control.models.usage import HubVisit

    HubVisit.objects.bulk_create(
        [HubVisit(host="acme", day="2026-10-30", saas_user_id="u1")] * 2, ignore_conflicts=True
    )
    HubVisit.objects.bulk_create([HubVisit(host="acme", day="2026-10-31", saas_user_id="u1")], ignore_conflicts=True)

    assert HubVisit.objects.count() == 2


def test_the_activity_of_a_day_is_one_row_per_hub_and_day_from_zero():
    from control.models.usage import HubActivityDaily

    hub = Hub.objects.create(slug="acme", db_name="hub_test_activity")
    HubActivityDaily.objects.create(hub=hub, day="2026-10-30")

    with pytest.raises(IntegrityError), transaction.atomic():
        HubActivityDaily.objects.create(hub=hub, day="2026-10-30")
    row = HubActivityDaily.objects.get()
    assert (row.requests, row.peak_connections, row.busy_requests) == (0, 0, 0)


def test_a_visit_says_when_its_person_was_last_seen_or_nothing_yet():
    from control.models.usage import HubVisit

    visit = HubVisit.objects.create(host="acme", day="2026-10-30", saas_user_id="u1")
    assert visit.last_seen_at is None

    HubVisit.objects.filter(pk=visit.pk).update(last_seen_at="2026-10-30T10:00Z")
    visit.refresh_from_db()
    assert visit.last_seen_at.isoformat() == "2026-10-30T10:00:00+00:00"


def test_a_night_of_measuring_is_one_row_per_day():
    from control.models.usage import UsageRun

    UsageRun.objects.create(day="2026-10-30", started_at="2026-10-31T00:15Z")

    with pytest.raises(IntegrityError), transaction.atomic():
        UsageRun.objects.create(day="2026-10-30", started_at="2026-10-31T00:16Z")
    assert UsageRun.objects.get().finished_at is None
