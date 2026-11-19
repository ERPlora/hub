"""Several businesses asked to move at once are copied one after another, and each is closed only while its own copy
runs: asked now or for its night, a business stays open until the worker starts its copy, and one a pass does not reach
is taken by a later one. One whose turn comes after its night is over waits, open, for its next night."""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest
from django.db.models import F
from django.utils import timezone

from base.registry import is_copying
from base.tenancy import move
from base.tenancy.tests.test_move import zone_at
from control import queries
from control.admin import staff_context
from control.models import Hub
from control.schemas import MOVE_AT_NIGHT, MOVE_NOW, HubIdIn, HubMoveIn
from control.services import hub_move, hub_move_cancel, night_start
from control.tests.test_admin import a_cluster

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def measured(monkeypatch):
    monkeypatch.setattr(queries, "measure", lambda cluster, names: {name: 1024 for name in names})


@pytest.fixture
def target():
    return a_cluster(name="cluster-2", host="writer-2.example")


@pytest.fixture
def copies(monkeypatch):
    """Each copy the worker makes, in order: the hub copied and the hubs closed while it ran. The copy ends its move."""
    made = []

    def copy(hub_id, **kwargs):
        closed = sorted(hub.slug for hub in Hub.objects.all() if is_copying(hub))
        made.append((Hub.objects.get(pk=hub_id).slug, closed))
        Hub.objects.filter(pk=hub_id).update(cluster=F("moving_to"), moving_to=None)

    monkeypatch.setattr(move, "move_hub", copy)
    return made


def asked(ctx, target, *slugs: str, when: str = MOVE_NOW, zone: str = "Europe/Madrid") -> list[Hub]:
    hubs = [
        Hub.objects.create(slug=slug, status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", timezone=zone)
        for slug in slugs
    ]
    for hub in hubs:
        hub_move(ctx, HubMoveIn(hub=hub.pk, cluster=target.pk, when=when))
    return hubs


def closed() -> list[str]:
    return sorted(hub.slug for hub in Hub.objects.all() if is_copying(hub))


def test_two_hubs_asked_together_only_the_one_being_copied_is_closed(rf, monkeypatch, django_user_model, target):
    root = django_user_model.objects.create_superuser(username="root", password="pw", email="r@example.com")
    request = rf.post("/")
    request.user = root
    hubs = [Hub.objects.create(slug=s, status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}") for s in ("a1", "b1")]
    for hub in hubs:
        hub_move(staff_context(request), HubMoveIn(hub=hub.pk, cluster=target.pk, when="now"))
    moved = []
    monkeypatch.setattr(move, "move_hub", lambda hub_id, **kw: moved.append(hub_id))
    move.run_due()
    assert len(moved) == 1
    assert sorted(is_copying(Hub.objects.get(pk=h.pk)) for h in hubs) == [False, True]


class TestAskedNow:
    def test_each_stays_open_until_its_own_copy_starts(self, admin_ctx, target, copies):
        hubs = asked(admin_ctx, target, "a1", "b1")

        assert closed() == []
        assert move.run_due() == 1
        assert copies == [("a1", ["a1"])]
        assert closed() == []

        assert move.run_due() == 1
        assert copies == [("a1", ["a1"]), ("b1", ["b1"])]
        assert {Hub.objects.get(pk=hub.pk).cluster_id for hub in hubs} == {target.pk}
        assert move.run_due() == 0

    def test_one_the_pass_does_not_reach_keeps_its_place_and_its_turn(self, admin_ctx, target, copies):
        first, second = asked(admin_ctx, target, "a1", "b1")

        move.run_due()

        waiting = Hub.objects.get(pk=second.pk)
        assert (waiting.moving_to_id, waiting.move_scheduled_to_id, waiting.move_scheduled_for) == (None, target.pk, None)
        assert Hub.objects.get(pk=first.pk).cluster_id == target.pk

    def test_cancelled_before_its_turn_it_is_taken_away_and_never_copied(self, admin_ctx, target, copies):
        _, second = asked(admin_ctx, target, "a1", "b1")

        hub_move_cancel(admin_ctx, HubIdIn(id=second.pk))

        cancelled = Hub.objects.get(pk=second.pk)
        assert (cancelled.moving_to_id, cancelled.move_scheduled_to_id, cancelled.move_undo_asked_at) == (None, None, None)
        assert closed() == []
        move.run_due()
        move.run_due()
        assert [slug for slug, _ in copies] == ["a1"]
        assert Hub.objects.get(pk=second.pk).cluster_id is None


class TestAskedForTheNight:
    def test_each_stays_open_until_its_own_copy_starts(self, admin_ctx, target, copies):
        asked(admin_ctx, target, "a1", "b1", when=MOVE_AT_NIGHT, zone=zone_at(timezone.now(), 3))
        now = timezone.now()

        assert move.run_due(now) == 1
        assert copies == [("a1", ["a1"])]
        assert closed() == []

        assert move.run_due(now) == 1
        assert copies == [("a1", ["a1"]), ("b1", ["b1"])]

    def test_one_whose_turn_comes_after_its_night_waits_open_for_the_next(self, admin_ctx, target, copies):
        zone = zone_at(timezone.now(), 3)
        _, second = asked(admin_ctx, target, "a1", "b1", when=MOVE_AT_NIGHT, zone=zone)
        now = timezone.now()
        move.run_due(now)
        morning = now + dt.timedelta(hours=2)

        assert move.run_due(morning) == 0

        assert [slug for slug, _ in copies] == ["a1"]
        waiting = Hub.objects.get(pk=second.pk)
        assert (waiting.moving_to_id, waiting.move_scheduled_to_id) == (None, target.pk)
        assert waiting.move_scheduled_for == night_start(morning, ZoneInfo(zone)) > morning
        assert closed() == []
