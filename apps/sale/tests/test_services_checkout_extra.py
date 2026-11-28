"""Charging with what another app adds to a tender (SALE-F39, the tip of Tips): ``sale.sale.complete`` keeps it on
each payment, apart from the sale. The sale's base, tax and total, the payments' amounts and the figures of Sales stay
the ones of the same sale without it; what is handed over covers both, and the change takes both out. Every test here charges
with an app that adds a step to the charge (``a_step_at_the_charge``); without one, the charge refuses what is added
(``test_services_checkout.py``).

The amounts are tax's real calculation over the factory catalogue (Spain): restaurant.food at 10 %.
"""

import pytest
from live.context import system_context
from live.errors import Conflict
from live.models import OutboxEvent

from apps.sale.models.numbering import SaleCounter
from apps.sale.models.payments import SalePayment
from apps.sale.models.sales import Sale
from apps.sale.tests.conftest import HUB_DB, B, ctx_for, run
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = [HUB_DB, pytest.mark.usefixtures("a_step_at_the_charge")]

KEY = "pos-extra-0001"
TIP = "Tip"


@pytest.fixture
def steak(product):
    return product("Steak", "STK", 1800, "restaurant.food")


def complete(*payments, key: str = KEY, ctx=None, sku: str = "STK", **data):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "lines": [{"product": sku}], "payments": list(payments), **data},
        ctx,
    )


def tipped(method: str, extra: int, **leg) -> dict:
    return {"method": method, "extra": extra, "extra_label": TIP, **leg}


def legs(sale) -> list[tuple]:
    return [
        (p.method_type, p.amount, p.extra, p.extra_label, p.tendered, p.change)
        for p in SalePayment.objects.filter(sale_id=sale.id).order_by("position")
    ]


def fiscal(sale) -> tuple:
    stored = Sale.objects.get(pk=sale.id)
    return (stored.subtotal, stored.tax_total, stored.total, stored.tax_breakdown)


def test_a_cash_tender_keeps_what_is_added_apart_and_its_change_takes_both_out(steak):
    sale = complete(tipped("cash", 200, tendered=2500))
    assert legs(sale) == [("cash", 1800, 200, TIP, 2500, 500)]
    assert (sale.total, sale.tendered_total, sale.change_total) == (1800, 2500, 500)
    plain = complete({"method": "cash", "tendered": 2500}, key="pos-extra-0002")
    assert fiscal(sale) == fiscal(plain)
    assert [(line.net_amount, line.tax_amount) for line in sale.lines] == [
        (line.net_amount, line.tax_amount) for line in plain.lines
    ]


def test_what_is_handed_over_has_to_cover_the_sale_and_what_is_added(steak):
    with pytest.raises(Conflict) as refusal:
        complete(tipped("cash", 200, tendered=1900))
    assert refusal.value.code == "sale.insufficient_tendered"
    assert Sale.objects.count() == 0 and not SaleCounter.objects.filter(last__gt=0).exists()
    # Exactly both is no change.
    assert legs(complete(tipped("cash", 200, tendered=2000))) == [("cash", 1800, 200, TIP, 2000, 0)]


def test_cash_without_what_was_handed_over_is_the_sale_and_what_is_added_exactly(steak):
    assert legs(complete(tipped("cash", 200))) == [("cash", 1800, 200, TIP, 2000, 0)]


def test_a_card_charges_the_sale_and_what_is_added(steak):
    sale = complete(tipped("card", 300, reference="AUTH-1"))
    assert legs(sale) == [("card", 1800, 300, TIP, 2100, 0)]
    assert (sale.total, sale.tendered_total, sale.change_total) == (1800, 2100, 0)


def test_a_split_charge_keeps_what_each_tender_adds_and_the_rest_counts_the_sale_only(steak):
    sale = complete(
        tipped("cash", 200, amount=1000, tendered=1500),
        tipped("card", 100),
    )
    assert legs(sale) == [
        ("cash", 1000, 200, TIP, 1500, 300),
        ("card", 800, 100, TIP, 900, 0),
    ]
    assert sale.total == 1800


def test_a_charge_of_nothing_takes_nothing_added(steak):
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.sale.complete",
            {
                "idempotency_key": KEY,
                "lines": [{"product": "STK", "is_gift": True}],
                "payments": [tipped("cash", 200)],
            },
        )
    assert refusal.value.code == "sale.payments_do_not_match_total"
    assert Sale.objects.count() == 0


def test_the_completed_notice_carries_what_each_tender_adds_apart(steak):
    sale = complete(tipped("cash", 200, tendered=2500))
    notice = OutboxEvent.objects.get(name="sale.sale.completed").payload
    assert notice["total"] == 1800 and notice["sale_id"] == str(sale.id)
    assert [
        (p["method_type"], p["amount"], p["extra"], p["extra_label"], p["tendered"], p["change"])
        for p in notice["payments"]
    ] == [("cash", 1800, 200, TIP, 2500, 500)]


def test_the_sale_read_again_says_what_each_tender_adds(steak):
    sale = complete(tipped("card", 300))
    for read in (sale, run("sale.sale.get", {"sale_id": str(sale.id)})):
        assert [(p.amount, p.extra, p.extra_label, p.tendered) for p in read.payments] == [(1800, 300, TIP, 2100)]


def test_the_same_attempt_charges_once_and_with_another_addition_it_is_refused(steak):
    first = complete(tipped("card", 300))
    again = complete(tipped("card", 300))
    assert (again.id, again.already) == (first.id, True)
    for other in (tipped("card", 400), {"method": "card"}):
        with pytest.raises(Conflict) as refusal:
            complete(other)
        assert refusal.value.code == "sale.idempotency_key_reused"
    assert Sale.objects.count() == 1


def test_the_cash_limit_looks_at_the_sale_and_not_at_what_is_added(product):
    product("Almost", "ALM", 99999, "product.generic")
    sale = complete(tipped("cash", 5000, tendered=105000), sku="ALM")
    assert legs(sale) == [("cash", 99999, 5000, TIP, 105000, 1)]


def test_the_ticket_limit_looks_at_the_sale_and_not_at_what_is_added(product):
    product("Watch", "WCH", 300000, "product.generic")
    sale = complete(tipped("card", 10000), sku="WCH")
    assert (sale.document_type, sale.total) == ("ticket", 300000)


def test_the_figures_of_sales_count_the_sale_and_not_what_is_added(steak):
    complete(tipped("cash", 200, tendered=2500))
    complete({"method": "cash", "tendered": 2500}, key="pos-extra-0002")
    assert run("sale.sale.today", {}).total == 3600
    stats = run("sale.sale.stats", {})
    assert (stats.total_revenue, stats.net_total + stats.tax_total) == (3600, 3600)
    assert [day.total for day in run("sale.sale.last_7_days", {}).rows][-1] == 3600


def test_what_is_added_in_one_business_never_reaches_the_database_of_another(steak, hub_b):
    with use_hub(hub_b):
        run(
            "inventory.product.create",
            {"name": "Steak", "sku": "STK", "price": 2000, "tax_category_key": "restaurant.food"},
            system_context(B),
        )
        complete(tipped("card", 700), key="pos-extra-in-b", ctx=ctx_for(scope=B))
    with hubs.assert_only_alias(hubs.HUB_A_ALIAS):
        sale = complete({"method": "card"})
        assert legs(sale) == [("card", 1800, 0, "", 1800, 0)]
        assert not SalePayment.objects.filter(extra__gt=0).exists()
        assert [p["extra"] for p in OutboxEvent.objects.get(name="sale.sale.completed").payload["payments"]] == [0]
    with use_hub(hub_b):
        assert [(p.amount, p.extra) for p in SalePayment.objects.all()] == [(2000, 700)]
