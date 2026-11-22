"""A move asked for the business's night."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from live.errors import Conflict

from control import services
from control.models import Cluster
from control.schemas import ClusterIdIn
from control.tests.conftest import a_cluster, a_ready_hub, events

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("nothing_cached")]


class TestTheNight:
    """A move asked for the night starts between ``NIGHT_STARTS`` and ``NIGHT_ENDS`` on the business's own clock: at once
    inside that window, else at the next 03:00 there. Its edges, and the two nights a year the clock changes."""

    MADRID = ZoneInfo("Europe/Madrid")

    @pytest.mark.parametrize(
        ("now", "starts"),
        [
            # 16 November 2026 is on winter time in Madrid (UTC+1).
            pytest.param("2026-11-16T01:59:59+00:00", "2026-11-16T02:00:00+00:00", id="at 02:59:59 it waits for 03:00"),
            pytest.param("2026-11-16T02:00:00+00:00", "2026-11-16T02:00:00+00:00", id="at 03:00 it starts at once"),
            pytest.param("2026-11-16T03:59:59+00:00", "2026-11-16T03:59:59+00:00", id="at 04:59:59 it starts at once"),
            pytest.param("2026-11-16T04:00:00+00:00", "2026-11-17T02:00:00+00:00", id="at 05:00 it waits a night"),
            pytest.param("2027-03-28T00:30:00+00:00", "2027-03-28T01:00:00+00:00", id="the night the clock goes forward"),
            pytest.param("2026-10-24T22:30:00+00:00", "2026-10-25T02:00:00+00:00", id="the night the clock goes back"),
        ],
    )
    def test_it_starts_within_the_window_of_the_business_s_own_clock(self, now, starts):
        assert services.night_start(dt.datetime.fromisoformat(now), self.MADRID) == dt.datetime.fromisoformat(starts)

    def test_the_window_is_from_three_to_five(self):
        assert (services.NIGHT_STARTS, services.NIGHT_ENDS) == (dt.time(3), dt.time(5))


class TestMoveAtNight:
    """``control.hub.move`` with ``when="at_night"`` leaves the move asked for the business's next night
    (``move_scheduled_to``, ``move_scheduled_for``): nothing closes now, and the worker starts it then
    (``base.tenancy.move``). It is refused for what a move now is refused for, and «Cancel the move» takes it away while
    it has not started."""

    #: 13:00 in Madrid, 07:00 in New York.
    NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.UTC)

    @pytest.fixture(autouse=True)
    def at_noon(self, monkeypatch):
        monkeypatch.setattr(timezone, "now", lambda: self.NOW)

    def test_waits_for_the_next_night_of_each_business_and_closes_nothing_meanwhile(self, admin_ctx, small):
        from base import registry
        from control.schemas import HubMoveIn

        old, new = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
        madrid = a_ready_hub(cluster=old, timezone="Europe/Madrid", last_error="schema_failed: an old one")
        york = a_ready_hub(slug="bistro", cluster=old, timezone="America/New_York")

        out = services.hub_move(admin_ctx, HubMoveIn(hub=madrid.pk, cluster=new.pk, when="at_night"))
        services.hub_move(admin_ctx, HubMoveIn(hub=york.pk, cluster=new.pk, when="at_night"))

        madrid.refresh_from_db()
        york.refresh_from_db()
        assert (madrid.moving_to_id, madrid.move_scheduled_to_id, madrid.last_error) == (None, new.pk, "")
        assert madrid.move_scheduled_for == dt.datetime(2026, 11, 17, 2, 0, tzinfo=dt.UTC)
        assert york.move_scheduled_for == dt.datetime(2026, 11, 17, 8, 0, tzinfo=dt.UTC)
        assert (out.moving_to, out.scheduled_to, out.scheduled_for) == (None, new.pk, madrid.move_scheduled_for)
        assert registry.refusal(madrid) is None
        assert events("control.hub.move_scheduled")[0] == {
            "id": str(madrid.pk),
            "slug": "acme",
            "from": str(old.pk),
            "to": str(new.pk),
            "at": "2026-11-17T02:00:00+00:00",
        }
        assert events("control.hub.move_requested") == []

    @pytest.mark.parametrize("zone", ["", "Mars/Olympus"])
    def test_a_business_without_a_zone_python_knows_keeps_the_deployment_s_clock(self, admin_ctx, small, settings, zone):
        from control.schemas import HubMoveIn

        settings.TIME_ZONE = "America/New_York"
        new = a_cluster()
        hub = a_ready_hub(timezone=zone)

        services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk, when="at_night"))

        hub.refresh_from_db()
        assert hub.move_scheduled_for == dt.datetime(2026, 11, 17, 8, 0, tzinfo=dt.UTC)

    def test_a_move_now_is_still_asked_at_once(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        new = a_cluster()
        hub = a_ready_hub(timezone="Europe/Madrid")

        out = services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk))

        hub.refresh_from_db()
        assert (hub.moving_to_id, hub.move_scheduled_to_id, hub.move_scheduled_for) == (new.pk, None, None)
        assert (out.scheduled_to, out.scheduled_for) == (None, None)

    def test_it_is_refused_for_what_a_move_now_is_refused_for(self, admin_ctx, monkeypatch):
        from control import queries
        from control.schemas import HubMoveIn

        closed, new = a_cluster(is_open=False), a_cluster(name="cluster-2", host="writer-2.example")
        hub = a_ready_hub()
        monkeypatch.setattr(queries, "measure", lambda cluster, names: {})

        for cluster, code in ((closed, "control.cluster_closed"), (new, "control.hub_database_missing")):
            with pytest.raises(Conflict) as refused:
                services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=cluster.pk, when="at_night"))
            assert refused.value.code == code
        hub.refresh_from_db()
        assert (hub.move_scheduled_to_id, hub.move_scheduled_for) == (None, None)

    def test_a_hub_with_a_move_asked_for_the_night_takes_no_other_until_it_is_cancelled(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        new, other = a_cluster(), a_cluster(name="cluster-2", host="writer-2.example")
        hub = a_ready_hub()
        services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk, when="at_night"))

        for when, cluster in (("now", new), ("at_night", other)):
            with pytest.raises(Conflict) as refused:
                services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=cluster.pk, when=when))
            assert refused.value.code == "control.hub_move_scheduled"
        hub.refresh_from_db()
        assert (hub.moving_to_id, hub.move_scheduled_to_id) == (None, new.pk)

    def test_the_moves_asked_for_the_night_take_room_on_their_cluster(self, admin_ctx, small):
        from control.schemas import HubMoveIn

        full = a_cluster(name="full", host="writer-full.example", max_hubs=2)
        a_ready_hub(slug="living", cluster=full)
        a_ready_hub(slug="tonight", move_scheduled_to=full, move_scheduled_for=self.NOW + dt.timedelta(hours=14))
        hub = a_ready_hub()

        for when in ("now", "at_night"):
            with pytest.raises(Conflict) as refused:
                services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=full.pk, when=when))
            assert refused.value.code == "control.cluster_full"

    def test_a_cluster_a_move_is_asked_to_for_the_night_is_never_deleted(self, admin_ctx):
        target = a_cluster()
        a_ready_hub(move_scheduled_to=target, move_scheduled_for=self.NOW + dt.timedelta(hours=14))

        with pytest.raises(Conflict) as refused:
            services.cluster_delete(admin_ctx, ClusterIdIn(id=target.pk))

        assert refused.value.code == "control.cluster_holds_hubs"
        assert Cluster.objects.filter(pk=target.pk).exists()

    def test_cancel_takes_it_away_and_nothing_was_ever_closed(self, admin_ctx, small):
        from control.schemas import HubIdIn, HubMoveIn

        new = a_cluster()
        hub = a_ready_hub()
        services.hub_move(admin_ctx, HubMoveIn(hub=hub.pk, cluster=new.pk, when="at_night"))

        out = services.hub_move_cancel(admin_ctx, HubIdIn(id=hub.pk))

        hub.refresh_from_db()
        assert (hub.moving_to_id, hub.move_scheduled_to_id, hub.move_scheduled_for) == (None, None, None)
        assert (hub.move_undo_asked_at, hub.last_error) == (None, "")
        assert (out.moving_to, out.scheduled_to, out.scheduled_for) == (None, None, None)
        assert events("control.hub.scheduled_move_cancelled") == [{"id": str(hub.pk), "slug": "acme", "to": str(new.pk)}]
        assert events("control.hub.move_cancel_requested") == []
        with pytest.raises(Conflict) as refused:
            services.hub_move_cancel(admin_ctx, HubIdIn(id=hub.pk))
        assert refused.value.code == "control.hub_not_moving"
