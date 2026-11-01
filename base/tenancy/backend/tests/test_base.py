"""The hubs' database engine (``base.tenancy.backend``): Django's PostgreSQL backend with the plan's limits on every
transaction (``base.tenancy.limits``; behaviour tested in ``base/tenancy/tests/test_limits.py``)."""

from django.db.backends.postgresql.base import DatabaseWrapper as PostgresWrapper
from django.db.utils import load_backend

from base.tenancy import limits


def test_the_engine_django_loads_is_postgresql_with_the_plans_limits():
    backend = load_backend(limits.ENGINE)

    assert issubclass(backend.DatabaseWrapper, PostgresWrapper)
    assert backend.DatabaseWrapper is not PostgresWrapper
    assert backend.DatabaseWrapper.vendor == "postgresql"


def test_each_connection_of_the_engine_carries_the_limit_at_its_cursor():
    backend = load_backend(limits.ENGINE)
    settings = {"NAME": "hub_x", "ENGINE": limits.ENGINE, "OPTIONS": {}, "TIME_ZONE": None, "CONN_MAX_AGE": 0,
                "CONN_HEALTH_CHECKS": False, "AUTOCOMMIT": True, "ATOMIC_REQUESTS": False}

    first = backend.DatabaseWrapper(settings, "hub_" + "a" * 32)
    copied = first.copy()

    assert len(first.execute_wrappers) == 1
    assert len(copied.execute_wrappers) == 1
    assert first.execute_wrappers[0] != copied.execute_wrappers[0]
