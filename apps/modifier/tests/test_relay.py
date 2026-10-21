"""Modifiers hear Inventory through the worker's outbox relay, end to end (MODIFIER-F09).

Inventory's real operation deletes a product (or a category) and records ``inventory.product.deleted`` in the
outbox; one tick of the worker's real loop (``base.worker.run`` → ``base.relay``) hands it to Modifiers
(``modifier.link.drop_product``), and the groups hung from it are let go — once: a second tick, or the same
notice handed over again, changes nothing. Before the tick the reads already leave that link out, so the till
never asks a group of something deleted. A product deleted in hub B lets go of B's links only, heard in B only.
"""

import pytest
from live.models import OutboxEvent

from apps.modifier.models import ModifierLink
from base import catalog, relay
from base.models import EventDelivery

from .conftest import FOOD, REGISTERED, A, B, ctx_for, heard, make_category, make_product, one_tick, run


def as_admin_of(scope, name: str, data: dict):
    """Run ``name`` as an admin of ``scope``: Inventory's and Modifiers' own operations, with their permissions."""
    return run(name, data, ctx=ctx_for(scope=scope))


def newest(name: str) -> OutboxEvent:
    return OutboxEvent.objects.filter(name=name).latest("id")


def delivery_to_modifier(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to Modifiers."""
    row = EventDelivery.objects.get(event_id=newest(name).id, app_label="modifier")
    return row.status, row.attempts


def detached() -> list[OutboxEvent]:
    return list(OutboxEvent.objects.filter(name="modifier.link.detached").order_by("id"))


def links_of(group, scope=A) -> list[tuple[str | None, str | None]]:
    """What the group's sheet lists under «Applies to»: ``(product_id, category_id)`` of each link."""
    page = as_admin_of(scope, "modifier.link.list", {"group_id": str(group.id)})
    return [
        (str(row.product_id) if row.product_id else None, str(row.category_id) if row.category_id else None)
        for row in page.rows
    ]


@pytest.fixture
def menu(db):
    """A burger with «Sauces» and «Extras», and the category «Mains» with «Sauces» too."""
    burger = make_product()
    mains = make_category()
    sauces = run("modifier.group.create", {"name": "Sauces"})
    extras = run("modifier.group.create", {"name": "Extras"})
    for group in (sauces, extras):
        run("modifier.link.attach", {"group_id": str(group.id), "product_id": str(burger.id)})
    run("modifier.link.attach", {"group_id": str(sauces.id), "category_id": str(mains.id)})
    return burger, mains, sauces, extras


def test_a_product_deleted_in_inventory_lets_go_of_its_groups_through_the_relay(tick, menu):
    burger, mains, sauces, extras = menu
    run("inventory.product.delete", {"id": str(burger.id)})
    before = len(detached())
    # Before the tick: the rows are still there, but the sheet already leaves the deleted product out.
    assert ModifierLink.objects.filter(product_id=burger.id).count() == 2
    assert links_of(sauces) == [(None, str(mains.id))]
    assert links_of(extras) == []

    tick()

    assert delivery_to_modifier("inventory.product.deleted") == ("delivered", 1)
    assert list(ModifierLink.objects.values_list("category_id", "product_id")) == [(mains.id, None)]
    said = detached()[before:]
    assert sorted(event.payload["group_id"] for event in said) == sorted([str(sauces.id), str(extras.id)])
    assert {(event.actor, event.scope_key) for event in said} == {("system", A.key)}
    counts = {row.name: row.link_count for row in run("modifier.group.list", {}).rows}
    assert counts == {"Extras": 0, "Sauces": 1}


def test_a_category_deleted_in_inventory_lets_go_of_its_groups_and_keeps_the_products(tick, menu):
    burger, mains, sauces, extras = menu
    run("inventory.category.delete", {"id": str(mains.id)})

    tick()

    assert delivery_to_modifier("inventory.category.deleted") == ("delivered", 1)
    assert sorted(ModifierLink.objects.values_list("group__name", "product_id")) == [
        ("Extras", burger.id),
        ("Sauces", burger.id),
    ]
    assert links_of(sauces) == [(str(burger.id), None)]
    (said,) = [event for event in detached() if event.payload["category_id"] == str(mains.id)]
    assert said.payload["group_id"] == str(sauces.id)


def test_a_second_tick_or_the_same_notice_handed_over_again_changes_nothing(tick, menu):
    burger, mains, sauces, _ = menu
    run("inventory.product.delete", {"id": str(burger.id)})
    tick()
    left, said = list(ModifierLink.objects.values_list("id", flat=True)), len(detached())

    tick()
    assert delivery_to_modifier("inventory.product.deleted") == ("delivered", 1)
    # The relay is at least once: the same notice again lets go of nothing more and says nothing more.
    assert relay.deliver("modifier", newest("inventory.product.deleted")).dropped == 0

    assert list(ModifierLink.objects.values_list("id", flat=True)) == left
    assert len(detached()) == said
    assert links_of(sauces) == [(None, str(mains.id))]


def test_a_product_never_linked_is_deleted_and_nothing_is_let_go(tick, menu):
    fries = make_product("Fries", "FRI", 300)
    links, said = ModifierLink.objects.count(), len(detached())
    run("inventory.product.delete", {"id": str(fries.id)})

    tick()

    assert delivery_to_modifier("inventory.product.deleted") == ("delivered", 1)
    assert (ModifierLink.objects.count(), len(detached())) == (links, said)


# ── Two hubs, on committed data ──────────────────────────────────────────────────────────────


def linked(scope, sku: str, group: str):
    """A product of ``scope`` with the group ``group`` hung from it."""
    product = as_admin_of(
        scope, "inventory.product.create", {"name": f"Burger {sku}", "sku": sku, "price": 800, "tax_category_key": FOOD}
    )
    made = as_admin_of(scope, "modifier.group.create", {"name": group})
    as_admin_of(scope, "modifier.link.attach", {"group_id": str(made.id), "product_id": str(product.id)})
    return product, made


def test_a_product_deleted_in_hub_b_lets_go_of_b_links_only_and_is_heard_in_b_only(listen, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    on_a, on_b = listen(A), listen(B)
    a_burger, a_sauces = linked(A, "BUR-A", "Sauces A")
    b_burger, b_sauces = linked(B, "BUR-B", "Sauces B")
    heard(on_a), heard(on_b)  # the creations' own notices

    as_admin_of(B, "inventory.product.delete", {"id": str(b_burger.id)})
    heard(on_b)  # the deletion's own notice
    one_tick()

    assert links_of(b_sauces, B) == []
    assert "modifier.link.detached" in heard(on_b)
    assert heard(on_a) == set()
    assert links_of(a_sauces, A) == [(str(a_burger.id), None)]
    (reaction,) = detached()
    assert (reaction.scope_kind, reaction.scope_key, reaction.payload["group_id"]) == (B.kind, B.key, str(b_sauces.id))
    # The positive control: a product deleted in hub A lets go of A's link, heard in A only.
    as_admin_of(A, "inventory.product.delete", {"id": str(a_burger.id)})
    heard(on_a)
    one_tick()
    assert links_of(a_sauces, A) == []
    assert "modifier.link.detached" in heard(on_a)
    assert heard(on_b) == set()
