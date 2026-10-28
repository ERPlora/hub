"""Closing the drawer by asking the assistant (CASH_REGISTER-F09; PLAN §30, «Cinco acciones de IA pulidas», the
first: the cash count, with its summary before and its confirmation), against the Hub's real assistant turn
(``base.assistant.turn``): «cierra la caja con 250 € contados» offers the summary and the close; the summary
(``cash_register.session.closing_summary``) is a read, so it runs by itself and goes back to the model, with the
expected cash only for whoever may see it; the close is a dangerous write: it waits on its card, names the session
and the count, and closes only after the person types the word. Cancelling leaves the session open."""

import json
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen
from apps.cash_register.models import Session
from apps.cash_register.tests.conftest import charge, ctx_for, open_session, run

pytestmark = pytest.mark.django_db

ASK = {"role": "user", "content": "cierra la caja con 250 € contados"}

SCREENS = json.loads(
    (Path(apps.get_app_config("cash_register").path) / "frontend/locale/es.json").read_text()
)["cash_register"]


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
    # In the person's language, Spanish here (FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH).
    assert [(field["name"], field["label"], field["kind"], field["value"]) for field in card["fields"]] == [
        ("session", "Sesión", "text", session.number),
        ("closing_balance", "Efectivo contado", "money", 25000),
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


# ── How the card names the data (FIX-HUB-CASH_REGISTER-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258) ──


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def cash_register_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "cash_register" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_cash_register_reaches_a_spanish_card_by_its_technical_name():
    """Every write of cash_register the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the title pydantic makes up from the field («Register Name»)."""
    screen = named_by_the_screen()
    writes = cash_register_writes()
    assert len(writes) > 5  # positive control: the registry has cash_register's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            name, label = field["name"], field["label"]
            if name not in screen and label == name.title().replace("_", " "):
                technical.setdefault(op.name, []).append(name)
    assert technical == {}


@pytest.mark.parametrize("name", ["cash_register.register.update", "cash_register.session.open"])
def test_the_card_names_a_drawer_named_by_its_name_as_the_screens_do(name):
    """The drawer the person names by its name is «Cajón», as the drawers of the settings and «Open session» say."""
    assert labels(assistant.card(get(name), {"register_name": "Barra"}, "es")) == [SCREENS["open"]["register"]]
    assert labels(assistant.card(get(name), {"register_name": "Bar"}, "en")) == ["Drawer"]


def test_renaming_a_drawer_names_the_drawer_and_its_new_name_apart():
    arguments = {"register_name": "Barra", "name": "Terraza", "is_active": True}
    card = assistant.card(get("cash_register.register.update"), arguments, "es")
    assert labels(card) == [
        SCREENS["open"]["register"],
        SCREENS["registers"]["modal"]["name"],
        SCREENS["registers"]["columns"]["active"],
    ]


# ── What closing will do, on its card (FIX-HUB-CASH_REGISTER-ASSISTANT-CLOSE-CARD-WITHOUT-PREVIEW; BASE-F98's hook) ──
# The card of the close listed only what it sends (the session and the counted cash), never what closing gives: the
# expected and the difference were said only in the chat, before the card. Through base's hook it shows, before the
# word is typed, what cash_register.session.closing_summary answers for the person: the session's number, its drawer,
# the expected cash and the difference, as money. Whoever a blind count hides the expected from gets neither.

PREVIEWED = ["number", "register_name", "expected_balance", "difference"]

SCREENS_EN = json.loads(
    (Path(apps.get_app_config("cash_register").path) / "frontend/locale/en.json").read_text()
)["cash_register"]


def close_preview(arguments, *, role="hub_admin", language="es", ctx=None):
    return assistant.preview(ctx or ctx_for(role, language=language), get("cash_register.session.close"), arguments)


def card_labels(screens: dict) -> list[str]:
    """The four data by the names the Cash register screens give them: the sessions' list, «Open session» and the
    «Close session» window."""
    return [
        screens["sessions"]["columns"]["number"],
        screens["open"]["register"],
        screens["close"]["expected"],
        screens["close"]["difference"],
    ]


def at_the_bar(opening_balance: int = 10000):
    """A shift open on the drawer «Barra»."""
    bar = run("cash_register.register.create", {"name": "Barra"})
    return open_session(opening_balance, register_id=str(bar.id))


@pytest.mark.parametrize(("counted", "difference"), [(25000, 14850), (10000, -150)], ids=["over", "short"])
def test_the_close_card_shows_the_session_its_drawer_the_expected_and_the_difference_as_money(coffee, counted, difference):
    session = at_the_bar(10000)
    charge()
    failure, preview = close_preview({"session": session.number, "closing_balance": counted})
    assert failure is None
    # The counted cash is not repeated: the card already lists it from what the close sends.
    assert [(field["name"], field["kind"], field["value"]) for field in preview] == [
        ("number", "text", session.number),
        ("register_name", "text", "Barra"),
        ("expected_balance", "money", 10150),
        ("difference", "money", difference),
    ]
    # The difference with its sign, as the screens write it (FIX-HUB-BASE-ASSISTANT-CARD-POSITIVE-DIFFERENCE-WITHOUT-SIGN):
    # over or short at a glance; the expected cash is an amount like any other.
    assert [field["name"] for field in preview if field.get("signed")] == ["difference"]
    assert [field["label"] for field in preview] == card_labels(SCREENS)
    assert [field["label"] for field in close_preview({"closing_balance": counted}, language="en")[1]] == card_labels(
        SCREENS_EN
    )
    assert assistant.preview_of(get("cash_register.session.close"))["fields"] == PREVIEWED


def test_the_card_the_person_sees_carries_that_preview_and_closes_nothing(coffee):
    session = at_the_bar(10000)
    charge()
    plan = turn(call("cash_register.session.close", {"session": session.number, "closing_balance": 25000}))
    card = plan["confirm"]
    assert (card["operation"], card["confirm_word"]) == ("cash_register.session.close", "CONFIRMAR")
    assert [(field["name"], field["value"]) for field in card["preview"]] == [
        ("number", session.number),
        ("register_name", "Barra"),
        ("expected_balance", 10150),
        ("difference", 14850),
    ]
    assert Session.objects.get(pk=session.id).status == Session.Status.OPEN


def test_with_a_blind_count_the_cashiers_card_shows_neither_the_expected_nor_the_difference(coffee):
    # gh:cash_register#24, #84: the card never opens the blind count either.
    run("cash_register.settings.update", {"require_blind_count": True})
    session = at_the_bar(10000)
    charge()
    failure, preview = close_preview({"session": session.number, "closing_balance": 25000}, role="hub_employee")
    assert failure is None
    assert [(field["name"], field["value"]) for field in preview] == [
        ("number", session.number),
        ("register_name", "Barra"),
    ]
    plan = turn(call("cash_register.session.close", {"closing_balance": 25000}), role="hub_employee")
    assert [field["name"] for field in plan["confirm"]["preview"]] == ["number", "register_name"]
    assert "10150" not in json.dumps(plan) and "14850" not in json.dumps(plan)
    # Whoever may see the expected still gets it on the card.
    assert [field["name"] for field in close_preview({"closing_balance": 25000}, role="hub_manager")[1]] == PREVIEWED


def test_with_the_count_required_a_close_without_a_count_gets_no_card_and_hears_why():
    open_session(10000)
    failure, preview = close_preview({})
    assert (failure.outcome, failure.code, preview) == ("error", "cash_register.closing_balance_required", None)
    plan = turn(call("cash_register.session.close", {}))
    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [
        ("error", "cash_register.closing_balance_required")
    ]
    assert Session.objects.get().status == Session.Status.OPEN


def test_a_session_without_a_drawer_shows_no_drawer(coffee):
    session = open_session(10000)
    charge()
    _, preview = close_preview({"closing_balance": 25000})
    assert [(field["name"], field["value"]) for field in preview] == [
        ("number", session.number),
        ("expected_balance", 10150),
        ("difference", 14850),
    ]


def test_without_the_permission_to_close_there_is_no_preview_nor_card():
    open_session(10000)
    cannot = ctx_for("hub_employee", language="es")
    cannot = cannot.__class__(
        scope=cannot.scope,
        actor=cannot.actor,
        permissions=cannot.permissions - {"cash_register.close_session"},
        language="es",
    )
    failure, preview = close_preview({"closing_balance": 25000}, ctx=cannot)
    assert (failure.outcome, preview) == ("refused", None)
