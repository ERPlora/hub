"""The Hub's assistant without the ORM (``base/assistant.py``, APP-BASE-9; PLAN §30): which operations are its tools
for this person, the few it offers in a turn, how a write is shown before it runs, how a tool runs as the person, and
the signed calls to erplora.com's gateway (``/internal/assistant/*``, ``/internal/speech/transcribe``).

The gateway is ``fake_gateway.FakeGateway``: a real HTTP server on 127.0.0.1 that answers in the gateway's contract.
"""

import asyncio
import json
import re
from collections.abc import Iterable
from pathlib import Path

import pytest
from django.conf import settings
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.operations import Operation, get, registry
from ninja import Field, Schema

from base import assistant, entitlement
from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

A = Scope("host", "a")
MANAGER = frozenset({"base.view_home", "demo.*"})
EMPLOYEE = frozenset({"base.view_home", "demo.view"})


def ctx(permissions=MANAGER, *, actor="ana", language="en", scope=A):
    return OperationContext(scope=scope, actor=actor, permissions=frozenset(permissions), language=language)



# ── Tools: what the assistant may use for this person (BASE-G118; gh:hub#11) ─────────────────────────────────────


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_a_tool_is_named_without_dots_and_read_back_from_its_name():
    assert assistant.tool_name("cash_register.session.close") == "cash_register__session__close"
    tools = assistant.catalog(ctx({"*"}))
    assert assistant.operation_of("demo__item__create", tools).name == "demo.item.create"
    assert assistant.operation_of("demo__item__nothing", tools) is None


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_tools_are_the_operations_this_person_may_use_and_nothing_else():
    names = set(assistant.catalog(ctx(EMPLOYEE)))
    assert "demo.item.list" in names
    # Without «demo.manage» the write is not even offered (the old hub's: as if it did not exist).
    assert "demo.item.create" not in names
    assert "base.access.settings_update" not in names


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    "name, why",
    [
        ("base.pin.set", "«Not an assistant tool»: a PIN is typed on the pad"),
        ("base.hub.reset", "never from the chat: it empties the business"),
        ("base.app.list", "no description for the assistant"),
        ("base.demo.create", "the system's (no permission declared)"),
    ],
)
def test_what_is_not_a_tool_is_never_offered_even_to_who_may_do_everything(name, why):
    assert name not in assistant.catalog(ctx({"*"})), why


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_an_app_the_business_has_no_right_to_offers_no_tool(monkeypatch):
    monkeypatch.setattr(entitlement, "blocked_apps", lambda scope: frozenset({"demo"}))
    assert not [name for name in assistant.catalog(ctx({"*"})) if name.startswith("demo.")]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_assistants_own_operations_are_not_its_tools():
    assert not [name for name in assistant.catalog(ctx({"*"})) if name.startswith("base.assistant.")]


# ── By relevance: a turn offers the tools of what was asked, never the whole catalogue (PLAN §30) ─────────────────


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_a_turn_offers_at_most_its_share_of_the_catalogue():
    tools = assistant.catalog(ctx({"*"}))
    assert len(tools) > assistant.MAX_TOOLS
    assert len(assistant.relevant(tools, ["hola"], "es")) <= assistant.MAX_TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_app_named_in_the_persons_own_language_comes_first():
    tools = assistant.catalog(ctx({"*"}))
    offered = assistant.relevant(tools, ["¿Cuántos clientes tengo este mes?"], "es")
    # After the two reads always at hand (``ALWAYS``), the app the person named.
    first = [op.name for op in offered if op.name not in assistant.ALWAYS][:5]
    assert first and all(name.startswith("customer.") for name in first), first
    assert "customer.customer.list" in first


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_what_the_person_asks_to_do_ranks_the_operation_that_does_it():
    tools = assistant.catalog(ctx({"*"}))
    offered = [op.name for op in assistant.relevant(tools, ["crea un servicio Corte caballero a 15 €"], "es")]
    assert "service.service.create" in offered


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_version_of_erplora_is_at_hand_for_who_runs_the_business():
    """gh:hub#1044: asked «what version of ERPlora do I have?», the old assistant said there was none."""
    tools = assistant.catalog(ctx({"base.view_home", "base.administer_hub"}))
    offered = [op.name for op in assistant.relevant(tools, ["¿Qué versión de ERPlora tengo?"], "es")]
    assert "base.system.status" in offered
    assert "base.system.status" not in assistant.catalog(ctx(EMPLOYEE))


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_checklist_read_is_always_at_hand():
    tools = assistant.catalog(ctx({"*"}))
    assert "base.setup.status" in [op.name for op in assistant.relevant(tools, ["zzz"], "es")]


def test_a_tool_is_offered_in_the_gateways_format():
    spec = assistant.tool_spec(get("demo.item.create"))
    assert spec["type"] == "function"
    assert spec["name"] == "demo__item__create"
    assert spec["description"].startswith("Creates a demo item")
    assert spec["parameters"]["properties"]["name"]["type"] == "string"


# ── The card of a write (BASE-G115, G116; gh:hub#1045) ───────────────────────────────────────────────────────────


def test_a_normal_write_asks_a_click_and_shows_what_it_will_send():
    card = assistant.card(get("demo.item.create"), {"name": "Mesa 4", "note": None}, "es")
    assert (card["risk"], card["confirm_word"], card["blocked"]) == ("normal", "", False)
    assert card["app"] == "demo"
    fields = {field["name"]: field for field in card["fields"]}
    assert fields["name"] == {**fields["name"], "kind": "text", "value": "Mesa 4"}
    assert fields["note"]["kind"] == "empty"


def test_an_amount_in_cents_is_marked_as_money_for_the_card():
    card = assistant.card(get("service.service.create"), {"name": "Corte", "price": 1500}, "es")
    price = next(field for field in card["fields"] if field["name"] == "price")
    assert (price["kind"], price["value"]) == ("money", 1500)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def test_every_datum_of_the_card_is_named_in_the_persons_language():
    """gh:hub#1040, FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH: a datum the screen does not name itself
    (``assistant-card.ts`` ``FIELDS``) went by its schema's English title, in Spanish too («Session»,
    «Counted cash»)."""
    close = get("cash_register.session.close")
    arguments = {"session": "S-1", "closing_balance": 25000}
    assert labels(assistant.card(close, arguments, "es")) == ["Sesión", "Efectivo contado"]
    assert labels(assistant.card(close, arguments, "en")) == ["Session", "Counted cash"]
    pin = assistant.card(get("base.access.settings_update"), {"pin_inactivity_minutes": 10, "pin_length": 6}, "es")
    assert labels(pin) == ["Volver a pedir tras (minutos)", "Dígitos del PIN"]


def test_a_datum_is_named_by_the_model_of_its_operation_before_another_of_its_app():
    """Two models of an app may name a field of the same name differently: the operation's entity says which."""
    assert labels(assistant.card(get("base.device.mode_set"), {"mode": "kiosk"}, "es")) == ["Modo"]
    assert labels(assistant.card(get("base.api_key.create"), {"mode": "read"}, "es")) == ["Qué puede hacer"]


class TitledIn(Schema):
    first_name: str = Field(title="Owner")
    last_name: str = Field(title="Family name")


TITLED = Operation(
    name="base.profile.titled",
    kind="command",
    permission="base.view_home",
    input=TitledIn,
    output=TitledIn,
    expose_api=False,
    ai={"description": "A write whose schema titles its data.", "risk": "high"},
    fn=lambda ctx, data: data,
)


def test_a_title_its_app_wrote_names_the_datum_in_its_translation_or_in_english():
    """A schema's own title is the name its app chose: translated when a catalog has it, as written in English (the
    language of the code); one nobody translated never reaches a Spanish card: the model's name of the field does."""
    arguments = {"first_name": "Ana", "last_name": "Gil"}
    assert labels(assistant.card(TITLED, arguments, "es")) == ["Propietario", "Apellidos"]
    assert labels(assistant.card(TITLED, arguments, "en")) == ["Owner", "Family name"]


def named_by_the_screen() -> set[str]:
    """The data the card's screen names itself (``assistant-card.ts`` ``FIELDS``: «Record», «Reason»…)."""
    source = (Path(settings.BASE_DIR) / "base/frontend/lib/assistant-card.ts").read_text()
    return set(re.findall(r"'([a-z_]+)'", re.search(r"const FIELDS = \[(.*?)\];", source, re.S).group(1)))


def test_no_datum_of_a_write_of_base_reaches_a_spanish_card_by_its_technical_name():
    """Every write of base itself: each datum by a name of its own in Spanish, never the title pydantic makes up from
    the field («Path», «Content Base64»). Base's half of the fix; each other app answers for its own."""
    screen = named_by_the_screen()
    assert {"id", "reason"} <= screen
    technical: dict[str, list[str]] = {}
    for op in registry.values():
        if op.app_label == "base" and op.kind == "command" and assistant.is_tool(op):
            props = op.input.model_json_schema().get("properties", {})
            for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
                if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                    technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}
    moved = assistant.card(get("base.file.move"), {"path": "marzo.pdf", "to": "Facturas"}, "es")
    assert labels(moved) == ["Archivo o carpeta", "Mover a"]


def test_an_action_of_the_platform_is_named_by_its_screen_never_base():
    """FIX-HUB-BASE-ASSISTANT-CARD-FIELD-LABELS-IN-ENGLISH: «Cambiar en Base» named the platform by its internal name.
    An action of base goes by the screen where the person does it (Shopify's Sidekick, Business Central's Copilot:
    the page, never the platform's name); one of an app, by the app."""
    pin = get("base.access.settings_update")
    assert assistant.card(pin, {"pin_length": 6}, "es")["app_name"] == "Ajustes"
    assert assistant.card(pin, {"pin_length": 6}, "en")["app_name"] == "Settings"
    assert assistant.card(get("base.file.delete"), {"path": "x"}, "es")["app_name"] == "Archivos"
    assert assistant.card(get("base.person.pin_remove"), {"person": "x"}, "es")["app_name"] == "Empleados"
    assert assistant.card(get("base.profile.update"), {"first_name": "x"}, "es")["app_name"] == "Mi perfil"
    assert assistant.card(get("base.failed_event.discard"), {"id": "x"}, "es")["app_name"] == "Sistema"
    assert assistant.card(get("demo.item.create"), {"name": "x"}, "es")["app_name"] == "Demo"


def test_every_action_of_base_names_its_screen():
    """Every tool of base, and what is never done from the chat (its receipt still names it), has its screen: a new
    entity of base without one fails here."""
    actions = {op.name for op in registry.values() if op.app_label == "base" and assistant.is_tool(op)}
    actions |= set(assistant.NOT_FROM_CHAT)
    assert sorted(name for name in actions if name.split(".")[1] not in assistant.BASE_SCREENS) == []


def named_actions() -> dict[str, dict[str, str]]:
    """The verbs the card and its receipt name an action by, per language: ``base.assistant.card.actions`` of base's
    catalogues, the very keys ``assistant-card.ts`` ``actionKey`` looks the card's ``action`` up in («other» is «Do
    this»)."""
    locale = Path(settings.BASE_DIR) / "base/frontend/locale"
    return {
        language: json.loads((locale / f"{language}.json").read_text())["base"]["assistant"]["card"]["actions"]
        for language in ("en", "es")
    }


def unnamed(operations: Iterable[Operation], verbs: dict[str, dict[str, str]]) -> list[str]:
    """The writes the assistant may call whose card and receipt would say «Do this» in a language: their card's
    ``action`` has no verb of its own there."""
    return sorted(
        f"{language}: {op.name}"
        for op in operations
        if op.kind == "command" and assistant.is_tool(op)
        for language, actions in verbs.items()
        if (action := assistant.card(op, {}, language)["action"]) == "other" or not str(actions.get(action, "")).strip()
    )


FROBNICATE = Operation(
    name="demo.item.frobnicate",
    kind="command",
    permission="demo.manage",
    input=TitledIn,
    output=TitledIn,
    expose_api=False,
    ai={"description": "A write whose verb no catalogue names."},
    fn=lambda ctx, data: data,
)


def test_every_write_the_assistant_may_call_names_its_action_in_english_and_spanish():
    """FIX-HUB-BASE-ASSISTANT-CARD-RECTIFY-SAYS-DO-THIS-IN-INVOICING: a closed list of 24 verbs left 124 actions as
    «Do this in Invoicing» (rectify, substitute, mark_paid, print, reschedule…). Every write of every app the
    assistant may call has its own verb in both catalogues: an app with a new one fails here, saying which."""
    assert unnamed(registry.values(), named_actions()) == []


def test_the_guardrail_catches_a_write_whose_verb_nobody_names():
    assert unnamed([FROBNICATE], named_actions()) == ["en: demo.item.frobnicate", "es: demo.item.frobnicate"]
    # A read never shows a card nor a receipt: it needs no verb.
    assert unnamed([get("demo.item.list")], {"en": {}, "es": {}}) == []


def test_a_dangerous_write_asks_to_type_a_word_in_the_persons_language():
    assert assistant.card(get("demo.item.delete"), {"id": "x"}, "es")["confirm_word"] == "CONFIRMAR"
    assert assistant.card(get("demo.item.delete"), {"id": "x"}, "en")["confirm_word"] == "CONFIRM"


def test_a_dangerous_write_over_named_records_asks_to_type_how_many():
    card = assistant.card(get("appointment.appointment.bulk_delete"), {"ids": ["a", "b", "c"]}, "es")
    assert (card["count"], card["confirm_word"], card["blocked"]) == (3, "3", False)


def test_a_dangerous_write_that_names_no_record_is_not_done_from_the_chat():
    card = assistant.card(get("appointment.appointment.bulk_delete"), {"ids": []}, "es")
    assert card["blocked"] is True


def test_the_typed_confirmation_is_compared_as_the_platforms_dialog_does():
    """As ``ConfirmDialog`` of ``@erplora/ui`` (the dialog that asks it): spaces around and case ignored, accents not."""
    card = assistant.card(get("demo.item.delete"), {"id": "x"}, "es")
    assert assistant.confirmed(card, "  CONFIRMAR ")
    assert assistant.confirmed(card, "confirmar")
    assert not assistant.confirmed(card, "CONFIRMA")
    assert not assistant.confirmed(card, "")
    normal = assistant.card(get("demo.item.create"), {"name": "x"}, "es")
    assert assistant.confirmed(normal, "")


# ── What a dangerous write will do, before it is confirmed (BASE-F98) ────────────────────────────────────────────
# FIX-HUB-BASE-ASSISTANT-HIGH-RISK-CARD-NO-OPERATION-PREVIEW: the card listed only what the write sends; the close of
# the drawer could not show the expected cash, nor a rectification the invoice it issues. A dangerous write may name,
# in its ``ai=``, a read of its own app that tells what it will do (``preview``): run as the person who asks, with
# the data of the write its input takes, before the card.


class SettleIn(Schema):
    id: str = Field(min_length=1)
    reason: str = ""


class SettlePreviewIn(Schema):
    id: str = Field(min_length=1)


class SettlePreviewOut(Schema):
    name: str = Field(title="Owner")
    total_cents: int
    expected_balance: int | None = Field(description="The cash there should be, in cents; none when it is hidden.")
    asked_by: str = Field(title="Person")
    note: str = ""


def settle_preview(ctx, data):
    if data.id == "gone":
        raise OperationError("This item is not there any more.", code="demo.item_not_found", status=404)
    return {"name": f"Item {data.id}", "total_cents": 4200, "expected_balance": None, "asked_by": ctx.actor, "note": ""}


# Not the order of the read's answer: the card follows the order the app names them in.
PREVIEW_FIELDS = ["asked_by", "name", "total_cents", "expected_balance", "note"]
SETTLE_PREVIEW = Operation(
    name="demo.item.settle_preview",
    kind="query",
    permission="demo.view",
    input=SettlePreviewIn,
    output=SettlePreviewOut,
    expose_api=False,
    ai={"description": "What settling a demo item would do."},
    fn=settle_preview,
)
SETTLE = Operation(
    name="demo.item.settle",
    kind="command",
    permission="demo.manage",
    input=SettleIn,
    output=SettlePreviewOut,
    expose_api=False,
    ai={
        "description": "Settles a demo item.",
        "risk": "high",
        "preview": {"operation": "demo.item.settle_preview", "fields": PREVIEW_FIELDS},
    },
    fn=lambda ctx, data: settle_preview(ctx, data),
)


@pytest.fixture
def settle(monkeypatch):
    """The write and its preview, registered as an app's would be."""
    monkeypatch.setitem(registry, SETTLE.name, SETTLE)
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    return SETTLE


def shown(fields: list[dict]) -> list[tuple]:
    return [(field["name"], field["kind"], field["value"]) for field in fields]


@pytest.mark.django_db
def test_a_dangerous_write_shows_what_its_app_says_it_will_do_read_as_the_person(settle):
    """In the order its app names them, by their names in the person's language, an amount in cents as money; what
    the read hides from this person (none, as a blind count's expected cash) or leaves empty is not there."""
    failure, fields = assistant.preview(ctx(language="es"), settle, {"id": "7", "reason": "cierre"})
    assert failure is None
    assert shown(fields) == [("asked_by", "text", "ana"), ("name", "text", "Item 7"), ("total_cents", "money", 4200)]
    assert (fields[0]["label"], fields[1]["label"]) == ("Persona", "Propietario")
    _, english = assistant.preview(ctx(language="en", actor="eva"), settle, {"id": "7"})
    assert [(field["label"], field["value"]) for field in english if field["name"] == "asked_by"] == [("Person", "eva")]


def test_a_write_without_a_preview_reads_nothing_and_its_card_is_as_before():
    assert assistant.preview(ctx(), get("demo.item.delete"), {"id": "x"}) == (None, None)
    assert set(assistant.card(get("demo.item.delete"), {"id": "x"}, "es")) == {
        "operation", "app", "app_name", "action", "risk", "fields", "count", "confirm_word", "blocked",
    }


@pytest.mark.django_db
def test_a_preview_the_person_may_not_read_is_refused_never_read_for_them(settle):
    """The read runs with the person's own session and permissions, as its screen would: never with more."""
    failure, fields = assistant.preview(ctx({"base.view_home", "demo.manage"}), settle, {"id": "7"})
    assert (failure.outcome, failure.code, fields) == ("refused", "permission_denied", None)


@pytest.mark.django_db
def test_a_preview_that_fails_says_why_never_an_empty_one(settle):
    failure, fields = assistant.preview(ctx(), settle, {"id": "gone"})
    assert (failure.outcome, failure.code, fields) == ("error", "demo.item_not_found", None)
    assert json.loads(failure.content)["error"]["message"] == "This item is not there any more."


@pytest.mark.django_db
def test_a_preview_whose_data_do_not_fit_comes_back_with_the_field(settle):
    failure, fields = assistant.preview(ctx(), settle, {"reason": "sin id"})
    assert (failure.outcome, failure.code, fields) == ("error", "invalid_payload", None)
    assert "id" in json.loads(failure.content)["error"]["fields"]


def preview_errors() -> list:
    from django.core import checks

    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E005"]


def declaring(preview, *, risk="high", input=SettleIn) -> Operation:
    return Operation(
        name="demo.item.settle",
        kind="command",
        permission="demo.manage",
        input=input,
        output=SettlePreviewOut,
        expose_api=False,
        ai={"description": "Settles a demo item.", "risk": risk, "preview": preview},
        fn=lambda ctx, data: data,
    )


class NoIdIn(Schema):
    reason: str = ""


@pytest.mark.parametrize(
    "write, why",
    [
        (declaring({"operation": "demo.item.nothing", "fields": ["name"]}), "no operation demo.item.nothing"),
        (declaring({"operation": "base.business.get", "fields": ["name"]}), "of another app"),
        (declaring({"operation": "demo.item.create", "fields": ["name"]}), "not a read"),
        (declaring({"operation": "demo.item.settle_preview", "fields": ["name", "total"]}), "no field total"),
        (declaring({"operation": "demo.item.settle_preview", "fields": []}), "names no field"),
        (declaring("demo.item.settle_preview"), "operation and fields"),
        (declaring({"operation": "demo.item.settle_preview", "fields": ["name"]}, input=NoIdIn), "takes id"),
        (declaring({"operation": "demo.item.settle_preview", "fields": ["name"]}, risk="normal"), "not dangerous"),
    ],
)
def test_a_preview_is_checked_at_start(monkeypatch, write, why):
    """Like ``ai=`` itself (live's E017): a preview that names no read of its own app, a datum its read does not give,
    data its write does not have, or that a normal write's one-line card would never show, is said at start."""
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    monkeypatch.setitem(registry, write.name, write)
    [error] = preview_errors()
    assert "demo.item.settle" in error.msg and why in error.msg


def test_the_previews_of_today_are_declared_right(settle):
    assert preview_errors() == []


# ── A tool runs as the person, by its own operation (BASE-G115, G118) ────────────────────────────────────────────


@pytest.mark.django_db
def test_a_tool_runs_by_its_operation_with_the_persons_permissions():
    outcome = assistant.run_tool(ctx(), get("demo.item.create"), '{"name": "Mesa 4"}')
    assert outcome.outcome == "ok"
    created = json.loads(outcome.content)
    listed = assistant.run_tool(ctx(EMPLOYEE), get("demo.item.list"), "{}")
    assert created["id"] in listed.content


@pytest.mark.django_db
def test_a_tool_the_person_may_not_use_is_refused_and_writes_nothing():
    outcome = assistant.run_tool(ctx(EMPLOYEE), get("demo.item.create"), '{"name": "Mesa 4"}')
    assert (outcome.outcome, outcome.code) == ("refused", "permission_denied")
    assert "Mesa 4" not in assistant.run_tool(ctx(EMPLOYEE), get("demo.item.list"), "{}").content


@pytest.mark.django_db
def test_arguments_that_do_not_fit_come_back_to_the_model_with_the_field():
    outcome = assistant.run_tool(ctx(), get("demo.item.create"), '{"name": ""}')
    assert (outcome.outcome, outcome.code) == ("error", "invalid_payload")
    assert "name" in json.loads(outcome.content)["error"]["fields"]
    broken = assistant.run_tool(ctx(), get("demo.item.create"), "{not json")
    assert (broken.outcome, broken.code) == ("error", "invalid_payload")


# ── The instructions of a turn (gh:hub#1039, #1045, #1046) ───────────────────────────────────────────────────────


def test_the_instructions_set_the_language_the_money_and_the_screens():
    text = assistant.instructions(language="es", currency="EUR", business="Bar Pepe", screens={"/settings": "Ajustes"})
    # gh:hub#1046: the old assistant answered anything (films, cinemas) on the business's allowance.
    assert "Only help with this business and with using ERPlora" in text
    assert "Spanish" in text
    assert "EUR" in text and "cents" in text
    assert "[Ajustes](/settings)" in text
    assert "Bar Pepe" in text


def test_the_setup_block_carries_what_is_pending_and_who_does_it():
    status = {
        "total": 3,
        "pending": 2,
        "unavailable": 0,
        "blocking_pending": 1,
        "items": [
            {"key": "base.business", "title": "Los datos de tu negocio", "state": "pending", "level": "legal",
             "actionable": True, "route": "/settings#business", "description": "Razón social y NIF."},
            {"key": "invoice.series", "title": "Tu numeración", "state": "pending", "level": "functional",
             "actionable": False, "route": "/m/invoice", "description": ""},
            {"key": "base.apps", "title": "Tus apps", "state": "done", "level": "recommended",
             "actionable": True, "route": "/apps", "description": ""},
        ],
    }
    block = assistant.setup_block(status)
    assert "Los datos de tu negocio" in block and "/settings#business" in block
    assert "Tu numeración" in block and "administrator" in block
    assert "Tus apps" in block
    assert "could not be read" in assistant.setup_block(None)


# ── The gateway's doors, signed (BASE-G122, G123, G112, G124) ────────────────────────────────────────────────────


def test_the_allowance_is_asked_signed_and_for_this_business(gateway):
    gateway.reply("/internal/assistant/usage", json={"used": 8, "limit": 10, "resets_at": "2026-11-01T00:00:00Z", "demo": False})
    assert assistant.usage(A) == {"used": 8, "limit": 10, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
    seen = gateway.sent("/internal/assistant/usage")[0]
    assert seen.body == {"hub": "a"}
    assert signed(seen)


def test_a_gateway_that_does_not_answer_is_said_never_made_up(settings):
    settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
    with pytest.raises(assistant.GatewayError) as caught:
        assistant.usage(A)
    assert caught.value.code == "assistant.unreachable"


def test_a_report_goes_to_erplora_with_the_question_and_the_answer(gateway):
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    answer = assistant.report(A, message_id="m1", reason="incorrect", comment="", question="¿Qué vendí?", answer="Nada")
    assert answer == {"sent": True, "duplicate": False}
    seen = gateway.sent("/internal/assistant/report")[0]
    assert seen.body == {"hub": "a", "message_id": "m1", "reason": "incorrect", "comment": "", "question": "¿Qué vendí?", "answer": "Nada"}
    assert signed(seen)


def test_a_report_that_could_not_be_sent_says_so(gateway):
    gateway.reply("/internal/assistant/report", status=503, json={"error": {"code": "assistant.report_not_sent", "message": "x"}})
    with pytest.raises(assistant.GatewayError) as caught:
        assistant.report(A, message_id="m1", reason="other", comment="", question="", answer="x")
    assert caught.value.code == "assistant.report_not_sent"


def test_a_dictation_is_transcribed_by_erplora(gateway):
    gateway.reply("/internal/speech/transcribe", json={"text": "cobra la mesa 4", "language": "es"})
    assert assistant.transcribe(A, audio="UklGRg==", mime_type="audio/webm", language="es") == {"text": "cobra la mesa 4", "language": "es"}
    assert gateway.sent("/internal/speech/transcribe")[0].body == {"hub": "a", "audio": "UklGRg==", "mime_type": "audio/webm", "language": "es"}


# ── The turn, streamed (BASE-G111, G119, G122, G124) ─────────────────────────────────────────────────────────────


def frames_of(**kwargs):
    async def collect():
        return [frame async for frame in assistant.stream_turn(A, **kwargs)]

    return asyncio.run(collect())


TURN = {"messages": [{"role": "user", "content": "hola"}], "tools": [], "instructions": "x", "continuation": None}


def test_the_answer_arrives_piece_by_piece_and_closes_with_what_to_keep(gateway):
    gateway.turn(
        {"type": "text_delta", "text": "Hola"},
        {"type": "text_delta", "text": ", Ana"},
        {"type": "response", "output": [], "usage": {}, "continuation": None},
        {"type": "usage", "used": 3, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False},
    )
    frames = frames_of(**TURN)
    assert [frame["type"] for frame in frames] == ["text", "text", "usage", "done"]
    assert "".join(frame["text"] for frame in frames if frame["type"] == "text") == "Hola, Ana"
    assert frames[-1]["append"] == [{"role": "assistant", "content": "Hola, Ana"}]
    assert frames[-1]["pending"] == []
    sent = gateway.sent("/internal/assistant/chat/stream")[0]
    assert sent.body["hub"] == "a" and sent.body["messages"] == TURN["messages"]
    assert signed(sent)


def test_the_tools_the_model_asks_for_wait_with_their_continuation(gateway):
    call = {"type": "function_call", "name": "demo__item__list", "call_id": "c1", "arguments": "{}"}
    gateway.turn(call, {"type": "response", "output": [call], "usage": {}, "continuation": "tok"})
    done = frames_of(**TURN)[-1]
    assert done["pending"] == [{"call_id": "c1", "name": "demo__item__list", "arguments": "{}"}]
    assert done["continuation"] == "tok"
    assert done["append"] == [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "demo__item__list", "arguments": "{}"}}
        ]}
    ]


def test_an_allowance_spent_is_not_a_breakdown(gateway):
    gateway.reply(
        "/internal/assistant/chat/stream",
        status=429,
        json={"error": {"code": "assistant.quota_exceeded", "message": "x", "upgrade_required": True, "used": 30,
                        "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}},
    )
    error = frames_of(**TURN)[-1]
    assert error["type"] == "error"
    assert (error["code"], error["used"], error["limit"]) == ("assistant.quota_exceeded", 30, 30)


@pytest.mark.parametrize(
    "status, code, expected",
    [
        (503, "assistant.no_model", "assistant.unavailable"),
        (503, "assistant.provider_not_configured", "assistant.unavailable"),
        (403, "hub_inactive", "assistant.unavailable"),
        (413, "payload_too_large", "assistant.too_large"),
        (429, "rate_limited", "assistant.rate_limited"),
    ],
)
def test_a_refusal_of_the_gateway_is_one_of_ours(gateway, status, code, expected):
    """gh:hub#1738: the old hub said «Could not reach the assistant» for any refusal; each one is said as it is."""
    gateway.reply("/internal/assistant/chat/stream", status=status, json={"error": {"code": code, "message": "x"}}, headers={"Retry-After": "40"})
    error = frames_of(**TURN)[-1]
    assert (error["type"], error["code"]) == ("error", expected)


def test_a_provider_that_fails_half_way_keeps_what_was_said(gateway):
    gateway.turn(
        {"type": "text_delta", "text": "Tienes"},
        {"type": "error", "code": "assistant.provider_unavailable", "message": "x", "retriable": True},
    )
    frames = frames_of(**TURN)
    assert [frame["type"] for frame in frames] == ["text", "error", "done"]
    assert frames[1] == {"type": "error", "code": "assistant.provider_failed", "retriable": True}
    assert frames[-1]["append"] == [{"role": "assistant", "content": "Tienes"}]


def test_a_connection_that_dies_half_way_is_said(gateway):
    gateway.turn({"type": "text_delta", "text": "Tienes"}, {"type": "text_delta", "text": " 3"}, cut_after=1)
    frames = frames_of(**TURN)
    assert [frame["type"] for frame in frames] == ["text", "error", "done"]
    assert frames[1]["code"] == "assistant.cut"


def test_a_gateway_out_of_reach_is_said(settings):
    settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"
    error = frames_of(**TURN)[-1]
    assert (error["type"], error["code"]) == ("error", "assistant.unreachable")
