"""The identity of a hub's database (PLAN-DB §3 and §14.4; plan 2026-10-22-fase-2-tenencia §4, step 6).

Every hub's database holds one row, ``base_hub_identity``, with its hub's id. ``use_hub`` reads it the first time a
process uses that alias and refuses a database that says it is another hub (a ``db_name`` changed by mistake, a
restore into the wrong database) or nothing: nothing is served from it. Once checked, an alias is not read again.

The refusals use hubs the session has no alias for, so they run outside a test case (``django_db_blocker``): Django's
test case only lets a test reach the aliases it names.
"""

import uuid
from types import SimpleNamespace

import pytest
from django.db import connections as django_connections

from base.tenancy import connections, context, identity
from base.tenancy.tests import hubs

pytestmark = pytest.mark.usefixtures("no_test_fallback")


@pytest.fixture(autouse=True)
def nothing_checked_yet(monkeypatch):
    monkeypatch.setattr(identity, "_verified", set())


def stranger(db_name: str):
    """A hub this session has no alias for, whose row names ``db_name``."""
    return SimpleNamespace(id=uuid.uuid7(), slug="stranger", db_name=db_name, cluster=None)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_database_that_is_its_hub_is_used(hub_a):
    with context.use_hub(hub_a) as active:
        assert active.alias == hubs.HUB_A_ALIAS
        assert django_connections[active.alias].settings_dict["NAME"] == hub_a.db_name


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_the_identity_is_read_once_per_process_and_alias(hub_a):
    seen = []

    def record(execute, sql, params, many, ctx):
        seen.append(sql)
        return execute(sql, params, many, ctx)

    with django_connections[hubs.HUB_A_ALIAS].execute_wrapper(record):
        with context.use_hub(hub_a):
            pass
        with context.use_hub(hub_a):
            pass

    assert len([sql for sql in seen if identity.IDENTITY_TABLE in sql]) == 1


def test_a_database_that_says_it_is_another_hub_is_refused(hub_databases, django_db_blocker):
    impostor = stranger(hub_databases.b)

    with django_db_blocker.unblock(), pytest.raises(identity.HubIdentityMismatch, match=str(hubs.HUB_B_ID)):
        with context.use_hub(impostor):
            pytest.fail("nothing runs on a database that is another hub's")


def test_a_database_without_its_identity_is_refused(hub_databases, django_db_blocker):
    assert identity.IDENTITY_TABLE in hubs.table_names(hub_databases.template)

    with django_db_blocker.unblock(), pytest.raises(identity.HubIdentityMismatch):
        connections.open_hub_alias(stranger(hub_databases.template))


def test_a_refusal_is_not_remembered_the_database_is_read_again(hub_databases, django_db_blocker):
    impostor = stranger(hub_databases.b)
    with django_db_blocker.unblock():
        alias = connections.register_hub_alias(impostor)
        with pytest.raises(identity.HubIdentityMismatch):
            identity.verify(alias, impostor.id)

        identity.verify(alias, hubs.HUB_B_ID)

    assert alias in identity._verified
