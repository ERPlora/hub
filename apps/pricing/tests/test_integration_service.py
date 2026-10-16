"""Pricing with the real Services app, which it does not require: a service is read by the name of
Services' operations (``service.service.get``) with the caller's session, and its new name arrives by
its event, handed to ``events.react`` as the outbox relay will."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from live.errors import PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.pricing import events
from apps.pricing.models import DiscountRule, PriceItem

from .conftest import A, TODAY, ctx_for

pytestmark = pytest.mark.django_db

WHEN = dt.datetime.combine(TODAY, dt.time(12), ZoneInfo("Europe/Madrid")).isoformat()


def run(name, data, ctx=None):
    op = get(name)
    return op(ctx or ctx_for("hub_admin"), op.input.model_validate(data))


def relay(name: str) -> None:
    event = OutboxEvent.objects.filter(name=name).latest("created_at")
    events.react(A, event.name, event.payload)


@pytest.fixture
def haircut():
    return run("service.service.create", {"name": "Haircut", "price": 1800, "tax_category_key": "service.generic"})


def test_a_service_of_services_is_priced_by_its_name_and_discounted(haircut):
    run("pricing.price_list.create", {"code": "GEN", "name": "General", "is_default": True})
    run("pricing.price_item.add", {"price_list": "GEN", "service": "haircut", "price": 1600})
    run("pricing.rule.create", {"code": "SALON", "name": "Salon", "rule_type": "fixed", "amount": 100, "applies_to": "services"})
    line = run("pricing.price.resolve", {"service": "Haircut", "when": WHEN})
    assert (line.service_id, line.base_price, line.unit_price, line.rule_code, line.total) == (haircut.id, 1800, 1600, "SALON", 1500)


def test_a_service_renamed_in_services_is_renamed_in_pricing(haircut):
    run("pricing.price_list.create", {"code": "GEN", "name": "General"})
    run("pricing.price_item.add", {"price_list": "GEN", "service_id": str(haircut.id), "price": 1600})
    run("pricing.rule.create", {"code": "CUT", "name": "Cut", "rule_type": "percent", "percent": "10", "applies_to": "service", "service": "Haircut"})
    run("service.service.update", {"id": str(haircut.id), "name": "Women's haircut"})
    relay("service.service.updated")
    assert PriceItem.objects.get().service_name == "Women's haircut"
    assert DiscountRule.objects.get(code="CUT").service_name == "Women's haircut"
    assert run("pricing.price_item.list", {"price_list": "GEN"}).rows[0].name == "Women's haircut"


def test_reading_a_service_needs_the_caller_s_permission_in_services(haircut):
    # Pricing reads Services with the session of whoever asks: no Services permission, no service.
    ctx = ctx_for(permissions={"pricing.view"})
    with pytest.raises(PermissionDenied):
        run("pricing.price.resolve", {"service_id": str(haircut.id), "when": WHEN}, ctx=ctx)
