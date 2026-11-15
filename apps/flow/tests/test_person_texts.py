"""The data an automation inserts (``{{…}}``) in a text a person reads (FLOW-F28, F29, F31): the question of «Ask
someone first» and the WhatsApp of «Send a message». In a text for a person each datum is said as the assistant's card
says it (BASE-F97): a yes or no as «Yes»/«No», a day and a time as the automation's language writes them at the
business's hour, and an amount the schema of the step that left it marks as money (``"money": true``) in the currency
that step answers, else the business's. What goes to a machine — another action's data, a call to another system, a
condition — keeps each datum as it is.

An event declares no schema: a number it brings is said as it is, never guessed as money. Nor are a description's words
(«in cents») nor a name in ``_cents``: only the mark says an amount (hub#498, as the assistant's card, BASE-F97).
"""

import dataclasses
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from live.context import system_context
from live.models import OutboxEvent
from live.operations import Operation, registry
from ninja import Field, Schema

from apps.cart_checkout.tests.conftest import make_cart
from apps.flow.models import Flow, FlowRun, Question
from apps.task.models import Task
from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import connect, receive
from base.models import Hub

from .conftest import A, ctx_for, make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
NOTIFY = "whatsapp_inbox.message.notify"
PREVIEW = "sale.checkout.preview"
ADD = "cart_checkout.item.add"
#: What a run brings: a yes or no, an instant, a day, an hour, an undeclared number and a phone.
INPUT = {
    "name": "Ana",
    "paid": True,
    "at": "2026-11-02T10:00:00+01:00",
    "day": "2026-11-02",
    "hour": "21:30:00",
    "total": 12050,
    "phone": "+34600111222",
}


class QuoteIn(Schema):
    pass


#: The mark of an amount (``json_schema_extra={"money": True}``): a whole number in the minor unit of its currency.
MONEY = {"money": True}


class QuoteOut(Schema):
    """A read whose answer marks an amount as money, as an app's schema does; neither its name nor its words say so."""

    title: str
    total: int = Field(description="What it costs.", json_schema_extra=MONEY)


#: A read of an app that is on (Tasks), granted to the automation like any other.
QUOTE = Operation(
    name="task.task.quote",
    kind="query",
    permission="task.view",
    input=QuoteIn,
    output=QuoteOut,
    expose_api=False,
    ai={"description": "Quotes a chore."},
    fn=lambda ctx, data: {"title": "Cut", "total": 12050},
)
QUOTE_STEP = {"id": "s0", "kind": "query", "operation": QUOTE.name, "params": {}}


@pytest.fixture(autouse=True)
def quote(monkeypatch):
    monkeypatch.setitem(registry, QUOTE.name, QUOTE)


def quoting(monkeypatch, output: type[Schema], answer: dict) -> None:
    """The read of ``QUOTE_STEP`` answers ``answer`` as ``output`` declares it."""
    monkeypatch.setitem(registry, QUOTE.name, dataclasses.replace(QUOTE, output=output, fn=lambda ctx, data: answer))


def tried(steps: list, language: str = "es") -> list:
    """«Try it» (FLOW-F13) on ``steps`` started by the last real ``customer.customer.created``, which brought
    ``INPUT``, as someone who reads ``language``: what each step would do."""
    OutboxEvent.objects.create(scope_kind=A.kind, scope_key=A.key, name="customer.customer.created", payload=INPUT)
    document = {"trigger": {"kind": "event", "event": "customer.customer.created"}, "steps": steps}
    return run("flow.flow.test", {"document": json.dumps(document)}, ctx_for(language=language)).steps


def ask(**texts) -> dict:
    return {"id": "s1", "kind": "ask", "title": "Refund?", **texts}


def asked(steps: list, language: str = "en", grants=(QUOTE.name,)) -> Question:
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=list(grants), language=language)
    ran = run("flow.flow.run", {"id": str(flow.id), "input": INPUT})
    assert ran.status == FlowRun.Status.ASKING, ran
    return Question.objects.get(run_id=ran.id)


# ── «Ask someone first»: the question and its details (FLOW-F28, F29) ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("language", "title", "details"),
    [
        ("en", "Refund Ana? Paid: Yes", "Bought Nov 2, 2026, 10:00 AM · Nov 2, 2026 at 9:30 PM"),
        ("es", "Refund Ana? Paid: Sí", "Bought 2 nov 2026, 10:00 · 2 nov 2026 at 21:30"),
    ],
)
def test_a_question_says_a_yes_or_no_and_a_moment_as_its_language_writes_them(clock, language, title, details):
    clock(NOON)
    question = asked(
        [ask(title="Refund {{input.name}}? Paid: {{input.paid}}", details="Bought {{input.at}} · {{input.day}} at {{input.hour}}")],
        language,
    )
    assert (question.title, question.details) == (title, details)


def test_a_no_is_said_as_no(clock):
    clock(NOON)
    question = asked([ask(title="Paid: {{input.paid}}")], "es")
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[ask(title="Paid: {{input.paid}}")], language="es")
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {**INPUT, "paid": False}})
    assert (question.title, Question.objects.get(run_id=ran.id).title) == ("Paid: Sí", "Paid: No")


def test_an_amount_a_step_marks_is_said_in_the_businesss_currency(clock):
    clock(NOON)
    question = asked([QUOTE_STEP, ask(title="Refund {{steps.s0.total}}?", details="{{steps.s0.title}}")], "es")
    assert (question.title, question.details) == ("Refund 120,50\xa0€?", "Cut")


class WordsOnlyOut(Schema):
    title: str
    total: int = Field(description="What it costs, in cents (minor units of the business's currency).")


class NameOnlyOut(Schema):
    title: str
    total_cents: int


@pytest.mark.parametrize(
    ("output", "field"), [(WordsOnlyOut, "total"), (NameOnlyOut, "total_cents")], ids=["its words", "its name"]
)
def test_neither_words_nor_a_name_make_an_amount_only_the_mark_does(clock, monkeypatch, output, field):
    # hub#498: Automations knew an amount only by the words of its description («in cents») or a name in ``_cents``,
    # so a payment's («in minor units of its currency») stayed «1250». As the assistant's card, only the mark counts.
    clock(NOON)
    quoting(monkeypatch, output, {"title": "Cut", field: 12050})
    question = asked([QUOTE_STEP, ask(title=f"Refund {{{{steps.s0.{field}}}}}?")], "es")
    assert question.title == "Refund 12050?"


class PricedQuoteOut(QuoteOut):
    currency: str = Field(description="Its currency (ISO 4217).")


@pytest.mark.parametrize(
    ("currency", "said"), [("USD", "120,50\xa0US$"), ("JPY", "12.050\xa0JPY"), ("", "120,50\xa0€")],
    ids=["dollars", "yen, without decimals", "none: the business's"],
)
def test_an_amount_is_said_in_the_currency_its_step_answers(clock, monkeypatch, currency, said):
    # A payment in dollars of a business in euros is not «120,50 €»: as the assistant's card says an amount of a read
    # (BASE-F98), in the currency the step's answer gives, else in the business's.
    clock(NOON)
    quoting(monkeypatch, PricedQuoteOut, {"title": "Cut", "total": 12050, "currency": currency})
    question = asked([QUOTE_STEP, ask(title="Refund {{steps.s0.total}}?")], "es")
    assert question.title == f"Refund {said}?"


def test_a_number_nobody_declares_money_is_said_as_it_is(clock):
    # An event declares no schema: «12050» may be cents, a count or a code; it is never guessed. Nor is a text that is
    # no ISO day, hour or instant read as one.
    clock(NOON)
    question = asked([ask(title="Total {{input.total}} · {{input.name}} · 2026")], "es")
    assert question.title == "Total 12050 · Ana · 2026"


def test_a_text_an_app_already_wrote_for_a_person_is_left_as_it_is(clock):
    # «21:00» is how an app writes an hour for a person (a reservation's notice): only the hour JSON gives («21:00:00»)
    # is read as one, as only its day («2026-11-02») and its instant («…T10:00…»).
    clock(NOON)
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[ask(title="At {{input.hour}} on {{input.when}}")])
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {**INPUT, "hour": "21:00", "when": "Monday, Nov. 9, 2026"}})
    assert Question.objects.get(run_id=ran.id).title == "At 21:00 on Monday, Nov. 9, 2026"


def test_trying_it_says_the_question_as_it_will_be_asked(clock):
    clock(NOON)
    [step] = tried([ask(title="Paid: {{input.paid}}", details="Bought {{input.at}}")])
    assert (step.params["title"], step.params["details"]) == ("Paid: Sí", "Bought 2 nov 2026, 10:00")


# ── «Send a message to a customer» (FLOW-F31) ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def chatting(settings):
    """A WhatsApp conversation with Ana that wrote ten minutes ago: a text goes as it is."""
    settings.SAAS_INTERNAL_URL = "http://saas.test"
    settings.INTERNAL_SHARED_SECRET = "s3cret"
    connect()
    receive("wamid.IN", sent_at=(timezone.now() - dt.timedelta(minutes=10)).isoformat())


def test_a_whatsapp_to_a_customer_says_each_datum_in_words(chatting):
    text = "Paid: {{input.paid}}. Your visit: {{input.at}}. Total: {{steps.s0.total}}."
    notify = {"id": "s1", "kind": "command", "operation": NOTIFY, "params": {"phone": "input.phone", "text": text}}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[QUOTE_STEP, notify], grants=[QUOTE.name, NOTIFY], language="es")
    done = run("flow.flow.run", {"id": str(flow.id), "input": INPUT})
    assert done.status == FlowRun.Status.SUCCEEDED, done
    body = Message.objects.get(direction="outbound").body
    assert body == "Paid: Sí. Your visit: 2 nov 2026, 10:00. Total: 120,50\xa0€."


def test_a_whatsapp_to_a_customer_says_an_amount_in_the_currency_its_step_answers(chatting, monkeypatch):
    # As the question (FLOW-F28): a total in dollars of a business in euros does not reach the customer as «120,50 €».
    quoting(monkeypatch, PricedQuoteOut, {"title": "Cut", "total": 12050, "currency": "USD"})
    notify = {"id": "s1", "kind": "command", "operation": NOTIFY, "params": {"phone": "input.phone", "text": "Total: {{steps.s0.total}}."}}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[QUOTE_STEP, notify], grants=[QUOTE.name, NOTIFY], language="es")
    done = run("flow.flow.run", {"id": str(flow.id), "input": INPUT})
    assert done.status == FlowRun.Status.SUCCEEDED, done
    assert Message.objects.get(direction="outbound").body == "Total: 120,50\xa0US$."


def test_a_whatsapp_to_a_customer_says_a_charge_s_legal_limit_in_euros_in_a_business_in_yen(chatting):
    # hub#926: as the question (FLOW-F28), a charge preview's cash limit reaches the customer in the euros the law
    # writes it in, never as «100000» nor in the business's yen; its total, in yen.
    Hub.objects.filter(slug=A.key).update(country="JP")
    coffee = {"name": "Coffee", "sku": "COF", "price": 1250, "tax_category_key": "product.generic"}
    run("inventory.product.create", coffee, system_context(A))
    check = run("sale.order.open", {"lines": [{"product": "COF"}]}, system_context(A))
    preview = {"id": "s0", "kind": "query", "operation": PREVIEW, "params": {"order_id": str(check.id)}}
    text = "No cash from {{steps.s0.cash_limit}}. Total: {{steps.s0.total}}."
    notify = {"id": "s1", "kind": "command", "operation": NOTIFY, "params": {"phone": "input.phone", "text": text}}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[preview, notify], grants=[PREVIEW, NOTIFY], language="es")
    done = run("flow.flow.run", {"id": str(flow.id), "input": INPUT})
    assert done.status == FlowRun.Status.SUCCEEDED, (done.error_code, done.error_message)
    assert Message.objects.get(direction="outbound").body == "No cash from 1.000,00\xa0€. Total: 1.250\xa0JPY."


def test_a_whatsapp_to_a_customer_says_the_amounts_inside_a_cart_s_line_in_its_cart_s_currency(chatting):
    # hub#941: the line a step adds to a cart and the cart after it carry their amounts inside (``item``, ``cart``):
    # they reached the customer as «2500»; in a business in yen, a cart in dollars says them in dollars.
    Hub.objects.filter(slug=A.key).update(country="JP")
    cart = make_cart("sess_941", currency="USD")
    line = {"cart_id": str(cart.id), "product_ref": "p-1", "product_name": "Champú", "quantity": "2", "unit_price": 1250}
    add = {"id": "s0", "kind": "command", "operation": ADD, "params": line}
    text = "{{steps.s0.item.product_name}}: {{steps.s0.item.line_total}}. Cart: {{steps.s0.cart.total_amount}}."
    notify = {"id": "s1", "kind": "command", "operation": NOTIFY, "params": {"phone": "input.phone", "text": text}}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[add, notify], grants=[ADD, NOTIFY], language="es")
    done = run("flow.flow.run", {"id": str(flow.id), "input": INPUT})
    assert done.status == FlowRun.Status.SUCCEEDED, (done.error_code, done.error_message)
    assert Message.objects.get(direction="outbound").body == "Champú: 25,00\xa0US$. Cart: 25,00\xa0US$."


def test_trying_a_whatsapp_says_it_as_it_will_go():
    notify = {"id": "s1", "kind": "command", "operation": NOTIFY, "params": {"phone": "input.phone", "text": "Paid: {{input.paid}}"}}
    [step] = tried([notify])
    assert step.params == {"phone": "+34600111222", "text": "Paid: Sí"}


# ── What goes to a machine keeps each datum as it is ──────────────────────────────────────────────────────────────────


def test_another_actions_data_keep_each_datum_as_it_is(clock):
    clock(NOON)
    create = {
        "id": "s1",
        "kind": "command",
        "operation": "task.task.create",
        "params": {"title": "{{input.paid}} {{input.at}} {{steps.s0.total}}"},
    }
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[QUOTE_STEP, create], grants=[QUOTE.name, "task.task.create"], language="es")
    done = run("flow.flow.run", {"id": str(flow.id), "input": INPUT})
    assert done.status == FlowRun.Status.SUCCEEDED, done
    assert Task.objects.get().title == "true 2026-11-02T10:00:00+01:00 12050"


def test_a_call_to_another_system_and_a_condition_keep_each_datum_as_it_is(clock):
    clock(NOON)
    call = {
        "id": "s1",
        "kind": "http",
        "method": "POST",
        "url": "https://api.example.com/hook",
        "body": json.dumps({"paid": "{{input.paid}}", "at": "{{input.at}}", "total": "{{input.total}}"}),
        "run_if": {"input.paid": {"eq": True}},
    }
    [step] = tried([call])
    assert step.outcome in ("would_call", "not_allowed")
    assert json.loads(step.params["body"]) == {"paid": "true", "at": "2026-11-02T10:00:00+01:00", "total": "12050"}
