"""The signed status poll (``GET /internal/hubs/{id}``) tells erplora.com when the move of the business asked for its
night starts, an instant in UTC, so that its owner can be told beforehand. It is ``null`` without one, once the worker
started it and once it was cancelled; it never says where the business goes, and reading it never changes the photo's
``state_version``."""

import datetime as dt

import pytest
from django.utils import timezone
from live.context import system_context

from base.models import Hub
from base.registry import REGISTRY_SCOPE
from base.services import provisioning
from base.tenancy import move
from base.tenancy.context import use_control
from base.tenancy.tests.business import HUB_DB
from base.tests.test_internal import HUB_ID, signed
from control import services as control_services
from control.models import Cluster
from control.schemas import HubIdIn, HubMoveIn

#: The business the SaaS registered, ``hub_a``, on its own database as every business is.
pytestmark = [HUB_DB, pytest.mark.usefixtures("hub_a")]

PATH = f"/internal/hubs/{HUB_ID}"
#: 13:00 in Madrid: a move asked then starts at 03:00 of the next night there, 02:00 in UTC.
NOON = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.UTC)
TONIGHT = dt.datetime(2026, 11, 17, 2, 0, tzinfo=dt.UTC)
#: What the poll answered before it said the move: a new key next to them, none of them changed.
POLL_KEYS = {"id", "slug", "status", "is_demo", "expires_at", "ready_at", "state_version", "maintenance"}


@pytest.fixture
def target(monkeypatch):
    """Another cluster, with the business's database measured on its own server as a move checks it."""
    from control import queries

    monkeypatch.setattr(queries, "measure", lambda cluster, names: dict.fromkeys(names, 5 * 1024 * 1024))
    return Cluster.objects.create(name="cluster-2", host="writer-2.example")


def ask_for_tonight(target: Cluster) -> None:
    """«Move to cluster…» › «In its next night», asked at noon of a business in Madrid."""
    Hub.objects.filter(pk=HUB_ID).update(timezone="Europe/Madrid", state_version=7)
    with pytest.MonkeyPatch.context() as clock:
        clock.setattr(timezone, "now", lambda: NOON)
        control_services.hub_move(
            system_context(REGISTRY_SCOPE), HubMoveIn(hub=HUB_ID, cluster=target.pk, when="at_night")
        )


def poll(client) -> dict:
    answer = signed(client, "get", PATH, b"", with_v2=True)
    assert answer.status_code == 200
    return answer.json()


def test_without_a_move_it_says_none(client, db):
    assert poll(client)["move_scheduled_for"] is None


def test_a_move_asked_for_the_night_says_when_it_starts_in_utc_and_nothing_else(client, db, target):
    ask_for_tonight(target)

    first, repeated = poll(client), poll(client)

    assert first == repeated
    assert first["move_scheduled_for"] == "2026-11-17T02:00:00Z"
    assert set(first) == POLL_KEYS | {"move_scheduled_for"}
    assert str(target.pk) not in str(first) and target.name not in str(first)
    assert first["maintenance"] is None
    assert Hub.objects.get(pk=HUB_ID).state_version == 7


def test_it_says_the_move_next_to_the_platform_freeze(client, db, target):
    from control.schemas import FreezeIn
    from control.services import freeze_set

    ask_for_tonight(target)
    freeze_set(system_context(REGISTRY_SCOPE), FreezeIn(frozen=True, reason="Aurora upgrade"))

    answer = poll(client)

    assert answer["maintenance"]["frozen"] is True
    assert answer["move_scheduled_for"] == "2026-11-17T02:00:00Z"


def test_once_the_worker_starts_the_move_it_says_none(client, db, target):
    ask_for_tonight(target)
    with use_control():
        assert provisioning.claim_hub(HUB_ID, TONIGHT, move.LEASE, owner="a:1") is not None
        assert control_services.start_scheduled_move(HUB_ID, TONIGHT, owner="a:1") is True

    assert poll(client)["move_scheduled_for"] is None


def test_once_the_move_is_cancelled_it_says_none(client, db, target):
    ask_for_tonight(target)
    assert poll(client)["move_scheduled_for"] == "2026-11-17T02:00:00Z"

    control_services.hub_move_cancel(system_context(REGISTRY_SCOPE), HubIdIn(id=HUB_ID))

    assert poll(client)["move_scheduled_for"] is None
