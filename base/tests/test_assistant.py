"""The card of a write of the Hub's assistant, what the person sees before it runs (``base/assistant/cards.py``):
what it will send, each datum named in the person's language, its secrets hidden, the verb of its action and the
word a dangerous write asks to type."""

import json
import re
from collections.abc import Iterable
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation
from live import assistant as shared
from live.operations import Operation, get, registry
from ninja import Field, Schema
from pydantic import SecretStr

from base import assistant
from base.tests.assistant_context import ctx, shown, titled


# ── The card of a write ──────────────────────────────────────────────────────────────────────────────────────────


def test_a_normal_write_asks_a_click_and_shows_what_it_will_send():
    card = assistant.cards.card(get("demo.item.create"), {"name": "Mesa 4", "note": None}, "es")
    assert (card["risk"], card["confirm_word"], card["blocked"]) == ("normal", "", False)
    assert card["app"] == "demo"
    fields = {field["name"]: field for field in card["fields"]}
    assert fields["name"] == {**fields["name"], "kind": "text", "value": "Mesa 4"}
    assert fields["note"]["kind"] == "empty"


class SummaryIn(Schema):
    name: str


SUMMARY_OPERATION = Operation(
    name="demo.item.summarize",
    kind="command",
    permission="demo.manage",
    input=SummaryIn,
    output=SummaryIn,
    expose_api=False,
    ai={"description": "A write whose app sums up its data."},
    fn=lambda ctx, data: data,
)


def test_a_summary_is_not_called_without_a_person_and_the_card_keeps_its_details(monkeypatch):
    def forbidden(ctx, arguments, fields):
        raise AssertionError("a summary must not run without a person")

    monkeypatch.setitem(SUMMARY_OPERATION.ai, "summary", forbidden)
    fields = assistant.cards.card(SUMMARY_OPERATION, {"name": "Mesa 4"}, "es")["fields"]
    assert [(field["name"], field["label"], field["value"]) for field in fields] == [("name", "Nombre", "Mesa 4")]


def test_a_summary_replaces_the_details_with_exactly_what_it_returns_as_the_person(monkeypatch):
    seen = {}
    expected = [{"name": "summary", "label": "Resumen", "kind": "text", "value": "Solo esto"}]

    def summarize(context, arguments, fields):
        seen.update(context=context, arguments=arguments, fields=fields)
        return expected

    monkeypatch.setitem(SUMMARY_OPERATION.ai, "summary", summarize)
    arguments = {"name": "Mesa 4"}
    person = ctx(language="es")
    card = assistant.cards.card(SUMMARY_OPERATION, arguments, "es", person)
    assert seen["context"] is person
    assert seen["arguments"] is arguments
    assert [(field["name"], field["label"], field["value"]) for field in seen["fields"]] == [("name", "Nombre", "Mesa 4")]
    assert card["fields"] == expected


def test_a_summary_that_is_not_callable_is_ignored(monkeypatch):
    monkeypatch.setitem(SUMMARY_OPERATION.ai, "summary", "not callable")
    fields = assistant.cards.card(SUMMARY_OPERATION, {"name": "Mesa 4"}, "es", ctx(language="es"))["fields"]
    assert [(field["name"], field["label"], field["value"]) for field in fields] == [("name", "Nombre", "Mesa 4")]


def test_a_summary_runs_in_the_requested_language(monkeypatch):
    def summarize(context, arguments, fields):
        return [{"name": "summary", "label": "Resumen", "kind": "text", "value": translation.gettext("Name")}]

    monkeypatch.setitem(SUMMARY_OPERATION.ai, "summary", summarize)
    with translation.override("en"):
        fields = assistant.cards.card(SUMMARY_OPERATION, {"name": "Mesa 4"}, "es", ctx(language="en"))["fields"]
        assert translation.gettext("Name") == "Name"
    assert [field["value"] for field in fields] == ["Nombre"]


def test_an_amount_in_cents_is_marked_as_money_for_the_card():
    card = assistant.cards.card(get("service.service.create"), {"name": "Corte", "price": 1500}, "es")
    price = next(field for field in card["fields"] if field["name"] == "price")
    assert (price["kind"], price["value"]) == ("money", 1500)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def test_every_datum_of_the_card_is_named_in_the_persons_language():
    """A datum the screen does not name itself (``FIELDS`` of the shared assistant's ``card.ts``) must not fall back to
    its schema's English title in Spanish («Session», «Counted cash»)."""
    close = get("cash_register.session.close")
    arguments = {"session": "S-1", "closing_balance": 25000}
    assert labels(assistant.cards.card(close, arguments, "es")) == ["Sesión", "Efectivo contado"]
    assert labels(assistant.cards.card(close, arguments, "en")) == ["Session", "Counted cash"]
    pin = assistant.cards.card(get("base.access.settings_update"), {"pin_inactivity_minutes": 10, "pin_length": 6}, "es")
    assert labels(pin) == ["Volver a pedir tras (minutos)", "Dígitos del PIN"]


def test_a_datum_is_named_by_the_model_of_its_operation_before_another_of_its_app():
    """Two models of an app may name a field of the same name differently: the operation's entity says which."""
    assert labels(assistant.cards.card(get("base.device.mode_set"), {"mode": "kiosk"}, "es")) == ["Modo"]
    assert labels(assistant.cards.card(get("base.api_key.create"), {"mode": "read"}, "es")) == ["Qué puede hacer"]


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
    assert labels(assistant.cards.card(TITLED, arguments, "es")) == ["Propietario", "Apellidos"]
    assert labels(assistant.cards.card(TITLED, arguments, "en")) == ["Owner", "Family name"]


class Place(Schema):
    city: str = ""


class HalfTitledIn(Schema):
    id: str = Field(title="Gizmo slot")
    name: str = ""
    #: A schema of its own: its title is its class's name («Place»), none its app wrote for the datum.
    category: Place | None = None


HALF_TITLED = Operation(
    name="base.profile.half_titled",
    kind="command",
    permission="base.view_home",
    input=HalfTitledIn,
    output=HalfTitledIn,
    expose_api=False,
    ai={"description": "A write whose schema titles a datum no catalog translates.", "risk": "high"},
    fn=lambda ctx, data: data,
)


def test_a_title_its_app_wrote_is_marked_so_for_the_card_to_name_the_datum_by_it():
    """A dangerous write of Tables said «Registro:
    5 (Terraza)» where its schema titles the check «Cuenta»: the screen names a datum it knows by its own word
    (``FIELDS`` of the shared assistant's ``card.ts``: ``id`` is «Record») and could not tell the title its app wrote from one made up.
    The card says which: a title its app wrote, said in the person's language, is ``titled``; one no catalog
    translates, the model's name of the field or the one pydantic makes up, never."""
    arguments = {"first_name": "Ana", "last_name": "Gil"}
    assert titled(assistant.cards.card(TITLED, arguments, "en")["fields"]) == {"first_name": True, "last_name": True}
    # «Family name» has no Spanish: its card says the model's «Apellidos», no title of its app's.
    assert titled(assistant.cards.card(TITLED, arguments, "es")["fields"]) == {"first_name": True, "last_name": False}
    half = {"id": "7", "name": "Ana", "category": {"city": "Vigo"}}
    assert titled(assistant.cards.card(HALF_TITLED, half, "es")["fields"]) == {"id": False, "name": False, "category": False}
    assert titled(assistant.cards.card(HALF_TITLED, half, "en")["fields"]) == {"id": True, "name": False, "category": False}
    price = assistant.cards.card(get("service.service.create"), {"price": 1500}, "es")["fields"]
    assert titled(price) == {"price": False}
    assert "titled" not in price[0]


# A card never paints a secret (a certificate's password, an automation's secret: ``SecretStr``) as typed, on the
# screen or in what the browser receives. Its schema says so (``format: password``, ``writeOnly``): at any depth, the
# card shows it hidden; the write still receives it.

HIDDEN = "••••••••"


class LoginIn(Schema):
    user: str
    password: SecretStr
    backup: SecretStr | None = None


class SecretSetIn(Schema):
    name: str = ""
    value: SecretStr | None = None
    login: LoginIn | None = None
    logins: list[LoginIn] = []
    tokens: dict[str, SecretStr] = {}
    pair: tuple[str, SecretStr] | None = None
    # Declared secret by one mark of the two alone.
    api_key: str = Field("", json_schema_extra={"writeOnly": True})
    pin: str = Field("", json_schema_extra={"format": "password"})


class SecretSetOut(Schema):
    name: str


SECRET_SET = Operation(
    name="demo.item.secret_set",
    kind="command",
    permission="demo.manage",
    input=SecretSetIn,
    output=SecretSetOut,
    expose_api=False,
    ai={"description": "Keeps a secret of a demo item."},
    fn=lambda ctx, data: {"name": data.name},
)


def test_a_secret_reaches_the_card_hidden_at_any_depth_and_the_rest_as_sent():
    arguments = {
        "name": "Banco",
        "value": "hunter2",
        "login": {"user": "ana", "password": "hunter3", "backup": "hunter4"},
        "logins": [{"user": "eva", "password": "hunter5"}],
        "tokens": {"main": "hunter6"},
        "pair": ["ana", "hunter7"],
        "api_key": "hunter8",
        "pin": "hunter9",
    }
    card = assistant.cards.card(SECRET_SET, arguments, "es")
    assert "hunter" not in json.dumps(card, ensure_ascii=False)
    assert shown(card["fields"]) == [
        ("name", "text", "Banco"),
        ("value", "text", HIDDEN),
        ("login", "object", {"user": "ana", "password": HIDDEN, "backup": HIDDEN}),
        ("logins", "list", [{"user": "eva", "password": HIDDEN}]),
        ("tokens", "object", {"main": HIDDEN}),
        ("pair", "list", ["ana", HIDDEN]),
        ("api_key", "text", HIDDEN),
        ("pin", "text", HIDDEN),
    ]


def test_an_empty_secret_is_said_empty_nothing_to_hide():
    card = assistant.cards.card(SECRET_SET, {"value": "", "login": None}, "es")
    assert shown(card["fields"]) == [("value", "empty", ""), ("login", "empty", None)]


SENTINEL = "s3cr3t-in-clear"


def with_secrets(prop: dict, defs: dict, depth: int = 0) -> object:
    """A value of the schema ``prop`` with ``SENTINEL`` in each secret it declares (``format: password`` or
    ``writeOnly``), at any depth, and nothing else; ``None`` when it declares none."""
    ref = prop.get("$ref")
    if ref:
        prop = {**defs.get(ref.rsplit("/", 1)[-1], {}), **{k: v for k, v in prop.items() if k != "$ref"}}
    if prop.get("format") == "password" or prop.get("writeOnly") is True:
        return SENTINEL
    if depth > 8:  # a schema that names itself
        return None
    for branch in [*prop.get("anyOf", []), *prop.get("oneOf", []), *prop.get("allOf", [])]:
        if (value := with_secrets(branch, defs, depth + 1)) is not None:
            return value
    if isinstance(prop.get("properties"), dict):
        found = {name: with_secrets(inner, defs, depth + 1) for name, inner in prop["properties"].items()}
        return {name: value for name, value in found.items() if value is not None} or None
    for key, wrap in (("items", lambda value: [value]), ("additionalProperties", lambda value: {"key": value})):
        if isinstance(prop.get(key), dict) and (value := with_secrets(prop[key], defs, depth + 1)) is not None:
            return wrap(value)
    return None


def test_no_operation_lets_a_secret_reach_its_card_in_clear():
    """Every operation of every app, tool of the assistant or not (one may become one): what its schema declares
    secret never reaches its card as sent."""
    checked = []
    for name, op in sorted({**registry, SECRET_SET.name: SECRET_SET}.items()):
        schema = op.input.model_json_schema()
        arguments = with_secrets(schema, schema.get("$defs", {}))
        if arguments:
            checked.append(name)
            assert SENTINEL not in json.dumps(assistant.cards.card(op, arguments, "es"), ensure_ascii=False), name
    # Not an empty sweep: today's secrets are among them (a certificate and its password, an automation's secret).
    assert {"verifactu.certificate.upload", "flow.secret.set", SECRET_SET.name} <= set(checked)


def named_by_the_screen() -> set[str]:
    """The data the card's screen names itself (``FIELDS`` of the shared assistant's ``card.ts``, @erplora/ui: «Record»,
    «Reason»…)."""
    source = (Path(settings.BASE_DIR) / "packages/ui/src/components/Assistant/card.ts").read_text()
    return set(re.findall(r"'([a-z_]+)'", re.search(r"const FIELDS = \[(.*?)\];", source, re.S).group(1)))


def technical_names(writes) -> dict[str, list[str]]:
    """The data of ``writes`` a Spanish card calls by the title pydantic makes up from the field («Path», «Group Ids»),
    by write, each sent with every datum it takes: none should be, but those the screen names itself."""
    screen = named_by_the_screen()
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.cards.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    return technical


def test_no_datum_of_a_write_of_base_reaches_a_spanish_card_by_its_technical_name():
    """Every write of base itself: each datum by a name of its own in Spanish, never the title pydantic makes up from
    the field («Path», «Content Base64»). Base's half of the fix; each other app answers for its own."""
    assert {"id", "reason"} <= named_by_the_screen()
    writes = [
        op
        for op in registry.values()
        if op.app_label == "base" and op.kind == "command" and assistant.tools.is_tool(op)
    ]
    assert technical_names(writes) == {}
    moved = assistant.cards.card(get("base.file.move"), {"path": "marzo.pdf", "to": "Facturas"}, "es")
    assert labels(moved) == ["Archivo o carpeta", "Mover a"]


def test_an_action_of_the_platform_is_named_by_its_screen_never_base():
    """«Cambiar en Base» would name the platform by its internal name. An action of base goes by the screen where the
    person does it (Shopify's Sidekick, Business Central's Copilot: the page, never the platform's name); one of an
    app, by the app."""
    pin = get("base.access.settings_update")
    assert assistant.cards.card(pin, {"pin_length": 6}, "es")["app_name"] == "Ajustes"
    assert assistant.cards.card(pin, {"pin_length": 6}, "en")["app_name"] == "Settings"
    assert assistant.cards.card(get("base.file.delete"), {"path": "x"}, "es")["app_name"] == "Archivos"
    assert assistant.cards.card(get("base.person.pin_remove"), {"person": "x"}, "es")["app_name"] == "Empleados"
    assert assistant.cards.card(get("base.profile.update"), {"first_name": "x"}, "es")["app_name"] == "Mi perfil"
    assert assistant.cards.card(get("base.failed_event.discard"), {"id": "x"}, "es")["app_name"] == "Sistema"
    assert assistant.cards.card(get("demo.item.create"), {"name": "x"}, "es")["app_name"] == "Demo"


def test_every_action_of_base_names_its_screen():
    """Every tool of base, and what is never done from the chat (its receipt still names it), has its screen: a new
    entity of base without one fails here."""
    actions = {op.name for op in registry.values() if op.app_label == "base" and assistant.tools.is_tool(op)}
    actions |= set(assistant.tools.NOT_FROM_CHAT)
    assert sorted(name for name in actions if name.split(".")[1] not in assistant.cards.BASE_SCREENS) == []


@pytest.mark.parametrize("language", ["en", "es"])
def test_each_screen_a_receipt_names_by_its_key_is_named_alike_by_the_screen(language):
    """A receipt names the platform's screen by its key (``screen``), in the language the screen is in
    (``base.assistant.screens.<key>`` of base's catalogue): the same name the card gives it in that language, for each
    screen an action of base happens on."""
    catalogue = json.loads((Path(settings.BASE_DIR) / f"base/frontend/locale/{language}.json").read_text())
    names = catalogue["base"]["assistant"]["screens"]
    with translation.override(language):
        assert {key: names.get(key) for key in set(assistant.cards.BASE_SCREENS.values())} == {
            key: str(assistant.cards.SCREEN_NAMES[key]) for key in set(assistant.cards.BASE_SCREENS.values())
        }
    pin = get("base.access.settings_update")
    assert (assistant.cards.screen(pin), assistant.cards.screen(get("demo.item.create"))) == ("settings", "")


def card_catalogues() -> dict[str, dict]:
    """``base.assistant.cards.card`` of base's catalogues, per language."""
    locale = Path(settings.BASE_DIR) / "base/frontend/locale"
    return {
        language: json.loads((locale / f"{language}.json").read_text())["base"]["assistant"]["card"]
        for language in ("en", "es")
    }


def named_operations() -> dict[str, dict[str, str]]:
    """The writes with a verb of their own, per language, by their name: ``base.assistant.card.operations.<app>.
    <entity>.<action>`` of base's catalogues, for one whose action's verb does not say what it does (emptying a cart is
    not taking one of its lines out)."""
    return {
        language: {
            f"{app}.{entity}.{action}": verb
            for app, entities in card["operations"].items()
            for entity, actions in entities.items()
            for action, verb in actions.items()
        }
        for language, card in card_catalogues().items()
    }


def named_actions() -> dict[str, dict[str, str]]:
    """The verbs the card and its receipt name a write by, per language, as ``actionKey`` of ``lib/assistant-hub.ts``
    looks them up: its whole operation's (``named_operations``), else its card's ``action``'s, ``base.assistant.card.actions``
    («other» is «Do this»). An operation goes by its name, with its dots; an action, which has none, by its own."""
    operations = named_operations()
    return {language: {**card["actions"], **operations[language]} for language, card in card_catalogues().items()}


def verb(op: Operation, verbs: dict[str, str], language: str = "en") -> str:
    """The verb a write's card and receipt say in a language whose verbs are ``verbs`` (``named_actions``): its whole
    operation's, else its action's; '' = none («Do this»)."""
    action = assistant.cards.card(op, {}, language)["action"]
    return "" if action == "other" else str(verbs.get(op.name) or verbs.get(action, "")).strip()


def unnamed(operations: Iterable[Operation], verbs: dict[str, dict[str, str]]) -> list[str]:
    """The writes the assistant may call whose card and receipt would say «Do this» in a language: neither their
    operation nor their card's ``action`` has a verb there."""
    return sorted(
        f"{language}: {op.name}"
        for op in operations
        if op.kind == "command" and assistant.tools.is_tool(op)
        for language, named in verbs.items()
        if not verb(op, named, language)
    )


def misnamed(verbs: dict[str, dict[str, str]]) -> list[str]:
    """The operations' own verbs (``named_operations``) that would never be said, or said in one language only: one
    that names no write the assistant may call (a typo, one renamed or gone: its card falls back to its action's verb in
    silence), or with no words in a language whose catalogue another one names it in."""
    def write(name: str) -> bool:
        return (op := registry.get(name)) is not None and op.kind == "command" and assistant.tools.is_tool(op)

    return sorted(
        f"{language}: {name}"
        for name in set().union(*verbs.values())
        for language, named in verbs.items()
        if not write(name) or not str(named.get(name, "")).strip()
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
    """A closed list of 24 verbs left 124 actions as «Do this in Invoicing» (rectify, substitute, mark_paid, print,
    reschedule…). Every write of every app the assistant may call has its own verb in both catalogues: an app with a
    new one fails here, saying which."""
    assert unnamed(registry.values(), named_actions()) == []


def test_the_guardrail_catches_a_write_whose_verb_nobody_names():
    assert unnamed([FROBNICATE], named_actions()) == ["en: demo.item.frobnicate", "es: demo.item.frobnicate"]
    # A read never shows a card nor a receipt: it needs no verb.
    assert unnamed([get("demo.item.list")], {"en": {}, "es": {}}) == []


def test_a_write_whose_actions_verb_does_not_say_what_it_does_is_named_by_its_own():
    """Emptying a cart (``cart_checkout.cart.clear``) said
    «Quitar», the verb of taking one of its lines out, which Kitchen's ``clear`` (taking a product's route away) does
    say; a cash count (``cash_register.count.add``) said «Añadir», as if it put money in. Their own verb goes first;
    their action's still names the rest."""
    verbs = named_actions()
    names = (
        "cart_checkout.cart.clear",
        "cart_checkout.item.remove",
        "kitchen.routing.clear",
        "cash_register.count.add",
        "cash_register.movement.add",
        "cart_checkout.item.add",
    )
    assert {name: (verb(get(name), verbs["es"], "es"), verb(get(name), verbs["en"])) for name in names} == {
        "cart_checkout.cart.clear": ("Vaciar", "Clear"),
        "cart_checkout.item.remove": ("Quitar", "Remove"),
        "kitchen.routing.clear": ("Quitar", "Clear"),
        "cash_register.count.add": ("Registrar arqueo", "Register count"),
        "cash_register.movement.add": ("Registrar movimiento", "Register movement"),
        "cart_checkout.item.add": ("Añadir", "Add"),
    }


def test_each_verb_of_its_own_names_a_write_the_assistant_may_call_in_english_and_spanish():
    assert misnamed(named_operations()) == []


def test_the_guardrail_catches_a_verb_of_its_own_that_would_never_be_said():
    verbs = {
        "en": {"cart_checkout.cart.clear": "Clear", "cart_checkout.cart.clean": "Clear", "cart_checkout.cart.list": "List"},
        "es": {"cart_checkout.cart.clear": " ", "cart_checkout.cart.clean": "Vaciar"},
    }
    # A typo, a read (which shows no card) and one with no words in Spanish.
    assert misnamed(verbs) == [
        "en: cart_checkout.cart.clean",
        "en: cart_checkout.cart.list",
        "es: cart_checkout.cart.clean",
        "es: cart_checkout.cart.clear",
        "es: cart_checkout.cart.list",
    ]
    # A write's own verb names it even where its action has none.
    assert unnamed([FROBNICATE], {"en": {"demo.item.frobnicate": "Frobnicate"}, "es": {}}) == ["es: demo.item.frobnicate"]


def test_a_dangerous_write_asks_to_type_a_word_in_the_persons_language():
    assert assistant.cards.card(get("demo.item.delete"), {"id": "x"}, "es")["confirm_word"] == "CONFIRMAR"
    assert assistant.cards.card(get("demo.item.delete"), {"id": "x"}, "en")["confirm_word"] == "CONFIRM"


def test_a_dangerous_write_over_named_records_asks_to_type_how_many():
    card = assistant.cards.card(get("appointment.appointment.bulk_delete"), {"ids": ["a", "b", "c"]}, "es")
    assert (card["count"], card["confirm_word"], card["blocked"]) == (3, "3", False)


def test_a_dangerous_write_that_names_no_record_is_not_done_from_the_chat():
    card = assistant.cards.card(get("appointment.appointment.bulk_delete"), {"ids": []}, "es")
    assert card["blocked"] is True


def test_the_typed_confirmation_is_compared_as_the_platforms_dialog_does():
    """As ``ConfirmDialog`` of ``@erplora/ui`` (the dialog that asks it): spaces around and case ignored, accents not."""
    card = assistant.cards.card(get("demo.item.delete"), {"id": "x"}, "es")
    assert shared.confirmed(card, "  CONFIRMAR ")
    assert shared.confirmed(card, "confirmar")
    assert not shared.confirmed(card, "CONFIRMA")
    assert not shared.confirmed(card, "")
    normal = assistant.cards.card(get("demo.item.create"), {"name": "x"}, "es")
    assert shared.confirmed(normal, "")
