"""Data migrations of base: the customer roles of a Membership get the ``hub_`` prefix (reversible)."""

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
