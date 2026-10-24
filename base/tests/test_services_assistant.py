"""The assistant's operations (APP-BASE-9): ``base.assistant.turn`` prepares a turn — it runs the reads the model
asked for, shows a write's card and runs it only with the person's yes, as the person —, and ``base.assistant.usage``,
``base.assistant.report`` and ``base.assistant.transcribe`` go to erplora.com's gateway (``fake_gateway``).
"""

import json

import pytest
from live.context import OperationContext, Scope
from live.errors import OperationError, Unauthorized
from live.operations import get

from base import assistant
from base.tenancy import context
from base.tenancy.tests import hubs
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
MANAGER = frozenset({"base.view_home", "demo.*"})
EMPLOYEE = frozenset({"base.view_home", "demo.view"})
ASK = {"role": "user", "content": "crea el elemento Mesa 4"}


def ctx(permissions=MANAGER, *, actor="ana", language="es"):
    return OperationContext(scope=A, actor=actor, permissions=frozenset(permissions), language=language)


def run(operation_name, permissions=MANAGER, *, actor="ana", **data):
    op = get(operation_name)
    return op(ctx(permissions, actor=actor), op.input.model_validate(data)).model_dump(mode="json")


def call(name, arguments, call_id="c1"):
    return {"call_id": call_id, "name": assistant.tool_name(name), "arguments": json.dumps(arguments)}


def asked(*calls):
    """The model's message that asked for ``calls``, as the browser keeps it."""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": c["call_id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in calls
        ],
    }


def turn(*calls, decision=None, permissions=MANAGER, messages=None, **extra):
    return run(
        "base.assistant.turn",
        permissions,
        messages=messages or [ASK, asked(*calls)],
        pending=list(calls),
        decision=decision,
        **extra,
    )


def items():
    return [row["name"] for row in run("demo.item.list", EMPLOYEE)["rows"]]


def test_the_turn_is_the_persons_and_not_a_tool():
    op = get("base.assistant.turn")
    assert (op.kind, op.permission) == ("command", "base.view_home")
    assert not assistant.is_tool(op)
    with pytest.raises(Unauthorized):
        run("base.assistant.turn", actor=None, messages=[ASK])


def test_a_new_question_offers_the_tools_of_what_it_asks_and_the_instructions():
    plan = run("base.assistant.turn", messages=[ASK])
    names = [tool["name"] for tool in plan["tools"]]
    assert "demo__item__create" in names
    assert "Spanish" in plan["instructions"]
    assert (plan["append"], plan["executed"], plan["confirm"], plan["pending"]) == ([], [], None, [])


# ── Reads run by themselves (BASE-G115) ──────────────────────────────────────────────────────────────────────────


def test_a_read_the_model_asked_for_runs_alone_and_its_result_goes_back():
    run("demo.item.create", name="Terraza")
    plan = turn(call("demo.item.list", {}))
    [result] = plan["append"]
    assert (result["role"], result["tool_call_id"]) == ("tool", "c1")
    assert "Terraza" in result["content"]
    assert plan["executed"] == [
        {"call_id": "c1", "name": "demo.item.list", "app": "demo", "kind": "query", "outcome": "ok", "code": ""}
    ]
    assert (plan["confirm"], plan["pending"]) == (None, [])


# ── A write waits for the person (BASE-G115, G116, G119) ─────────────────────────────────────────────────────────


def test_a_write_waits_for_its_card_and_changes_nothing_meanwhile():
    write = call("demo.item.create", {"name": "Mesa 4"})
    plan = turn(write)
    assert plan["confirm"]["operation"] == "demo.item.create"
    assert plan["confirm"]["risk"] == "normal"
    assert plan["pending"] == [write]
    assert (plan["append"], plan["executed"]) == ([], [])
    assert "Mesa 4" not in items()


def test_the_yes_runs_the_write_as_the_person():
    write = call("demo.item.create", {"name": "Mesa 4"})
    plan = turn(write, decision={"call_id": "c1", "accepted": True})
    assert plan["executed"][0]["outcome"] == "ok"
    assert "Mesa 4" in items()
    assert json.loads(plan["append"][0]["content"])["name"] == "Mesa 4"


def test_the_no_runs_nothing_and_the_model_is_told():
    write = call("demo.item.create", {"name": "Mesa 4"})
    plan = turn(write, decision={"call_id": "c1", "accepted": False})
    assert plan["executed"][0]["outcome"] == "cancelled"
    assert json.loads(plan["append"][0]["content"])["error"]["code"] == "base.assistant_not_confirmed"
    assert "Mesa 4" not in items()


def test_a_dangerous_write_runs_only_with_the_word_typed():
    created = run("demo.item.create", name="Barra")
    delete = call("demo.item.delete", {"id": created["id"]})
    asked_card = turn(delete)["confirm"]
    assert (asked_card["risk"], asked_card["confirm_word"]) == ("high", "CONFIRMAR")
    wrong = turn(delete, decision={"call_id": "c1", "accepted": True, "typed": "confirmar"})
    assert wrong["executed"][0]["outcome"] == "cancelled"
    assert "Barra" in items()
    right = turn(delete, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"})
    assert right["executed"][0]["outcome"] == "ok"
    assert "Barra" not in items()


def test_each_write_of_a_chain_asks_its_own_yes():
    first = call("demo.item.create", {"name": "Uno"}, "c1")
    second = call("demo.item.create", {"name": "Dos"}, "c2")
    plan = turn(first, second, decision={"call_id": "c1", "accepted": True})
    assert [row["outcome"] for row in plan["executed"]] == ["ok"]
    assert plan["confirm"]["fields"][0]["value"] == "Dos"
    assert plan["pending"] == [second]
    assert "Uno" in items() and "Dos" not in items()


def test_stop_cancels_this_write_and_the_rest_of_the_chain():
    first = call("demo.item.create", {"name": "Uno"}, "c1")
    read = call("demo.item.list", {}, "c2")
    second = call("demo.item.create", {"name": "Dos"}, "c3")
    plan = turn(first, read, second, decision={"call_id": "c1", "accepted": False, "stop": True})
    assert [row["outcome"] for row in plan["executed"]] == ["cancelled", "cancelled", "cancelled"]
    assert [result["tool_call_id"] for result in plan["append"]] == ["c1", "c2", "c3"]
    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert items() == []


# ── What the person may not do is not done (BASE-G118; gh:hub#11) ────────────────────────────────────────────────


def test_a_tool_this_person_was_not_offered_is_refused_and_writes_nothing():
    write = call("demo.item.create", {"name": "Mesa 4"})
    plan = turn(write, decision={"call_id": "c1", "accepted": True}, permissions=EMPLOYEE)
    assert (plan["executed"][0]["outcome"], plan["executed"][0]["code"]) == ("refused", "not_available")
    assert plan["confirm"] is None
    assert "Mesa 4" not in items()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_write_the_assistant_runs_for_one_business_never_lands_in_another(hub_a, hub_b, monkeypatch):
    """Two businesses with a database each, as production (no fallback on the shared one)."""
    monkeypatch.setattr(context, "_test_fallback", None)
    write = call("demo.item.create", {"name": "Solo en A"})
    op = get("base.assistant.turn")
    as_a = OperationContext(scope=Scope("host", hub_a.slug), actor="ana", permissions=MANAGER, language="es")
    data = {"messages": [ASK, asked(write)], "pending": [write], "decision": {"call_id": "c1", "accepted": True}}
    with context.use_hub(hub_a):
        assert op(as_a, op.input.model_validate(data)).executed[0].outcome == "ok"

    def listed(hub):
        read = get("demo.item.list")
        as_hub = OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=MANAGER)
        with context.use_hub(hub):
            return [row.name for row in read(as_hub, read.input()).rows]

    assert listed(hub_a) == ["Solo en A"]
    assert listed(hub_b) == []


# ── A loop is cut (BASE-G119) ────────────────────────────────────────────────────────────────────────────────────


def test_after_too_many_rounds_the_turn_stops_and_says_why():
    rounds = [asked(call("demo.item.list", {}, f"r{n}")) for n in range(assistant.MAX_ROUNDS)]
    messages = [ASK]
    for n, message in enumerate(rounds[:-1]):
        messages += [message, {"role": "tool", "tool_call_id": f"r{n}", "content": "{}"}]
    last = call("demo.item.list", {}, f"r{assistant.MAX_ROUNDS - 1}")
    plan = run("base.assistant.turn", messages=[*messages, asked(last)], pending=[last])
    assert plan["stop"] == "assistant.too_many_steps"
    assert plan["executed"][0]["outcome"] == "ok"


# ── The setup (BASE-G121) ────────────────────────────────────────────────────────────────────────────────────────


def test_in_setup_the_turn_reads_the_checklist_again_for_the_model():
    plan = run("base.assistant.turn", messages=[ASK], setup=True)
    assert "Finish setting up your business" in plan["instructions"]
    assert "Finish setting up" not in run("base.assistant.turn", messages=[ASK])["instructions"]


# ── The gateway's doors (BASE-G122, G123, G112) ──────────────────────────────────────────────────────────────────


def test_the_allowance_of_the_month(gateway):
    gateway.reply("/internal/assistant/usage", json={"used": 25, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False})
    usage = run("base.assistant.usage", EMPLOYEE)
    assert usage == {"used": 25, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}


def test_an_allowance_that_cannot_be_read_is_an_error_never_a_number(gateway):
    with pytest.raises(OperationError) as caught:
        run("base.assistant.usage", EMPLOYEE)
    assert (caught.value.status, caught.value.code) == (503, "base.assistant_unavailable")


def test_a_report_of_a_bad_answer(gateway):
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    answer = run("base.assistant.report", EMPLOYEE, message_id="m1", reason="incorrect", comment="", question="q", answer="a")
    assert answer == {"sent": True, "duplicate": False}


def test_a_report_that_could_not_leave_says_so(gateway):
    gateway.reply("/internal/assistant/report", status=503, json={"error": {"code": "assistant.report_not_sent", "message": "x"}})
    with pytest.raises(OperationError) as caught:
        run("base.assistant.report", EMPLOYEE, message_id="m1", reason="other", answer="a")
    assert (caught.value.status, caught.value.code) == (503, "base.assistant_report_not_sent")


def test_a_dictation_becomes_text_and_nothing_runs(gateway):
    gateway.reply("/internal/speech/transcribe", json={"text": "crea el elemento Mesa 4", "language": "es"})
    text = run("base.assistant.transcribe", EMPLOYEE, audio="UklGRg==", mime_type="audio/webm", language="es")
    assert text == {"text": "crea el elemento Mesa 4", "language": "es"}
    assert "Mesa 4" not in items()


def test_a_dictation_too_long_is_said(gateway):
    gateway.reply("/internal/speech/transcribe", status=413, json={"error": {"code": "payload_too_large", "message": "x"}})
    with pytest.raises(OperationError) as caught:
        run("base.assistant.transcribe", EMPLOYEE, audio="UklGRg==", mime_type="audio/webm")
    assert (caught.value.status, caught.value.code) == (413, "base.assistant_audio_too_long")
