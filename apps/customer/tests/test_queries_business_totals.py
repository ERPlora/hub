"""The customers' figures over HTTP (CUSTOMER-F02): how many customers there are reaches whoever reads the customers,
but what they all spent altogether is a figure of the whole business, so it reaches only whoever sees the business
totals (``base.view_business_totals``: the owner, the administrator and the manager). Anyone else gets it empty."""

import pytest

from apps.customer.models import Customer
from apps.flow.tests.test_api import get

from .conftest import HUB_DB

pytestmark = HUB_DB


@pytest.fixture
def cards():
    Customer.objects.create(name="Ana", total_spent=5000)
    Customer.objects.create(name="Bea", total_spent=12000, lifecycle_stage="vip")


def stats_as(make_user, client, role: str) -> dict:
    client.force_login(make_user(f"someone_{role}", role=role))
    response = get(client, "/customer/customers/stats")
    assert response.status_code == 200, response.content
    return response.json()


def test_an_employee_counts_the_customers_but_never_reads_what_they_all_spent(make_user, client, cards):
    assert stats_as(make_user, client, "hub_employee") == {"total": 2, "active": 2, "vip": 1, "total_revenue": None}


@pytest.mark.parametrize("role", ["hub_manager", "hub_admin", "hub_owner"])
def test_whoever_sees_the_business_totals_reads_it(make_user, client, cards, role):
    assert stats_as(make_user, client, role)["total_revenue"] == 17000
