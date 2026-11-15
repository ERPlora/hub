"""What a test of an app needs to run inside the businesses' own databases, as production runs: the scopes of the root
conftest's ``hub_a`` and ``hub_b``, the mark that names their databases, business A entered for the whole test and
the factory data a committed test plants again.

An app's ``conftest.py`` imports the fixtures it uses: ``in_business_a`` is autouse, so it applies to that app's tests
only."""

from importlib import import_module

import pytest
from django.apps import apps as registry
from django.db import connections
from live.context import Scope
from pytest_django.fixtures import validate_django_db

from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests import hubs

A = Scope("host", "tenant-a")
B = Scope("host", "tenant-b")
#: The host of business A's pages and API.
HOST = f"{A.key}.localhost"
#: Control's database and both businesses' own, each in the test's transaction.
HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)
HUB_DB_COMMITTED = pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)
#: The migrations that plant the factory data a sale or a document needs: Taxes' catalogue and Sales' payment methods.
FACTORY_DATA = (
    "apps.tax.migrations.0002_factory_catalogue",
    "apps.tax.migrations.0005_retail_alcohol",
    "apps.sale.migrations.0002_factory_payment_methods",
)


def uses_the_database(request) -> bool:
    marked = request.node.get_closest_marker("django_db") is not None
    return marked or bool({"db", "transactional_db"} & set(request.fixturenames))


def require_the_businesses_databases(request) -> None:
    """A test whose mark leaves out the businesses' databases would commit what it writes in them, outside its
    transaction, and leave it to the next test."""
    marker = request.node.get_closest_marker("django_db")
    databases = validate_django_db(marker)[2] if marker else None
    if not databases or hubs.HUB_A_ALIAS not in databases:
        pytest.fail(f"{request.node.nodeid} uses the database: mark it HUB_DB, with both businesses' own databases.")


@pytest.fixture(autouse=True)
def in_business_a(request, no_test_fallback, hub_databases):
    """Business A (``hub_a``), entered for the whole test if the test uses the database.

    ``hub_databases`` is asked for here, not only through ``hub_a``: built inside a test, its aliases would be forgotten
    with the test's own and the next tests would find them gone."""
    if not uses_the_database(request):
        yield None
        return
    require_the_businesses_databases(request)
    hub = request.getfixturevalue("hub_a")
    assert hub.slug == A.key, f"hub_a is {hub.slug!r}, not the scope A of these tests"
    with use_hub(hub):
        yield hub


def plant_factory_data() -> None:
    """The factory data planted again in the business at work, as its migrations plant it (idempotent)."""
    with connections[current_alias()].schema_editor() as editor:
        for module in FACTORY_DATA:
            import_module(module).plant(registry, editor)


@pytest.fixture
def factory_data(transactional_db, in_business_a):
    """A committed test finds business A's database emptied by the committed test before it."""
    plant_factory_data()


@pytest.fixture
def factory_data_b(transactional_db, hub_b):
    """The same in business B's database, for a committed test that works in it too."""
    with use_hub(hub_b):
        plant_factory_data()
