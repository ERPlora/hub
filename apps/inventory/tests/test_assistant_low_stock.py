"""What the assistant is told of a product low on stock: a balance at zero does not take it off the till.

Asked what is running low, the model read a cheesecake at 0 and answered that the till would not offer it until more
arrived, while the till kept selling it. Only a product marked sold out leaves the till (INVENTORY-F29); a balance at
zero or below does not. The low-stock read says so, and each of its rows says whether the product is marked sold out,
so the model tells the person what the till does from what it read.
"""

import json
from decimal import Decimal

from live.assistant import description
from live.assistant.running import run_tool
from live.operations import get

from apps.inventory.models import Product

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB

LOW_STOCK = "inventory.product.list_low_stock"


def test_the_low_stock_read_says_a_balance_at_zero_does_not_take_a_product_off_the_till():
    said = description(get(LOW_STOCK))
    assert (
        "A balance at zero or below does not take an article off the till: the till still offers it, and only one "
        "marked sold out (is_sold_out) is not offered."
    ) in said


def test_each_low_stock_row_the_model_reads_says_whether_the_product_is_marked_sold_out():
    low = {"stock": Decimal("0"), "low_stock_threshold": Decimal("10"), "price": 550}
    Product.objects.create(name="Cheesecake", sku="DES-03", **low)
    Product.objects.create(name="Croquettes", sku="TAP-01", is_sold_out=True, **low)

    outcome = run_tool(ctx_for("hub_employee"), get(LOW_STOCK), json.dumps({"sort": "name"}))

    assert outcome.outcome == "ok", outcome.content
    rows = json.loads(outcome.content)["rows"]
    assert [(row["name"], row["stock"], row["is_sold_out"]) for row in rows] == [
        ("Cheesecake", "0.000", False),
        ("Croquettes", "0.000", True),
    ]
