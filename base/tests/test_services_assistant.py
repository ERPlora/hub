"""The assistant's operations (APP-BASE-9): ``base.assistant.turn`` prepares a turn — it runs the reads the model
asked for, shows a write's card and runs it only with the person's yes, as the person —, and ``base.assistant.usage``,
``base.assistant.report`` and ``base.assistant.transcribe`` go to erplora.com's gateway (``fake_gateway``).
"""

import dataclasses
import json
from datetime import datetime

import pytest
from django.db import connections
from live.context import OperationContext, Scope
from live.errors import OperationError, Unauthorized
from live.operations import Operation, get, registry
from ninja import Schema

from base import assistant
from base.models import Hub, Membership
from base.tenancy import context
from base.tenancy.tests import hubs
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture
from base.tests.test_assistant import SECRET_SET, PricedPreviewOut, count_preview, declaring
from base.tests.test_assistant import settle  # noqa: F401 - the fixture: a dangerous write with its preview

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
    # The business's currency with its decimals: an amount in its minor unit
    # (FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY).
    assert "17.00 EUR → 1700" in plan["instructions"] and "`currency_decimals`" in plan["instructions"]


def test_the_instructions_take_the_decimals_of_the_business_currency_not_two():
    """FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY: a yen business has no cents, so its turn
    tells the model «17 JPY → 17» (``base.business.get``'s ``currency_decimals``), never a fixed «.00 → 1700»;
    the card's money carries the same decimals."""
    Hub.objects.filter(slug="a").update(country="JP")
    plan = turn(call("demo.item.create", {"name": "Mesa 4"}))
    assert "17 JPY → 17" in plan["instructions"]
    assert plan["confirm"]["money"] == {"currency": "JPY", "decimals": 0}


# ── Reads run by themselves (BASE-G115) ──────────────────────────────────────────────────────────────────────────


def test_a_read_the_model_asked_for_runs_alone_and_its_result_goes_back():
    run("demo.item.create", name="Terraza")
    plan = turn(call("demo.item.list", {}))
    [result] = plan["append"]
    assert (result["role"], result["tool_call_id"]) == ("tool", "c1")
    assert "Terraza" in result["content"]
    assert plan["executed"] == [
        {
            "call_id": "c1",
            "name": "demo.item.list",
            "app": "demo",
            "app_name": "Demo",
            "screen": "",
            "kind": "query",
            "outcome": "ok",
            "code": "",
        }
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


def test_a_write_its_operation_would_refuse_shows_no_card_and_the_model_hears_what_to_correct():
    """live#17 (QA 2026-10-31, A2.12): a card said what its write would refuse, the person typed the word, the write
    failed and the model asked again: two cards for one change. The data are checked before any card is drawn; the
    model hears which do not fit, field by field, and asks again with them corrected."""
    plan = turn(call("demo.item.create", {"name": "Mesa 4", "status": "abierto"}))
    assert plan["confirm"] is None
    assert plan["pending"] == []
    assert (plan["executed"][0]["outcome"], plan["executed"][0]["code"]) == ("error", "invalid_payload")
    assert set(json.loads(plan["append"][0]["content"])["error"]["fields"]) == {"status"}
    assert "Mesa 4" not in items()
    corrected = turn(call("demo.item.create", {"name": "Mesa 4", "status": "open"}))
    assert corrected["confirm"]["operation"] == "demo.item.create"


def test_the_card_carries_the_business_currency_for_its_amounts():
    """gh:hub#1045: an amount in cents is painted in the business's currency, with its decimals."""
    plan = turn(call("demo.item.create", {"name": "Mesa 4"}))
    assert plan["confirm"]["money"] == {"currency": "EUR", "decimals": 2}


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
    wrong = turn(delete, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMA"})
    assert wrong["executed"][0]["outcome"] == "cancelled"
    assert "Barra" in items()
    right = turn(delete, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"})
    assert right["executed"][0]["outcome"] == "ok"
    assert "Barra" not in items()


def test_a_secret_reaches_the_browser_hidden_on_its_card_and_its_write_as_typed(monkeypatch):
    """FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-SECRETSTR-IN-CLEAR: the card the browser receives (and keeps while it waits)
    never carries a secret as typed; the yes runs the write with it."""
    received = []
    secret_set = dataclasses.replace(
        SECRET_SET, fn=lambda ctx, data: received.append(data.value.get_secret_value()) or {"name": data.name}
    )
    monkeypatch.setitem(registry, secret_set.name, secret_set)
    write = call(secret_set.name, {"name": "Banco", "value": "hunter2"})
    asked_card = turn(write)["confirm"]
    assert asked_card["operation"] == secret_set.name
    assert "hunter2" not in json.dumps(asked_card, ensure_ascii=False)
    plan = turn(write, decision={"call_id": "c1", "accepted": True})
    assert plan["executed"][0]["outcome"] == "ok"
    assert received == ["hunter2"]


# ── What a dangerous write will do, on its card (BASE-F98) ───────────────────────────────────────────────────────


def test_a_dangerous_card_carries_what_its_app_says_it_will_do_read_as_the_person(settle):
    """FIX-HUB-BASE-ASSISTANT-HIGH-RISK-CARD-NO-OPERATION-PREVIEW: the expected cash of a close, the invoice a
    rectification issues… inside the card, before the word is typed; what the read hides is not there."""
    plan = turn(call("demo.item.settle", {"id": "7", "reason": "cierre"}))
    card = plan["confirm"]
    assert (card["operation"], card["confirm_word"], card["money"]) == ("demo.item.settle", "CONFIRMAR", {"currency": "EUR", "decimals": 2})
    assert [(field["name"], field["kind"], field["value"]) for field in card["preview"]] == [
        ("asked_by", "text", "ana"),
        ("name", "text", "Item 7"),
        ("total_cents", "money", 4200),
    ]
    assert (plan["executed"], plan["append"]) == ([], [])


def test_an_amount_its_preview_declares_signed_reaches_the_card_marked_so_and_no_other_does(monkeypatch):
    """FIX-HUB-BASE-ASSISTANT-CARD-POSITIVE-DIFFERENCE-WITHOUT-SIGN: the turn's card dropped the mark on its way out
    (its schema had no place for it), so a difference over still came without its «+»."""
    read = count_preview({"expected_balance": 11210, "difference": 13790})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, "demo.item.settle", declaring({"operation": read.name, "fields": ["expected_balance", "difference"]}))
    card = turn(call("demo.item.settle", {"id": "7", "reason": "cierre"}))["confirm"]
    assert [(field["name"], field["kind"], field["value"], field["signed"]) for field in card["preview"]] == [
        ("expected_balance", "money", 11210, False),
        ("difference", "money", 13790, True),
    ]
    assert [field["signed"] for field in card["fields"]] == [False, False]


def test_an_amount_of_a_preview_reaches_the_card_in_the_currency_its_read_answers(monkeypatch):
    """FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY: the turn's card keeps the currency of each
    amount of the preview (the read's, here złoty) beside the business's (euros) for what the write sends."""
    read = count_preview(
        {"note": "R1", "total_cents": -12100, "difference": 4200, "currency": "PLN", "currency_decimals": 2},
        PricedPreviewOut,
    )
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, "demo.item.settle", declaring({"operation": read.name, "fields": ["note", "total_cents", "difference"]}))
    card = turn(call("demo.item.settle", {"id": "7", "reason": "cierre"}))["confirm"]
    pln = {"currency": "PLN", "decimals": 2}
    assert card["money"] == {"currency": "EUR", "decimals": 2}
    assert [(field["name"], field["kind"], field["signed"], field["money"]) for field in card["preview"]] == [
        ("note", "text", False, None),
        ("total_cents", "money", False, pln),
        ("difference", "money", True, pln),
    ]
    assert [field["money"] for field in card["fields"]] == [None, None]


class ListedIn(Schema):
    starts: list[datetime]
    codes: list[str]


LISTED = Operation(
    name="demo.item.settle",
    kind="command",
    permission="demo.manage",
    input=ListedIn,
    output=ListedIn,
    expose_api=False,
    ai={"description": "Books a demo item on several days."},
    fn=lambda ctx, data: data,
)


def test_a_list_said_item_by_item_reaches_the_card_marked_named_and_one_of_codes_does_not(monkeypatch):
    """FIX-HUB-PRINTING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS: the turn's card dropped the mark on its way out (its
    schema had no place for it), so the printers of a device, named on the server, reached the screen as «2 items»; a
    list of codes nobody names keeps saying how many."""
    monkeypatch.setitem(registry, LISTED.name, LISTED)
    arguments = {"starts": ["2026-11-02T09:00:00Z", "2026-11-09T09:00:00Z"], "codes": ["sale.sale.create"]}
    card = turn(call(LISTED.name, arguments))["confirm"]
    assert [(field["name"], field["kind"], field["named"]) for field in card["fields"]] == [
        ("starts", "list", True),
        ("codes", "list", False),
    ]


def test_a_card_whose_app_declares_no_preview_is_as_before():
    created = run("demo.item.create", name="Barra")
    assert turn(call("demo.item.delete", {"id": created["id"]}))["confirm"]["preview"] is None


def test_a_preview_that_cannot_be_read_shows_no_card_does_nothing_and_says_why(settle):
    """Nothing is confirmed blind: the write is not done, its receipt says it failed, and the model hears why (the
    read's own error) to tell the person, as when the write itself refuses."""
    plan = turn(call("demo.item.settle", {"id": "gone"}))
    assert (plan["confirm"], plan["pending"]) == (None, [])
    [row] = plan["executed"]
    assert (row["name"], row["kind"], row["outcome"], row["code"]) == ("demo.item.settle", "command", "error", "demo.item_not_found")
    assert json.loads(plan["append"][0]["content"])["error"]["message"] == "This item is not there any more."


def test_a_preview_the_person_may_not_read_shows_no_card(settle):
    plan = turn(call("demo.item.settle", {"id": "7"}), permissions={"base.view_home", "demo.manage"})
    assert plan["confirm"] is None
    assert (plan["executed"][0]["outcome"], plan["executed"][0]["code"]) == ("refused", "permission_denied")


def test_taking_a_pin_away_names_whose_it_is(make_user):
    """Base's own: the card of «Remove the PIN» named the person by the id the model sent («saas:3»)."""
    make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva", last_name="Gil", email="eva@example.com")
    admin = {"base.view_home", "base.administer_hub"}
    card = turn(call("base.person.pin_remove", {"person": "saas:3"}), permissions=admin)["confirm"]
    assert {field["name"]: field["value"] for field in card["preview"]} == {"name": "Eva Gil", "email": "eva@example.com"}


@pytest.mark.parametrize("name", ["base.app.enable", "base.app.disable"])
def test_turning_an_app_on_or_off_names_it_on_its_card(name):
    """B28c (hub#539): «Activa la app de reservas» showed «online_booking», and Reservas online was the one confirmed."""
    admin = {"base.view_home", "base.administer_hub"}
    plan = turn(call(name, {"app": "online_booking"}), permissions=admin)
    assert [(field["name"], field["value"]) for field in plan["confirm"]["fields"]] == [("app", "Reservas online")]
    assert plan["executed"] == []


@pytest.mark.parametrize("name", ["base.app.enable", "base.app.disable"])
def test_a_name_that_fits_several_apps_shows_no_card_and_the_model_asks_which(name):
    """«reserva» is Reservas and Reservas online: nothing to confirm blind; the model hears both names to ask."""
    admin = {"base.view_home", "base.administer_hub"}
    plan = turn(call(name, {"app": "reserva"}), permissions=admin)
    assert (plan["confirm"], plan["pending"]) == (None, [])
    [row] = plan["executed"]
    assert (row["name"], row["outcome"], row["code"]) == (name, "error", "base.app_ambiguous")
    said = json.loads(plan["append"][0]["content"])["error"]["message"]
    assert "Reservas online" in said and "Reservas," in said


@pytest.mark.parametrize("name", ["base.app.enable", "base.app.disable"])
def test_a_name_that_is_no_apps_shows_no_card(name):
    """A name of no app put an empty card up, and the yes ended in a 404: it goes back to the model before any card."""
    admin = {"base.view_home", "base.administer_hub"}
    plan = turn(call(name, {"app": "nope"}), permissions=admin)
    assert (plan["confirm"], plan["pending"]) == (None, [])
    [row] = plan["executed"]
    assert (row["name"], row["outcome"], row["code"]) == (name, "error", "not_found")


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


def test_the_receipt_names_where_it_happened_in_the_persons_language():
    """The receipt under the answer says it as the card does: an app by its name, the platform by its screen («No se
    hizo, cancelado: Cambiar en Ajustes»), never «Base» (FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH)."""
    pin = call("base.access.settings_update", {"pin_length": 6})
    plan = turn(pin, decision={"call_id": "c1", "accepted": False}, permissions={"base.view_home", "base.administer_hub"})
    assert (plan["executed"][0]["outcome"], plan["executed"][0]["app_name"]) == ("cancelled", "Ajustes")
    written = turn(call("demo.item.create", {"name": "Mesa 4"}), decision={"call_id": "c1", "accepted": True})
    assert written["executed"][0]["app_name"] == "Demo"


def test_the_receipt_carries_the_platforms_screen_by_its_key_for_the_screen_to_name_it_in_its_own_language():
    """FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY (seen on its e2e): a receipt kept from a turn
    in English, read once the person had switched to Spanish, said «No se hizo, cancelado: Rectificar en Invoicing» —
    its name came written in the turn's language. The platform's screen goes by its key too (``screen``), the one the
    screen names in its own language; an app's, none (its menu names it)."""
    admin = {"base.view_home", "base.administer_hub"}
    pin = turn(call("base.access.settings_update", {"pin_length": 6}), decision={"call_id": "c1", "accepted": False}, permissions=admin)
    assert (pin["executed"][0]["app"], pin["executed"][0]["screen"]) == ("base", "settings")
    written = turn(call("demo.item.create", {"name": "Mesa 4"}), decision={"call_id": "c1", "accepted": True})
    assert (written["executed"][0]["app"], written["executed"][0]["screen"]) == ("demo", "")


def test_a_tool_that_does_not_exist_is_refused_with_its_own_name():
    plan = turn({"call_id": "c1", "name": "demo__item__explode", "arguments": "{}"}, permissions=EMPLOYEE)
    assert (plan["executed"][0]["name"], plan["executed"][0]["app"], plan["executed"][0]["kind"]) == ("demo__item__explode", "", "")


def test_a_tool_this_person_was_not_offered_is_refused_and_writes_nothing():
    write = call("demo.item.create", {"name": "Mesa 4"})
    plan = turn(write, decision={"call_id": "c1", "accepted": True}, permissions=EMPLOYEE)
    assert (plan["executed"][0]["outcome"], plan["executed"][0]["code"]) == ("refused", "not_available")
    # The receipt names what was refused, as the person's panel says it («Not done, not allowed: Create in Demo»).
    assert (plan["executed"][0]["name"], plan["executed"][0]["app"], plan["executed"][0]["kind"]) == (
        "demo.item.create",
        "demo",
        "command",
    )
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


# ── A dangerous write that names no record never runs, whatever the browser answers (BASE-G116) ──────────────────


def test_a_blocked_write_does_not_run_even_with_a_yes_and_the_word_typed():
    """The card said «not from the chat»; a yes with the word typed (a browser that ignores ``blocked``) runs nothing."""
    permissions = frozenset({"base.view_home", "appointment.*"})
    delete_all = call("appointment.appointment.bulk_delete", {"ids": []})
    card = turn(delete_all, permissions=permissions)["confirm"]
    assert card["blocked"] is True
    plan = turn(delete_all, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"}, permissions=permissions)
    assert (plan["executed"][0]["outcome"], plan["executed"][0]["code"]) == ("cancelled", "base.assistant_not_from_chat")
    assert json.loads(plan["append"][0]["content"])["error"]["code"] == "base.assistant_not_from_chat"
    assert plan["confirm"] is None


# ── The screens the assistant may link are the person's (BASE-G114, G118) ────────────────────────────────────────


def test_the_system_screen_is_linked_only_to_who_administers():
    assert "](/system)" in run("base.assistant.turn", {"base.view_home", "base.administer_hub"}, messages=[ASK])["instructions"]
    assert "/system" not in run("base.assistant.turn", EMPLOYEE, messages=[ASK])["instructions"]


def test_the_files_screen_is_linked_to_who_sees_the_files():
    """BASE-F72 (APP-BASE-8): «Files» is a screen of the platform; the old panel could name it but never link it."""
    text = run("base.assistant.turn", {"base.view_home", "base.view_files"}, messages=[ASK])["instructions"]
    assert "[Archivos](/files)" in text
    assert "/files" not in run("base.assistant.turn", EMPLOYEE, messages=[ASK])["instructions"]



def test_the_employees_screen_is_linked_as_the_menu_shows_it():
    """APP-BASE-5 (BASE-F77…F91): «Employees» is in everybody's menu, so the assistant may link it to everybody."""
    assert "[Empleados](/employees)" in run("base.assistant.turn", EMPLOYEE, messages=[ASK])["instructions"]

# ── What waits on erplora.com holds no transaction meanwhile (BASE-G122, G123, G112; rv-hub-247) ──────────────────

GATEWAY_CALLS = [
    ("base.assistant.usage", "/internal/assistant/usage", {"used": 1, "limit": 30, "resets_at": None, "demo": False}, {}),
    (
        "base.assistant.report",
        "/internal/assistant/report",
        {"sent": True, "duplicate": False},
        {"message_id": "m1", "reason": "incorrect", "answer": "a"},
    ),
    (
        "base.assistant.transcribe",
        "/internal/speech/transcribe",
        {"text": "hola", "language": "es"},
        {"audio": "UklGRg==", "mime_type": "audio/webm"},
    ),
]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("operation_name", "path", "answer", "data"), GATEWAY_CALLS)
def test_waiting_for_erplora_com_holds_no_transaction(gateway, monkeypatch, operation_name, path, answer, data):
    """Up to 15 s of waiting inside a transaction would hold the hub's connection (and, on the Free plan, its one
    transaction at a time: PLAN §14.2), so the till would wait too: while the gateway answers, none is open."""
    gateway.reply(path, json=answer)
    seen = []
    post = assistant._post

    def probe(*args, **kwargs):
        seen.append(any(connection.in_atomic_block for connection in connections.all()))
        return post(*args, **kwargs)

    monkeypatch.setattr(assistant, "_post", probe)
    run(operation_name, EMPLOYEE, **data)
    assert seen == [False]


def test_a_turn_reads_the_hubs_own_words():
    """In the Hub a «cuenta» is a table's open check (``base.assistant.SYNONYMS``): the turn offers the read of a check
    among its first tools, as the assistant's QA ranks it (base/tests/test_assistant_asks.py), never at 14."""
    asked = {"role": "user", "content": "¿qué hay en la cuenta de la mesa 6?"}
    plan = run("base.assistant.turn", {"*"}, messages=[asked])
    assert assistant.tool_name("sale.order.get") in [tool["name"] for tool in plan["tools"]][:10]
