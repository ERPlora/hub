"""Services with the real Taxes app: the tax category of a service is a tax.TaxCategory, without doubles.

What the till does with a service (Sales reads ``service.service.list_for_sale`` and prices the line
with ``tax.rate.calculate``) is run here with the real operations of both apps.
"""

import pytest
from live.errors import InvalidPayload
from live.operations import get

from apps.tax.models import TaxCategory

from .conftest import ctx_for

pytestmark = pytest.mark.django_db


def run(name, data, role="hub_admin"):
    op = get(name)
    return op(ctx_for(role), op.input.model_validate(data))


def test_a_service_taxes_with_a_factory_category_of_taxes_and_the_till_prices_it():
    # Migration 0002 of tax seeds the Spanish catalogue: service.generic at 21 % in Spain.
    cut = run(
        "service.service.create",
        {"name": "Haircut", "price": 2420, "tax_category_key": "service.generic"},
    )
    [line] = run("service.service.list_for_sale", {}).rows
    assert (line.id, line.tax_category_key, line.needs_tax_setup) == (
        cut.id,
        "service.generic",
        False,
    )
    priced = run(
        "tax.rate.calculate",
        {
            "amount": line.price,
            "tax_category_key": line.tax_category_key,
            "country_code": "ES",
            "tax_included": True,
        },
    )
    assert (priced.base, priced.tax, priced.total, priced.tax_rate_pct) == (
        2000,
        420,
        2420,
        21,
    )


def test_a_category_created_in_taxes_is_offered_to_services_and_becomes_the_default():
    created = run(
        "tax.category.create", {"key": "salon.beauty", "name": "Beauty treatments"}
    )
    settings = run("service.settings.update", {"default_tax_category_key": created.key})
    assert (settings.default_tax_category_key, settings.default_tax_category_name) == (
        "salon.beauty",
        "Beauty treatments",
    )
    facial = run("service.service.create", {"name": "Facial"})
    assert (facial.tax_category_key, facial.tax_category_name, facial.status) == (
        "salon.beauty",
        "Beauty treatments",
        "active",
    )


def test_a_category_taxes_deactivates_leaves_its_services_unconfigured_and_no_longer_offered():
    run("tax.category.create", {"key": "salon.old", "name": "Old"})
    service = run(
        "service.service.create", {"name": "Perm", "tax_category_key": "salon.old"}
    )
    TaxCategory.objects.filter(key="salon.old").update(is_active=False)
    assert run("service.service.get", {"id": str(service.id)}).status == "unconfigured"
    assert run("service.service.list_for_sale", {}).rows[0].needs_tax_setup is True
    with pytest.raises(InvalidPayload):
        run(
            "service.service.create", {"name": "Other", "tax_category_key": "salon.old"}
        )
    assert run("service.catalog.status", {}).sellable_services == 0
