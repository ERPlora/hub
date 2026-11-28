"""Fixtures of the service tests: contexts per role and scope, users with a role on a host, a raw DSN,
builders of the data a test starts from (straight to the models: the operations are under test) and the
helpers the tests of the reads and the writes share.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``), nothing falling back on control's. Business B (``hub_b``) has its own database beside it; a test
of B asks for ``hub_b`` and enters it.

The builders import the models lazily, so that the tests of apps.py still collect while the models
do not exist.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connections
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import atomic, get
from psycopg.conninfo import make_conninfo

from apps.flow.tests.test_relay import worker_loop
from apps.sale.tests.conftest import night_elsewhere
from base.models import Membership
from base.services.sessions import ensure_hub_user
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases (the platform staff with business A chosen in the Hub
#: admin, business A at night in another zone or on a plan with room for several sessions, the worker's real loop over
#: them) that these tests take from here.
__all__ = [
    "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "hub_staff", "in_business_a", "night_elsewhere", "plan_with_room",
    "worker_loop",
]


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
        host: str | None = A.key,
        role: str = Membership.Role.ADMIN,
    ):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        # Who they are in the business's database, as their entry makes it: what a record hangs from.
        user.person = ensure_hub_user(user)
        return user

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of control's test database, where the live notices go after the COMMIT, for raw psycopg sessions."""
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
    from apps.service.models.catalog import Category

    return Category.objects.create(name=name, **fields)


def make_service(name: str = "Haircut", *, tax=None, price: int = 2000, **fields):
    from apps.service.models.catalog import Service

    return Service.objects.create(name=name, tax_category=tax, price=price, **fields)


def make_member(first_name: str = "Ana", last_name: str = "López", **fields):
    from apps.staff.models import Member

    return Member.objects.create(first_name=first_name, last_name=last_name, **fields)


def make_customer(name: str = "Lucía Pérez", **fields):
    from apps.customer.models import Customer

    return Customer.objects.create(name=name, **fields)


def make_package(name: str = "Bono 5 cortes", services=(), sessions: int = 1, **fields):
    from apps.service.models.packages import Package, PackageItem

    package = Package.objects.create(name=name, **fields)
    for position, service in enumerate(services):
        PackageItem.objects.create(
            package=package, service=service, sessions=sessions, sort_order=position
        )
    return package


def make_grant(package, customer, *, days_ago: int = 0, **fields):
    """A voucher sold ``days_ago`` days ago, with the package's terms frozen unless given."""
    from apps.service.models.grants import Grant

    fields.setdefault("max_uses", package.max_uses)
    fields.setdefault("validity_days", package.validity_days)
    granted_at = timezone.now() - dt.timedelta(days=days_ago)
    return Grant.objects.create(
        package=package, customer=customer, granted_at=granted_at, **fields
    )


def make_redemption(grant, service=None, **fields):
    from apps.service.models.grants import Redemption

    return Redemption.objects.create(grant=grant, service=service, **fields)


def refused(**create) -> bool:
    """Whether creating ``model(**fields)`` breaks a constraint (inside its own savepoint)."""
    model, fields = create.pop("model"), create
    try:
        with atomic():
            model.objects.create(**fields)
    except IntegrityError:
        return True
    return False


# Helpers the tests of the reads and the writes share


def run(name, data=None, role="hub_admin", **ctx):
    op = get(name)
    if data is None:
        data = op.input()
    elif isinstance(data, dict):
        data = op.input.model_validate(data)
    return op(ctx_for(role, **ctx), data)


def names(page) -> list[str]:
    return [row.name for row in page.rows]


def events() -> list[str]:
    return list(OutboxEvent.objects.order_by("id").values_list("name", flat=True))


def payload(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).latest("id").payload


@pytest.fixture
def tax():
    return make_tax()
