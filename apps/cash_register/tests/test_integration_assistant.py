"""Closing the drawer by asking the assistant (CASH_REGISTER-F09; PLAN §30, «Cinco acciones de IA pulidas», the
first: the cash count, with its summary before and its confirmation), against the Hub's real assistant turn
(``base.assistant.turn``): «cierra la caja con 250 € contados» offers the summary and the close; the summary
(``cash_register.session.closing_summary``) is a read, so it runs by itself and goes back to the model, with the
expected cash only for whoever may see it; the close is a dangerous write: it waits on its card, names the session
and the count, and closes only after the person types the word. Cancelling leaves the session open."""

import json

import pytest
from live.operations import get

from base import assistant
from apps.cash_register.models import Session
from apps.cash_register.tests.conftest import charge, ctx_for, open_session, run

pytestmark = pytest.mark.django_db

ASK = {"role": "user", "content": "cierra la caja con 250 € contados"}


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


def turn(*calls, role="hub_admin", decision=None, messages=None):
    """A turn of the assistant of a person with ``role``, in Spanish, answering the model's ``calls``."""
    data = {"messages": messages or [ASK, *([asked(*calls)] if calls else [])], "pending": list(calls), "decision": decision}
    return run("base.assistant.turn", data, ctx_for(role, language="es")).model_dump(mode="json")


def test_close_the_drawer_offers_the_summary_and_the_close():
    names = [tool["name"] for tool in turn()["tools"]]
    assert "cash_register__session__closing_summary" in names
    assert "cash_register__session__close" in names


def test_the_close_tells_the_assistant_to_read_its_summary_first_and_to_name_the_session():
    description = assistant.description(get("cash_register.session.close"))
    assert "cash_register.session.closing_summary" in description
    assert assistant.risk(get("cash_register.session.close")) == "high"
    # The summary is a read the assistant may run by itself: never a card, never a change.
    summary = get("cash_register.session.closing_summary")
    assert (summary.kind, assistant.is_tool(summary)) == ("query", True)


def test_the_summary_runs_by_itself_and_tells_the_model_the_session_the_count_the_expected_and_the_difference(coffee):
    session = open_session(10000)
    charge()
    plan = turn(call("cash_register.session.closing_summary", {"closing_balance": 25000}))
    assert plan["confirm"] is None
    assert [(row["name"], row["kind"], row["outcome"]) for row in plan["executed"]] == [
        ("cash_register.session.closing_summary", "query", "ok")
    ]
    told = json.loads(plan["append"][0]["content"])
    assert (told["number"], told["closing_balance"], told["expected_balance"], told["difference"]) == (
        session.number,
        25000,
        10150,
        14850,
    )
    assert Session.objects.get(pk=session.id).status == Session.Status.OPEN


def test_a_blind_count_keeps_the_expected_from_the_model_when_a_cashier_asks(coffee):
    # gh:cash_register#24, #84: the blind count cannot be opened by asking the assistant.
    run("cash_register.settings.update", {"require_blind_count": True})
    open_session(10000)
    charge()
    plan = turn(call("cash_register.session.closing_summary", {"closing_balance": 25000}), role="hub_employee")
    content = plan["append"][0]["content"]
    told = json.loads(content)
    assert (told["expected_balance"], told["difference"], told["expected_hidden"]) == (None, None, True)
    assert "10150" not in content and "14850" not in content


def test_with_the_count_required_the_summary_without_a_count_says_so_and_no_card_comes():
    open_session(10000)
    plan = turn(call("cash_register.session.closing_summary", {}))
    assert plan["confirm"] is None
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [
        ("error", "cash_register.closing_balance_required")
    ]


def test_the_close_waits_on_its_dangerous_card_naming_the_session_and_the_count():
    session = open_session(10000)
    close = call("cash_register.session.close", {"session": session.number, "closing_balance": 25000})
    plan = turn(close)
    card = plan["confirm"]
    assert (card["operation"], card["risk"], card["confirm_word"], card["blocked"]) == (
        "cash_register.session.close",
        "high",
        "CONFIRMAR",
        False,
    )
    assert [(field["name"], field["label"], field["kind"], field["value"]) for field in card["fields"]] == [
        ("session", "Session", "text", session.number),
        ("closing_balance", "Counted cash", "money", 25000),
    ]
    assert plan["pending"] == [close]
    assert Session.objects.get(pk=session.id).status == Session.Status.OPEN


def test_typing_the_word_closes_the_session_as_the_person_with_the_three_figures():
    session = open_session(10000)
    close = call("cash_register.session.close", {"session": session.number, "closing_balance": 25000})
    plan = turn(close, decision={"call_id": "c1", "accepted": True, "typed": " confirmar "})
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("ok", "")]
    closed = Session.objects.get(pk=session.id)
    assert (closed.status, closed.closing_balance, closed.expected_balance, closed.difference, closed.closed_by) == (
        Session.Status.CLOSED,
        25000,
        10000,
        15000,
        "tester",
    )


@pytest.mark.parametrize(
    "decision",
    [
        {"call_id": "c1", "accepted": False},
        {"call_id": "c1", "accepted": True, "typed": "sí"},
        {"call_id": "c1", "accepted": False, "stop": True},
    ],
    ids=["cancel", "wrong-word", "cancel-all"],
)
def test_without_the_word_the_session_stays_open(decision):
    session = open_session(10000)
    close = call("cash_register.session.close", {"session": session.number, "closing_balance": 25000})
    plan = turn(close, decision=decision)
    assert [row["outcome"] for row in plan["executed"]] == ["cancelled"]
    assert Session.objects.get(pk=session.id).status == Session.Status.OPEN


def test_a_session_closed_meanwhile_on_another_device_is_not_closed_twice_nor_another_one_closed():
    session = open_session(10000)
    close = call("cash_register.session.close", {"session": session.number, "closing_balance": 25000})
    # Between the card and the yes, another device closes it and opens the next shift.
    run("cash_register.session.close", {"closing_balance": 9000})
    later = open_session(5000)
    plan = turn(close, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"})
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("error", "cash_register.session_not_open")]
    assert Session.objects.get(pk=session.id).closing_balance == 9000
    assert Session.objects.get(pk=later.id).status == Session.Status.OPEN
