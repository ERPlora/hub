"""A line keeps what its product or service costs the business, whoever sells it (SALE-F01, SALE-F15).

The cost is frozen into the line when it is added, as the price is, and the comps of a sale and of a shift are valued
with it. An employee does not see the costs (``base.view_costs``), so Inventory and Services answer them the cost empty:
the till still reads it, to keep it in the line, never to show it.
"""

import pytest
from live.context import system_context
from live.operations import get

from apps.sale.models import OrderLine, Sale, SaleLine
from apps.sale.tests.conftest import HUB_DB, A, ctx_for, run

pytestmark = HUB_DB

EMPLOYEE = "hub_employee"


@pytest.fixture
def shelf(product):
    product("Wax", "WAX", 900, "product.generic", cost=400)
    op = get("service.service.create")
    op(system_context(A), op.input.model_validate({"name": "Haircut", "price": 2500, "cost": 700,
                                                   "tax_category_key": "service.generic"}))


def test_an_employee_s_check_keeps_the_cost_of_each_product_and_service_it_takes(shelf):
    employee = ctx_for(EMPLOYEE)
    order = run("sale.order.open", {"lines": [{"product": "WAX"}]}, employee)
    run("sale.order.add_service_line", {"order_id": str(order.id), "service": "Haircut"}, employee)
    assert sorted(OrderLine.objects.filter(order_id=order.id).values_list("name", "cost")) == [
        ("Haircut", 700),
        ("Wax", 400),
    ]


def test_an_employee_s_sale_keeps_the_costs_and_values_its_comp_with_them(shelf):
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "cost-sale-0001",
            "lines": [{"product": "WAX", "is_gift": True}, {"product": "WAX", "quantity": "2"}],
            "payments": [{"method": "card"}],
        },
        ctx_for(EMPLOYEE),
    )
    assert list(SaleLine.objects.filter(sale_id=sale.id).values_list("cost", flat=True)) == [400, 400]
    assert Sale.objects.get(pk=sale.id).gift_total == 400
