"""Data migrations of base: the customer roles of a Membership get the ``hub_`` prefix (reversible); the sessions
alive before ``SessionOwner`` get their note; the hubs of before round 2026-10-27 keep every app on (reversible)."""

from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection

from base.models import Membership

pytestmark = pytest.mark.django_db


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _roles():
    return import_module("base.migrations.0002_prefixed_membership_roles")


def _roles_by_host() -> dict[str, str]:
    return dict(Membership.objects.values_list("host", "role"))


def test_roles_saved_without_the_prefix_get_it_and_lose_it_on_revert(make_user):
    user = make_user()
    Membership.objects.bulk_create(
        [
            Membership(user=user, host="a", role="admin"),
            Membership(user=user, host="b", role="manager"),
            Membership(user=user, host="c", role="employee"),
            Membership(user=user, host="d", role="hub_owner"),
        ]
    )

    _roles().add_prefix(global_apps, _SchemaEditor())
    assert _roles_by_host() == {"a": "hub_admin", "b": "hub_manager", "c": "hub_employee", "d": "hub_owner"}

    _roles().remove_prefix(global_apps, _SchemaEditor())
    # Before this migration there was no owner: the owner goes back as an admin.
    assert _roles_by_host() == {"a": "admin", "b": "manager", "c": "employee", "d": "admin"}


def _owners():
    return import_module("base.migrations.0008_session_owner")


def test_the_sessions_alive_before_the_index_get_their_note_from_what_they_say():
    """``/internal/sessions/revoke`` reads ``SessionOwner``: the sessions opened before it get their note once."""
    import datetime as dt

    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    from base.models import SessionOwner

    def saved(data: dict) -> str:
        store = SessionStore()
        store.update(data)
        store.create()
        return store.session_key

    member = saved({"saas_user_id": "ana", "hub_host": "acme"})
    staff = saved({"saas_user_id": "ana", "hub_host": "@platform"})
    hostless = saved({"saas_user_id": "olga"})  # from before the sessions noted their host
    saved({"demo_slug": "demo-1a2b3c4d", "hub_host": "demo-1a2b3c4d"})  # a demo's: no SaaS account
    expired = saved({"saas_user_id": "ana", "hub_host": "acme"})
    Session.objects.filter(pk=expired).update(expire_date=timezone.now() - dt.timedelta(seconds=1))

    _owners().note_the_live_sessions(global_apps, _SchemaEditor())

    assert set(SessionOwner.objects.values_list("session_id", "saas_user_id", "host")) == {
        (member, "ana", "acme"),
        (staff, "ana", "@platform"),
        (hostless, "olga", ""),
    }
    _owners().note_the_live_sessions(global_apps, _SchemaEditor())  # a second run notes nothing twice
    assert SessionOwner.objects.count() == 3


# ── Round 2026-10-27: a hub is born with every app off; the hubs of before keep theirs (base.0017) ──────────────────


def _apps_kept():
    return import_module("base.migrations.0017_hubs_of_before_keep_their_apps")


def _activations(host: str) -> dict:
    from base.activation import Activation
    from base.models import AppActivation

    return {
        row.app: Activation(row.state, row.chosen) for row in AppActivation.objects.filter(host=host).order_by("app")
    }


@pytest.fixture
def hubs_of_before():
    """The registry as a deployment has it before the migration: hubs on the baseline of then (no row, every app on),
    one that already changed its apps, a purged demo and a hub with a database of its own."""
    from django.utils import timezone

    from base.models import AppActivation, Hub

    AppActivation.objects.filter(host__in=["a", "b"]).delete()  # the suite's local hubs, as a hub of before
    Hub.objects.create(slug="acme", status="ready")
    Hub.objects.create(slug="demo-0000beef", is_demo=True, status="ready", expires_at=timezone.now())
    Hub.objects.create(slug="cancelled", status="cancelled")
    Hub.objects.create(slug="chose", status="ready")
    AppActivation.objects.create(host="chose", app="task", state="on", chosen=True)
    Hub.objects.create(slug="demo-0000dead", is_demo=True, status="purged", expires_at=timezone.now())
    Hub.objects.create(slug="own", status="ready", db_name="hub_own")


def test_every_hub_of_before_without_rows_keeps_every_app_on_and_nothing_else_changes(hubs_of_before):
    from base import activation

    every_on = activation.every_on(activation.module_graph())

    _apps_kept().write_every_app_on(global_apps, _SchemaEditor())

    for host in ("a", "b", "acme", "demo-0000beef", "cancelled"):
        assert _activations(host) == every_on, host
    assert sum(row.chosen for row in every_on.values()) == 17  # its roots chosen, as the baseline of before
    assert _activations("chose") == {"task": activation.Activation("on", True)}  # what it chose stays
    assert _activations("demo-0000dead") == {}  # purged: nothing of it is served again
    assert _activations("own") == {}  # its apps live in its own database, migrated there


def test_running_it_again_writes_nothing_more(hubs_of_before):
    from base.models import AppActivation

    _apps_kept().write_every_app_on(global_apps, _SchemaEditor())
    count = AppActivation.objects.count()

    _apps_kept().write_every_app_on(global_apps, _SchemaEditor())

    assert AppActivation.objects.count() == count


def test_reverting_forgets_exactly_the_rows_it_wrote(hubs_of_before):
    """Back to the baseline of before (no row, every app on): the hubs whose rows are still every app on lose them;
    one that changed something since keeps its rows, as does one that had chosen before."""
    from base import activation
    from base.models import AppActivation

    _apps_kept().write_every_app_on(global_apps, _SchemaEditor())
    AppActivation.objects.filter(host="acme", app="task").update(state="off", chosen=False)

    _apps_kept().forget_every_app_on(global_apps, _SchemaEditor())

    for host in ("a", "b", "demo-0000beef", "cancelled"):
        assert _activations(host) == {}, host
    acme = activation.every_on(activation.module_graph())
    acme["task"] = activation.Activation("off", False)
    assert _activations("acme") == acme
    assert _activations("chose") == {"task": activation.Activation("on", True)}


def test_on_a_hubs_own_database_it_does_nothing(hubs_of_before):
    """The registry lives in control's database: a hub's own one (its ``__ddl`` alias) has no hub of before."""
    from base.models import AppActivation

    class OnAHubsDatabase:
        class connection:
            alias = "hub_0123__ddl"

    _apps_kept().write_every_app_on(global_apps, OnAHubsDatabase())
    _apps_kept().forget_every_app_on(global_apps, OnAHubsDatabase())

    assert AppActivation.objects.filter(host="acme").count() == 0
    assert AppActivation.objects.filter(host="chose").count() == 1


def test_the_migration_goes_both_ways():
    from django.db import migrations

    run = [operation for operation in _apps_kept().Migration.operations if isinstance(operation, migrations.RunPython)]
    assert len(run) == 1 and run[0].reversible
    assert ("control", "0001_initial") in _apps_kept().Migration.dependencies
