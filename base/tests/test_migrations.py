"""Data migrations of base: the customer roles of a Membership get the ``hub_`` prefix (reversible); the sessions
alive before ``SessionOwner`` get their note."""

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
