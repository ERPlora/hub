"""Closing the drawer by asking the assistant (CASH_REGISTER-F09; PLAN §30, «Cinco acciones de IA pulidas», the
first: the cash count, with its summary before and its confirmation), against the Hub's real assistant turn
(``base.assistant.turn``): «cierra la caja con 250 € contados» offers the summary and the close; the summary
(``cash_register.session.closing_summary``) is a read, so it runs by itself and goes back to the model, with the
expected cash only for whoever may see it; the close is a dangerous write: it waits on its card, names the session
and the count, and closes only after the person types the word. Cancelling leaves the session open."""

import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import get, registry

from base import assistant
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID
from apps.cash_register.models import Session
from apps.cash_register.tests.conftest import A, charge, ctx_for, open_session, run

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
    # The difference reaches the person's card marked signed, the rest not (the turn's schema dropped the mark:
    # FIX-HUB-BASE-ASSISTANT-CARD-POSITIVE-DIFFERENCE-WITHOUT-SIGN).
    assert [field["name"] for field in card["preview"] if field["signed"]] == ["difference"]
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


# ── The record a write names by its id, by its name (FIX-HUB-CASH_REGISTER-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS;
# base's half is hub#416) ──
# Since hub#416 the card leaves out an id its schema does not mark: «count the drawer», «take 5 € out», «close it»,
# «print its report», «open the bar» or «rename the bar» said no session and no drawer. Now the session is named by its
# number, as the sessions' list and every window of a shift say it («Arqueo de caja · S-…»), and the drawer by its name,
# as «Open session» and the drawers of the settings. Read as whoever asks, in the hub they ask in: never by the id, and
# left out when nobody, or somebody who may not see the sessions, is behind the request.

#: The writes that name a session by its id, with what each sends besides it, as the model would.
ON_A_SESSION = {
    "cash_register.count.add": {"total": 12000},
    "cash_register.movement.add": {"type": "out", "amount": 500, "description": "Proveedor"},
    "cash_register.session.close": {"closing_balance": 12000},
    "cash_register.session.print": {},
}
#: The writes that name a drawer by its id, with what each sends besides it.
ON_A_DRAWER = {
    "cash_register.session.open": {"opening_balance": 10000},
    "cash_register.register.update": {"name": "Terraza"},
}
#: The roles a business gives that work the till: the employee is the least of them.
TILL_ROLES = ("hub_employee", "hub_manager", "hub_admin", "hub_owner")


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def no_id(card: dict) -> bool:
    return not AN_ID.search(json.dumps(card, ensure_ascii=False))


def cards(ctx, writes: dict, datum: str, record, language: str = "es") -> dict:
    """The card of each of ``writes`` naming ``record`` by its id, as ``ctx``'s person would confirm it."""
    return {
        name: assistant.card(get(name), {datum: str(record), **besides}, language, ctx)
        for name, besides in writes.items()
    }


def may_run(role: str, name: str) -> bool:
    return ctx_for(role).has(get(name).permission)


@pytest.mark.parametrize(("language", "session_label"), [("es", "Sesión"), ("en", "Session")])
@pytest.mark.parametrize("role", TILL_ROLES)
def test_a_write_on_a_session_names_it_by_its_number(role, language, session_label):
    """«Cuenta la caja», «saca 5 €», «ciérrala», «imprime su informe»: the card says which session as the sessions' list
    does, by its number, never by its id — for every role that may run the write."""
    session = at_the_bar()
    said = cards(ctx_for(role, language=language), ON_A_SESSION, "session_id", session.id, language)
    assert {name: values(card).get("session_id") for name, card in said.items()} == dict.fromkeys(
        ON_A_SESSION, session.number
    )
    assert all(no_id(card) for card in said.values())
    assert {name: card["fields"][0]["label"] for name, card in said.items()} == dict.fromkeys(
        ON_A_SESSION, session_label
    )


@pytest.mark.parametrize(("language", "drawer_label"), [("es", "Cajón"), ("en", "Drawer")])
@pytest.mark.parametrize("role", TILL_ROLES)
def test_a_write_on_a_drawer_names_it_by_its_name(role, language, drawer_label):
    """«Abre la caja en la Barra», «llama Terraza a la Barra»: the card says which drawer by its name, as «Open session»
    and the drawers of the settings, never by its id — for every role that may run the write."""
    bar = run("cash_register.register.create", {"name": "Barra"})
    writes = {name: besides for name, besides in ON_A_DRAWER.items() if may_run(role, name)}
    assert "cash_register.session.open" in writes  # positive control: every till role opens the drawer
    said = cards(ctx_for(role, language=language), writes, "register_id", bar.id, language)
    assert {name: values(card).get("register_id") for name, card in said.items()} == dict.fromkeys(writes, "Barra")
    assert all(no_id(card) for card in said.values())
    assert {name: card["fields"][0]["label"] for name, card in said.items()} == dict.fromkeys(writes, drawer_label)


def test_renaming_a_drawer_by_its_id_says_the_old_name_and_the_new_one_apart():
    bar = run("cash_register.register.create", {"name": "Barra"})
    card = assistant.card(
        get("cash_register.register.update"),
        {"register_id": str(bar.id), "name": "Terraza", "is_active": True},
        "es",
        ctx_for(language="es"),
    )
    assert values(card) == {"register_id": "Barra", "name": "Terraza", "is_active": True}
    assert labels(card) == [
        SCREENS["open"]["register"],
        SCREENS["registers"]["modal"]["name"],
        SCREENS["registers"]["columns"]["active"],
    ]


def test_an_inactive_drawer_is_still_named_when_it_is_activated_again():
    bar = run("cash_register.register.create", {"name": "Barra"})
    run("cash_register.register.update", {"register_id": str(bar.id), "is_active": False})
    card = assistant.card(
        get("cash_register.register.update"), {"register_id": str(bar.id), "is_active": True}, "es", ctx_for()
    )
    assert values(card) == {"register_id": "Barra", "is_active": True}


def test_a_closed_session_is_named_when_its_report_is_printed():
    session = at_the_bar()
    run("cash_register.session.close", {"session_id": str(session.id), "closing_balance": 10000})
    card = assistant.card(get("cash_register.session.print"), {"session_id": str(session.id)}, "es", ctx_for())
    assert values(card) == {"session_id": session.number}


def test_with_a_blind_count_the_cashier_still_reads_which_session_the_card_names():
    # gh:cash_register#24, #84: the blind count hides the expected, never which session it is.
    run("cash_register.settings.update", {"require_blind_count": True})
    session = at_the_bar()
    said = cards(ctx_for("hub_employee", language="es"), ON_A_SESSION, "session_id", session.id)
    assert {name: values(card).get("session_id") for name, card in said.items()} == dict.fromkeys(
        ON_A_SESSION, session.number
    )


def test_whoever_may_run_a_write_reads_the_record_its_card_names():
    """The read runs as the person: a role that may run a write and not read what its card names would get a card with
    nothing to recognise, just in the common case. Every role a business gives, every write that names a record."""
    unread: list[tuple[str, str]] = []
    checked = 0
    for role in TILL_ROLES:
        mine = ctx_for(role)
        for name in (*ON_A_SESSION, *ON_A_DRAWER):
            op = get(name)
            if not mine.has(op.permission):
                continue
            schema = assistant._schema(op)
            for prop in schema.get("properties", {}).values():
                marked = assistant.refers_of(assistant._resolved(prop, schema.get("$defs", {})))
                if marked is not None:
                    checked += 1
                    if not mine.has(registry[marked["read"]].permission):
                        unread.append((role, name))
    # Positive control: the employee and the manager run five of the six writes, the admin and the owner all six.
    assert checked == 5 + 5 + 6 + 6
    assert unread == []


def test_nobody_behind_the_request_reads_no_session_nor_drawer():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    session = at_the_bar()
    bar = session.register_id
    for writes, datum, record in ((ON_A_SESSION, "session_id", session.id), (ON_A_DRAWER, "register_id", bar)):
        for name, card in cards(None, writes, datum, record).items():
            assert datum not in values(card) and no_id(card), name


def test_who_may_not_see_the_sessions_reads_none_of_them_on_the_card():
    """Whoever asks without «view sessions» (a key that only counts, say) gets the record left out, never its id."""
    session = at_the_bar()
    counter = OperationContext(
        scope=A, actor="tester", permissions=frozenset({"cash_register.add_count"}), language="es"
    )
    for writes, datum, record in (
        (ON_A_SESSION, "session_id", session.id),
        (ON_A_DRAWER, "register_id", session.register_id),
    ):
        for name, card in cards(counter, writes, datum, record).items():
            assert datum not in values(card) and no_id(card), name


def test_a_record_that_is_not_there_is_left_out_never_by_its_id():
    for writes, datum in ((ON_A_SESSION, "session_id"), (ON_A_DRAWER, "register_id")):
        for name, card in cards(ctx_for(), writes, datum, uuid.uuid7()).items():
            assert datum not in values(card) and no_id(card), name


@pytest.fixture
def no_fallback(monkeypatch):
    """As production: without ``use_hub`` a hub's model fails, nothing falls back on the shared database."""
    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_session_or_drawer_of_hub_b_is_never_named_on_a_card_of_hub_a(hub_a, hub_b, no_fallback):
    """The read runs in the hub the person asks in: hub B's session or drawer is nobody in hub A."""
    in_b = ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_b):
        bar = run("cash_register.register.create", {"name": "Barra B"}, in_b)
        session = run("cash_register.session.open", {"opening_balance": 0, "register_id": str(bar.id)}, in_b)
        named_in_b = (
            assistant.card(get("cash_register.count.add"), {"session_id": str(session.id), "total": 1}, "es", in_b),
            assistant.card(get("cash_register.session.open"), {"register_id": str(bar.id)}, "es", in_b),
        )
    in_a = ctx_for(scope=Scope("host", hub_a.slug))
    with use_hub(hub_a):
        said = (
            assistant.card(get("cash_register.count.add"), {"session_id": str(session.id), "total": 1}, "es", in_a),
            assistant.card(get("cash_register.session.open"), {"register_id": str(bar.id)}, "es", in_a),
        )
    assert [("session_id" in values(card), "register_id" in values(card), no_id(card)) for card in said] == [
        (False, False, True),
        (False, False, True),
    ]
    # Positive control: in hub B the same cards name them.
    assert (values(named_in_b[0])["session_id"], values(named_in_b[1])["register_id"]) == (session.number, "Barra B")
