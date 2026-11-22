"""Where a new hub is made: the open cluster with the fewest hubs under its limit, those on their way to it counted;
never a full or closed one, nor the settings' own server while there are clusters."""

import datetime as dt

from django.db import connections as django_connections
from django.utils import timezone

from base import services
from base.models.locations import Location
from base.tenancy import provision
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tenancy.tests.test_provision import databases, fresh, nothing_checked_yet
from control.models import Hub

#: The provisioning tests' own autouse fixture.
__all__ = ["nothing_checked_yet"]


def test_a_new_hub_goes_to_the_open_cluster_with_the_fewest_hubs_under_its_limit(registry, hub_databases, told):
    busy = registry.cluster("busy")
    roomy = registry.cluster("roomy", max_hubs=1)
    registry.cluster("closed", is_open=False)
    for _ in range(2):
        registry.hub(status=Hub.Status.READY, db_name="", cluster=busy)
    hub = registry.hub()

    assert provision.provision(hub) is True

    hub = fresh(hub)
    assert (hub.status, hub.cluster) == ("ready", roomy)
    # The template its database was cloned from is that cluster's own (here, the same local server).
    assert hubs.table_names(hub.db_name) == hubs.table_names(hub_databases.template)
    with use_hub(hub) as active:
        assert django_connections.settings[active.alias]["HOST"] == roomy.host
        assert Location.objects.count() >= 0


def test_a_full_or_closed_cluster_never_takes_a_new_hub_nor_does_the_settings_server(registry, told):
    full = registry.cluster("full", max_hubs=1)
    registry.cluster("closed", is_open=False)
    registry.hub(status=Hub.Status.READY, db_name="", cluster=full)
    hub = registry.hub()

    assert provision.provision(hub) is False

    hub = fresh(hub)
    assert (hub.status, hub.cluster, hub.attempts) == ("failed", None, 1)
    assert hub.last_error.startswith("no_cluster_available: ")
    assert hub.db_name not in databases()


def test_a_hub_on_its_way_to_a_cluster_takes_its_place_there(registry, told):
    # A hub moving to a cluster (control.hub.move) counts against its limit, as it will be on it in a moment.
    full = registry.cluster("full", max_hubs=1)
    registry.hub(status=Hub.Status.READY, db_name="", moving_to=full)
    hub = registry.hub()

    assert provision.provision(hub) is False

    hub = fresh(hub)
    assert (hub.status, hub.cluster) == ("failed", None)
    assert hub.last_error.startswith("no_cluster_available: ")


def test_a_hub_going_to_a_cluster_in_its_night_takes_its_place_there(registry, told):
    # A move asked for the business's night holds its place until the worker starts it: a new hub placed there
    # meanwhile would have it refused at night for a full cluster.
    full = registry.cluster("full", max_hubs=1)
    tonight = timezone.now() + dt.timedelta(hours=12)
    registry.hub(status=Hub.Status.READY, db_name="", move_scheduled_to=full, move_scheduled_for=tonight)
    hub = registry.hub()

    assert provision.provision(hub) is False

    hub = fresh(hub)
    assert (hub.status, hub.cluster) == ("failed", None)
    assert hub.last_error.startswith("no_cluster_available: ")


def test_a_purged_hub_frees_its_place_on_a_cluster(registry, told):
    small = registry.cluster("small", max_hubs=1)
    registry.hub(status=Hub.Status.PURGED, db_name="", cluster=small)
    hub = registry.hub()

    services.provisioning.place_hub(hub.pk)

    assert fresh(hub).cluster == small
