"""Two people at once: real sessions in threads, real row locks and unique indexes (WORKBOOK «Para quien
lo mantiene»). Two «make it general» at the same moment leave one general list; two lists, two rules
or two prices with the same code or quantity at once leave one, and the other is told why."""

import threading

import pytest
from django.db import connection
from live.errors import OperationError
from live.operations import get

from apps.pricing.models import DiscountRule, PriceItem, PriceList

from .conftest import ctx_for, make_list, make_product

pytestmark = pytest.mark.django_db(transaction=True)


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # an expected refusal or an unexpected failure, both reported
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_two_lists_made_general_at_once_leave_one_general_list():
    make_list("OLD", is_default=True)
    make_list("A")
    make_list("B")
    results = at_once(*(lambda code=code: run("pricing.price_list.set_default", {"price_list": code}) for code in ("A", "B")))
    assert not [result for result in results if isinstance(result, Exception)], results
    assert PriceList.objects.filter(is_default=True).count() == 1
    assert PriceList.objects.get(is_default=True).code in {"A", "B"}


def test_two_general_lists_created_at_once_leave_one():
    results = at_once(
        *(lambda code=code: run("pricing.price_list.create", {"code": code, "name": code, "is_default": True}) for code in "XYZ")
    )
    assert not [result for result in results if isinstance(result, Exception)], results
    assert PriceList.objects.count() == 3
    assert PriceList.objects.filter(is_default=True).count() == 1


def test_the_same_code_at_once_makes_one_list_and_one_rule():
    lists = at_once(*(lambda case=case: run("pricing.price_list.create", {"code": case, "name": "VIP"}) for case in ("VIP", "vip")))
    refused = [result for result in lists if isinstance(result, OperationError)]
    assert len(refused) == 1 and refused[0].code == "pricing.duplicate_code"
    assert PriceList.objects.count() == 1
    rule = {"name": "Ten", "rule_type": "percent", "percent": "10"}
    rules = at_once(*(lambda: run("pricing.rule.create", {"code": "TEN", **rule}) for _ in range(2)))
    refused = [result for result in rules if isinstance(result, OperationError)]
    assert len(refused) == 1 and refused[0].code == "pricing.duplicate_code"
    assert DiscountRule.objects.count() == 1


def test_the_same_price_at_once_is_put_once():
    make_list("VIP")
    product = make_product("Shampoo", "SH-1")
    data = {"price_list": "VIP", "product_id": str(product.id), "price": 1000, "min_quantity": "5"}
    results = at_once(*(lambda: run("pricing.price_item.add", data) for _ in range(2)))
    refused = [result for result in results if isinstance(result, OperationError)]
    assert len(refused) == 1 and refused[0].code == "pricing.price_item_exists"
    assert PriceItem.objects.count() == 1
