"""``manage.py seed_local_hubs``: the local hubs ``a`` and ``b``, ready in the registry (plan 2026-10-17, §1.3).

The host gate answers 404 to a slug without a row, so a developer's database needs them once; local development
only (``DEBUG``), idempotent, through its operation (``base.hub.seed_local``), never a data migration (it would put
them in production).
"""

import logging
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from live.context import OperationContext
from live.errors import PermissionDenied

from base import registry
from base.models import Hub
from base.schemas import HubSeedLocalIn
from base.services import hub_seed_local
from base.tenancy import provision

pytestmark = pytest.mark.django_db


@pytest.fixture
def fresh(settings):
    """A developer's database before its first seed: the suite's own `a` and `b` (conftest) are not there."""
    settings.DEBUG = True
    Hub.objects.filter(slug__in=["a", "b"]).delete()


def seed() -> str:
    out = StringIO()
    call_command("seed_local_hubs", stdout=out)
    return out.getvalue()


@pytest.mark.usefixtures("fresh")
def test_creates_a_and_b_ready():
    output = seed()
    assert sorted(Hub.objects.values_list("slug", "status", "is_demo")) == [("a", "ready", False), ("b", "ready", False)]
    assert all(hub.ready_at is not None for hub in Hub.objects.all())
    assert "a: created" in output and "b: created" in output


@pytest.mark.usefixtures("fresh")
def test_leaves_a_and_b_on_the_shared_database_while_some_app_cannot_live_in_a_hubs_own(caplog):
    """a and b turn every app on, and some apps' tables refer to control's users (staff, attendance, task,
    whatsapp_inbox and what needs them; ``provision.portable_apps``): until they can live in a hub's own database, a
    and b keep their data in control's (``db_name=""``) and the log says which apps hold them there. The day every app
    can, the same command gives them their own (``base/tenancy/tests/test_provision.py``)."""
    blocked = sorted(provision.hub_app_labels() - provision.portable_apps())
    assert blocked, "every app can live in a hub's own database now: this test's premise is gone"

    with caplog.at_level(logging.WARNING, logger="base.management.commands.seed_local_hubs"):
        output = seed()

    assert sorted(Hub.objects.values_list("slug", "db_name")) == [("a", ""), ("b", "")]
    assert "base.seed_local_hubs.shared_database" in caplog.text
    assert all(label in caplog.text for label in blocked)
    assert "share the control database" in output


@pytest.mark.usefixtures("fresh")
def test_is_idempotent():
    seed()
    ids = dict(Hub.objects.values_list("slug", "id"))
    output = seed()
    assert dict(Hub.objects.values_list("slug", "id")) == ids
    assert "a: already ready" in output and "b: already ready" in output


@pytest.mark.usefixtures("fresh")
def test_brings_a_local_hub_back_when_it_was_left_cancelled():
    seed()
    Hub.objects.filter(slug="a").update(status="cancelled")
    assert "a: ready again" in seed()
    assert Hub.objects.get(slug="a").status == "ready"


def test_is_only_for_local_development(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        seed()


def test_only_the_platform_seeds(make_user):
    ctx = OperationContext(scope=registry.REGISTRY_SCOPE, actor=make_user(), permissions=frozenset({"*"}))
    with pytest.raises(PermissionDenied):
        hub_seed_local(ctx, HubSeedLocalIn(slugs=["a"]))


class TestCheck:
    """``--check``: whether ``a`` and ``b`` are ready, writing nothing (the e2e's global setup asks it)."""

    def test_passes_when_both_are_ready(self, settings):
        settings.DEBUG = True
        out = StringIO()
        call_command("seed_local_hubs", "--check", stdout=out)
        assert "a: ready" in out.getvalue() and "b: ready" in out.getvalue()

    @pytest.mark.usefixtures("fresh")
    def test_names_the_missing_ones_and_writes_nothing(self):
        Hub.objects.create(slug="a", status="cancelled")
        with pytest.raises(CommandError, match=r"Not ready in the registry: a \(cancelled\), b \(missing\)"):
            call_command("seed_local_hubs", "--check", stdout=StringIO())
        assert list(Hub.objects.filter(slug__in=["a", "b"]).values_list("slug", "status")) == [("a", "cancelled")]

    def test_is_only_for_local_development_too(self, settings):
        settings.DEBUG = False
        with pytest.raises(CommandError, match="DEBUG"):
            call_command("seed_local_hubs", "--check", stdout=StringIO())
