"""The data an automation inserts (``{{…}}``) in a text a person reads (FIX-HUB-FLOW-PENDING-ANSWER-CARD-SHOWS-RAW-VALUES;
FLOW-F28, F29, F31): the question of «Ask someone first» and the WhatsApp of «Send a message» said each one as the
code keeps it — «true», «2026-11-02T10:00:00+01:00», an amount in cents («12050») —, so «Waiting for your answer»
asked «Refund Ana? Paid: true» and a customer could get «Your total: 12050». In a text for a person each datum is said
as the assistant's card says it (BASE-F97): a yes or no as «Yes»/«No», a day and a time as the automation's language
writes them at the business's hour, and an amount a step declares in cents in the business's currency. What goes to a
machine — another action's data, a call to another system, a condition — keeps each datum as it is.

An event declares no schema: a number it brings is said as it is, never guessed as money.
"""

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import Operation, registry
from ninja import Schema

from apps.flow.models import Flow, FlowRun, Question
from apps.task.models import Task
from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import connect, receive

from .conftest import A, ctx_for, make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
NOTIFY = "whatsapp_inbox.message.notify"
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


class QuoteOut(Schema):
    """A read whose answer declares an amount in cents, as an app's schema does (``…_cents``)."""

    title: str
    total_cents: int


#: A read of an app that is on (Tasks), granted to the automation like any other.
QUOTE = Operation(
    name="task.task.quote",
    kind="query",
    permission="task.view",
    input=QuoteIn,
    output=QuoteOut,
    expose_api=False,
    ai={"description": "Quotes a chore."},
    fn=lambda ctx, data: {"title": "Cut", "total_cents": 12050},
)
QUOTE_STEP = {"id": "s0", "kind": "query", "operation": QUOTE.name, "params": {}}


@pytest.fixture(autouse=True)
def quote(monkeypatch):
    monkeypatch.setitem(registry, QUOTE.name, QUOTE)


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


def test_an_amount_a_step_declares_in_cents_is_said_in_the_businesss_currency(clock):
    clock(NOON)
    question = asked([QUOTE_STEP, ask(title="Refund {{steps.s0.total_cents}}?", details="{{steps.s0.title}}")], "es")
    assert (question.title, question.details) == ("Refund 120,50\xa0€?", "Cut")


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
    text = "Paid: {{input.paid}}. Your visit: {{input.at}}. Total: {{steps.s0.total_cents}}."
    notify = {"id": "s1", "kind": "command", "operation": NOTIFY, "params": {"phone": "input.phone", "text": text}}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[QUOTE_STEP, notify], grants=[QUOTE.name, NOTIFY], language="es")
    done = run("flow.flow.run", {"id": str(flow.id), "input": INPUT})
    assert done.status == FlowRun.Status.SUCCEEDED, done
    body = Message.objects.get(direction="outbound").body
    assert body == "Paid: Sí. Your visit: 2 nov 2026, 10:00. Total: 120,50\xa0€."


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
        "params": {"title": "{{input.paid}} {{input.at}} {{steps.s0.total_cents}}"},
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
