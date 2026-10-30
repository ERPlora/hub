"""FIX-HUB-FLOW-PENDING-ANSWER-CARD-SHOWS-RAW-VALUES (FLOW-F29 step 1, FLOW-F38 step 4): the assistant's change that
waits in «Waiting for your answer» painted each datum as the model sent it, in its details — «Services: [{}]», an
amount in cents, «True», a day and a time as ISO 8601 writes them — and was written once, for nobody, when it was
asked: it could neither name a record nor say the business's hour. Now each datum comes with the question as the
assistant's confirmation card in the chat says it (BASE-F97 step 2, ``base.assistant.card``), read for whoever opens
the inbox: a moment in their language at the business's hour, a value of a closed list by its label, an amount in
cents marked as money, a yes or no as one, a list as a list, and a record by its name only when they may read it —
never by its id. The details keep only what the assistant said.
"""

import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.operations import Operation, registry
from ninja import Field, Schema

from apps.flow import gateway as flow_gateway
from apps.flow.models import Flow, Question
from apps.flow.queries import TURN
from base import relay
from base.models import Hub, Membership
from base.schemas import names
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

from .conftest import ctx_for, make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
CHAT = "/internal/assistant/chat"
QUOTA = {"used": 1, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
SERVICE = "0192f0b2-2222-7000-8000-000000000002"
MEMBER = "0192f0b2-3333-7000-8000-000000000003"

#: What a datum of the card never carries: an id…
AN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
#: …nor a day or a time as ISO 8601 writes them.
AN_ISO_MOMENT = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}")


class ChoreStepIn(Schema):
    title: str


class ChorePlanIn(Schema):
    """A write with one datum of each kind the card says in words."""

    title: str
    due_at: dt.datetime
    price_cents: int
    urgent: bool
    steps: list[ChoreStepIn]
    person: str = Field(json_schema_extra=names("base.person.detail", by="person"))


#: A write of an app that is on (Tasks), granted to the automation like any other.
PLAN = Operation(
    name="task.task.plan",
    kind="command",
    permission="task.add",
    input=ChorePlanIn,
    output=ChorePlanIn,
    expose_api=False,
    ai={"description": "Plans a chore for someone."},
    fn=lambda ctx, data: data,
)

CHORE = {
    "title": "Call Ana",
    "due_at": "2026-11-02T10:00:00+01:00",
    "price_cents": 1500,
    "urgent": True,
    "steps": [{"title": "Dial"}, {"title": "Note it"}],
    "person": "saas:3",
}

#: Who runs the business (they may read a person), and someone who may answer the assistant's change (it is asked
#: of whoever manages automations) but may not read a person of the business.
OWNER = {"base.view_home", "base.administer_hub", "flow.view", "flow.answer", "flow.answer_manager", "flow.manage"}
NO_PEOPLE = {"base.view_home", "flow.view", "flow.answer", "flow.manage"}


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    monkeypatch.setattr(flow_gateway, "PAUSES", (0, 0))


@pytest.fixture
def plan(monkeypatch):
    monkeypatch.setitem(registry, PLAN.name, PLAN)
    return PLAN


@pytest.fixture
def worker(monkeypatch, django_capture_on_commit_callbacks):
    """One pass of the outbox relay, as the worker runs it every tick (base.relay)."""
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def tick():
        with django_capture_on_commit_callbacks(execute=True):
            return relay.run(timezone.now())

    def request(name, data, ctx=None):
        with django_capture_on_commit_callbacks(execute=True):
            return run(name, data, ctx)

    tick.request = request
    return tick


@pytest.fixture
def eva():
    """Eva Gil, an employee of the business, as erplora.com names her (``saas:3``)."""
    user = get_user_model().objects.create_user(username="saas:3", password="pw", first_name="Eva", last_name="Gil")
    Membership.objects.create(user=user, host="a", role=Membership.Role.EMPLOYEE)
    return user


def wants(name: str, arguments: dict, text: str = "") -> dict:
    said = [{"type": "message", "content": [{"type": "output_text", "text": text}]}] if text else []
    call = {"type": "function_call", "call_id": "call_1", "name": name, "arguments": json.dumps(arguments)}
    return {"output": [*said, call], "continuation": "token-1", "quota": QUOTA}


def waiting(worker, gateway, operation: str, arguments: dict, text: str = "") -> Question:
    """An automation whose assistant, asking first, wants to run ``operation`` with ``arguments``: its question."""
    step = {"id": "s1", "kind": "assistant", "prompt": "Help {{input.name}}", "tools": [operation]}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[step], grants=[operation])
    gateway.reply(CHAT, json=wants(operation.replace(".", "__"), arguments, text))
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {"name": "Ana"}})
    worker()
    return Question.objects.get(run_id=ran.id)


def row_of(question: Question, permissions: set[str], language: str = "es") -> dict:
    ctx = ctx_for(permissions=permissions, language=language)
    [row] = [row for row in run("flow.question.list", {}, ctx).rows if row.id == question.id]
    return row.model_dump(mode="json")


def values(row: dict) -> dict:
    return {field["name"]: field["value"] for field in row["fields"]}


def kinds(row: dict) -> dict:
    return {field["name"]: field["kind"] for field in row["fields"]}


@pytest.mark.parametrize(
    ("language", "due", "label"),
    [("es", "2 nov 2026, 10:00", "Título"), ("en", "Nov 2, 2026, 10:00\u202fAM", "Title")],
)
def test_each_datum_of_the_change_comes_as_the_chat_card_says_it(gateway, clock, worker, plan, eva, language, due, label):
    clock(NOON)
    question = waiting(worker, gateway, PLAN.name, CHORE)
    row = row_of(question, OWNER, language)
    assert values(row) == {
        "title": "Call Ana",
        "due_at": due,
        "price_cents": 1500,
        "urgent": True,
        "steps": [{"title": "Dial"}, {"title": "Note it"}],
        "person": "Eva Gil",
    }
    assert kinds(row) == {
        "title": "text", "due_at": "text", "price_cents": "money", "urgent": "bool", "steps": "list", "person": "text",
    }
    assert {field["name"]: field["label"] for field in row["fields"]}["title"] == label
    shown = json.dumps(row["fields"], ensure_ascii=False)
    assert not AN_ID.search(shown) and not AN_ISO_MOMENT.search(shown)


def test_the_details_keep_what_the_assistant_said_and_no_datum_as_sent(gateway, clock, worker, plan, eva):
    clock(NOON)
    question = waiting(worker, gateway, PLAN.name, CHORE, text="I will plan the call.")
    row = row_of(question, OWNER)
    assert row["details"] == "I will plan the call."
    for sent in ("1500", "True", "2026-11-02", "saas:3", "[{"):
        assert sent not in row["details"]


def test_a_record_is_named_only_for_whoever_may_read_it(gateway, clock, worker, plan, eva):
    # The names are read as the person who opens the inbox, never as the automation nor for somebody else: who may
    # answer it but may not read a person of the business sees the card leave her out — never by her id.
    clock(NOON)
    question = waiting(worker, gateway, PLAN.name, CHORE)
    assert values(row_of(question, OWNER))["person"] == "Eva Gil"
    other = row_of(question, NO_PEOPLE)
    assert "person" not in values(other)
    assert "saas:3" not in json.dumps(other, ensure_ascii=False)


def test_a_moment_is_said_at_the_businesss_hour(gateway, clock, worker, plan, eva):
    """The business's own zone (Settings › Business), read as whoever opens the inbox."""
    clock(NOON)
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "timezone": "Atlantic/Canary"})
    question = waiting(worker, gateway, PLAN.name, CHORE)
    assert values(row_of(question, OWNER))["due_at"] == "2 nov 2026, 9:00"


def test_a_booking_s_services_are_a_list_never_its_ids(gateway, clock, worker):
    # The symptom: «ask me first» with a booking said «Services: [{}]» and its professional by an id.
    clock(NOON)
    booking = {
        "customer": "Ana López",
        "services": [{"service_id": SERVICE}],
        "staff_id": MEMBER,
        "start": "2026-11-02T10:00:00+01:00",
        "source": "counter",
    }
    question = waiting(worker, gateway, "appointment.appointment.create", booking)
    row = row_of(question, OWNER)
    assert kinds(row)["services"] == "list"
    assert (values(row)["start"], values(row)["source"]) == ("2 nov 2026, 10:00", "Mostrador")
    assert "staff_id" not in values(row)
    assert "[{}]" not in row["details"] and SERVICE not in row["details"]


def test_a_question_an_automation_step_asks_has_no_data_of_a_change(clock):
    # «Ask someone first» (FLOW-F28) asks with its own words: there is no change of the assistant to describe.
    from .conftest import make_run

    clock(NOON)
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[{"id": "s1", "kind": "ask", "title": "Refund?"}])
    ran = make_run(flow, status="asking")
    question = Question.objects.create(
        run=ran, flow=flow, step_id="s1", title="Refund?", details="Ana, 15 €", expires_at=NOON + dt.timedelta(hours=72)
    )
    row = row_of(question, OWNER)
    assert (row["details"], row["fields"]) == ("Ana, 15 €", [])



# --- The action it waits on (FIX-HUB-FLOW-PENDING-ANSWER-CARD-DOES-NOT-SAY-THE-ACTION) ------------------------------
# The card was always titled «The assistant wants to change something in «Reservations»», a cancellation too: whoever
# approved read the record, the reason and on whose behalf, never the action. Now the card says the action first, as
# the History names it (``queries.action_label``), and its title, in the language of whoever reads it — also for a
# question that was already waiting, since both come from the change it waits on, never from what was kept.

RESERVATION = "0192f0b2-4444-7000-8000-000000000004"


def waiting_in(worker, gateway, language: str, operation: str, arguments: dict) -> Question:
    """``waiting``, for an automation written in ``language``."""
    step = {"id": "s1", "kind": "assistant", "prompt": "Help {{input.name}}", "tools": [operation]}
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[step], grants=[operation], language=language)
    gateway.reply(CHAT, json=wants(operation.replace(".", "__"), arguments, ""))
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {"name": "Ana"}})
    worker()
    return Question.objects.get(run_id=ran.id)


@pytest.mark.parametrize(
    ("operation", "arguments", "said"),
    [
        (
            "reservation.reservation.cancel",
            {"id": RESERVATION, "reason": "The guest called"},
            {"en": "Cancel a reservation", "es": "Anular una reserva"},
        ),
        (
            "reservation.reservation.create",
            {"guest_name": "Ana", "party_size": 4, "date": "2026-11-02", "time": "21:00"},
            {"en": "Create a reservation", "es": "Crear una reserva"},
        ),
        (
            "reservation.reservation.update",
            {"id": RESERVATION, "party_size": 6},
            {"en": "Change a reservation", "es": "Cambiar una reserva"},
        ),
    ],
)
def test_the_card_says_the_action_the_assistant_wants_in_the_readers_language(
    gateway, clock, worker, operation, arguments, said
):
    # The automation is written in Spanish; each person reads the same question in their own language.
    clock(NOON)
    question = waiting_in(worker, gateway, "es", operation, arguments)
    english, spanish = row_of(question, OWNER, "en"), row_of(question, OWNER, "es")
    assert (english["action"], spanish["action"]) == (said["en"], said["es"])
    assert english["title"] == "The assistant wants to change something in «Reservations»"
    assert spanish["title"] == "El asistente quiere cambiar algo en «Reservas»"
    for row in (english, spanish):
        assert operation not in json.dumps(row, ensure_ascii=False)


def test_a_booking_says_book_an_appointment(gateway, clock, worker):
    clock(NOON)
    booking = {"customer": "Ana López", "services": [{"service_id": SERVICE}], "staff_id": MEMBER,
               "start": "2026-11-02T10:00:00+01:00", "source": "counter"}
    question = waiting_in(worker, gateway, "en", "appointment.appointment.create", booking)
    assert row_of(question, OWNER, "es")["action"] == "Reservar una cita"
    assert row_of(question, OWNER, "en")["action"] == "Book an appointment"


def test_one_question_read_by_id_says_the_action_too(gateway, clock, worker):
    clock(NOON)
    question = waiting_in(worker, gateway, "en", "reservation.reservation.cancel", {"id": RESERVATION})
    found = run("flow.question.get", {"id": str(question.id)}, ctx_for(permissions=OWNER, language="es"))
    assert (found.action, found.title) == ("Anular una reserva", "El asistente quiere cambiar algo en «Reservas»")


def test_a_question_already_waiting_with_the_old_title_says_the_action(gateway, clock, worker):
    # One asked before this change kept only «… in «Reservations»», in the automation's language.
    clock(NOON)
    question = waiting_in(worker, gateway, "en", "reservation.reservation.cancel", {"id": RESERVATION})
    Question.objects.filter(pk=question.pk).update(title="The assistant wants to change something in «Reservations»")
    row = row_of(question, OWNER, "es")
    assert (row["action"], row["title"]) == ("Anular una reserva", "El asistente quiere cambiar algo en «Reservas»")


def test_an_action_without_its_own_words_is_still_said_with_its_app(gateway, clock, worker, plan):
    # ``task.task.plan`` has no words of its own in the History: its verb and its app, never empty nor its name.
    clock(NOON)
    question = waiting_in(worker, gateway, "en", PLAN.name, CHORE)
    for language, app in (("en", "Tasks"), ("es", "Tareas")):
        action = row_of(question, OWNER, language)["action"]
        assert app in action and action.strip()
        assert PLAN.name not in action


def test_an_action_that_is_gone_says_none_and_keeps_its_title(gateway, clock, worker, plan, monkeypatch):
    clock(NOON)
    question = waiting_in(worker, gateway, "en", PLAN.name, CHORE)
    monkeypatch.delitem(registry, PLAN.name)
    row = row_of(question, OWNER, "es")
    assert (row["action"], row["title"]) == ("", question.title)


def test_a_question_an_automation_step_asks_says_no_action_and_keeps_its_words(clock):
    # «Ask someone first» (FLOW-F28): its title is what whoever set up the automation wrote, untouched.
    from .conftest import make_run

    clock(NOON)
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[{"id": "s1", "kind": "ask", "title": "Refund?"}])
    ran = make_run(flow, status="asking")
    question = Question.objects.create(
        run=ran, flow=flow, step_id="s1", title="Refund?", details="Ana, 15 €", expires_at=NOON + dt.timedelta(hours=72)
    )
    assert (row_of(question, OWNER, "en")["action"], row_of(question, OWNER, "en")["title"]) == ("", "Refund?")


# --- The run it cancels says the action too ----------------------------------------------------------------------
# A no, or nobody answering, cancelled the run with «Cancelled: Marta answered no to «The assistant wants to change
# something in «Reservations»».»: the History said that something was refused, never what. Now it names the action of
# the change, as the card does, in the language of whoever reads the History; an «Ask someone first» question keeps
# what was asked.


def history_of(flow: Flow, language: str):
    """The History of ``flow`` as a person whose screen is in ``language`` reads it: its runs and one by id."""
    ctx = ctx_for(language=language)
    [row] = run("flow.run.list", {"flow_id": str(flow.id)}, ctx).rows
    return row.error_message, run("flow.run.get", {"id": str(row.id)}, ctx).error_message


def test_a_no_to_the_assistant_s_change_names_its_action_in_the_readers_language(gateway, clock, worker):
    clock(NOON)
    question = waiting_in(worker, gateway, "es", "reservation.reservation.cancel", {"id": RESERVATION})
    worker.request("flow.question.answer", {"id": str(question.id), "approve": False})
    assert history_of(question.flow, "en") == ("Cancelled: tester answered no to «Cancel a reservation».",) * 2
    assert history_of(question.flow, "es") == ("Cancelada: tester contestó que no a «Anular una reserva».",) * 2


def test_nobody_answering_the_assistant_s_change_names_its_action_in_the_readers_language(gateway, clock, worker):
    from live.context import system_context

    from .conftest import A

    clock(NOON)
    question = waiting_in(worker, gateway, "en", "appointment.appointment.create", {"customer": "Ana López"})
    clock(NOON + dt.timedelta(hours=72))
    assert run("flow.question.expire_due", {}, system_context(A)).count == 1
    assert history_of(question.flow, "es") == ("Cancelada: nadie contestó a tiempo «Reservar una cita».",) * 2
    assert history_of(question.flow, "en") == ("Cancelled: nobody answered «Book an appointment» in time.",) * 2


def test_a_no_to_a_change_whose_action_is_gone_says_what_was_kept(gateway, clock, worker, plan, monkeypatch):
    clock(NOON)
    question = waiting_in(worker, gateway, "en", PLAN.name, CHORE)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": False})
    monkeypatch.delitem(registry, PLAN.name)
    said = f"Cancelada: tester contestó que no a «{question.title}»."
    assert history_of(question.flow, "es") == (said, said)


def test_a_no_to_an_ask_someone_first_question_keeps_what_was_asked(clock):
    clock(NOON)
    flow = make_flow(language="es", trigger_kind=Flow.Trigger.MANUAL, steps=[{"id": "s1", "kind": "ask", "title": "Refund?"}])
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    question = Question.objects.get(run_id=ran.id)
    run("flow.question.answer", {"id": str(question.id), "approve": False})
    assert history_of(flow, "en") == ("Cancelled: tester answered no to «Refund?».",) * 2


def test_an_ask_someone_first_question_after_the_assistant_s_turn_says_no_action(clock, plan):
    # The step that asks decides, never what the run keeps: a run whose turn still holds a change of the assistant
    # and asks a person at an «Ask someone first» step (FLOW-F28) says no action, on the card and in the History.
    from .conftest import make_run

    clock(NOON)
    steps = [{"id": "s1", "kind": "assistant", "prompt": "Help", "tools": [PLAN.name]}, {"id": "s2", "kind": "ask", "title": "Refund?"}]
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=[PLAN.name])
    held = {TURN: {"proposal": {"operation": PLAN.name, "arguments": json.dumps(CHORE)}}}
    ran = make_run(flow, status="asking", step_index=1, outputs=held)
    question = Question.objects.create(
        run=ran, flow=flow, step_id="s2", title="Refund?", details="", expires_at=NOON + dt.timedelta(hours=72)
    )
    assert (row_of(question, OWNER, "en")["action"], row_of(question, OWNER, "en")["title"]) == ("", "Refund?")
    run("flow.question.answer", {"id": str(question.id), "approve": False})
    assert history_of(flow, "en") == ("Cancelled: tester answered no to «Refund?».",) * 2
