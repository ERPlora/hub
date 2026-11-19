"""hub#668 (FLOW-F11, F28, F31): an amount an event brings — ``{{input.total}}`` after a sale is charged — reached
«Waiting for your answer» and the customer's WhatsApp in cents («Total: 12050»), since an event said nothing about its
data. Each app now names, beside its events, the data they bring that are amounts (``events.AMOUNTS``): a text a person
reads says them as money, in the currency the event brings beside them, else the business's. What goes to a machine
keeps the figure, and a number no app declares is still said as it is. The net below reads every event an app records
and fails on an amount one brings that its app does not declare.
"""

import ast
import datetime as dt
import json
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
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


def _keys(node: ast.Dict) -> tuple[set[str], set[str]]:
    """The names a dict written in the code gives and the ``**name`` it spreads."""
    names = {key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}
    spread = {value.id for key, value in zip(node.keys, node.values) if key is None and isinstance(value, ast.Name)}
    return names, spread


def _functions(trees: list[ast.Module]) -> list[ast.FunctionDef]:
    return [node for tree in trees for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]


def _built(payload: ast.expr, local: dict[str, ast.expr], returned: dict[str, set[str]]) -> ast.Dict | set[str]:
    """What a payload is: a dict written in the call or in a variable of its function, or the names a function of the
    app returns in a dict."""
    payload = local.get(payload.id, payload) if isinstance(payload, ast.Name) else payload
    if isinstance(payload, ast.Call) and isinstance(payload.func, ast.Name):
        return returned.get(payload.func.id, set())
    return payload if isinstance(payload, ast.Dict) else set()


def recorded_data(source: list[str]) -> set[str]:
    """The names of the data the events of an app's code (``source``) bring, as it writes them: a dict written in the
    ``record_event`` call, in a variable of its function or returned by a function of the app, and the keywords a
    function that adds them to its event (``**more``) is called with. What the code builds otherwise is not seen."""
    functions = _functions([ast.parse(text) for text in source])
    returned: dict[str, set[str]] = {}
    for function in functions:
        for node in ast.walk(function):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                returned.setdefault(function.name, set()).update(_keys(node.value)[0])
    names: set[str] = set()
    spreading: set[str] = set()
    for function in functions:
        local = {
            node.targets[0].id: node.value
            for node in ast.walk(function)
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        }
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "record_event" and len(node.args) > 2:
                built = _built(node.args[2], local, returned)
                given, spread = _keys(built) if isinstance(built, ast.Dict) else (built, set())
                names |= given
                if function.args.kwarg is not None and function.args.kwarg.arg in spread:
                    spreading.add(function.name)
    for function in functions:
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in spreading:
                names |= {keyword.arg for keyword in node.keywords if keyword.arg}
    return names


def _source(path: Path) -> list[str]:
    """The code of a module, without its tests nor its migrations."""
    return [
        file.read_text()
        for file in sorted(path.rglob("*.py"))
        if not {"tests", "migrations"} & set(file.relative_to(path).parts)
    ]


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
        brought = recorded_data(_source(Path(config.path)))
        amounts = {
            name
            for name in brought
            if name.endswith("_cents") or name in money.get(label, ()) or name in AMOUNTS_BY_NAME.get(label, ())
        }
        if missing := sorted(amounts - event_amounts(f"{label}.any.event")):
            found[label] = missing
    assert found == UNDECLARED_EVENT_AMOUNTS


def test_every_amount_an_app_declares_is_one_its_events_bring():
    """A declared name no event of its app brings is a slip of the pen (``totl``), or an amount the app stopped sending."""
    for config in module_configs():
        declared = event_amounts(f"{config.label}.any.event")
        assert declared <= recorded_data(_source(Path(config.path))), config.label


ADDED = '''
def _line(line):
    return {"line_id": str(line.id), "unit_price": line.price}

def _event(ctx, name, sale, **more):
    record_event(ctx, name, {"id": str(sale.id), **more})

def charge(ctx, sale, line):
    record_event(ctx, "x.sale.charged", {"total": sale.total, "count": 2})
    payload = {"tip": sale.tip}
    record_event(ctx, "x.sale.tipped", payload)
    record_event(ctx, "x.line.added", _line(line))
    _event(ctx, "x.sale.voided", sale, refunded=sale.refunded)
'''


def test_the_net_sees_a_payload_written_in_the_call_in_a_variable_by_a_function_or_by_keywords():
    assert recorded_data([ADDED]) == {"total", "count", "tip", "line_id", "unit_price", "id", "refunded"}
