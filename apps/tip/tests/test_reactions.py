"""Voiding a sale or refunding it whole voids its tips by themselves (TIP-F06): the customer gets back what they paid,
tip included. A refund of only some lines leaves them as they are. The worker hands each event of Sales to
``events.react``; a repeated delivery changes nothing."""

import dataclasses

import pytest
from live.context import system_context
from live.errors import PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.cash_register.models import Movement
from apps.tip import events
from apps.tip.models import Tip

from .conftest import (
    CARD,
    HUB_DB,
    A,
    add_tip,
    charge,
    ctx_for,
    open_session,
    refund,
    void,
)

pytestmark = HUB_DB


def deliver(name: str):
    """Hands the last event ``name`` of the outbox to Tips, as the worker's relay does."""
    event = OutboxEvent.objects.filter(name=name).latest("created_at")
    return events.react(A, name, event.payload)


def statuses() -> list[str]:
    return list(Tip.objects.order_by("created_at", "id").values_list("status", flat=True))


def test_voiding_a_sale_voids_its_tips_and_takes_them_out_of_the_open_drawer(coffee):
    open_session()
    sale = charge()
    add_tip(100, "cash", sale_id=str(sale.id))
    add_tip(50, "card", sale_id=str(sale.id))
    other = charge(payments=CARD)
    add_tip(70, "card", sale_id=str(other.id))
    void(sale)
    assert deliver("sale.sale.voided").changed == 2
    assert statuses() == ["voided", "voided", "active"]
    voided = Tip.objects.filter(status="voided").first()
    # Who voided the sale and why: the sale's own void.
    assert (voided.voided_by, voided.void_reason) == ("tester", "wrong ticket")
    assert list(Movement.objects.filter(app="tip", type="out").values_list("method_type", "amount").order_by("amount")) == [
        ("card", 50),
        ("cash", 100),
    ]
    assert OutboxEvent.objects.filter(name="tip.tip.voided").count() == 2


def test_a_repeated_delivery_changes_nothing(coffee):
    open_session()
    sale = charge()
    add_tip(100, "cash", sale_id=str(sale.id))
    void(sale)
    deliver("sale.sale.voided")
    assert deliver("sale.sale.voided").changed == 0
    assert Movement.objects.filter(app="tip", type="out").count() == 1


def test_refunding_a_sale_whole_voids_its_tips(coffee):
    sale = charge(payments=CARD)
    add_tip(100, sale_id=str(sale.id))
    refund(sale, sale.total)
    assert deliver("sale.sale.refunded").changed == 1
    assert statuses() == ["voided"]
    assert (Tip.objects.get().voided_by, Tip.objects.get().void_reason) == ("tester", "returned")


def test_a_refund_of_part_of_a_sale_leaves_its_tips(coffee):
    sale = charge("2", payments=CARD)
    add_tip(100, sale_id=str(sale.id))
    refund(sale, 150)
    assert deliver("sale.sale.refunded").changed == 0
    assert statuses() == ["active"]


def test_a_voided_sale_without_tips_changes_nothing(coffee):
    sale = charge(payments=CARD)
    void(sale)
    assert deliver("sale.sale.voided").changed == 0


def test_the_reactions_run_as_the_platform_only(coffee):
    sale = charge(payments=CARD)
    op = get("tip.sale.void")
    payload = op.input.model_validate({"sale_id": str(sale.id)})
    for role in ("hub_manager", "hub_employee"):
        with pytest.raises(PermissionDenied):
            op(ctx_for(role), payload)
    assert op(system_context(A), payload).changed == 0


def test_not_even_the_owner_s_whole_app_reaches_the_reactions(coffee):
    sale = charge(payments=CARD)
    op = get("tip.sale.void")
    owner = dataclasses.replace(ctx_for(), permissions=frozenset({"tip.*"}))
    with pytest.raises(PermissionDenied):
        op(owner, op.input.model_validate({"sale_id": str(sale.id)}))
