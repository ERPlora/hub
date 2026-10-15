"""Migration 0002 of the sale app: the two factory payment methods (Cash and Card), planted once,
never clobbering the owner's own, reversible.

The functions of the ``RunPython`` are called the way the migration runs them, with the app registry
and a schema editor whose connection is the test database.
"""

from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection

from apps.sale.models import PaymentMethod

pytestmark = pytest.mark.django_db

seed = import_module("apps.sale.migrations.0002_factory_payment_methods")


def run_forward():
    with connection.schema_editor() as editor:
        seed.plant(global_apps, editor)


def run_backward():
    with connection.schema_editor() as editor:
        seed.uproot(global_apps, editor)


def factory():
    return list(
        PaymentMethod.objects.filter(is_system=True)
        .order_by("sort_order")
        .values_list("name", "type", "sort_order")
    )


def test_cash_and_card_come_planted():
    assert factory() == [("Cash", "cash", 10), ("Card", "card", 20)]
    assert PaymentMethod.objects.filter(is_active=True).count() == 2


def test_planting_twice_changes_nothing():
    run_forward()
    assert factory() == [("Cash", "cash", 10), ("Card", "card", 20)]


def test_an_owner_who_already_has_a_method_of_a_type_keeps_his():
    PaymentMethod.objects.filter(is_system=True).delete()
    PaymentMethod.objects.create(name="Efectivo de caja", type="cash")
    run_forward()
    assert factory() == [("Card", "card", 20)]
    assert PaymentMethod.objects.filter(type="cash").count() == 1


def test_the_reverse_takes_out_only_the_unused_factory_methods():
    PaymentMethod.objects.create(name="Bizum", type="other")
    run_backward()
    assert factory() == []
    assert list(PaymentMethod.objects.values_list("name", flat=True)) == ["Bizum"]


def test_the_reverse_keeps_a_factory_method_a_refund_gave_money_back_by(product):
    from apps.sale.tests.conftest import run

    product("Coffee", "COF", 150, "product.generic")
    run("sale.payment_method.create", {"name": "Bizum", "type": "other"})
    sale = run("sale.sale.complete", {"idempotency_key": "mig-key-0001", "lines": [{"product": "COF"}], "payments": [{"method": "Bizum"}]})
    cash = PaymentMethod.objects.get(is_system=True, type="cash")
    run(
        "sale.sale.refund",
        {"sale_id": str(sale.id), "reason": "x", "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 150, "to_method_id": str(cash.id)}]},
    )
    run_backward()
    # Cash gave money back: it stays; Card was never used: it goes.
    assert factory() == [("Cash", "cash", 10)]
