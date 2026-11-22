"""``manage.py demo_expire <slug>``: end a demo now and purge it at once.

Support's tool and the e2e's clock: through its operations (``base.demo.expire``, then its drop), in every environment
(not only ``DEBUG``), and it says how the demo was left. When the worker's pass took the demo first (its lease), the
command waits for that drop, as long as a lease lasts at most, instead of saying the step it caught it in. While the
platform is frozen for a database upgrade (``control.freeze.set``; hub#930) it ends the demo all the same and leaves
its database where it is: a ``DROP DATABASE`` meanwhile would never reach the upgrade's copy; the reaper drops it once
the freeze is lifted.
"""

import hashlib
import time
from io import StringIO
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone
from live.context import system_context

from base.models import DemoCode, Hub, Membership
from base.registry import REGISTRY_SCOPE
from base.schemas.demos import DemoCodeIn, DemoCreateIn, DemoSlugIn
from base.services import provisioning
from base.services.demos import (
    demo_code_create,
    demo_create,
    demo_expire,
    demo_purge,
    purge_demo_data,
    reap_demos,
    redeem_demo_code,
)
from base.tenancy import provision
from base.tenancy.context import use_control
from base.tenancy.tests.business import HUB_DB
from base.tests.test_services_demo import open_session
from control.models import HubDue
from control.schemas import FreezeIn
from control.services import freeze_set

pytestmark = HUB_DB

OWNER = hashlib.sha256(b"ana's browser").hexdigest()
#: The worker's name on the leases it holds: another process than the command's.
WORKER = "worker-host:1:0badf00d"


def entered_demo(inside: Hub) -> str:
    """A demo its browser entered: made ready by the worker (``base.tenancy.provision``), a code spent and the
    owner's session open in ``inside``'s database, which stands in for the demo's own; its slug."""
    ctx = system_context(REGISTRY_SCOPE)
    slug = demo_create(ctx, DemoCreateIn(session_key=OWNER)).slug
    Hub.objects.filter(slug=slug).update(status="ready")
    redeemed = redeem_demo_code(slug, demo_code_create(ctx, DemoCodeIn(slug=slug, session_key=OWNER)).code)
    request = RequestFactory().post("/auth/callback")
    SessionMiddleware(lambda request: None).process_request(request)
    open_session(request, redeemed.hub, inside=inside)
    return slug


def expire(slug: str) -> str:
    out = StringIO()
    call_command("demo_expire", slug, stdout=out)
    return out.getvalue()


def the_worker_took_it(slug: str, *, dropping: bool) -> UUID:
    """The demo ``slug`` ended and the worker's pass took its lease before the command's own try: as the worker is
    between its claim and its drop (``expired``), or in the middle of the drop (``dropping``)."""
    demo_expire(system_context(REGISTRY_SCOPE), DemoSlugIn(slug=slug))
    hub_id = Hub.objects.get(slug=slug).pk
    now = timezone.now()
    with use_control():
        assert provisioning.claim_hub(hub_id, now, provision.LEASE, owner=WORKER) is not None
        if dropping:
            assert provisioning.demo_dropping(hub_id, now, provision.LEASE, owner=WORKER) is not None
    return hub_id


def the_worker_ends_its_drop(hub_id: UUID) -> None:
    """The worker's drop of ``hub_id`` goes on to its end: its database and its files, its rows purged, its lease
    given back."""
    with use_control():
        hub = provisioning.demo_dropping(hub_id, timezone.now(), provision.LEASE, owner=WORKER)
        purge_demo_data(hub)
        demo_purge(system_context(REGISTRY_SCOPE), DemoSlugIn(slug=hub.slug))
        provisioning.release_hub(hub_id, timezone.now(), owner=WORKER)


@pytest.mark.parametrize("dropping", [False, True], ids=["its-lease-taken", "dropping-it"])
def test_while_the_worker_drops_the_demo_the_command_waits_for_it_and_says_purged(monkeypatch, hub_b, dropping):
    slug = entered_demo(hub_b)
    hub_id = the_worker_took_it(slug, dropping=dropping)
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        if not waits:
            the_worker_ends_its_drop(hub_id)
        waits.append(seconds)

    monkeypatch.setattr(time, "sleep", sleep)

    assert expire(slug).strip() == f"{slug}: purged"
    assert len(waits) == 1
    assert Hub.objects.get(slug=slug).status == "purged"
    assert not HubDue.objects.filter(pk=hub_id).exists()


def test_a_worker_that_never_lets_go_is_waited_for_as_long_as_a_lease_lasts_and_no_more(monkeypatch, hub_b):
    slug = entered_demo(hub_b)
    the_worker_took_it(slug, dropping=True)
    waits: list[float] = []
    monkeypatch.setattr(time, "sleep", waits.append)

    assert expire(slug).strip() == f"{slug}: dropping"
    assert sum(waits) == pytest.approx(provision.LEASE.total_seconds())


def test_a_worker_that_died_mid_drop_is_waited_for_until_its_lease_runs_out_and_the_command_drops_it(monkeypatch, hub_b):
    slug = entered_demo(hub_b)
    hub_id = the_worker_took_it(slug, dropping=True)
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        if sum(waits) >= provision.LEASE.total_seconds():
            HubDue.objects.filter(pk=hub_id).update(lease_until=timezone.now())

    monkeypatch.setattr(time, "sleep", sleep)

    assert expire(slug).strip() == f"{slug}: purged"
    assert sum(waits) == pytest.approx(provision.LEASE.total_seconds())


def test_with_nobody_else_on_the_demo_it_is_purged_without_waiting(monkeypatch, hub_b):
    slug = entered_demo(hub_b)
    waits: list[float] = []
    monkeypatch.setattr(time, "sleep", waits.append)

    assert expire(slug).strip() == f"{slug}: purged"
    assert waits == []


@pytest.mark.parametrize("debug", [True, False])
def test_ends_the_demo_and_purges_it_at_once(settings, debug, hub_b):
    settings.DEBUG = debug
    slug = entered_demo(hub_b)
    output = expire(slug)
    hub = Hub.objects.get(slug=slug)
    assert (hub.status, hub.purged_at is not None) == ("purged", True)
    assert not Membership.objects.filter(host=slug).exists()
    assert not get_user_model().objects.filter(username=f"demo:{slug}").exists()
    assert not DemoCode.objects.filter(hub=hub).exists()
    assert output.strip() == f"{slug}: purged"


def test_a_demo_already_purged_says_so_again(hub_b):
    slug = entered_demo(hub_b)
    expire(slug)
    assert expire(slug).strip() == f"{slug}: purged"


@pytest.mark.parametrize("slug", ["demo-00000000", "a"])
def test_a_slug_that_names_no_demo_is_an_error_and_changes_nothing(slug):
    with pytest.raises(CommandError, match="no demo"):
        expire(slug)
    assert Hub.objects.get(slug="a").status == "ready"


def test_frozen_it_ends_the_demo_and_leaves_its_database_for_after_the_freeze(hub_b):
    platform = system_context(REGISTRY_SCOPE)
    slug = entered_demo(hub_b)
    freeze_set(platform, FreezeIn(frozen=True, reason="Aurora upgrade"))

    output = expire(slug)

    assert Hub.objects.get(slug=slug).status == "expired"
    assert output.strip() == f"{slug}: expired (frozen: its database is dropped once the freeze is lifted)"

    freeze_set(platform, FreezeIn(frozen=False))
    reap_demos()

    assert Hub.objects.get(slug=slug).status == "purged"


def test_a_drop_that_fails_is_logged_and_the_command_still_says_how_the_demo_was_left(monkeypatch, caplog, hub_b):
    slug = entered_demo(hub_b)

    def refused(hub: Hub) -> None:
        raise RuntimeError("the server refused to drop the database")

    monkeypatch.setattr(provision.demos, "purge_demo_data", refused)

    assert expire(slug).strip() == f"{slug}: dropping"
    assert "base.demo.purge_failed" in caplog.text
    assert Hub.objects.get(slug=slug).last_error.startswith("drop_failed: RuntimeError")
