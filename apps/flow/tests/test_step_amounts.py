"""hub#498 (FLOW-F28, F31): an amount a step leaves (``{{steps.<id>.<field>}}``) is money in a text a person reads
when the schema of that step's answer marks it so (``json_schema_extra={"money": True}``), as the assistant's card
reads an amount (BASE-F97). Automations knew one only by its words — a name in ``_cents``, «in cents» in its
description —, so the amount of a payment a step records («in minor units of its currency») reached «Waiting for your
answer» as «1250». Every amount a step leaves that says cents in its name or its description now carries its mark (the
ratchet below), and nothing Automations said as money by its words stops being so. hub#923: the amounts whose words
say nothing (a service's or a menu's price, an invoice's total, a check's provisional total, a voucher's amount, a
cash movement's signed amount) carry it too, and the ratchet's net is the schemas themselves, not only those words.
hub#915: a cart's line, a price of a list and a rule's amount per unit carry it as well, beside the currency each is in.
"""

import datetime as dt
import re
from decimal import Decimal
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid7
from zoneinfo import ZoneInfo

import pytest
from live.operations import Operation, registry
from ninja import Field, Schema

from apps.cart_checkout.tests.conftest import make_cart
from apps.cart_checkout.tests.conftest import make_item as make_cart_line
from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries import _money_paths, step_fields
from apps.payment.tests.conftest import make_method
from apps.pricing.tests.conftest import make_item as make_price
from apps.pricing.tests.conftest import make_list, make_rule
from apps.service.tests.conftest import make_tax

from .conftest import make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
RECORD = "payment.payment.create"


def paid(currency: str | None = None) -> Question:
    """«Ask someone first» after a step that records a payment of 12.50 (in ``currency``, else the business's)."""
    method = make_method()
    payment = {
        "method_id": str(method.id),
        "payment_date": "2026-10-15",
        "amount": 1250,
        "beneficiary_name": "Proveedor Norte SL",
        **({"currency": currency} if currency else {}),
    }
    steps = [
        {"id": "s1", "kind": "command", "operation": RECORD, "params": payment},
        {"id": "s2", "kind": "ask", "title": "Paid {{steps.s1.amount}} to {{steps.s1.beneficiary_name}}?"},
    ]
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=[RECORD], language="es")
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    assert ran.status == FlowRun.Status.ASKING, ran
    return Question.objects.get(run_id=ran.id)


def test_a_step_that_records_a_payment_leaves_its_amount_as_money():
    assert _money_paths([{"id": "s1", "kind": "command", "operation": RECORD}]) == {"steps.s1.amount"}


@pytest.mark.parametrize(
    ("currency", "said"), [(None, "12,50\xa0€"), ("USD", "12,50\xa0US$")], ids=["the business's", "dollars"]
)
def test_the_question_after_a_payment_says_its_amount_in_its_currency(clock, currency, said):
    clock(NOON)
    assert paid(currency).title == f"Paid {said} to Proveedor Norte SL?"


#: The amounts of hub#923 a step leaves, by the operation that leaves them: their words never said cents.
UNSPOKEN_AMOUNTS = {
    "invoice.invoice.create": {"base_amount", "tax_amount", "total_amount"},
    "service.service.create": {"price", "cost", "min_price", "max_price"},
    "service.service.list_for_sale": {"price", "min_price", "max_price"},
    "service.assignment.assign": {"price", "custom_price"},
    "service.assignment.eligible": {"price", "custom_price"},
    "service.package.create": {"fixed_price", "discount_amount"},
    "service.grant.adjust": {"amount", "net_amount", "tax_amount"},
    "service.grant.list_orphans": {"amount"},
    "combo.combo.create": {"price"},
    "combo.combo.for_sale": {"price"},
    "combo.option.create": {"price_delta"},
    "combo.combo.resolve": {"amount"},
    "sale.order.add_combo_line": {"provisional_total"},
    "sale.refund.options": {"total", "refunded_total", "refundable_total"},
    "cash_register.movement.add": {"signed_amount"},
}


@pytest.mark.parametrize("operation", sorted(UNSPOKEN_AMOUNTS))
def test_an_amount_whose_words_say_nothing_is_money_all_the_same(operation):
    """hub#923: an invoice's total, a service's or a menu's price, a check's provisional total, a voucher's amount and a
    cash movement's signed amount reached a question or a WhatsApp as «12100»: their schema did not mark them."""
    paths = _money_paths([{"id": "s1", "kind": "command", "operation": operation}])
    assert {f"steps.s1.{name}" for name in UNSPOKEN_AMOUNTS[operation]} <= paths


def test_the_question_after_a_step_that_creates_a_service_says_its_price_as_money(clock):
    clock(NOON)
    create = "service.service.create"
    tax = make_tax()
    service = {"name": "Corte", "price": 12100, "tax_category_key": tax.key}
    steps = [
        {"id": "s1", "kind": "command", "operation": create, "params": service},
        {"id": "s2", "kind": "ask", "title": "{{steps.s1.name}} costs {{steps.s1.price}}?"},
    ]
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=[create], language="es")
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    assert ran.status == FlowRun.Status.ASKING, (ran.error_code, ran.error_message)
    assert Question.objects.get(run_id=ran.id).title == "Corte costs 121,00\xa0€?"


#: The amounts of hub#915 a step leaves, by the operation that leaves them, and the currency it answers beside them:
#: a cart's line in its cart's, a price in its list's, a rule's amount per unit in the business's (a rule belongs to
#: no list). Marked without it, an amount in another currency would be said in the business's.
AMOUNTS_IN_THEIR_CURRENCY = {
    "cart_checkout.item.get": {"unit_price", "line_total"},
    "cart_checkout.item.list": {"unit_price", "line_total"},
    "pricing.price_item.add": {"base_price", "price"},
    "pricing.price_item.update": {"base_price", "price"},
    "pricing.price_item.list": {"base_price", "price"},
    **{f"pricing.rule.{action}": {"amount"} for action in ("create", "update", "get", "list", "activate", "deactivate")},
}


def test_a_cart_line_and_a_price_list_rule_leave_their_amounts_as_money():
    """hub#915, its «How to reproduce»: a read of a cart's line and of a rule left no amount as money."""
    steps = [
        {"id": "s1", "kind": "query", "operation": "cart_checkout.item.get"},
        {"id": "s2", "kind": "query", "operation": "pricing.rule.get"},
    ]
    assert _money_paths(steps) == {"steps.s1.unit_price", "steps.s1.line_total", "steps.s2.amount"}


@pytest.mark.parametrize("operation", sorted(AMOUNTS_IN_THEIR_CURRENCY))
def test_a_line_a_price_and_a_rule_leave_their_amounts_with_their_currency(operation):
    """hub#915: each amount is marked, and the step answers the currency it is in (``_answered_currency``)."""
    paths = _money_paths([{"id": "s1", "kind": "command", "operation": operation}])
    assert {f"steps.s1.{name}" for name in AMOUNTS_IN_THEIR_CURRENCY[operation]} <= paths
    assert step_fields(registry[operation]).get("currency", {}).get("type") == "string"


def asked_after(read: str, params: dict, title: str) -> str:
    """The question «Ask someone first» puts after a step that reads ``read`` with ``params``, in Spanish."""
    steps = [
        {"id": "s1", "kind": "query", "operation": read, "params": params},
        {"id": "s2", "kind": "ask", "title": title},
    ]
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=[read], language="es")
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    assert ran.status == FlowRun.Status.ASKING, (ran.error_code, ran.error_message)
    return Question.objects.get(run_id=ran.id).title


@pytest.mark.parametrize(
    ("currency", "said"),
    [("EUR", ("12,50\xa0€", "25,00\xa0€")), ("USD", ("12,50\xa0US$", "25,00\xa0US$"))],
    ids=["the business's", "dollars"],
)
def test_the_question_after_a_cart_s_line_says_its_amounts_in_its_cart_s_currency(clock, currency, said):
    clock(NOON)
    line = make_cart_line(make_cart("sess_915", currency=currency), unit_price=1250, quantity=Decimal("2"))
    said_line = "{{steps.s1.unit_price}} × 2 = {{steps.s1.line_total}}?"
    title = asked_after("cart_checkout.item.get", {"item_id": str(line.id)}, said_line)
    assert title == f"{said[0]} × 2 = {said[1]}?"


def test_the_question_after_a_price_of_a_list_in_dollars_says_it_in_dollars(clock):
    clock(NOON)
    vip = make_list("VIP", currency="USD")
    make_price(vip, service_id=uuid7(), service_name="Corte", price=1250)
    title = asked_after("pricing.price_item.list", {"price_list": "VIP"}, "{{steps.s1.name}}: {{steps.s1.price}}?")
    assert title == "Corte: 12,50\xa0US$?"


def test_the_question_after_a_fixed_rule_says_its_amount_per_unit_as_money(clock):
    clock(NOON)
    make_rule("FIFTY", rule_type="fixed", amount=50)
    title = asked_after("pricing.rule.get", {"rule": "FIFTY"}, "{{steps.s1.code}}: {{steps.s1.amount}}?")
    assert title == "FIFTY: 0,50\xa0€?"


# ── The ratchet: amounts a step leaves that nobody marks, by app ─────────────────────────────────────────────────────

#: How an amount says itself in this repo's schemas, as the assistant's ratchet reads it
#: (``base/tests/test_assistant_card_values.py``): a whole number named ``…_cents``, or whose description speaks of
#: cents or of the minor unit. The words find the amounts to mark; they never make one.
AMOUNT_WORDS = re.compile(r"\bcents?\b|\bminor units?\b|\bcéntimos?\b", re.IGNORECASE)

#: The decimals of a currency say «its amounts' minor unit»: a count, never an amount.
NO_AMOUNT = frozenset({"currency_decimals"})

#: The amounts a step leaves whose words say nothing and whose app marks no other datum of their name, by app: no net
#: of the schemas can see them, so they are named here (hub#923). A cash movement's ``signed_amount``; a charge
#: preview's legal limits, which are in euros whatever the business's currency (``LIMITS_CURRENCY``, hub#926).
AMOUNTS_BY_NAME: dict[str, frozenset[str]] = {
    "cash_register": frozenset({"signed_amount"}),
    "sale": frozenset({"cash_limit", "ticket_limit"}),
}

#: The amounts a step leaves that no mark declares, by app: Automations says them as a bare figure. Only ever lower:
#: an app that marks its own lowers its number here, and none comes in. A charge preview's limits are in euros, not in
#: the business's currency (hub#926).
UNMARKED_STEP_AMOUNTS: dict[str, int] = {"sale": 2}


def money_names(operations: list[Operation]) -> dict[str, frozenset[str]]:
    """The names each app marks as money in any datum its operations take or answer, at any depth — on the datum or
    on a branch of its union, as ``Cents | None`` does. A name its app marks once is an amount wherever it says it."""
    found: dict[str, set[str]] = {}

    def walk(node, names: set[str]) -> None:
        if isinstance(node, dict):
            for name, prop in (node.get("properties") or {}).items():
                branches = (prop, *prop.get("anyOf", [])) if isinstance(prop, dict) else ()
                if any(branch.get("money") is True for branch in branches):
                    names.add(name)
            for inner in node.values():
                walk(inner, names)
        elif isinstance(node, list):
            for inner in node:
                walk(inner, names)

    for op in operations:
        names = found.setdefault(op.app_label, set())
        walk(op.input.model_json_schema(), names)
        walk(op.output.model_json_schema(), names)
    return {app: frozenset(names) for app, names in found.items()}


def looks_like_an_amount(app: str, name: str, prop: dict, money: dict[str, frozenset[str]]) -> bool:
    """A whole number that its words say is in cents, whose name its app marks as money elsewhere (a twin: a service's
    ``price`` answered as its form takes it) or that ``AMOUNTS_BY_NAME`` names."""
    return (
        name not in NO_AMOUNT
        and _type(prop) == "integer"
        and (
            name.endswith("_cents")
            or bool(AMOUNT_WORDS.search(str(prop.get("description", ""))))
            or name in money.get(app, frozenset())
            or name in AMOUNTS_BY_NAME.get(app, frozenset())
        )
    )


def _type(prop: dict) -> str | None:
    """The type of ``prop``: its own, or that of the branch of its union that is not ``null``."""
    return prop.get("type") or next((b.get("type") for b in prop.get("anyOf", []) if b.get("type") != "null"), None)


def steps() -> list[Operation]:
    """Every operation a step can name: a write or a read."""
    return [op for _, op in sorted(registry.items()) if op.kind in ("command", "query")]


def unmarked_amounts(op: Operation, money: dict[str, frozenset[str]]) -> list[str]:
    return [
        name
        for name, prop in step_fields(op).items()
        if looks_like_an_amount(op.app_label, name, prop, money) and prop.get("money") is not True
    ]


def amounts_by_app(operations: list[Operation], money: dict[str, frozenset[str]]) -> dict[str, int]:
    counted: dict[str, int] = {}
    for op in operations:
        if found := unmarked_amounts(op, money):
            counted[op.app_label] = counted.get(op.app_label, 0) + len(found)
    return dict(sorted(counted.items()))


def test_every_amount_a_step_leaves_is_marked_but_the_known_ones():
    """A new amount a step leaves without its mark — one whose words say cents, whose name its app marks elsewhere or
    that ``AMOUNTS_BY_NAME`` names — fails here, and so does one whose mark is lost; an app that marks its own lowers
    its number."""
    every = steps()
    assert amounts_by_app(every, money_names(every)) == UNMARKED_STEP_AMOUNTS


#: A whole number in cents as an app's input takes it (``Cents``): its mark goes on the branch of ``Cents | None``.
Cents = Annotated[int, Field(ge=0, json_schema_extra={"money": True})]


class PriceIn(Schema):
    price: Cents
    deposit: Cents | None = None


class PricedOut(Schema):
    price: int
    deposit: int | None
    signed_amount: int
    quantity: int
    total_cents: int
    marked: int = Field(json_schema_extra={"money": True})


def test_the_net_sees_an_amount_by_its_twin_or_by_name_without_any_word():
    """A whole number whose words say nothing is still an amount when its app marks its name elsewhere (here in an
    input, also on a union's branch) or names it; a count is not, and neither is one already marked."""
    op = SimpleNamespace(app_label="cash_register", kind="command", input=PriceIn, output=PricedOut)
    assert unmarked_amounts(op, money_names([op])) == ["price", "deposit", "signed_amount", "total_cents"]


def test_no_amount_automations_said_as_money_stops_being_one():
    """What Automations said as money by its words before (a whole number named ``_cents`` or described «in cents»)
    carries the mark now, every one of them."""

    def by_words(name: str, prop: dict) -> bool:
        return _type(prop) == "integer" and (name.endswith("_cents") or "in cents" in str(prop.get("description", "")).lower())

    said = {(op.name, name) for op in steps() for name, prop in step_fields(op).items() if by_words(name, prop)}
    marked = {(op.name, name) for op in steps() for name, prop in step_fields(op).items() if prop.get("money") is True}
    assert len(said) > 200
    assert sorted(said - marked) == []
