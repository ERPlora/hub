"""The worker's data pass (round 2026-10-30 of PLAN-DB, decision 2 and proposals (a), (f)): a reset and a business that
leaves, each copied first.

Every tick the worker takes one hub with data work due (``base.services.claim_next_data_hub``, under its lease):

- a reset asked (``base.hub.reset``): its database copied (``base.tenancy.dumps``, ``reset``) and, only if the copy was
  kept, the sections emptied in its database with ``base.hub.data_reset`` recorded there; a copy that fails empties
  nothing and says so (``failed``, «Try again» on the screen); an emptying that fails keeps the copy and empties
  nothing either;
- a business that left (``DELETE /internal/hubs/{id}``) with its own database: copied once (``offboarding``); a copy
  that fails is tried again later (1 min, 5 min, 15 min, then every hour); its database stays (``restore`` still
  brings it back).

Real databases (``hub_a``; ``transaction=True``: the pass releases its connections) and a real S3 (moto's).
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from base import blueprint, services, worker
from base.models import Membership
from base.permissions import permissions_for
from base.registry import REGISTRY_SCOPE
from base.tenancy import dumps, provision
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from base.tenancy.tests.s3 import aws_test_credentials, dumps_bucket, moto_s3, no_dumps_bucket, objects  # noqa: F401
from control.models import Hub, HubDue, HubDump

pytestmark = [
    pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]


@pytest.fixture
def no_test_fallback(monkeypatch):
    from base.tenancy import context

    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.fixture
def told(monkeypatch) -> list[tuple[str, list[str]]]:
    """Every live notice the pass sends: ``(channel, events)``."""
    sent: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(services, "notify", lambda scope, names: sent.append((scope.channel, list(names))))
    return sent


def call(ctx, name, /, **data):
    op = get(name)
    return op(ctx, op.input(**data))


def owner_of(hub: Hub) -> OperationContext:
    user = get_user_model().objects.create_user(username=f"olga-{hub.slug}", password="pw", first_name="Olga")
    Membership.objects.create(user=user, host=hub.slug, role=Membership.Role.OWNER)
    return OperationContext(scope=Scope("host", hub.slug), actor=user, permissions=permissions_for(user, Scope("host", hub.slug)), language="es")


def ready(hub: Hub) -> Hub:
    """``hub`` as the provisioning leaves it: ready, its database finished."""
    Hub.objects.filter(pk=hub.pk).update(ready_at=timezone.now())
    return Hub.objects.get(pk=hub.pk)


def loaded_and_asked(hub: Hub, apps: list[str]) -> OperationContext:
    owner = owner_of(hub)
    with use_hub(hub):
        call(owner, "base.blueprint.import", template="restaurant.es")
        assert call(owner, "base.hub.reset", apps=apps, confirm=hub.slug).status == "copying"
    return owner


def rows(hub: Hub, owner: OperationContext, operation: str) -> int:
    with use_hub(Hub.objects.get(pk=hub.pk)):
        return call(owner, operation, limit=1).total


def data_reset_events(hub: Hub) -> list[dict]:
    with use_hub(Hub.objects.get(pk=hub.pk)):
        return list(OutboxEvent.objects.filter(name="base.hub.data_reset").values_list("payload", flat=True))


def run_pass(now: dt.datetime | None = None) -> None:
    worker._data(now or timezone.now())


def test_a_reset_is_copied_first_then_emptied_and_the_screen_hears_each_step(hub_a, dumps_bucket, moto_s3, told):
    owner = loaded_and_asked(ready(hub_a), ["table"])

    run_pass()

    hub = Hub.objects.get(pk=hub_a.pk)
    dump = HubDump.objects.get(hub=hub)
    assert (dump.kind, dump.requested_by) == ("reset", "Olga")
    assert set(objects(moto_s3, dumps_bucket)) == {dump.key}
    assert rows(hub, owner, "table.table.list") == 0
    assert data_reset_events(hub) == [{"apps": ["table"]}]
    assert hub.reset_requested_at is None
    assert hub.reset_sections["state"] == "done"
    assert hub.reset_sections["dump"] == str(dump.id)
    assert hub.reset_sections["error"] == ""
    assert hub.reset_sections["finished_at"] is not None
    assert [(app["id"], app["label"], app["removed"]) for app in hub.reset_sections["removed"]] == [("table", "Mesas", 12)]
    channel = Scope("host", hub.slug).channel
    assert told == [
        (channel, ["base.hub.reset_progressed"]),  # asked (the request's)
        (channel, ["base.hub.reset_progressed"]),  # copied: emptying
        (channel, ["base.hub.reset_progressed"]),  # done
    ]
    assert not HubDue.objects.filter(hub=hub).exists()


class SlowUpload:
    """The bucket's client with a slow upload: the copy goes up in three parts of 0.7 s, then 1.5 s more before the
    upload returns, longer in all than the lease (1 s here); each part tells boto3's ``Callback``, if it is given.
    After the second part another worker tries to take the hub (``rival``): it must find the lease alive."""

    def __init__(self, real, rival):
        self.real = real
        self.rival = rival

    def upload_file(self, path, bucket, key, ExtraArgs=None, Callback=None, Config=None):  # noqa: N803 (boto3's)
        import os
        import time

        size = os.path.getsize(path)
        for part in range(3):
            time.sleep(0.7)
            if Callback is not None:
                Callback(size // 3)
            if part == 1:
                self.rival()
        time.sleep(1.5)
        return self.real.upload_file(path, bucket, key, ExtraArgs=ExtraArgs)


def test_a_slow_upload_keeps_its_lease_and_the_reset_is_done_with_one_copy(hub_a, dumps_bucket, moto_s3, monkeypatch):
    """Review of round 3: the upload renews the lease as it goes (boto3's Callback) and right after it, so the reset
    is never left «copying» with another copy in the bucket at every pass."""
    owner = loaded_and_asked(ready(hub_a), ["table"])
    real = dumps.client
    taken: list[object] = []

    def rival() -> None:
        with use_control():
            taken.append(services.claim_hub(hub_a.pk, timezone.now(), provision.LEASE, owner="another:1:x"))

    monkeypatch.setattr(dumps, "client", lambda: SlowUpload(real(), rival))
    monkeypatch.setattr(provision, "LEASE", dt.timedelta(seconds=1))
    monkeypatch.setattr(dumps, "POLL_SECONDS", 0.3)

    run_pass()

    hub = Hub.objects.get(pk=hub_a.pk)
    assert taken == [None]  # the lease was alive mid-upload: no other worker could take the hub
    assert hub.reset_sections["state"] == "done"
    assert len(objects(moto_s3, dumps_bucket)) == 1
    assert HubDump.objects.filter(hub=hub).count() == 1
    assert rows(hub, owner, "table.table.list") == 0


def test_a_copy_that_fails_empties_nothing_and_says_so(hub_a, dumps_bucket, moto_s3, settings, told):
    owner = loaded_and_asked(ready(hub_a), ["table"])
    settings.DB_MIGRATOR_PASSWORD = "wrong-secret-6f1c"

    run_pass()

    hub = Hub.objects.get(pk=hub_a.pk)
    assert rows(hub, owner, "table.table.list") == 10
    assert data_reset_events(hub) == []
    assert not HubDump.objects.exists()
    assert objects(moto_s3, dumps_bucket) == {}
    assert hub.reset_requested_at is None
    assert (hub.reset_sections["state"], hub.reset_sections["error"]) == ("failed", "dump_failed")
    assert "wrong-secret-6f1c" not in str(hub.reset_sections)
    assert told[-1] == (Scope("host", hub.slug).channel, ["base.hub.reset_progressed"])


def test_without_a_bucket_in_the_worker_nothing_is_emptied(hub_a, dumps_bucket, monkeypatch):
    owner = loaded_and_asked(ready(hub_a), ["table"])
    monkeypatch.setenv("HUB_DUMPS_BUCKET", "")

    run_pass()

    hub = Hub.objects.get(pk=hub_a.pk)
    assert rows(hub, owner, "table.table.list") == 10
    assert (hub.reset_sections["state"], hub.reset_sections["error"]) == ("failed", "dumps_unavailable")


def test_an_emptying_that_fails_keeps_the_copy_and_empties_nothing(hub_a, dumps_bucket, monkeypatch):
    owner = loaded_and_asked(ready(hub_a), ["table"])
    real = blueprint.reset

    def breaks_after_the_first_rows(ctx, chosen):
        assert real(ctx, chosen)["apps"][0]["removed"] == 12
        raise RuntimeError("the database went away")

    monkeypatch.setattr(blueprint, "reset", breaks_after_the_first_rows)

    run_pass()

    hub = Hub.objects.get(pk=hub_a.pk)
    assert rows(hub, owner, "table.table.list") == 10  # rolled back with the rest
    assert data_reset_events(hub) == []
    assert HubDump.objects.filter(hub=hub, kind="reset").count() == 1
    assert (hub.reset_sections["state"], hub.reset_sections["error"]) == ("failed", "emptying_failed")
    assert hub.reset_requested_at is None


def test_a_reset_asked_again_after_a_failure_is_done(hub_a, dumps_bucket, settings):
    owner = loaded_and_asked(ready(hub_a), ["table"])
    settings.DB_MIGRATOR_PASSWORD = "wrong-secret-6f1c"
    run_pass()
    settings.DB_MIGRATOR_PASSWORD = settings.DATABASES["default"]["PASSWORD"]

    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        call(owner, "base.hub.reset", apps=["table"], confirm=hub_a.slug)
    run_pass()

    assert Hub.objects.get(pk=hub_a.pk).reset_sections["state"] == "done"
    assert rows(hub_a, owner, "table.table.list") == 0


def test_a_reset_of_a_business_that_left_meanwhile_empties_nothing(hub_a, dumps_bucket):
    owner = loaded_and_asked(ready(hub_a), ["table"])
    Hub.objects.filter(pk=hub_a.pk).update(status=Hub.Status.CANCELLED, cancelled_at=timezone.now())

    run_pass()  # the copy of its leaving: below; the reset is not done

    hub = Hub.objects.get(pk=hub_a.pk)
    assert (hub.reset_sections["state"], hub.reset_sections["error"]) == ("failed", "hub_not_ready")
    assert rows(hub, owner, "table.table.list") == 10


def test_the_pass_leaves_a_reset_whose_lease_another_worker_holds(hub_a, dumps_bucket):
    loaded_and_asked(ready(hub_a), ["table"])
    with use_control():
        assert services.claim_hub(hub_a.pk, timezone.now(), provision.LEASE, owner="another:1:x") is not None

    run_pass()

    assert Hub.objects.get(pk=hub_a.pk).reset_sections["state"] == "copying"
    assert not HubDump.objects.exists()


def test_a_reset_still_to_do_stays_due_when_the_provisioning_pass_gives_its_lease_back(hub_a, dumps_bucket):
    loaded_and_asked(ready(hub_a), ["table"])
    now = timezone.now()
    with use_control():
        # S3: the provisioning's pass never takes a ready hub's ring (its data work's or its apps' to set up).
        assert services.claim_next_due_hub(now, provision.LEASE) is None
        assert services.claim_next_data_hub(now, provision.LEASE) == hub_a.pk
        services.release_hub(hub_a.pk, now)

    assert HubDue.objects.filter(hub_id=hub_a.pk, due_at=now, lease_until=None).exists()


def test_the_worker_empties_only_through_its_own_operation(hub_a):
    with use_hub(ready(hub_a)), pytest.raises(PermissionDenied) as refused:
        call(owner_of(hub_a), "base.hub.reset_apply", apps=["table"])

    assert refused.value.code == "base.internal_only"


def test_a_business_s_owner_with_every_permission_never_empties_through_it(hub_databases, monkeypatch):
    """The platform's alone, refused before anything else (review of hub#490, OPEN_OPERATIONS «platform»). The local
    ``a`` has no database of its own: since S5 only the suite's fallback enters such a business."""
    from base.tenancy import context
    from base.tenancy.tests.legacy import LEGACY

    monkeypatch.setattr(context, "_test_fallback", LEGACY)
    owner = get_user_model().objects.create_user(username="saas:owner-of-a")
    Membership.objects.create(user=owner, host="a", role=Membership.Role.OWNER)
    ctx = OperationContext(scope=Scope("host", "a"), actor=owner, permissions=frozenset({"*"}))

    with use_hub(Hub.objects.get(slug="a")), pytest.raises(PermissionDenied) as refused:
        call(ctx, "base.hub.reset_apply", apps=["table"])

    assert refused.value.code == "base.internal_only"


def test_the_emptying_is_never_run_on_a_shared_database(dumps_bucket, monkeypatch):
    # Since S5 production never enters a business without its own database: only the suite's fallback does.
    from base.tenancy import context
    from base.tenancy.tests.legacy import LEGACY

    monkeypatch.setattr(context, "_test_fallback", LEGACY)
    shared = Hub.objects.get(slug="a")

    with use_hub(shared), pytest.raises(Conflict) as refused:
        call(system_context(Scope("host", "a")), "base.hub.reset_apply", apps=["table"])

    assert refused.value.code == "base.reset_shared_database"


# ── A business that leaves (proposal (a)) ────────────────────────────────────────────────────────────────────────


def cancel(hub: Hub) -> None:
    call(system_context(REGISTRY_SCOPE), "base.hub.cancel", id=hub.pk)


def test_a_business_that_leaves_is_copied_once_and_keeps_its_database(hub_a, dumps_bucket, moto_s3):
    hub = ready(hub_a)
    cancel(hub)
    assert HubDue.objects.filter(hub=hub).exists()

    run_pass()
    run_pass()

    [dump] = HubDump.objects.filter(hub=hub)
    assert (dump.kind, dump.requested_by) == ("offboarding", "")
    assert dump.created_at >= Hub.objects.get(pk=hub.pk).cancelled_at
    assert set(objects(moto_s3, dumps_bucket)) == {dump.key}
    assert not HubDue.objects.filter(hub=hub).exists()
    call(system_context(REGISTRY_SCOPE), "base.hub.restore", id=hub.pk)
    assert Hub.objects.get(pk=hub.pk).status == Hub.Status.READY


def test_a_business_that_leaves_again_is_copied_again(hub_a, dumps_bucket):
    hub = ready(hub_a)
    cancel(hub)
    run_pass()
    call(system_context(REGISTRY_SCOPE), "base.hub.restore", id=hub.pk)

    cancel(Hub.objects.get(pk=hub.pk))
    run_pass()

    assert HubDump.objects.filter(hub=hub, kind="offboarding").count() == 2


def test_a_copy_of_a_business_that_left_that_fails_is_tried_again_later(hub_a, dumps_bucket, settings):
    hub = ready(hub_a)
    cancel(hub)
    settings.DB_MIGRATOR_PASSWORD = "wrong-secret-6f1c"
    now = timezone.now()

    run_pass(now)

    failed = Hub.objects.get(pk=hub.pk)
    assert failed.status == Hub.Status.CANCELLED
    assert failed.attempts == 1
    assert failed.last_error.startswith("dump_failed: ")
    assert "wrong-secret-6f1c" not in failed.last_error
    assert failed.next_attempt_at >= now + dt.timedelta(minutes=1)
    assert HubDue.objects.get(hub=hub).due_at == failed.next_attempt_at
    run_pass(now + dt.timedelta(seconds=30))  # not due yet
    assert Hub.objects.get(pk=hub.pk).attempts == 1

    settings.DB_MIGRATOR_PASSWORD = settings.DATABASES["default"]["PASSWORD"]
    run_pass(failed.next_attempt_at)

    done = Hub.objects.get(pk=hub.pk)
    assert HubDump.objects.filter(hub=hub, kind="offboarding").count() == 1
    assert (done.attempts, done.last_error, done.next_attempt_at) == (0, "", None)
    assert not HubDue.objects.filter(hub=hub).exists()


def test_a_business_brought_back_forgets_its_failed_copy_and_leaving_again_is_copied_at_once(hub_a, dumps_bucket, settings):
    """Review of round 3: a restore clears the copy that failed (attempts, last error, next attempt), so a second
    leaving starts from the first wait, not from the long one."""
    hub = ready(hub_a)
    cancel(hub)
    settings.DB_MIGRATOR_PASSWORD = "wrong-secret-6f1c"
    run_pass()
    settings.DB_MIGRATOR_PASSWORD = settings.DATABASES["default"]["PASSWORD"]
    Hub.objects.filter(pk=hub.pk).update(attempts=4, next_attempt_at=timezone.now() + dt.timedelta(hours=1))

    call(system_context(REGISTRY_SCOPE), "base.hub.restore", id=hub.pk)

    back = Hub.objects.get(pk=hub.pk)
    assert (back.status, back.attempts, back.last_error, back.next_attempt_at) == (Hub.Status.READY, 0, "", None)
    cancel(back)
    run_pass()
    assert HubDump.objects.filter(hub=hub, kind="offboarding").count() == 1


def test_a_business_cancelled_before_its_database_was_finished_is_never_copied(hub_a, dumps_bucket):
    cancel(hub_a)  # ready_at is None: its database was never finished

    run_pass()

    assert not HubDump.objects.exists()


def test_a_business_without_its_own_database_that_leaves_is_never_copied(dumps_bucket):
    shared = Hub.objects.get(slug="a")
    Hub.objects.filter(pk=shared.pk).update(ready_at=timezone.now())

    cancel(shared)
    run_pass()

    assert not HubDue.objects.filter(hub=shared).exists()
    assert not HubDump.objects.exists()


def test_a_pass_with_nothing_to_do_does_nothing(dumps_bucket):
    run_pass()

    assert not HubDump.objects.exists()
