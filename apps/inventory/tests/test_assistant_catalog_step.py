"""«Your catalog» as the assistant reads it, in the owner's language: the step done with its line on the list, which
names no figure, and the count of active products from Inventory's own tool, where the checklist's read sends the model
for a figure (INVENTORY-F28). With seventeen products the model had answered «you have one».
"""

from dataclasses import replace

import pytest
from live.context import OperationContext
from live.operations import get

from apps.inventory.schemas.products import ProductIn
from apps.inventory.schemas.stock import SummaryIn
from apps.tax.models import TaxCategory
from base import assistant
from base.models import Membership
from base.schemas.home import SetupStatusIn

from .conftest import HUB_DB, ctx_for

STEP = "inventory.catalog"
COUNT = "inventory.stock.get_summary"
PRODUCTS = 17
LINES = {
    "en": "Add at least one product so there is something to sell.",
    "es": "Añade al menos un producto para que haya algo que vender.",
}


def owner(language: str) -> OperationContext:
    return replace(ctx_for(Membership.Role.OWNER), language=language)


@pytest.fixture
def seventeen_products(db):
    tax = TaxCategory.objects.get_or_create(key="test.general", defaults={"name": "General"})[0]
    for n in range(PRODUCTS):
        data = ProductIn(name=f"Dish {n}", sku=f"DISH-{n}", price=100, tax_category_key=tax.key)
        get("inventory.product.create")(owner("en"), data)


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_step_comes_done_with_its_line_and_no_figure(seventeen_products, language):
    items = get("base.setup.status")(owner(language), SetupStatusIn()).model_dump(mode="json")["items"]
    (step,) = [item for item in items if item["key"] == STEP]
    assert (step["state"], step["app"], step["description"]) == ("done", "inventory", LINES[language])


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_tool_of_the_step_app_gives_the_real_count(seventeen_products, language):
    ctx = owner(language)
    tool = assistant.tools.catalog(ctx)[COUNT]
    assert tool.app_label == "inventory"
    assert tool(ctx, SummaryIn()).active_products == PRODUCTS
