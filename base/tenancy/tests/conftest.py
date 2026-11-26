"""The databases of a recovery from a separate copy and of a move to another cluster, and the hubs and clusters a
provisioning test writes in control, for every module of the tenancy tests that runs one."""

import datetime as dt
import uuid

import pytest
from django.db import connections as django_connections
from django.utils import timezone
from live.models import OutboxEvent

from base import services
from base.tenancy import connections as tenancy_connections, names
from base.tenancy.context import use_control
from base.tenancy.tests import hubs
from base.tenancy.tests.test_move import Moves
from base.tenancy.tests.test_recovery import Recoveries
from control.models.hubs import Cluster, Hub


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


@pytest.fixture
def moves(django_db_blocker, hub_databases, dumps_bucket):
    with django_db_blocker.unblock():
        made = Moves(hub_databases.template)
        yield made
        made.clean()


@pytest.fixture
def told(monkeypatch):
    """The SaaS's ``ready`` notices (``services.report_ready``), recorded instead of sent."""
    heard: list[uuid.UUID] = []
    monkeypatch.setattr(services.provisioning, "report_ready", heard.append)
    return heard


@pytest.fixture
def registry(django_db_blocker, hub_databases):
    """Rows of control this test writes (committed: no test case here), deleted after it with their databases."""
    started = timezone.now()
    made: list[Hub] = []
    clusters: list[Cluster] = []

    def hub(*, demo: bool = False, vertical: str = hubs.TEMPLATE_VERTICAL, **fields) -> Hub:
        hub_id = uuid.uuid7()
        control = tenancy_connections.control_name()
        build = names.demo_db_name if demo else names.hub_db_name
        values = {
            "id": hub_id,
            "slug": f"{'demo-' if demo else 'acme-'}{hub_id.hex[-8:]}",
            "status": Hub.Status.REQUESTED,
            "db_name": build(control, hub_id),
            "vertical": vertical,
            "is_demo": demo,
            "expires_at": timezone.now() + dt.timedelta(hours=1) if demo else None,
        }
        made.append(row := Hub.objects.create(**(values | fields)))
        return row

    def cluster(name: str, **fields) -> Cluster:
        default = django_connections.settings["default"]
        values = {"host": default["HOST"], "port": default["PORT"], "pooler_host": ""}
        clusters.append(row := Cluster.objects.create(name=name, **(values | fields)))
        return row

    with django_db_blocker.unblock():
        yield SimpleRegistry(hub=hub, cluster=cluster)
        with hubs._maintenance() as conn:
            for row in made:
                if row.db_name:
                    hubs._drop(conn, row.db_name, hub_databases.control)
        Hub.objects.filter(pk__in=[row.pk for row in made]).delete()
        Cluster.objects.filter(pk__in=[row.pk for row in clusters]).delete()
        with use_control():
            OutboxEvent.objects.filter(created_at__gte=started).delete()


class SimpleRegistry:
    def __init__(self, *, hub, cluster):
        self.hub, self.cluster = hub, cluster
