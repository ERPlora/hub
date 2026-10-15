"""The modifier app's event vocabulary (``modifier.<entity>.<fact in the past tense>``) and its reactions
to Inventory's events: a deleted product or category drops the groups hung from it (MODIFIER-F09)."""

import re

import pytest
from live.context import Scope
from live.models import OutboxEvent
from live.operations import NAME_RE

from apps.modifier import events
from apps.modifier.models import ModifierGroup, ModifierLink

from .conftest import A, make_category, make_product, run

PAST_FACT = re.compile(r"^modifier\.(group|option|link)\.[a-z_]+ed$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str)
    }


def test_the_eight_events_and_the_two_of_inventory_it_hears():
    assert declared() == {
        "GROUP_CREATED": "modifier.group.created",
        "GROUP_UPDATED": "modifier.group.updated",
        "GROUP_DELETED": "modifier.group.deleted",
        "OPTION_CREATED": "modifier.option.created",
        "OPTION_UPDATED": "modifier.option.updated",
        "OPTION_DELETED": "modifier.option.deleted",
        "LINK_ATTACHED": "modifier.link.attached",
        "LINK_DETACHED": "modifier.link.detached",
        "PRODUCT_DELETED": "inventory.product.deleted",
        "CATEGORY_DELETED": "inventory.category.deleted",
    }


def test_every_own_event_is_app_entity_fact_in_the_past():
    for value in events.ALL:
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value
    assert events.ALL == [
        value for value in declared().values() if value.startswith("modifier.")
    ]


def test_each_reaction_is_an_operation_of_this_app():
    assert events.REACTIONS == {
        "inventory.product.deleted": "modifier.link.drop_product",
        "inventory.category.deleted": "modifier.link.drop_category",
    }


def test_an_event_without_a_reaction_does_nothing():
    assert events.react(A, "inventory.product.created", {"id": "x"}) is None


@pytest.mark.django_db
def test_a_deleted_product_drops_its_links_and_says_so_once():
    burger = make_product()
    sauces = run("modifier.group.create", {"name": "Sauces"})
    extras = run("modifier.group.create", {"name": "Extras"})
    for group in (sauces, extras):
        run(
            "modifier.link.attach",
            {"group_id": str(group.id), "product_id": str(burger.id)},
        )
    kept = run(
        "modifier.link.attach",
        {"group_id": str(sauces.id), "category_id": str(make_category().id)},
    )
    run("inventory.product.delete", {"id": str(burger.id)})
    before = OutboxEvent.objects.filter(name="modifier.link.detached").count()

    result = events.react(
        A,
        "inventory.product.deleted",
        {"id": str(burger.id), "sku": "BUR", "name": "Burger"},
    )

    assert result.dropped == 2
    assert list(ModifierLink.objects.values_list("id", flat=True)) == [kept.id]
    detached = OutboxEvent.objects.filter(name="modifier.link.detached").order_by(
        "created_at"
    )[before:]
    assert sorted(event.payload["group_id"] for event in detached) == sorted(
        [str(sauces.id), str(extras.id)]
    )
    assert all(event.actor == "system" for event in detached)
    # Delivered again (the relay is at least once): nothing more to drop, nothing said.
    assert (
        events.react(A, "inventory.product.deleted", {"id": str(burger.id)}).dropped
        == 0
    )
    assert (
        OutboxEvent.objects.filter(name="modifier.link.detached").count() == before + 2
    )


@pytest.mark.django_db
def test_a_deleted_category_drops_its_links():
    mains = make_category()
    sauces = run("modifier.group.create", {"name": "Sauces"})
    run(
        "modifier.link.attach",
        {"group_id": str(sauces.id), "category_id": str(mains.id)},
    )
    run("inventory.category.delete", {"id": str(mains.id)})

    assert (
        events.react(
            A, "inventory.category.deleted", {"id": str(mains.id), "name": "Mains"}
        ).dropped
        == 1
    )
    assert ModifierLink.objects.count() == 0
    assert ModifierGroup.objects.count() == 1


@pytest.mark.django_db
def test_the_reaction_runs_as_the_system_scope_given():
    other = Scope("host", "b")
    burger = make_product()
    group = run("modifier.group.create", {"name": "Sauces"})
    run(
        "modifier.link.attach",
        {"group_id": str(group.id), "product_id": str(burger.id)},
    )
    events.react(other, "inventory.product.deleted", {"id": str(burger.id)})
    assert (
        OutboxEvent.objects.filter(name="modifier.link.detached")
        .latest("created_at")
        .scope_key
        == "b"
    )
