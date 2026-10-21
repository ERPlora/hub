"""The pricing app's events (``pricing.<entity>.<fact>``) and its reactions to other apps' events.

Here a reaction is tested by handing ``react`` the event as the relay does: its name, its scope and its
payload; ``test_relay.py`` runs each one end to end through the worker's real relay.
"""

import re
import uuid

import pytest
from live.operations import NAME_RE, registry

from apps.pricing import events
from apps.pricing.models import DiscountRule, PriceItem, PriceList

from .conftest import A, make_category, make_item, make_list, make_product, make_rule, make_service

PAST_FACT = re.compile(r"^pricing\.[a-z_]+\.[a-z_]+ed$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("pricing.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "PRICE_LIST_CREATED": "pricing.price_list.created",
        "PRICE_LIST_UPDATED": "pricing.price_list.updated",
        "PRICE_LIST_DEFAULT_CHANGED": "pricing.price_list.default_changed",
        "PRICE_LIST_DEACTIVATED": "pricing.price_list.deactivated",
        "PRICE_LIST_ACTIVATED": "pricing.price_list.activated",
        "PRICE_ITEM_ADDED": "pricing.price_item.added",
        "PRICE_ITEM_UPDATED": "pricing.price_item.updated",
        "PRICE_ITEM_REMOVED": "pricing.price_item.removed",
        "RULE_CREATED": "pricing.rule.created",
        "RULE_UPDATED": "pricing.rule.updated",
        "RULE_DEACTIVATED": "pricing.rule.deactivated",
        "RULE_ACTIVATED": "pricing.rule.activated",
    }


def test_the_old_module_s_four_events_keep_their_names():
    assert {"pricing.price_list.created", "pricing.price_item.added", "pricing.rule.created", "pricing.rule.deactivated"} <= set(
        declared().values()
    )


def test_every_event_is_app_entity_fact_in_the_past_and_listed_once():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value
    assert events.ALL == list(declared().values())
    assert events.PRICE_LIST_EVENTS + events.PRICE_ITEM_EVENTS + events.RULE_EVENTS == events.ALL


def test_it_reacts_to_what_deletes_or_renames_what_it_points_at():
    assert events.REACTIONS == {
        "inventory.product.deleted": "pricing.catalog.forget_product",
        "inventory.category.deleted": "pricing.catalog.forget_category",
        "customer.group.deleted": "pricing.catalog.forget_group",
        "service.service.updated": "pricing.catalog.refresh_service",
    }
    for operation_name in events.REACTIONS.values():
        assert registry[operation_name].permission == "pricing.system", operation_name


@pytest.mark.django_db
def test_react_runs_each_reaction_as_the_platform():
    product = make_product()
    make_item(make_list("VIP"), product)
    category = make_category()
    make_rule("CAT", applies_to="category", category=category)
    group_id = uuid.uuid7()
    make_list("GROUP", customer_group_id=group_id)
    service = make_service("Haircut")
    make_item(make_list("SALON"), None, service_id=service.id, service_name="Old name")

    events.react(A, "inventory.product.deleted", {"id": str(product.id), "sku": product.sku, "name": product.name})
    events.react(A, "inventory.category.deleted", {"id": str(category.id), "name": category.name})
    events.react(A, "customer.group.deleted", {"id": str(group_id)})
    events.react(A, "service.service.updated", {"id": str(service.id)})

    assert not PriceItem.objects.filter(product=product).exists()
    assert DiscountRule.objects.get(code="CAT").is_active is False
    assert PriceList.objects.get(code="GROUP").customer_group_id is None
    assert PriceItem.objects.get(service_id=service.id).service_name == "Haircut"


def test_an_event_without_reaction_is_ignored():
    assert events.react(A, "inventory.product.created", {"id": str(uuid.uuid7())}) is None
