"""hub#498 (FLOW-F28, F31): an amount a step leaves (``{{steps.<id>.<field>}}``) is money in a text a person reads
when the schema of that step's answer marks it so (``json_schema_extra={"money": True}``), as the assistant's card
reads an amount (BASE-F97). Automations knew one only by its words — a name in ``_cents``, «in cents» in its
description —, so the amount of a payment a step records («in minor units of its currency») reached «Waiting for your
answer» as «1250». Every amount a step leaves that says cents in its name or its description now carries its mark (the
ratchet below, whose net is those words), and nothing Automations said as money by its words stops being so. An amount
whose schema says nothing (a service's price, an invoice's total) is still unmarked and outside the ratchet (hub#923).
"""

import datetime as dt
import re
from zoneinfo import ZoneInfo

import pytest
from live.operations import Operation, registry

from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries import _money_paths, step_fields
from apps.payment.tests.conftest import make_method

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


# ── The ratchet: amounts a step leaves that nobody marks, by app ─────────────────────────────────────────────────────

#: How an amount says itself in this repo's schemas, as the assistant's ratchet reads it
#: (``base/tests/test_assistant_card_values.py``): a whole number named ``…_cents``, or whose description speaks of
#: cents or of the minor unit. The words find the amounts to mark; they never make one.
AMOUNT_WORDS = re.compile(r"\bcents?\b|\bminor units?\b|\bcéntimos?\b", re.IGNORECASE)

#: The decimals of a currency say «its amounts' minor unit»: a count, never an amount.
NO_AMOUNT = frozenset({"currency_decimals"})

#: The amounts a step leaves that no mark declares, by app: Automations says them as a bare figure. Only ever lower:
#: an app that marks its own lowers its number here, and none comes in. A cart's line and a price list's rule answer
#: no currency of their own (their cart's, their list's), so marked they would be said in the business's.
UNMARKED_STEP_AMOUNTS: dict[str, int] = {"cart_checkout": 4, "pricing": 6}


def looks_like_an_amount(name: str, prop: dict) -> bool:
    return (
        name not in NO_AMOUNT
        and _type(prop) == "integer"
        and (name.endswith("_cents") or bool(AMOUNT_WORDS.search(str(prop.get("description", "")))))
    )


def _type(prop: dict) -> str | None:
    """The type of ``prop``: its own, or that of the branch of its union that is not ``null``."""
    return prop.get("type") or next((b.get("type") for b in prop.get("anyOf", []) if b.get("type") != "null"), None)


def steps() -> list[Operation]:
    """Every operation a step can name: a write or a read."""
    return [op for _, op in sorted(registry.items()) if op.kind in ("command", "query")]


def unmarked_amounts(op: Operation) -> list[str]:
    return [name for name, prop in step_fields(op).items() if looks_like_an_amount(name, prop) and prop.get("money") is not True]


def amounts_by_app(operations: list[Operation]) -> dict[str, int]:
    counted: dict[str, int] = {}
    for op in operations:
        if found := unmarked_amounts(op):
            counted[op.app_label] = counted.get(op.app_label, 0) + len(found)
    return dict(sorted(counted.items()))


def test_every_amount_a_step_leaves_is_marked_but_the_known_ones():
    """A new amount a step leaves without its mark — or one whose mark is lost while its words say cents — fails here;
    an app that marks its own lowers its number."""
    assert amounts_by_app(steps()) == UNMARKED_STEP_AMOUNTS


def test_no_amount_automations_said_as_money_stops_being_one():
    """What Automations said as money by its words before (a whole number named ``_cents`` or described «in cents»)
    carries the mark now, every one of them."""

    def by_words(name: str, prop: dict) -> bool:
        return _type(prop) == "integer" and (name.endswith("_cents") or "in cents" in str(prop.get("description", "")).lower())

    said = {(op.name, name) for op in steps() for name, prop in step_fields(op).items() if by_words(name, prop)}
    marked = {(op.name, name) for op in steps() for name, prop in step_fields(op).items() if prop.get("money") is True}
    assert len(said) > 200
    assert sorted(said - marked) == []
