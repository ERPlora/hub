"""A test of an app runs inside business A's own database, as a request of A runs in production, and a committed test
finds the factory data of each business planted again."""

from types import SimpleNamespace

import pytest
from django.apps import apps

from base.tenancy import context
from base.tenancy.tests import hubs
from base.tenancy.tests.business import (
    HUB_DB,
    HUB_DB_COMMITTED,
    A,
    factory_data,
    factory_data_b,
    in_business_a,
    require_the_businesses_databases,
)


@HUB_DB
def test_a_test_in_the_businesses_databases_runs_inside_business_a(in_business_a):
    assert in_business_a.slug == A.key
    assert context.current_alias() == hubs.HUB_A_ALIAS


def test_a_test_without_the_database_enters_no_business(in_business_a):
    assert in_business_a is None
    assert context.peek() is None


def a_test_marked(mark) -> SimpleNamespace:
    node = SimpleNamespace(nodeid="apps/x/tests/test_y.py::test_z", get_closest_marker=lambda name: mark)
    return SimpleNamespace(node=node, fixturenames=["db"])


@pytest.mark.parametrize("mark", [None, pytest.mark.django_db.mark, pytest.mark.django_db(transaction=True).mark])
def test_a_test_with_the_database_but_not_the_businesses_is_stopped_and_told_its_mark(mark):
    with pytest.raises(pytest.fail.Exception, match="apps/x/tests/test_y.py::test_z .*mark it HUB_DB"):
        require_the_businesses_databases(a_test_marked(mark))


@pytest.mark.parametrize("mark", [HUB_DB.mark, HUB_DB_COMMITTED.mark])
def test_a_test_marked_with_the_businesses_databases_goes_on(mark):
    require_the_businesses_databases(a_test_marked(mark))


def factory_payment_methods() -> int:
    return apps.get_model("sale", "PaymentMethod").objects.count()


@HUB_DB_COMMITTED
def test_the_factory_data_a_committed_test_emptied_is_planted_again_in_each_business(request, hub_databases, hub_b):
    hubs.empty(hub_databases.a)
    hubs.empty(hub_databases.b)
    assert factory_payment_methods() == 0
    request.getfixturevalue("factory_data")
    request.getfixturevalue("factory_data_b")
    assert factory_payment_methods() > 0
    with context.use_hub(hub_b):
        assert factory_payment_methods() > 0
