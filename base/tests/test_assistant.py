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
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.operations import Operation, get, registry
from ninja import Field, Schema
from pydantic import ConfigDict, SecretStr

from base import assistant, entitlement
from base.models import Membership
from base.permissions import permissions_for
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
        ("base.blueprint.export", "never from the chat: a file to download"),
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


#: Writes only the platform runs, of both shapes their permission takes (``<app>.system``, ``system.<app>``), each with
#: an ``ai=`` that does not start with «System only»: «Platform reaction…», «Platform only…», «Lower the stock…».
PLATFORM_WRITES = {
    "appointment.customer.erase",
    "online_booking.customer.erase",
    "table.hold.expire",
    "inventory.stock.apply_sale",
    "service.grant.reassign",
}


def platform_operations(owner: OperationContext) -> list[str]:
    """The operations only who holds «*» reaches (the system; a superuser, on the platform's scope only): not even the
    owner of the business, who holds every permission its apps declare, may run them."""
    return sorted(name for name, op in registry.items() if op.permission is not None and not owner.has(op.permission))


@pytest.fixture
def owner(make_user) -> OperationContext:
    """The owner of business A with the permissions a request of theirs carries (``base.permissions``)."""
    return ctx(permissions_for(make_user("olga", host=A.key, role=Membership.Role.OWNER), A))


def test_no_operation_of_the_platform_is_a_tool_whatever_its_ai_says(owner):
    """FIX-HUB-BASE-ASSISTANT-OFFERS-PLATFORM-WRITES-AS-TOOLS: the platform's reactions and scheduled tasks (erasing or
    reassigning the customer of an appointment, expiring a hold, lowering the stock of a sale) were tools of whoever
    holds «*», because their ``ai=`` does not start with «System only». Its permission says so, not its words."""
    platform = platform_operations(owner)
    assert PLATFORM_WRITES <= set(platform)  # not an empty sweep
    assert [name for name in platform if assistant.is_tool(registry[name])] == []


def test_a_superusers_assistant_is_offered_no_operation_of_the_platform(owner, superuser):
    """The tools a superuser's turn gets (``base.assistant.turn``: ``catalog`` of the person's own permissions): on a
    business's host those of a person without a role, since ERPlora's staff holds nothing there without a Membership
    (``base.permissions``); and «*» itself offers every write of the business's apps, none that only the platform
    runs."""
    staff_tools = assistant.catalog(ctx(permissions_for(superuser, A), actor=superuser))
    assert staff_tools == assistant.catalog(ctx(frozenset(), actor=superuser))  # what a person without a role gets
    assert "demo.item.create" not in staff_tools
    tools = assistant.catalog(ctx({"*"}, actor=superuser))
    assert "demo.item.create" in tools
    assert sorted(set(tools) & set(platform_operations(owner))) == []


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


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("permissions", [EMPLOYEE, MANAGER, {"*"}])
def test_the_documentation_search_is_always_at_hand_for_everybody(permissions):
    """saas ASSISTANT-F28 (Ioan, 2026-10-31: «everything it is asked, it answers with our information, inventing
    nothing»): a how-to question («¿cómo abro la caja?») shares no word with the tool, so it is in every turn."""
    assert "base.docs.search" in assistant.ALWAYS
    tools = assistant.catalog(ctx(permissions))
    assert "base.docs.search" in tools
    assert "base.docs.search" in [op.name for op in assistant.relevant(tools, ["¿cómo abro la caja?"], "es")]


@pytest.mark.parametrize(("language", "name"), [("en", "Help"), ("es", "Ayuda")])
def test_a_documentation_search_is_named_help_on_its_receipt(language, name):
    """As the panel of erplora.com names it: the help, not a screen of the business."""
    with translation.override(language):
        assert assistant.app_name(get("base.docs.search")) == name


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
    (``FIELDS`` of the shared assistant's ``card.ts``) went by its schema's English title, in Spanish too («Session»,
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


def titled(fields: list[dict]) -> dict[str, bool]:
    return {field["name"]: field.get("titled", False) for field in fields}


def test_a_title_its_app_wrote_is_marked_so_for_the_card_to_name_the_datum_by_it():
    """FIX-HUB-BASE-ASSISTANT-DANGER-CARD-CALLS-THE-RECORD-BY-ITS-FIELD-NAME: a dangerous write of Tables said «Registro:
    5 (Terraza)» where its schema titles the check «Cuenta»: the screen names a datum it knows by its own word
    (``FIELDS`` of the shared assistant's ``card.ts``: ``id`` is «Record») and could not tell the title its app wrote from one made up.
    The card says which: a title its app wrote, said in the person's language, is ``titled``; one no catalog
    translates, the model's name of the field or the one pydantic makes up, never."""
    arguments = {"first_name": "Ana", "last_name": "Gil"}
    assert titled(assistant.card(TITLED, arguments, "en")["fields"]) == {"first_name": True, "last_name": True}
    # «Family name» has no Spanish: its card says the model's «Apellidos», no title of its app's.
    assert titled(assistant.card(TITLED, arguments, "es")["fields"]) == {"first_name": True, "last_name": False}
    half = {"id": "7", "name": "Ana", "category": {"city": "Vigo"}}
    assert titled(assistant.card(HALF_TITLED, half, "es")["fields"]) == {"id": False, "name": False, "category": False}
    assert titled(assistant.card(HALF_TITLED, half, "en")["fields"]) == {"id": True, "name": False, "category": False}
    price = assistant.card(get("service.service.create"), {"price": 1500}, "es")["fields"]
    assert titled(price) == {"price": False}
    assert "titled" not in price[0]


@pytest.mark.django_db
def test_a_title_the_read_of_a_preview_wrote_is_marked_so_too(settle):
    """What a dangerous write will do (BASE-F98) is said as what it sends: the read titles its owner and its person."""
    failure, fields = assistant.preview(ctx(language="es"), settle, {"id": "7"})
    assert failure is None
    assert titled(fields) == {"asked_by": True, "name": True, "total_cents": False}


# FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-SECRETSTR-IN-CLEAR: the card painted a secret (a certificate's password, an
# automation's secret: ``SecretStr``) as typed, on the screen and in what the browser receives. Its schema says so
# (``format: password``, ``writeOnly``): at any depth, the card shows it hidden; the write still receives it.

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
    card = assistant.card(SECRET_SET, arguments, "es")
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
    card = assistant.card(SECRET_SET, {"value": "", "login": None}, "es")
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
            assert SENTINEL not in json.dumps(assistant.card(op, arguments, "es"), ensure_ascii=False), name
    # Not an empty sweep: today's secrets are among them (a certificate and its password, an automation's secret).
    assert {"verifactu.certificate.upload", "flow.secret.set", SECRET_SET.name} <= set(checked)


def named_by_the_screen() -> set[str]:
    """The data the card's screen names itself (``FIELDS`` of the shared assistant's ``card.ts``, @erplora/ui: «Record»,
    «Reason»…)."""
    source = (Path(settings.BASE_DIR) / "packages/ui/src/components/Assistant/card.ts").read_text()
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


@pytest.mark.parametrize("language", ["en", "es"])
def test_each_screen_a_receipt_names_by_its_key_is_named_alike_by_the_screen(language):
    """A receipt names the platform's screen by its key (``screen``), in the language the screen is in
    (``base.assistant.screens.<key>`` of base's catalogue): the same name the card gives it in that language, for each
    screen an action of base happens on (FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY)."""
    catalogue = json.loads((Path(settings.BASE_DIR) / f"base/frontend/locale/{language}.json").read_text())
    names = catalogue["base"]["assistant"]["screens"]
    with translation.override(language):
        assert {key: names.get(key) for key in set(assistant.BASE_SCREENS.values())} == {
            key: str(assistant.SCREEN_NAMES[key]) for key in set(assistant.BASE_SCREENS.values())
        }
    pin = get("base.access.settings_update")
    assert (assistant.screen(pin), assistant.screen(get("demo.item.create"))) == ("settings", "")


def card_catalogues() -> dict[str, dict]:
    """``base.assistant.card`` of base's catalogues, per language."""
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
    action = assistant.card(op, {}, language)["action"]
    return "" if action == "other" else str(verbs.get(op.name) or verbs.get(action, "")).strip()


def unnamed(operations: Iterable[Operation], verbs: dict[str, dict[str, str]]) -> list[str]:
    """The writes the assistant may call whose card and receipt would say «Do this» in a language: neither their
    operation nor their card's ``action`` has a verb there."""
    return sorted(
        f"{language}: {op.name}"
        for op in operations
        if op.kind == "command" and assistant.is_tool(op)
        for language, named in verbs.items()
        if not verb(op, named, language)
    )


def misnamed(verbs: dict[str, dict[str, str]]) -> list[str]:
    """The operations' own verbs (``named_operations``) that would never be said, or said in one language only: one
    that names no write the assistant may call (a typo, one renamed or gone: its card falls back to its action's verb in
    silence), or with no words in a language whose catalogue another one names it in."""
    def write(name: str) -> bool:
        return (op := registry.get(name)) is not None and op.kind == "command" and assistant.is_tool(op)

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
    """FIX-HUB-BASE-ASSISTANT-CARD-RECTIFY-SAYS-DO-THIS-IN-INVOICING: a closed list of 24 verbs left 124 actions as
    «Do this in Invoicing» (rectify, substitute, mark_paid, print, reschedule…). Every write of every app the
    assistant may call has its own verb in both catalogues: an app with a new one fails here, saying which."""
    assert unnamed(registry.values(), named_actions()) == []


def test_the_guardrail_catches_a_write_whose_verb_nobody_names():
    assert unnamed([FROBNICATE], named_actions()) == ["en: demo.item.frobnicate", "es: demo.item.frobnicate"]
    # A read never shows a card nor a receipt: it needs no verb.
    assert unnamed([get("demo.item.list")], {"en": {}, "es": {}}) == []


def test_a_write_whose_actions_verb_does_not_say_what_it_does_is_named_by_its_own():
    """FIX-HUB-BASE-ASSISTANT-CARD-SAYS-REMOVE-FOR-EMPTYING-A-CART: emptying a cart (``cart_checkout.cart.clear``) said
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
    total_cents: int = Field(json_schema_extra={"money": True})
    expected_balance: int | None = Field(
        description="The cash there should be, in cents; none when it is hidden.", json_schema_extra={"money": True}
    )
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


class CountPreviewOut(Schema):
    expected_balance: int | None = Field(description="The cash there should be, in cents.", json_schema_extra={"money": True})
    difference: int | None = Field(
        description="Counted − expected, in cents (positive = over, negative = short).",
        json_schema_extra={"signed": True, "money": True},
    )


def count_preview(answer: dict, output: type[Schema] = CountPreviewOut) -> Operation:
    return Operation(
        name="demo.item.count_preview",
        kind="query",
        permission="demo.view",
        input=SettlePreviewIn,
        output=output,
        expose_api=False,
        ai={"description": "What counting a demo item would give."},
        fn=lambda ctx, data: answer,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("difference", [13790, -490, 0], ids=["over", "short", "even"])
def test_an_amount_its_read_declares_signed_is_marked_so_and_no_other_amount_is(monkeypatch, difference):
    """FIX-HUB-BASE-ASSISTANT-CARD-POSITIVE-DIFFERENCE-WITHOUT-SIGN: a cash difference over came as a bare amount
    («€137.90») where Cash register writes «+€137.90». An amount the read's schema declares signed (``"signed": true``)
    is marked so, whatever its value, for the card to write its sign; the expected cash beside it, and the amounts a
    write sends, stay as they were."""
    read = count_preview({"expected_balance": 11210, "difference": difference})
    write = declaring({"operation": read.name, "fields": ["expected_balance", "difference"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.preview(ctx(), write, {"id": "7"})
    assert failure is None
    assert [{key: value for key, value in field.items() if key != "label"} for field in fields] == [
        {"name": "expected_balance", "kind": "money", "value": 11210},
        {"name": "difference", "kind": "money", "value": difference, "signed": True},
    ]
    price = next(field for field in assistant.card(get("service.service.create"), {"price": 1500}, "es")["fields"])
    assert price == {"name": "price", "label": price["label"], "kind": "money", "value": 1500}


class PricedPreviewOut(Schema):
    """A read whose amounts are in a currency of its own (an invoice's), as Invoicing's previews answer it."""

    note: str = ""
    total_cents: int = Field(json_schema_extra={"money": True})
    difference: int | None = Field(description="Counted − expected, in cents.", json_schema_extra={"signed": True, "money": True})
    currency: str = ""
    currency_decimals: int | None = None


def priced(monkeypatch, answer: dict) -> list[dict]:
    """The preview of a write whose read answers ``answer``: its data without their labels."""
    read = count_preview({"note": "R1", "total_cents": -12100, "difference": 4200, **answer}, PricedPreviewOut)
    write = declaring({"operation": read.name, "fields": ["note", "total_cents", "difference"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.preview(ctx(), write, {"id": "7"})
    assert failure is None
    return [{key: value for key, value in field.items() if key != "label"} for field in fields]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("answer", "money"),
    [
        ({"currency": "EUR", "currency_decimals": 2}, {"currency": "EUR", "decimals": 2}),
        # Its amounts' minor unit, as the read answers it, even where the currency's own says another (ISK: 0).
        ({"currency": "ISK", "currency_decimals": 2}, {"currency": "ISK", "decimals": 2}),
        ({"currency": "JPY"}, {"currency": "JPY", "decimals": 0}),
    ],
    ids=["its currency and decimals", "decimals as it answers them", "decimals of its currency when it answers none"],
)
def test_an_amount_of_a_preview_carries_the_currency_its_read_answers(monkeypatch, answer, money):
    """FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY: an invoice issued in EUR, rectified once the
    business had moved to another currency, showed «-100,00» in the new one on the card. An amount of the preview
    carries the currency the read answers (``currency``) with its decimals (``currency_decimals``, else the
    currency's own: no yen with cents), the sign of a difference with it; a datum that is no amount, none; and the
    amounts a write sends stay in the business's (the card's ``money``)."""
    assert priced(monkeypatch, answer) == [
        {"name": "note", "kind": "text", "value": "R1"},
        {"name": "total_cents", "kind": "money", "value": -12100, "money": money},
        {"name": "difference", "kind": "money", "value": 4200, "signed": True, "money": money},
    ]
    price = next(field for field in assistant.card(get("service.service.create"), {"price": 1500}, "es")["fields"])
    assert price == {"name": "price", "label": price["label"], "kind": "money", "value": 1500}


@pytest.mark.django_db
def test_a_preview_whose_read_answers_no_currency_invents_none(monkeypatch):
    """Without a currency in the read's answer (Cash register's close: the drawer is in the business's), its amounts
    carry none and the card paints them in the business's, as before."""
    assert [field.get("money") for field in priced(monkeypatch, {})] == [None, None, None]
    assert [field.get("money") for field in priced(monkeypatch, {"currency": "", "currency_decimals": 2})] == [None] * 3


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


class SignedNameOut(Schema):
    name: str = Field(title="Owner", json_schema_extra={"signed": True})
    total_cents: int = Field(json_schema_extra={"signed": True, "money": True})
    paid_cents: str = Field(description="What was paid, in cents, as written.", json_schema_extra={"signed": True})
    counted: int = Field(description="Counted − expected, in cents.", json_schema_extra={"signed": True})


def test_a_preview_marks_signed_only_an_amount(monkeypatch):
    """A sign means over or short: only an amount — a whole number its schema marks ``money`` — may be declared
    signed, said at start like the rest. A text whose name says cents is no amount, nor a number whose description
    says cents without the mark (FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS)."""
    read = count_preview({}, SignedNameOut)
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(
        registry,
        SETTLE.name,
        declaring({"operation": read.name, "fields": ["name", "total_cents", "paid_cents", "counted"]}),
    )
    [error] = preview_errors()
    assert "marks name signed, but it is no amount marked money" in error.msg
    assert "marks paid_cents signed, but it is no amount marked money" in error.msg
    assert "marks counted signed, but it is no amount marked money" in error.msg
    assert "total_cents" not in error.msg


@pytest.mark.parametrize(
    ("prop", "value"),
    [
        ({"type": "string", "signed": True, "money": True}, "Ana"),
        ({"type": "integer", "description": "Counted − expected.", "signed": True, "money": True}, None),
        ({"type": "integer", "description": "Counted − expected.", "signed": "yes", "money": True}, 13790),
    ],
    ids=["a text", "an amount left empty", "not declared with True"],
)
def test_only_an_amount_declared_signed_carries_the_mark(prop, value):
    """The mark is for the card to write a sign on an amount: a datum that is no amount in cents, an amount left empty
    (a difference hidden from this person) or a declaration that is not ``True`` carry none, whatever the schema says."""
    assert "signed" not in assistant._field("difference", "Diferencia", prop, {}, value)


def test_the_previews_of_today_are_declared_right(settle):
    assert preview_errors() == []


# ── What a write's app checks before its card (hub#538) ─────────────────────────────────────────────────────────
# A new member with a role the business does not have showed its card, the person said yes, and only then the write
# refused the role. A write may name, in its ``ai=``, a read of its own app that checks its data (``check``): run as
# the person, with the data of the write its input takes, before the card; its refusal is the write's outcome and
# no card is drawn. Nothing of its answer is shown: a normal write's card stays a single line.


class NoteIn(Schema):
    id: str = Field(min_length=1)
    note: str = ""


def checking(check, *, risk="normal", preview=None, input=NoteIn) -> Operation:
    """A write of demo whose ``ai=`` names ``check`` (and, when dangerous, ``preview``)."""
    declared = {"description": "Notes something on a demo item.", "risk": risk, "check": check}
    if preview is not None:
        declared["preview"] = preview
    return Operation(
        name="demo.item.note",
        kind="command",
        permission="demo.manage",
        input=input,
        output=SettlePreviewOut,
        expose_api=False,
        ai=declared,
        fn=lambda ctx, data: data,
    )


@pytest.fixture
def note(monkeypatch):
    """A normal write that checks its item first, registered as an app's would be, with the read it names."""
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    write = checking(SETTLE_PREVIEW.name)
    monkeypatch.setitem(registry, write.name, write)
    return write


@pytest.mark.django_db
def test_a_write_whose_check_refuses_its_data_gets_no_card_and_says_why(note):
    failure, fields = assistant.preview(ctx(), note, {"id": "gone", "note": "x"})
    assert (failure.outcome, failure.code, fields) == ("error", "demo.item_not_found", None)
    assert json.loads(failure.content)["error"]["message"] == "This item is not there any more."


@pytest.mark.django_db
def test_a_check_that_passes_leaves_a_normal_writes_card_as_it_was(note):
    """Nothing of the check's answer reaches the card: a normal write has no preview."""
    assert assistant.preview(ctx(), note, {"id": "7", "note": "x"}) == (None, None)


class StrictCheckIn(Schema):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)


@pytest.mark.django_db
def test_a_check_reads_only_the_data_its_own_input_takes(monkeypatch):
    """The write's other data (its note) never reach its check: a read that refuses data it does not take still lets
    a write whose data it takes reach its card."""
    strict = Operation(**{**vars(SETTLE_PREVIEW), "name": "demo.item.note_check", "input": StrictCheckIn})
    monkeypatch.setitem(registry, strict.name, strict)
    write = checking(strict.name)
    monkeypatch.setitem(registry, write.name, write)
    assert assistant.preview(ctx(), write, {"id": "7", "note": "x"}) == (None, None)
    failure, _ = assistant.preview(ctx(), write, {"id": "gone", "note": "x"})
    assert failure.code == "demo.item_not_found"


@pytest.mark.django_db
def test_a_check_the_person_may_not_read_is_refused_never_read_for_them(note):
    failure, fields = assistant.preview(ctx({"base.view_home", "demo.manage"}), note, {"id": "7"})
    assert (failure.outcome, failure.code, fields) == ("refused", "permission_denied", None)


@pytest.mark.django_db
def test_a_dangerous_write_is_checked_before_its_preview_is_read(monkeypatch):
    """The check refuses first: the preview is never read for data the write refuses."""
    read: list[str] = []

    def counted(ctx, data):
        read.append(data.id)
        return settle_preview(ctx, data)

    previewed = Operation(**{**vars(SETTLE_PREVIEW), "name": "demo.item.note_preview", "fn": counted})
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    monkeypatch.setitem(registry, previewed.name, previewed)
    write = checking(SETTLE_PREVIEW.name, risk="high", preview={"operation": previewed.name, "fields": ["name"]})
    monkeypatch.setitem(registry, write.name, write)
    failure, _ = assistant.preview(ctx(), write, {"id": "gone"})
    assert (failure.code, read) == ("demo.item_not_found", [])
    failure, fields = assistant.preview(ctx(), write, {"id": "7"})
    assert (failure, shown(fields), read) == (None, [("name", "text", "Item 7")], ["7"])


def check_errors() -> list:
    from django.core import checks

    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E012"]


class NoItemIn(Schema):
    note: str = ""


@pytest.mark.parametrize(
    "write, why",
    [
        (checking("demo.item.nothing"), "names no operation demo.item.nothing"),
        (checking("base.business.get"), "of another app"),
        (checking("demo.item.create"), "not a read"),
        (checking({"operation": "demo.item.settle_preview"}), "is not the name of a read"),
        (checking("demo.item.settle_preview", input=NoItemIn), "the write never takes id"),
    ],
)
def test_a_check_is_checked_at_start(monkeypatch, write, why):
    """Like a preview (base.E005): a check that names no read of its own app, or reads data its write does not
    have, is said at start."""
    monkeypatch.setitem(registry, SETTLE_PREVIEW.name, SETTLE_PREVIEW)
    monkeypatch.setitem(registry, write.name, write)
    [error] = check_errors()
    assert "demo.item.note" in error.msg and why in error.msg


def test_the_checks_of_today_are_declared_right(note):
    assert check_errors() == []


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


def test_the_instructions_answer_how_to_questions_only_from_the_documentation():
    """saas ASSISTANT-F28: how ERPlora works comes from its documentation, cited; what it does not cover is said, never
    made up. Its records still come only from its tools."""
    text = " ".join(assistant.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={}).split())
    assert (
        "For questions about how ERPlora works (how to do something, what an option means, plans), search the "
        "documentation with `base__docs__search` and answer only from what it returns, citing the section; if it "
        "returns nothing, say the documentation does not cover it."
    ) in text
    assert "Never invent a record" in text



def test_the_instructions_keep_ids_out_of_the_answer():
    """hub#538: after creating a member, the answer listed it in a table with «ID 01a192cb-…». The model reads ids to
    call its tools, but names a record to the person by its name, as the card and the screens do, never by its id."""
    text = " ".join(assistant.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={}).split())
    assert (
        "Name a record to the person by its name, as the screens do: never write an id (a code such as "
        "0190a3b4-…) in the answer, not in a table either."
    ) in text


def test_the_instructions_set_the_language_the_money_and_the_screens():
    text = assistant.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={"/settings": "Ajustes"})
    # gh:hub#1046: the old assistant answered anything (films, cinemas) on the business's allowance.
    assert "Only help with this business and with using ERPlora" in text
    assert "Spanish" in text
    # An amount by its mark, not by the words «in cents» (FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS).
    assert "EUR" in text and '"money": true' in text and "minor unit" in text
    assert "[Ajustes](/settings)" in text
    assert "Bar Pepe" in text


@pytest.mark.parametrize(
    ("currency", "decimals", "example"),
    [("EUR", 2, "17.00 EUR → 1700"), ("JPY", 0, "17 JPY → 17"), ("KWD", 3, "17.000 KWD → 17000")],
)
def test_the_instructions_say_an_amount_in_the_currency_its_result_gives(currency, decimals, example):
    """FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY: a tool's result gives its amounts with their
    currency (``currency`` and ``currency_decimals``: an invoice keeps the one it was issued in) and the card paints them
    in it, but the model was told to say every amount in the business's, with two decimals: its text and the card
    disagreed. An amount goes in the minor unit of its currency (no cents in yen), said in the currency its result
    gives, else in the business's."""
    text = assistant.instructions(language="en", currency=currency, decimals=decimals, business="Bar Pepe", screens={})
    assert example in text
    assert "`currency`" in text and "`currency_decimals`" in text
    assert "two decimals" not in text


# ── Who asks: their role and what it may do (hub#585, BASE-F100) ─────────────────────────────────────────────────


def _said(language="en", **who):
    text = assistant.instructions(language=language, currency="EUR", decimals=2, business="Bar Pepe", screens={}, **who)
    return " ".join(text.split())


@pytest.mark.parametrize(
    ("role", "language", "name"),
    [
        (Membership.Role.OWNER, "en", "Owner"),
        (Membership.Role.OWNER, "es", "Propietario"),
        (Membership.Role.ADMIN, "en", "Admin"),
        (Membership.Role.ADMIN, "es", "Administrador"),
        (Membership.Role.MANAGER, "en", "Manager"),
        (Membership.Role.MANAGER, "es", "Encargado"),
        (Membership.Role.EMPLOYEE, "en", "Employee"),
        (Membership.Role.EMPLOYEE, "es", "Empleado"),
    ],
)
def test_the_instructions_name_the_persons_role_in_the_chat_language(role, language, name):
    """hub#585: the model never knew whom it served, so an employee who asked to switch an app off got «too many
    steps» or a made-up «it is already off». It is told their role as the screens name it, and that its tools are
    that role's."""
    assert f"You talk to the «{name}» of this business: your tools are the ones this role may use, no more." in _said(
        language, role=role
    )


@pytest.mark.parametrize(
    ("role", "who"),
    [(Membership.Role.EMPLOYEE, "a manager or the owner"), (Membership.Role.MANAGER, "the owner or an administrator")],
)
def test_a_role_that_cannot_do_something_is_told_who_can_and_no_other_tool_is_tried(role, who):
    text = _said(role=role)
    assert (
        "When they ask for something none of your tools does, do not try other tools for it and never tell the state "
        "of something else instead: say plainly that their role cannot do it here and that "
        f"{who} can, or on which screen it is done."
    ) in text


@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN])
def test_the_owner_and_an_administrator_are_never_told_their_role_cannot(role):
    """They hold every permission of every app: what no tool does is done on its screen, not someone else's."""
    text = _said(role=role)
    assert "their role cannot" not in text
    assert "If something cannot be done from here (you have no tool for it), say on which screen it is done." in text


@pytest.mark.parametrize("role", ["", "staff", None])
def test_without_a_role_of_the_business_no_role_is_named(role):
    """An automation's step (``apps.flow``) or a session with no role here: nobody to name."""
    assert "You talk to the" not in _said(role=role)


def test_a_write_a_manager_approves_is_said_to_ask_for_that_approval():
    """BASE-F100 step 1: an employee is offered the write their app lets a manager approve; the model says it will ask
    a manager to approve it, instead of running it as if it were theirs or saying they cannot."""
    text = _said(role=Membership.Role.EMPLOYEE, approvable=["demo.item.add_line", "demo.item.create"])
    assert (
        "This person needs a manager's approval to run `demo__item__add_line`, `demo__item__create`: before you call "
        "one, say that its card will ask a manager to approve it (their PIN or badge) and that it runs only once "
        "approved."
    ) in text
    assert "approv" not in _said(role=Membership.Role.EMPLOYEE)


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
