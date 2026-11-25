"""Control's operations while a business is at work: the platform staff with business A chosen in the Hub admin
(``/admin/hub/<slug>/``), or code that calls them inside a business's context. They run on control: their rows and
their events stay there, under the registry's scope, and neither business's own outbox gets anything."""

from live.models import OutboxEvent

from base.tenancy.context import use_hub
from base.tenancy.tests.business import HUB_DB
from base.tenancy.tests.concurrency import PLATFORM_HOST
from control import services
from control.models import Cluster, Freeze, Hub
from control.schemas import ClusterIdIn, FreezeIn
from control.tests.conftest import events

pytestmark = HUB_DB


def control_events_in(hub: Hub) -> list[str]:
    with use_hub(hub):
        return list(OutboxEvent.objects.filter(name__startswith="control.").values_list("name", flat=True))


def a_cluster(name: str = "cluster-1") -> Cluster:
    return Cluster.objects.create(name=name, host=f"writer-{name}.example")


def test_the_freeze_set_with_a_business_chosen_freezes_the_platform_in_control(hub_a, hub_b, hub_staff):
    switch, _ = Freeze.objects.get_or_create()

    response = hub_staff.post(
        f"/admin/control/freeze/{switch.pk}/change/",
        {"frozen": "on", "reason": "Aurora upgrade", "_save": "Save"},
        HTTP_HOST=PLATFORM_HOST,
    )

    assert response.status_code == 302
    assert Freeze.objects.get().frozen is True
    assert events("control.freeze.started") == [{"reason": "Aurora upgrade"}]
    assert control_events_in(hub_a) == control_events_in(hub_b) == []


def test_a_cluster_closed_with_a_business_chosen_is_closed_in_control(hub_a, hub_b, hub_staff):
    cluster, untouched = a_cluster(), a_cluster("cluster-2")

    response = hub_staff.post(
        "/admin/control/cluster/",
        {"action": "close_to_new_hubs", "_selected_action": [str(cluster.pk)]},
        HTTP_HOST=PLATFORM_HOST,
        follow=True,
    )

    assert "1 cluster closed to new hubs" in response.content.decode()
    cluster.refresh_from_db()
    untouched.refresh_from_db()
    assert (cluster.is_open, untouched.is_open) == (False, True)
    assert events("control.cluster.closed") == [{"id": str(cluster.pk), "name": "cluster-1"}]
    assert control_events_in(hub_a) == control_events_in(hub_b) == []


def test_the_move_of_b_cancelled_with_a_chosen_marks_b_alone_in_control(hub_a, hub_b, hub_staff):
    target = a_cluster("cluster-2")
    Hub.objects.filter(pk__in=[hub_a.pk, hub_b.pk]).update(moving_to=target)

    html = hub_staff.post(
        "/admin/control/hub/",
        {"action": "cancel_the_move", "_selected_action": [str(hub_b.pk)]},
        HTTP_HOST=PLATFORM_HOST,
        follow=True,
    ).content.decode()

    assert "1 move will be undone" in html
    hub_a.refresh_from_db()
    hub_b.refresh_from_db()
    assert (hub_a.move_undo_asked_at, hub_b.move_undo_asked_at is not None) == (None, True)
    assert events("control.hub.move_cancel_requested") == [{"id": str(hub_b.pk), "slug": hub_b.slug}]
    assert control_events_in(hub_a) == control_events_in(hub_b) == []


def test_an_operation_of_control_called_inside_a_business_runs_on_control(hub_a, hub_b, admin_ctx):
    cluster = a_cluster()

    with use_hub(hub_a):
        services.freeze.freeze_set(admin_ctx, FreezeIn(frozen=True, reason="Aurora upgrade"))
        services.clusters.cluster_close(admin_ctx, ClusterIdIn(id=cluster.pk))

    cluster.refresh_from_db()
    assert (Freeze.objects.get().frozen, cluster.is_open) == (True, False)
    assert events("control.freeze.started") == [{"reason": "Aurora upgrade"}]
    assert events("control.cluster.closed") == [{"id": str(cluster.pk), "name": "cluster-1"}]
    assert control_events_in(hub_a) == control_events_in(hub_b) == []
