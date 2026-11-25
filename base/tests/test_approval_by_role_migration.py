"""The record of approvals keeps also what was done by whoever may do it themselves (``base/0032``): with no pass and no
limit in time. What it kept stays as it was. Going back is refused while it keeps one of those, and touches nothing:
nobody deletes a line of the record. These run on a business's own database, cloned from the template for each test,
through the migrator's alias as ``migrate_hubs`` runs them.
"""

import datetime as dt
import hashlib
import uuid

import pytest
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.utils import timezone

from base.tenancy import connections as tenancy_connections
from base.tenancy import names
from base.tenancy.tests import hubs
from base.tests.test_api_key_actions_migration import migrate

BEFORE = [("base", "0031_support_entry")]
AFTER = [("base", "0032_approval_by_role")]


@pytest.fixture
def database(hub_databases, django_db_blocker):
    """The migrator's connection to a business's database cloned from the template for the test, dropped after it."""
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        database = connections[tenancy_connections.register_ddl_alias(name)]
        try:
            yield database
        finally:
            database.close()


def row(models, alias: str, who: str, **fields):
    passed = {
        "fingerprint": "f" * 64,
        "token_digest": hashlib.sha256(who.encode()).hexdigest(),
        "approved_by_name": "Adam",
        "way": "pin",
        "expires_at": timezone.now() + dt.timedelta(minutes=2),
    }
    return models.get_model("base", "Approval").objects.using(alias).create(
        operation="sale.sale.void", permission="sale.void_sale", requested_by_name=who, **{**passed, **fields}
    )


def by_role(models, alias: str, who: str):
    return row(
        models, alias, who, way="role", fingerprint="", token_digest=None, approved_by_name="", expires_at=None,
        used_at=timezone.now(),
    )


def kept(models, alias: str) -> dict:
    return dict(models.get_model("base", "Approval").objects.using(alias).values_list("requested_by_name", "way"))


def test_it_keeps_what_it_had_and_takes_what_was_done_by_role(database):
    alias = database.alias
    old = migrate(database, BEFORE)
    row(old, alias, "Eva")
    row(old, alias, "Luis", way="badge")

    new = migrate(database, AFTER)
    by_role(new, alias, "Mario")
    by_role(new, alias, "Marta")

    assert kept(new, alias) == {"Eva": "pin", "Luis": "badge", "Mario": "role", "Marta": "role"}
    with pytest.raises(IntegrityError), transaction.atomic(using=alias):
        row(new, alias, "Ana", way="other")


def test_going_back_leaves_what_a_pin_or_a_badge_approved(database):
    alias = database.alias
    new = migrate(database, AFTER)
    row(new, alias, "Eva")

    old = migrate(database, BEFORE)

    assert kept(old, alias) == {"Eva": "pin"}
    with pytest.raises(IntegrityError), transaction.atomic(using=alias):
        row(old, alias, "Ana", way="role")


def test_going_back_is_refused_while_it_keeps_one_done_by_role_and_touches_nothing(database):
    alias = database.alias
    new = migrate(database, AFTER)
    row(new, alias, "Eva")
    by_role(new, alias, "Mario")

    with pytest.raises(DatabaseError):
        migrate(database, BEFORE)

    assert kept(new, alias) == {"Eva": "pin", "Mario": "role"}
