"""Fixtures of the service tests: contexts per role and scope, users with a role on a host, a raw DSN,
and builders of the data a test starts from (straight to the models: the operations are under test).

The builders import the models lazily, so that the tests of apps.py still collect while models.py
does not exist.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from psycopg.conninfo import make_conninfo

from base.models import Membership

A = Scope("host", "a")
B = Scope("host", "b")


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: object = "tester",
    permissions: set[str] | None = None,
) -> OperationContext:
    """The context a caller with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    ``permissions`` replaces the role's when a test needs a combination no role has.
    """
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor=actor, permissions=permissions)


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English: a request in Spanish leaves its language active on the thread."""
    with translation.override("en"):
        yield


@pytest.fixture
def make_user(db):
    def make(
        username: str = "ana",
        *,
        host: str | None = "a",
        role: str = Membership.Role.ADMIN,
    ):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (reading only what is committed)."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


# Builders


def make_tax(key: str = "test.service", name: str = "Service — test", **fields):
    from apps.tax.models import TaxCategory

    return TaxCategory.objects.create(key=key, name=name, **fields)


def make_category(name: str = "Hair", **fields):
    from apps.service.models import Category

    return Category.objects.create(name=name, **fields)


def make_service(name: str = "Haircut", *, tax=None, price: int = 2000, **fields):
    from apps.service.models import Service

    return Service.objects.create(name=name, tax_category=tax, price=price, **fields)


def make_member(first_name: str = "Ana", last_name: str = "López", **fields):
    from apps.staff.models import Member

    return Member.objects.create(first_name=first_name, last_name=last_name, **fields)


def make_customer(name: str = "Lucía Pérez", **fields):
    from apps.customer.models import Customer

    return Customer.objects.create(name=name, **fields)


def make_package(name: str = "Bono 5 cortes", services=(), sessions: int = 1, **fields):
    from apps.service.models import Package, PackageItem

    package = Package.objects.create(name=name, **fields)
    for position, service in enumerate(services):
        PackageItem.objects.create(
            package=package, service=service, sessions=sessions, sort_order=position
        )
    return package


def make_grant(package, customer, *, days_ago: int = 0, **fields):
    """A voucher sold ``days_ago`` days ago, with the package's terms frozen unless given."""
    from apps.service.models import Grant

    fields.setdefault("max_uses", package.max_uses)
    fields.setdefault("validity_days", package.validity_days)
    granted_at = timezone.now() - dt.timedelta(days=days_ago)
    return Grant.objects.create(
        package=package, customer=customer, granted_at=granted_at, **fields
    )


def make_redemption(grant, service=None, **fields):
    from apps.service.models import Redemption

    return Redemption.objects.create(grant=grant, service=service, **fields)
