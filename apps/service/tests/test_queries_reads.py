"""How the lists of the service app page: a descending list is the ascending one read backwards, ties included."""

import pytest

from apps.service.schemas.catalog import ServiceListIn
from apps.service.schemas.categories import CategoryListIn
from apps.service.schemas.packages import PackageListIn

from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import HUB_DB, make_category, make_package, make_service, make_tax, run

pytestmark = HUB_DB


def _tied_services():
    tax = make_tax()
    return [make_service(f"Cut {n}", tax=tax, price=2000).id for n in range(4)]


def _tied_service_categories():
    return [make_category(f"Family {n}", sort_order=1).id for n in range(4)]


def _tied_packages():
    return [make_package(f"Bono {n}", sort_order=1).id for n in range(4)]


@pytest.mark.parametrize(
    ("operation", "schema", "tied", "column"),
    [
        ("service.service.list", ServiceListIn, _tied_services, "price"),
        ("service.category.list", CategoryListIn, _tied_service_categories, "sort_order"),
        ("service.package.list", PackageListIn, _tied_packages, "sort_order"),
    ],
)
def test_ties_read_backwards_in_a_descending_list(operation, schema, tied, column):
    """hub#768 (as in Customers): a descending list is the ascending one read backwards, ties
    included, and its pages neither repeat nor lose rows. A live name is unique, so the name settles these ties."""
    assert_reads_backwards(listed_with(run, operation, column, schema=schema), tied())
