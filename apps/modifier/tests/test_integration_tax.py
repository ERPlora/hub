"""Modifiers together with the real Taxes app (its ``requires``), without doubles.

An option's own tax category is one of Taxes' (its factory catalogue, migration tax.0002), named the
way a person says it: its key, its name in Spanish or English, or a factory alias. What Taxes calculates
for that key is what Sales will charge on the option's own line.
"""

from decimal import Decimal

import pytest
from django.db.models import ProtectedError
from django.utils import translation
from live.operations import get

from apps.tax.models import TaxCategory

from .conftest import FOOD, GENERIC, ctx_for, make_product, run

pytestmark = pytest.mark.django_db


@pytest.fixture
def drinks():
    return run("modifier.group.create", {"name": "Drinks"})


@pytest.mark.parametrize(
    "said",
    [GENERIC, "Producto — general", "Product — generic", "goods"],
)
def test_a_tax_category_is_named_by_its_key_its_name_in_any_language_or_an_alias(
    drinks, said
):
    soda = run(
        "modifier.option.create",
        {
            "group": "Drinks",
            "name": "Soda",
            "price_delta": 250,
            "tax_category_key": said,
        },
    )
    assert soda.tax_category_key == GENERIC


def test_the_name_is_shown_in_the_readers_language(drinks):
    run("modifier.option.create", {"group": "Drinks", "name": "Soda", "price_delta": 250, "tax_category_key": GENERIC})
    assert run("modifier.option.list").rows[0].tax_category_name == "Product — generic"
    with translation.override("es"):
        assert run("modifier.option.list").rows[0].tax_category_name == "Producto — general"


def test_what_the_own_line_carries_is_what_taxes_calculates(drinks):
    run(
        "modifier.option.create",
        {
            "group": "Drinks",
            "name": "Soda",
            "price_delta": 250,
            "tax_category_key": GENERIC,
        },
    )
    make_product("Burger", "BUR-01", tax=FOOD)
    run("modifier.link.attach", {"group": "Drinks", "product": "BUR-01"})
    soda_id = (
        run("modifier.group.for_target", {"product": "BUR-01"}).groups[0].options[0].id
    )
    [pick] = run(
        "modifier.selection.resolve",
        {"product": "BUR-01", "option_ids": [str(soda_id)]},
    ).picks
    assert (pick.own_line, pick.tax_category_key) == (True, GENERIC)

    calculate = get("tax.rate.calculate")
    tax = calculate(
        ctx_for(),
        calculate.input(
            amount=pick.price_delta,
            tax_category_key=pick.tax_category_key,
            tax_included=True,
        ),
    )
    # 21 % in Spain on the soda's own line; the burger keeps its 10 %.
    assert (tax.tax_rate_pct, tax.total, tax.base + tax.tax) == (
        Decimal("21.00"),
        250,
        250,
    )


def test_a_tax_category_in_use_by_an_option_cannot_be_deleted(drinks):
    run(
        "modifier.option.create",
        {
            "group": "Drinks",
            "name": "Soda",
            "price_delta": 250,
            "tax_category_key": GENERIC,
        },
    )
    with pytest.raises(ProtectedError):
        TaxCategory.objects.get(key=GENERIC).delete()
