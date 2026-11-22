"""A copy of any size is asked from a temporary cluster, to put the business back as it was at a moment
(``control.hub.restore``) or to make it aside (``control.hub.restore_aside``): the worker copies it through the dumps
bucket, never through its own disk, so its size stops nothing (``control.services._copy_to_restore`` only checks the
copy is there). What both refuse is in ``test_services_restore.py``'s ``AskedFromATemporaryCluster``."""

import datetime as dt

import pytest

from control import queries, services
from control.models import Hub, RestoredCopy
from control.schemas import HubRestoreIn
from control.tests.conftest import a_cluster, a_ready_hub

pytestmark = pytest.mark.django_db

MOMENT = dt.datetime(2026, 11, 9, 14, 30, tzinfo=dt.UTC)
#: Far beyond what a file of the worker could hold.
FORTY_GIB = 40 * 1024**3


def restoring(hub: Hub) -> bool:
    return Hub.objects.get(pk=hub.pk).restoring_from_id is not None


def copied_aside(hub: Hub) -> bool:
    return RestoredCopy.objects.filter(hub=hub).exists()


@pytest.mark.parametrize(
    ("operation", "asked"),
    [(services.hub_restore, restoring), (services.hub_restore_aside, copied_aside)],
    ids=["in-place", "aside"],
)
def test_a_copy_of_any_size_is_asked(admin_ctx, monkeypatch, operation, asked):
    hub = a_ready_hub()
    temporary = a_cluster(name="restore-1", host="writer-restore.example", is_open=False)
    monkeypatch.setattr(queries, "measure", lambda cluster, names: {names[0]: FORTY_GIB})

    operation(admin_ctx, HubRestoreIn(hub=hub.pk, cluster=temporary.pk, at=MOMENT))

    assert asked(hub)
