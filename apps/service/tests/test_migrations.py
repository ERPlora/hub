"""Migration 0004 of the service app: the sessions delivered before a session had a value take their share of what
their voucher was paid, in the order they were spent, so the ones spent from now on share only what is left.

The function of the ``RunPython`` is called the way the migration runs it, with the app registry and a schema editor
whose connection is the test database.
"""

import datetime as dt
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection
from django.utils import timezone

from apps.service.models import GrantAdjustment, Redemption

from .conftest import make_customer, make_grant, make_package, make_redemption, make_service, make_tax

pytestmark = pytest.mark.django_db

migration = import_module("apps.service.migrations.0004_redemption_value")


def run_forward():
    with connection.schema_editor() as editor:
        migration.value_delivered_sessions(global_apps, editor)


@pytest.fixture
def voucher():
    cut = make_service("Cut", tax=make_tax())

    def make(name="Bono", amount=10000, uses=3):
        return make_grant(make_package(name, [cut], max_uses=uses), make_customer(f"Lucía {name}"), amount=amount)

    return make


def delivered(grant, days_ago, **fields):
    return make_redemption(grant, redeemed_at=timezone.now() - dt.timedelta(days=days_ago), **fields)


def values(*sessions):
    return [Redemption.objects.get(pk=session.pk).value for session in sessions]


def test_the_sessions_delivered_share_the_price_in_the_order_they_were_spent(voucher):
    grant = voucher()
    second, first = delivered(grant, 1), delivered(grant, 2)
    run_forward()
    assert values(first, second) == [3333, 3334]


def test_each_voucher_shares_its_own_price(voucher):
    one, other = voucher("Uno"), voucher("Otro", amount=9000)
    sessions = delivered(one, 1), delivered(other, 1)
    run_forward()
    assert values(*sessions) == [3333, 3000]


def test_the_sessions_added_and_taken_count_as_they_do_in_the_balance(voucher):
    added, taken = voucher("Añadidas"), voucher("Quitadas")
    GrantAdjustment.objects.create(grant=added, uses_delta=1, reason="courtesy")
    GrantAdjustment.objects.create(grant=taken, uses_delta=-1, reason="correction")
    sessions = delivered(added, 1), delivered(taken, 2), delivered(taken, 1)
    run_forward()
    assert values(*sessions) == [2500, 5000, 5000]


def test_only_the_delivered_sessions_take_a_share(voucher):
    grant = voucher()
    gone = [
        delivered(grant, 3, status=status)
        for status in (Redemption.Status.HELD, Redemption.Status.RELEASED, Redemption.Status.EXPIRED, Redemption.Status.RETURNED)
    ]
    spent = delivered(grant, 1)
    run_forward()
    assert values(*gone) == [None, None, None, None]
    assert values(spent) == [3333]


def test_an_unlimited_voucher_has_no_share_to_give(voucher):
    session = delivered(voucher(uses=None), 1)
    run_forward()
    assert values(session) == [None]


def test_more_sessions_delivered_than_it_has_now_never_go_below_nothing(voucher):
    grant = voucher(uses=1)
    sessions = delivered(grant, 2), delivered(grant, 1)
    run_forward()
    assert values(*sessions) == [10000, 0]


def test_running_it_again_changes_nothing(voucher):
    grant = voucher()
    session = delivered(grant, 1)
    run_forward()
    Redemption.objects.filter(pk=session.pk).update(value=1)
    run_forward()
    assert values(session) == [1]
