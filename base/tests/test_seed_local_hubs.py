"""``manage.py seed_local_hubs``: the local hubs ``a`` and ``b``, ready in the registry (plan 2026-10-17, §1.3).

The host gate answers 404 to a slug without a row, so a developer's database needs them once; local development
only (``DEBUG``), idempotent, through its operation (``base.hub.seed_local``), never a data migration (it would put
them in production).
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from live.context import OperationContext, system_context
from live.errors import PermissionDenied

from base import registry
from base.models import Hub
from base.schemas import HubSeedLocalIn
from base.services import hub_seed_local
from base.tenancy import migrator

pytestmark = pytest.mark.django_db


@pytest.fixture
def fresh(settings, monkeypatch):
    """A developer's database before its first seed: the suite's own `a` and `b` (conftest) are not there. Some app
    cannot live in a hub's own database here (``staff``, made unportable for these tests), so the command refuses
    before making any: their own databases are ``base/tenancy/tests/test_provision.py``'s, on real ones."""
    settings.DEBUG = True
    Hub.objects.filter(slug__in=["a", "b"]).delete()
    portable = tuple(label for label in migrator.portable_apps() if label != "staff")
    monkeypatch.setattr(migrator, "portable_apps", lambda: portable)


def seed() -> str:
    out = StringIO()
    call_command("seed_local_hubs", stdout=out)
    return out.getvalue()


@pytest.mark.usefixtures("fresh")
def test_refuses_while_some_app_cannot_live_in_a_hub_s_own_database():
    """Since S5 there is no shared database to leave a and b on: while some app cannot live in a hub's own database
    (``migrator.portable_apps``; here ``staff``), it refuses and writes nothing. Every app can since W10 (hub#474):
    the command then makes their databases (``base/tenancy/tests/test_provision.py``, on real ones)."""
    with pytest.raises(CommandError, match="staff"):
        seed()
    assert not Hub.objects.filter(slug__in=["a", "b"]).exists()


@pytest.mark.usefixtures("fresh")
def test_the_operation_names_each_local_hub_s_own_database_and_leaves_it_due():
    from control.models import HubDue

    from base.tenancy import connections as tenancy_connections
    from base.tenancy import names

    Hub.objects.create(slug="a", status="ready")  # a developer's a of phase 1, on control's database

    answer = hub_seed_local(system_context(registry.REGISTRY_SCOPE), HubSeedLocalIn(slugs=["a", "b"]))

    control = tenancy_connections.control_name()
    for hub in Hub.objects.filter(slug__in=["a", "b"]):
        assert (hub.status, hub.db_name) == ("requested", names.hub_db_name(control, hub.id))
        assert HubDue.objects.filter(pk=hub.pk).exists()
    assert {seeded.slug: seeded.outcome for seeded in answer.hubs} == {"a": "requested", "b": "created"}


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
