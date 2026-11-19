"""hub#668 (FLOW-F11, F28, F31): an amount an event brings — ``{{input.total}}`` after a sale is charged — reached
«Waiting for your answer» and the customer's WhatsApp in cents («Total: 12050»), since an event said nothing about its
data. Each app now names, beside its events, the data they bring that are amounts (``events.AMOUNTS``): a text a person
reads says them as money, in the currency the event brings beside them, else the business's. What goes to a machine
keeps the figure, and a number no app declares is still said as it is. The net below reads every event an app records
and fails on an amount one brings that its app does not declare.
"""

import datetime as dt
import json
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps
from live.context import system_context
from live.meta import module_configs
from live.models import OutboxEvent

from apps.cart_checkout.tests.conftest import make_cart
from apps.flow.models import FlowRun, Question
from apps.flow.queries.catalog import event_amounts
from apps.pricing.tests.conftest import make_list, make_product
from apps.task.models import Task
from apps.whatsapp_inbox.models import Message

from .conftest import A, HUB_DB, TASK_STEP, ctx_for, make_flow, run
from .test_field_words import PayloadReader, services_source
from .test_step_amounts import AMOUNTS_BY_NAME, money_names, steps

pytestmark = HUB_DB

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
CHARGED = "sale.sale.completed"
NOTIFY = "whatsapp_inbox.message.notify"
#: What a charge brings, as the till records it: its total in cents of its currency, and numbers that are no amount.
SALE = {"sale_number": "T-0042", "total": 12050, "currency": "EUR", "items_count": 3, "phone": "+34600111222"}


def ask(title: str) -> dict:
    return {"id": "s1", "kind": "ask", "title": title}


def notify(text: str) -> dict:
    return {"id": "s1", "kind": "command", "operation": NOTIFY, "params": {"phone": "input.phone", "text": text}}


def charged(steps: list, payload: dict = SALE, grants: tuple = ()) -> FlowRun:
    """The run an automation on a charge starts when the relay hands it a ``sale.sale.completed`` with ``payload``."""
    flow = make_flow(trigger_event=CHARGED, steps=steps, grants=list(grants), language="es")
    started = run("flow.run.react", {"event_id": str(uuid.uuid4()), "event": CHARGED, "payload": payload}, system_context(A))
    assert started.started == 1, started
    return FlowRun.objects.get(flow=flow)


def test_the_question_after_a_charge_says_its_total_as_money(clock):
    clock(NOON)
    asked = charged([ask("Refund {{input.sale_number}}? Total {{input.total}} · {{input.items_count}} items")])
    assert Question.objects.get(run_id=asked.id).title == "Refund T-0042? Total 120,50\xa0€ · 3 items"


@pytest.mark.parametrize(
    ("currency", "said"), [("USD", "120,50\xa0US$"), ("JPY", "12.050\xa0JPY"), (None, "120,50\xa0€")],
    ids=["dollars", "yen, without decimals", "none: the business's"],
)
def test_an_amount_of_an_event_is_said_in_the_currency_it_brings(clock, currency, said):
    clock(NOON)
    payload = {**SALE, "currency": currency} if currency else {k: v for k, v in SALE.items() if k != "currency"}
    asked = charged([ask("Total {{input.total}}")], payload)
    assert Question.objects.get(run_id=asked.id).title == f"Total {said}"


def test_a_whatsapp_after_a_charge_says_its_total_as_money(chatting):
    done = charged([notify("Thanks! Your ticket {{input.sale_number}}: {{input.total}}.")], grants=(NOTIFY,))
    assert done.status == FlowRun.Status.SUCCEEDED, done.error
    assert Message.objects.get(direction="outbound").body == "Thanks! Your ticket T-0042: 120,50\xa0€."


def test_what_an_event_brings_reaches_another_action_as_it_is():
    done = charged([{**TASK_STEP, "params": {"title": "Charged {{input.total}}"}}], grants=("task.task.create",))
    assert done.status == FlowRun.Status.SUCCEEDED, done.error
    assert Task.objects.get().title == "Charged 12050"


def test_trying_it_says_the_total_of_the_last_charge_as_money(clock):
    clock(NOON)
    OutboxEvent.objects.create(scope_kind=A.kind, scope_key=A.key, name=CHARGED, payload=SALE)
    document = {"trigger": {"kind": "event", "event": CHARGED}, "steps": [ask("Total {{input.total}}")]}
    [step] = run("flow.flow.test", {"document": json.dumps(document)}, ctx_for(language="es")).steps
    assert step.params["title"] == "Total 120,50\xa0€"


def asked_when(event: str, title: str, write: str, params: dict) -> str:
    """The question an automation on ``event`` asks once ``write`` with ``params`` records it, as the relay hands it."""
    make_flow(trigger_event=event, steps=[ask(title)], grants=[], language="es")
    run(write, params)
    notice = OutboxEvent.objects.get(name=event)
    run("flow.run.react", {"event_id": str(notice.id), "event": event, "payload": notice.payload}, system_context(A))
    return Question.objects.get().title


def test_a_price_put_in_a_list_in_dollars_is_said_in_dollars(clock):
    clock(NOON)
    make_list("VIP", currency="USD")
    make_product("Shampoo", "SH-1")
    price = {"price_list": "VIP", "product": "SH-1", "price": 1250}
    assert asked_when("pricing.price_item.added", "New: {{input.price}}", "pricing.price_item.add", price) == "New: 12,50\xa0US$"


def test_a_line_added_to_a_cart_in_dollars_is_said_in_dollars(clock):
    clock(NOON)
    cart = make_cart("sess_668", currency="USD")
    line = {"cart_id": str(cart.id), "product_ref": "p-1", "product_name": "Champú", "quantity": "2", "unit_price": 1250}
    assert asked_when("cart_checkout.item.added", "Line: {{input.line_total}}", "cart_checkout.item.add", line) == "Line: 25,00\xa0US$"


def test_an_amount_one_app_declares_is_no_amount_in_another_s_event():
    # «total» is a sale's amount; in an event of an app that declares none it may be a count, and is never guessed.
    assert "total" in event_amounts(CHARGED)
    assert event_amounts("task.task.created") == frozenset()
    assert event_amounts("nobody.thing.happened") == frozenset()


# ── The net: every amount an event brings is declared ───────────────────────────────────────────────────────────────


def brought(path: str) -> set[str]:
    """The data the events of the app at ``path`` bring, as its writes build them (``PayloadReader``, which fails on a
    payload it cannot follow in ``test_field_words.py``), nested ones by their dotted path."""
    source, name = services_source(Path(path))
    return set(PayloadReader(source, name).keys) if source else set()


#: The amounts an app's events bring that it does not declare, by app: Automations says them as a bare figure. Only ever
#: lower: none comes in.
UNDECLARED_EVENT_AMOUNTS: dict[str, list[str]] = {}


def test_every_amount_an_event_brings_is_declared_by_its_app():
    """An amount an event brings — a name its app marks as money in what its operations take or answer, one in
    ``_cents`` or one ``AMOUNTS_BY_NAME`` names — that its app does not declare fails here."""
    money = money_names(steps())
    found: dict[str, list[str]] = {}
    for config in module_configs():
        label = config.label
        named = money.get(label, frozenset()) | AMOUNTS_BY_NAME.get(label, frozenset())
        amounts = {key for key in brought(config.path) if key.endswith("_cents") or key.rsplit(".", 1)[-1] in named}
        if missing := sorted(amounts - event_amounts(f"{label}.any.event")):
            found[label] = missing
    assert found == UNDECLARED_EVENT_AMOUNTS


def test_every_amount_an_app_declares_is_one_its_events_bring():
    """A declared name no event of its app brings is a slip of the pen (``totl``), or an amount the app stopped sending."""
    for config in module_configs():
        assert event_amounts(f"{config.label}.any.event") <= brought(config.path), config.label


def test_the_net_sees_the_amounts_of_a_sale_and_of_a_till():
    # Positive control: what a charge and a till session bring is read.
    assert {"total", "subtotal", "tax_amount", "currency"} <= brought(apps.get_app_config("sale").path)
    assert {"opening_balance", "difference"} <= brought(apps.get_app_config("cash_register").path)
