"""Fixed data of an «Ask the assistant» step (FIX-HUB-FLOW-ASSISTANT-STEP-ACTS-ON-ANOTHER-CUSTOMER-WITHOUT-ON-BEHALF-OF;
WORKBOOK FLOW-F37, FLOW-F38, FLOW-F29).

A step's tool may get data the automation fixes (``pinned``: ``{tool: {input: value}}``), filled in when it runs with
the same data as the prompt: the assistant never sees them and cannot change nor leave them out — what it sends for
them is replaced, «Ask me first» or «On its own» —, and a tool whose fixed datum is empty when it runs is not used
(nothing half done). Before, the only barrier between a WhatsApp guest and another guest's reservation was the prompt
asking for ``on_behalf_of`` and the card naming the other person: after the yes, Reservations cancelled it.

The market fixes such a datum the same way: Zapier's «Set a specific value» (the AI ignores the field), n8n's tool
parameters without ``$fromAI()``, Copilot Studio's «Set as a value», LangChain's ``InjectedToolArg`` (left out of the
schema the model sees, added before the call), Intercom Fin's data connectors on a protected attribute, Salesforce
Agentforce's input bindings.
"""

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pydantic
import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.context import system_context
from live.errors import InvalidPayload

from apps.flow import gateway as flow_gateway
from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries import TURN
from base import relay
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

from .conftest import A, ctx_for, make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
CHAT = "/internal/assistant/chat"
QUOTA = {"used": 1, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
CANCEL = "reservation.reservation.cancel"
UPDATE = "reservation.reservation.update"
#: Whoever may answer and cancel a reservation themselves (the yes to a cancellation, hub#418).
MAY_CANCEL = {
    "flow.view", "flow.manage", "flow.answer", "flow.answer_manager",
    "reservation.view_reservation", "reservation.change_reservation", "customer.view",
}
#: The card of whoever writes, read in an earlier step: what the step fixes ``on_behalf_of`` to.
THEIRS = {CANCEL: {"on_behalf_of": "input.customer"}, UPDATE: {"on_behalf_of": "input.customer"}}


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    monkeypatch.setattr(flow_gateway, "PAUSES", (0, 0))


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
def guests(clock):
    """Lucía, who writes, and Marta, another guest: each with her card and a pending table tomorrow at nine."""
    from apps.reservation.tests.conftest import make_table, open_week

    clock(NOON)
    open_week()
    owner = ctx_for("hub_owner")
    lucia = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, owner)
    marta = run("customer.customer.create", {"name": "Marta Ruiz", "phone": "600999888"}, owner)

    def book(card, table: str):
        return run(
            "reservation.reservation.create",
            {"customer_id": str(card.id), "guest_name": card.name, "date": "2026-10-16", "time": "21:00",
             "party_size": 2, "table_id": str(make_table(table).id)},
            system_context(A),
        )

    return {"lucia": lucia, "marta": marta, "hers": book(lucia, "5"), "other": book(marta, "6")}


def assistant(tools=(CANCEL,), pinned=None, **more) -> dict:
    step = {"id": "s1", "kind": "assistant", "prompt": "Help the guest {{input.name}}", "tools": list(tools)}
    return step | ({"pinned": pinned} if pinned is not None else {}) | more


def document(*steps) -> dict:
    return {"name": "Table by message", "trigger": {"kind": "manual"}, "steps": list(steps)}


def said(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}], "continuation": None, "quota": QUOTA}


def wants(name: str, arguments: dict | str) -> dict:
    text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    call = {"type": "function_call", "call_id": "call_1", "name": name.replace(".", "__"), "arguments": text}
    return {"output": [call], "continuation": "token-1", "quota": QUOTA}


def status_of(reservation) -> str:
    from apps.reservation.models import Reservation

    return Reservation.objects.get(pk=reservation.id).status


def time_of(reservation) -> dt.time:
    from apps.reservation.models import Reservation

    return Reservation.objects.get(pk=reservation.id).time


def asked(worker, gateway, guests, step: dict, call: dict, name: str = CANCEL, grants=(CANCEL, UPDATE), customer="lucia"):
    """Lucía's message reaches a step whose assistant wants ``name`` with ``call``: the run as it is then."""
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[step], grants=list(grants))
    gateway.reply(CHAT, json=wants(name, call))
    gateway.reply(CHAT, json=said("Done"))
    data = {"name": "Lucía"} | ({"customer": str(guests[customer].id)} if customer else {})
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": data})
    worker()
    return FlowRun.objects.get(pk=ran.id)


def yes(worker, ran: FlowRun) -> None:
    question = Question.objects.get(run_id=ran.id, status=Question.Status.PENDING)
    worker.request("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for(permissions=MAY_CANCEL, actor="owner"))
    worker()


def told(gateway) -> list[dict]:
    """What the assistant heard of its calls, in its last turn."""
    return [message for message in gateway.sent(CHAT)[-1].body["messages"] if message.get("role") == "tool"]


# ── Running it (FLOW-F38) ───────────────────────────────────────────────────────────────────────────────────────────


def test_asking_first_another_guest_s_reservation_is_not_cancelled_when_the_assistant_leaves_the_fixed_datum_out(
    gateway, worker, guests
):
    # The premise: on main the yes cancelled Marta's table, the model having sent no on_behalf_of.
    ran = asked(worker, gateway, guests, assistant(pinned=THEIRS), {"id": str(guests["other"].id), "reason": "She wrote"})
    yes(worker, ran)
    assert status_of(guests["other"]) == "pending"
    assert "reservation.customer_mismatch" in json.dumps(told(gateway))


def test_asking_first_the_fixed_datum_the_assistant_changes_is_replaced(gateway, worker, guests):
    call = {"id": str(guests["other"].id), "on_behalf_of": str(guests["marta"].id)}
    ran = asked(worker, gateway, guests, assistant(pinned=THEIRS), call)
    proposal = ran.outputs[TURN]["proposal"]
    assert json.loads(proposal["arguments"])["on_behalf_of"] == str(guests["lucia"].id)
    yes(worker, ran)
    assert status_of(guests["other"]) == "pending"


def test_asking_first_their_own_reservation_is_cancelled_with_the_fixed_datum_put_in(gateway, worker, guests):
    ran = asked(worker, gateway, guests, assistant(pinned=THEIRS), {"id": str(guests["hers"].id)})
    assert json.loads(ran.outputs[TURN]["proposal"]["arguments"]) == {
        "id": str(guests["hers"].id), "on_behalf_of": str(guests["lucia"].id),
    }
    yes(worker, ran)
    assert status_of(guests["hers"]) == "cancelled"
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


def test_asking_first_another_guest_s_reservation_is_not_changed(gateway, worker, guests):
    step = assistant(tools=[UPDATE], pinned={UPDATE: {"on_behalf_of": "input.customer"}})
    ran = asked(worker, gateway, guests, step, {"id": str(guests["other"].id), "time": "22:00"}, name=UPDATE, grants=[UPDATE])
    yes(worker, ran)
    assert time_of(guests["other"]) == dt.time(21, 0)
    assert "reservation.customer_mismatch" in json.dumps(told(gateway))


def test_on_its_own_another_guest_s_reservation_is_not_changed(gateway, worker, guests):
    step = assistant(tools=[UPDATE], pinned={UPDATE: {"on_behalf_of": "input.customer"}}, mode="auto")
    asked(worker, gateway, guests, step, {"id": str(guests["other"].id), "time": "22:00", "on_behalf_of": None}, name=UPDATE, grants=[UPDATE])
    assert time_of(guests["other"]) == dt.time(21, 0)
    assert "reservation.customer_mismatch" in json.dumps(told(gateway))


def test_on_its_own_their_own_reservation_is_changed_with_the_fixed_datum_put_in(gateway, worker, guests):
    step = assistant(tools=[UPDATE], pinned={UPDATE: {"on_behalf_of": "input.customer"}}, mode="auto")
    asked(worker, gateway, guests, step, {"id": str(guests["hers"].id), "time": "22:00"}, name=UPDATE, grants=[UPDATE])
    assert time_of(guests["hers"]) == dt.time(22, 0)


@pytest.mark.parametrize(
    "call",
    [
        {"onBehalfOf": "MARTA"},  # under another name
        {"reservation": {"on_behalf_of": "MARTA"}},  # inside another datum
    ],
)
def test_the_fixed_datum_under_another_name_or_inside_another_one_changes_nothing(gateway, worker, guests, call):
    step = assistant(tools=[UPDATE], pinned={UPDATE: {"on_behalf_of": "input.customer"}}, mode="auto")
    sent = json.loads(json.dumps(call).replace("MARTA", str(guests["marta"].id)))
    asked(worker, gateway, guests, step, {"id": str(guests["other"].id), "time": "22:00", **sent}, name=UPDATE, grants=[UPDATE])
    assert time_of(guests["other"]) == dt.time(21, 0)
    assert json.loads(told(gateway)[0]["content"])["error"]["code"] == "invalid_payload"


def test_the_fixed_datum_is_left_out_of_what_the_assistant_is_offered(gateway, worker, guests):
    asked(worker, gateway, guests, assistant(tools=[CANCEL, UPDATE], pinned={CANCEL: THEIRS[CANCEL]}), {"id": str(guests["hers"].id)})
    first = gateway.sent(CHAT)[0]
    offered = {tool["name"]: tool["parameters"] for tool in first.body["tools"]}
    assert "on_behalf_of" not in offered["reservation__reservation__cancel"]["properties"]
    assert "on_behalf_of" not in offered["reservation__reservation__cancel"].get("required", [])
    assert "id" in offered["reservation__reservation__cancel"]["properties"]
    # A tool with nothing fixed is offered whole.
    assert "on_behalf_of" in offered["reservation__reservation__update"]["properties"]


def test_a_fixed_datum_is_filled_in_with_the_data_of_the_run_as_the_prompt_is(gateway, worker, guests):
    # Their card read in one of two earlier steps (found, or created): the one that is there.
    pinned = {CANCEL: {"on_behalf_of": "{{input.found}}{{input.customer}}"}}
    ran = asked(worker, gateway, guests, assistant(pinned=pinned), {"id": str(guests["hers"].id)})
    assert json.loads(ran.outputs[TURN]["proposal"]["arguments"])["on_behalf_of"] == str(guests["lucia"].id)


def test_a_tool_whose_fixed_datum_is_empty_is_not_used_and_the_history_says_why(gateway, worker, guests):
    # Their card was not found: nothing waits for a yes and nothing is cancelled; the assistant hears it to say so.
    ran = asked(worker, gateway, guests, assistant(pinned=THEIRS), {"id": str(guests["other"].id)}, customer=None)
    assert not Question.objects.filter(run_id=ran.id).exists()
    assert status_of(guests["other"]) == "pending"
    [heard] = told(gateway)
    error = json.loads(heard["content"])["error"]
    assert error["code"] == "flow.pinned_empty" and "on_behalf_of" in error["message"]
    entry = next(entry for entry in FlowRun.objects.get(pk=ran.id).log if entry["outcome"] == "assistant_pinned_empty")
    assert (entry["operation"], entry["fields"]) == (CANCEL, ["on_behalf_of"])
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


def test_the_card_of_the_change_says_the_fixed_datum_by_name(gateway, worker, guests):
    # FLOW-F29: the yes is given knowing on whose behalf (her name, never her card's id).
    ran = asked(worker, gateway, guests, assistant(pinned=THEIRS), {"id": str(guests["other"].id)})
    question = Question.objects.get(run_id=ran.id)
    [row] = [row for row in run("flow.question.list", {}, ctx_for(permissions=MAY_CANCEL)).rows if row.id == question.id]
    shown = {field["name"]: field["value"] for field in row.model_dump(mode="json")["fields"]}
    assert shown["on_behalf_of"] == "Lucía Pérez"


def test_an_automation_saved_without_fixed_data_runs_as_before(gateway, worker, guests):
    # Compatibility: a step written before (no ``pinned``) passes on what the model sends, as it did.
    ran = asked(worker, gateway, guests, assistant(), {"id": str(guests["hers"].id), "on_behalf_of": str(guests["lucia"].id)})
    yes(worker, ran)
    assert status_of(guests["hers"]) == "cancelled"


# ── Saving it (FLOW-F37) ────────────────────────────────────────────────────────────────────────────────────────────


def test_a_step_with_fixed_data_is_saved_and_read_back():
    created = run("flow.flow.create", document(assistant(pinned={CANCEL: {"on_behalf_of": "input.customer"}})))
    assert created.steps[0]["pinned"] == {CANCEL: {"on_behalf_of": "input.customer"}}
    read = run("flow.flow.detail", {"id": str(created.id)})
    assert read.steps[0]["pinned"] == {CANCEL: {"on_behalf_of": "input.customer"}}


def test_a_step_without_fixed_data_is_saved_as_before():
    created = run("flow.flow.create", document(assistant()))
    assert "pinned" not in created.steps[0]


@pytest.mark.parametrize(
    ("pinned", "message"),
    [
        (
            {UPDATE: {"on_behalf_of": "input.customer"}},
            "«reservation.reservation.update» has fixed data but the assistant may not use it: add it to what it may "
            "use or remove its fixed data.",
        ),
        (
            {CANCEL: {"customer_id": "input.customer"}},
            "«customer_id» is no datum of «reservation.reservation.cancel».",
        ),
        (
            {CANCEL: {"on_behalf_of": ""}},
            "Give «on_behalf_of» of «reservation.reservation.cancel» a value, or remove it.",
        ),
        (
            {CANCEL: {"on_behalf_of": "  "}},
            "Give «on_behalf_of» of «reservation.reservation.cancel» a value, or remove it.",
        ),
    ],
)
def test_fixed_data_of_a_tool_it_may_not_use_or_of_no_datum_of_it_is_not_saved(pinned, message):
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.create", document(assistant(pinned=pinned)))
    assert refused.value.code == "invalid_payload"
    assert refused.value.fields == {"steps.0.pinned": message}


def test_fixed_data_of_a_tool_it_may_not_use_is_not_saved_on_a_change_either():
    created = run("flow.flow.create", document(assistant()))
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.update", {"id": str(created.id), "steps": [assistant(pinned={UPDATE: {"on_behalf_of": "x"}})]})
    assert set(refused.value.fields) == {"steps.0.pinned"}


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("steps.s2.id", "Step 1 reads «steps.s2.id», which no earlier step leaves."),
        ("{{steps.s2.id}}", "Step 1 reads «steps.s2.id», which no earlier step leaves."),
        ("steps.s1.text", "Step 1 reads «steps.s1.text», which no earlier step leaves."),
        ("{{secret.KEY}}", "Step 1 reads «secret.KEY»: a secret or the call's key only go in «Call another system»."),
    ],
)
def test_a_fixed_datum_reads_only_the_data_the_prompt_may_read(value, message):
    # Never what a later step (or the step itself) leaves, nor a secret: the document is refused as the prompt's is.
    later = {"id": "s2", "kind": "query", "operation": "customer.customer.by_phone", "params": {"phone": "input.phone"}}
    with pytest.raises(pydantic.ValidationError) as refused:
        run("flow.flow.create", document(assistant(pinned={CANCEL: {"on_behalf_of": value}}), later))
    assert message in str(refused.value)


def test_a_fixed_datum_may_read_an_earlier_step():
    earlier = {"id": "s0", "kind": "query", "operation": "customer.customer.by_phone", "params": {"phone": "input.phone"}}
    created = run("flow.flow.create", document(earlier, assistant(pinned={CANCEL: {"on_behalf_of": "{{steps.s0.id}}"}})))
    assert created.steps[1]["pinned"] == {CANCEL: {"on_behalf_of": "{{steps.s0.id}}"}}


# ── Trying it (FLOW-F13) ────────────────────────────────────────────────────────────────────────────────────────────


def test_trying_it_says_each_fixed_datum_with_the_value_it_would_have_and_which_would_be_empty(gateway):
    # Nothing is asked: each datum the step fixes, tool by tool, filled in with the trial's data as the run would fill
    # it; an empty one means its tool would not be used, and one read from a step that does not run here is unknown.
    earlier = {"id": "s0", "kind": "query", "operation": "customer.customer.by_phone", "params": {"phone": "input.phone"}}
    pinned = {
        CANCEL: {"on_behalf_of": "{{input.customer}}", "reason": "Asked by WhatsApp"},
        UPDATE: {"on_behalf_of": "{{steps.s0.id}}"},
    }
    step = assistant(tools=[CANCEL, UPDATE], pinned=pinned) | {"id": "s1"}
    tried = run("flow.flow.test", {"document": json.dumps({"trigger": {"kind": "manual"}, "steps": [earlier, step]})})
    assert tried.steps[1].outcome == "would_ask_assistant"
    assert [(row.tool, row.field, row.state, row.said and row.said.value) for row in tried.steps[1].pinned] == [
        (CANCEL, "on_behalf_of", "empty", None),
        (CANCEL, "reason", "filled", "Asked by WhatsApp"),
        (UPDATE, "on_behalf_of", "unknown", None),
    ]
    assert tried.steps[0].pinned == []
    assert gateway.sent(CHAT) == []


def test_trying_it_says_each_fixed_datum_as_the_card_of_the_change_says_it(gateway, guests):
    # FLOW-F13 as FLOW-F29: a datum is said with the card's own words, read as whoever tries it — a card by its name,
    # a day as their language writes it, a yes or no —, never by its id; whoever may not read that card gets it left
    # out, as the card leaves it out, never its id either.
    lucia = str(guests["lucia"].id)
    pinned = {CANCEL: {"on_behalf_of": lucia, "reason": "Asked by WhatsApp"}, UPDATE: {"date": "2026-10-16", "no_table": True}}
    data = {"document": json.dumps({"trigger": {"kind": "manual"}, "steps": [assistant(tools=[CANCEL, UPDATE], pinned=pinned)]})}

    def tried(ctx) -> dict:
        rows = run("flow.flow.test", data, ctx).model_dump(mode="json")["steps"][0]["pinned"]
        return {(row["tool"], row["field"]): row for row in rows}

    def said(rows: dict) -> dict:
        return {key: (row["state"], row["said"] and (row["said"]["kind"], row["said"]["value"])) for key, row in rows.items()}

    assert said(tried(ctx_for())) == {
        (CANCEL, "on_behalf_of"): ("filled", ("text", "Lucía Pérez")),
        (CANCEL, "reason"): ("filled", ("text", "Asked by WhatsApp")),
        (UPDATE, "date"): ("filled", ("text", "Oct 16, 2026")),
        (UPDATE, "no_table"): ("filled", ("bool", True)),
    }
    assert said(tried(ctx_for(language="es")))[(UPDATE, "date")] == ("filled", ("text", "16 oct 2026"))
    blind = tried(ctx_for(permissions={"flow.view", "flow.manage", "reservation.view_reservation"}))
    assert said(blind)[(CANCEL, "on_behalf_of")] == ("filled", None)
    assert lucia not in json.dumps(list(blind.values()))
    assert gateway.sent(CHAT) == []


def test_trying_it_says_a_fixed_amount_in_the_business_s_currency():
    # The amount comes with the business's currency, so «Try it» writes it as the card does without a live read of
    # its own: opening the tab would otherwise reopen the page's live stream.
    create = "service.service.create"
    step = assistant(tools=[create], pinned={create: {"price": 1500}})
    tried = run("flow.flow.test", {"document": json.dumps({"trigger": {"kind": "manual"}, "steps": [step]})})
    [row] = tried.model_dump(mode="json")["steps"][0]["pinned"]
    assert (row["said"]["kind"], row["said"]["value"], row["said"]["money"]) == (
        "money", 1500, {"currency": "EUR", "decimals": 2}
    )
