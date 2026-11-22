"""The databases of a recovery from a separate copy and of a move to another cluster, for every module of the tenancy
tests that runs one."""

import pytest

from base.tenancy.tests.test_move import Moves
from base.tenancy.tests.test_recovery import Recoveries


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


@pytest.fixture
def moves(django_db_blocker, hub_databases, dumps_bucket):
    with django_db_blocker.unblock():
        made = Moves(hub_databases.template)
        yield made
        made.clean()
