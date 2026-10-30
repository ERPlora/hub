"""FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-RAW-VALUES (BASE-F97, step 2): the card of a write the assistant wants to run said
each datum as the model sent it — «Starts at: 2026-11-02T10:00:00+01:00», «Booked through: whatsapp», «Professional:
<uuid>» — where the person reads a day and a time, a channel and a person. Its schema says what each datum is, at any
depth: a moment (``format: date-time``, ``date``, ``time``) is said as the person's language writes it, in the
business's zone; a value of a closed list (``enum``) by the label its app's models give it; a record named by its id
(``format: uuid``, or a datum its schema marks ``refers``) by the read that mark names, run as the person — otherwise
it is left out, never shown by its id.
"""

import dataclasses
import datetime as dt
import json
import re
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from django.conf import settings
from django.core import checks
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.operations import Operation, get, registry
from ninja import Field, Schema

from base import access, assistant
from base.models import Hub, Membership, TrustedDevice
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_record_details import api_key, failed_event, load, signed_in
from base.tests.test_record_details import device as a_device
from base.tests.test_services_assistant import call, turn

A = Scope("host", "a")
ADMIN = frozenset({"base.view_home", "base.administer_hub"})

CUSTOMER = "0192f0b2-1111-7000-8000-000000000001"
SERVICE = "0192f0b2-2222-7000-8000-000000000002"
MEMBER = "0192f0b2-3333-7000-8000-000000000003"
TABLE = "0192f0b2-4444-7000-8000-000000000004"

#: What a card never carries: an id…
AN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
#: …nor a day or a time as ISO 8601 writes them.
AN_ISO_MOMENT = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}")

BOOKING = {
    "customer_id": CUSTOMER,
    "customer": "Ana López",
    "services": [{"service_id": SERVICE}],
    "staff_id": MEMBER,
    "start": "2026-11-02T10:00:00+01:00",
    "source": "counter",
    "notes": "",
}
TABLE_BOOKING = {
    "customer_id": CUSTOMER,
    "guest_name": "Ana López",
    "date": "2026-11-02",
    "time": "21:30:00",
    "party_size": 4,
    "table_id": TABLE,
    "source": "in_person",
}


def ctx(permissions=ADMIN, *, actor="ana", language="es") -> OperationContext:
    return OperationContext(scope=A, actor=actor, permissions=frozenset(permissions), language=language)


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


# ── A moment and a value of a closed list, as the person reads them ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("language", "start", "source"),
    [("es", "2 nov 2026, 10:00", "Mostrador"), ("en", "Nov 2, 2026, 10:00 AM", "Front desk")],
)
def test_a_booking_says_when_and_through_what_as_the_person_reads_them(language, start, source):
    card = assistant.card(get("appointment.appointment.create"), BOOKING, language)
    assert (values(card)["start"], values(card)["source"]) == (start, source)
    assert not AN_ISO_MOMENT.search(json.dumps(card, ensure_ascii=False))


@pytest.mark.parametrize(
    ("language", "expected"),
    [("es", ("2 nov 2026", "21:30", "En el local")), ("en", ("Nov 2, 2026", "9:30 PM", "In person"))],
)
def test_a_table_booking_says_its_day_its_time_and_through_what(language, expected):
    shown = values(assistant.card(get("reservation.reservation.create"), TABLE_BOOKING, language))
    assert (shown["date"], shown["time"], shown["source"]) == expected


def test_a_moment_with_its_offset_is_said_in_the_businesss_zone_and_a_wall_clock_one_as_it_is():
    """Without the person at hand (an automation's card), the deployment's zone (Europe/Madrid): the one every app
    reads a wall-clock time in. An instant of another zone is said at the business's hour; the wall-clock time the
    model sent (the app books it at the business's hour) as it is, summer or winter."""
    op = get("appointment.appointment.create")
    def start(sent: str) -> str:
        return values(assistant.card(op, {**BOOKING, "start": sent}, "es"))["start"]

    assert start("2026-11-02T09:00:00Z") == "2 nov 2026, 10:00"
    assert start("2026-07-02T08:00:00Z") == "2 jul 2026, 10:00"
    assert start("2026-11-02 10:00") == "2 nov 2026, 10:00"


@pytest.mark.django_db
def test_a_moment_is_said_in_the_zone_of_the_business_the_person_works_in():
    """With the person at hand, the business's own zone (Settings › Business: ``base.business.get``)."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "timezone": "Atlantic/Canary"})
    card = assistant.card(get("appointment.appointment.create"), BOOKING, "es", ctx=ctx())
    assert values(card)["start"] == "2 nov 2026, 9:00"


def test_what_is_no_moment_no_value_of_its_list_or_no_id_is_shown_as_sent():
    """The write refuses it with its reason; the card makes nothing up, nor hides it."""
    arguments = {**BOOKING, "start": "mañana a las 10", "source": "carrier pigeon", "staff_id": "Ana"}
    shown = values(assistant.card(get("appointment.appointment.create"), arguments, "es"))
    assert (shown["start"], shown["source"], shown["staff_id"]) == ("mañana a las 10", "carrier pigeon", "Ana")


# ── A record named by its id ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("language", ["es", "en"])
def test_a_record_named_by_its_id_never_reaches_the_card_by_it(language):
    for name, arguments in [("appointment.appointment.create", BOOKING), ("reservation.reservation.create", TABLE_BOOKING)]:
        assert not AN_ID.search(json.dumps(assistant.card(get(name), arguments, language))), name
    shown = values(assistant.card(get("appointment.appointment.create"), BOOKING, language))
    assert "customer_id" not in shown and "staff_id" not in shown
    assert shown["customer"] == "Ana López"
    # Still one service: a list says how many it carries.
    assert shown["services"] == [{}]


class VisitIn(Schema):
    staff_id: UUID
    start: dt.datetime
    source: Literal["counter", "phone"]


class VisitsIn(Schema):
    first: VisitIn
    then: list[VisitIn] = []
    staff_ids: list[UUID] = []


VISITS = Operation(
    name="appointment.appointment.visits",
    kind="command",
    permission="appointment.add_own_appointment",
    input=VisitsIn,
    output=VisitsIn,
    expose_api=False,
    ai={"description": "Books several visits."},
    fn=lambda ctx, data: data,
)


def test_inside_an_object_or_a_list_a_moment_and_a_value_are_said_and_an_id_left_out():
    visit = {"staff_id": MEMBER, "start": "2026-11-02T10:00:00+01:00", "source": "phone"}
    card = assistant.card(VISITS, {"first": visit, "then": [visit], "staff_ids": [MEMBER, MEMBER]}, "es")
    said = {"start": "2 nov 2026, 10:00", "source": "Teléfono"}
    # A list of ids still says how many: each one is there, by no id.
    assert values(card) == {"first": said, "then": [said], "staff_ids": [None, None]}
    assert [field["kind"] for field in card["fields"]] == ["object", "list", "list"]


@pytest.mark.django_db
def test_a_record_its_schema_marks_is_named_by_the_read_of_its_app_as_the_person(make_user):
    """Base's own: «Remove the PIN» named the person by the id the model sent («Persona: saas:3»)."""
    make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva", last_name="Gil")
    card = assistant.card(get("base.person.pin_remove"), {"person": "saas:3"}, "es", ctx=ctx())
    assert values(card) == {"person": "Eva Gil"}
    assert [field["label"] for field in card["fields"]] == ["Persona"]


@pytest.mark.django_db
def test_a_record_the_person_may_not_read_or_that_is_not_there_is_left_out_never_by_its_id(make_user):
    make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva", last_name="Gil")
    op = get("base.person.pin_remove")
    assert values(assistant.card(op, {"person": "saas:3"}, "es", ctx=ctx({"base.view_home"}))) == {}
    assert values(assistant.card(op, {"person": "saas:0"}, "es", ctx=ctx())) == {}
    # Without the person at hand (an automation's card) the read is not run for anybody.
    assert values(assistant.card(op, {"person": "saas:3"}, "es")) == {}


@pytest.mark.parametrize(("language", "label"), [("es", "Terracota"), ("en", "Terracotta")])
def test_a_palette_is_said_by_the_name_my_profile_gives_it(language, label):
    card = assistant.card(get("base.profile.preferences_set"), {"palette": "terracotta"}, language)
    assert values(card) == {"palette": label}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_every_record_a_write_of_base_names_by_its_id_is_named_on_its_card(client, hub_a, monkeypatch):
    """«Revoke» an API key, remove or rename a device, resend or discard a failed event, undo a load or load again what
    did not go in: the card says which, by the name its screen gives it (base's own reads by id), never by the id."""
    monkeypatch.setattr(context, "_test_fallback", None)
    signed_in(client, hub_a)
    key, device, delivery, batch = (made(client, hub_a) for made in (api_key, a_device, failed_event, load))
    owner = OperationContext(scope=Scope("host", hub_a.slug), actor="saas:1", permissions=ADMIN, language="es")
    writes = [
        ("base.api_key.revoke", {"id": key}, {"id": "Tienda online"}),
        ("base.device.remove", {"id": device}, {"id": "Barra"}),
        ("base.device.rename", {"id": device, "name": "Caja"}, {"id": "Barra", "name": "Caja"}),
        ("base.failed_event.retry", {"id": delivery}, {"id": "sale.sale.completed"}),
        ("base.failed_event.discard", {"id": delivery, "reason": "Ya hecho"}, {"id": "sale.sale.completed", "reason": "Ya hecho"}),
        ("base.import.undo", {"id": batch}, {"id": "Peluquería"}),
        ("base.blueprint.import", {"retry_of": batch}, {"retry_of": "Peluquería"}),
    ]
    with use_hub(hub_a):
        shown = {name: values(assistant.card(get(name), arguments, "es", ctx=owner)) for name, arguments, _ in writes}
    assert shown == {name: expected for name, _, expected in writes}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_device_nobody_named_is_said_by_what_it_is_as_the_devices_list_says_it(hub_a, monkeypatch):
    """Settings › Devices shows «Unnamed device» and, under it, what it is («Chrome · macOS»): the card, the latter."""
    monkeypatch.setattr(context, "_test_fallback", None)
    with use_hub(hub_a):
        device = TrustedDevice.objects.create(
            token_digest=access.token_digest("unnamed"), agent="Chrome · macOS", last_entry_at=timezone.now()
        )
        owner = OperationContext(scope=Scope("host", hub_a.slug), actor="saas:1", permissions=ADMIN, language="es")
        assert values(assistant.card(get("base.device.remove"), {"id": str(device.pk)}, "es", ctx=owner)) == {
            "id": "Chrome · macOS"
        }


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_device_with_no_name_nor_a_browser_it_knows_is_left_out(hub_a, monkeypatch):
    """Devices shows it only as «Unnamed device», which says nothing of which: the card leaves it out, never its id."""
    monkeypatch.setattr(context, "_test_fallback", None)
    with use_hub(hub_a):
        device = TrustedDevice.objects.create(token_digest=access.token_digest("bare"), last_entry_at=timezone.now())
        owner = OperationContext(scope=Scope("host", hub_a.slug), actor="saas:1", permissions=ADMIN, language="es")
        assert values(assistant.card(get("base.device.remove"), {"id": str(device.pk)}, "es", ctx=owner)) == {}


@pytest.mark.django_db
def test_the_card_a_turn_shows_names_the_person_and_says_the_moment(make_user):
    make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva", last_name="Gil")
    card = turn(call("base.person.pin_remove", {"person": "saas:3"}), permissions=ADMIN)["confirm"]
    assert values(card) == {"person": "Eva Gil"}


# ── Every write: no id and no ISO moment on any card ──────────────────────────────────────────────────────────────────

#: A datum of each kind the card says in words, as a model sends it.
SENT = {"uuid": MEMBER, "date-time": "2026-11-02T10:00:00+01:00", "date": "2026-11-02", "time": "21:30:00"}


def ids_and_moments(prop: dict, defs: dict, depth: int = 0) -> object:
    """A value of the schema ``prop`` with an id in each datum it declares one (``format: uuid``) and a moment in each
    it declares a day, a day and a time or a time, at any depth, and nothing else; ``None`` when it declares none."""
    ref = prop.get("$ref")
    if ref:
        prop = {**defs.get(ref.rsplit("/", 1)[-1], {}), **{k: v for k, v in prop.items() if k != "$ref"}}
    if prop.get("type") == "string" and prop.get("format") in SENT:
        return SENT[prop["format"]]
    if depth > 8:  # a schema that names itself
        return None
    for branch in [*prop.get("anyOf", []), *prop.get("oneOf", []), *prop.get("allOf", [])]:
        if (value := ids_and_moments(branch, defs, depth + 1)) is not None:
            return value
    if isinstance(prop.get("properties"), dict):
        found = {name: ids_and_moments(inner, defs, depth + 1) for name, inner in prop["properties"].items()}
        return {name: value for name, value in found.items() if value is not None} or None
    for key, wrap in (("items", lambda value: [value]), ("additionalProperties", lambda value: {"key": value})):
        if isinstance(prop.get(key), dict) and (value := ids_and_moments(prop[key], defs, depth + 1)) is not None:
            return wrap(value)
    return None


def test_no_write_lets_an_id_or_an_iso_moment_reach_its_card():
    """Every write the assistant may run: what its schema declares an id or a moment never reaches its card as sent."""
    checked = []
    for name, op in sorted(registry.items()):
        if op.kind != "command" or not assistant.is_tool(op):
            continue
        schema = op.input.model_json_schema()
        arguments = ids_and_moments(schema, schema.get("$defs", {}))
        if arguments:
            checked.append(name)
            text = json.dumps(assistant.card(op, arguments, "es"), ensure_ascii=False)
            assert not AN_ID.search(text), name
            assert not AN_ISO_MOMENT.search(text), name
    # Not an empty sweep: a booking, a table booking and a work schedule (times in a list) are among them.
    assert {"appointment.appointment.create", "reservation.reservation.create", "staff.schedule.create"} <= set(checked)


# ── The ratchet: references nobody marks and lists nobody labels, by app ──────────────────────────────────────────────

#: The references (``format: uuid``) of the assistant's writes no ``refers`` mark names, by app: their card leaves
#: them out. An attempt key (``attempt_key``) is no reference. Only ever lower: an app that marks its own lowers its
#: number here, and none comes in.
UNNAMED_REFERENCES = {
    "appointment": 34,
    "combo": 25,
    "customer": 22,
    "demo": 3,
    "inventory": 15,
    "invoice": 12,
    "kitchen": 23,
    "modifier": 14,
    "online_booking": 7,
    "payment": 8,
    "pricing": 25,
    "printing": 11,
    "sale": 101,
    "schedule": 4,
    "service": 35,
    "staff": 15,
    "task": 15,
    "tax": 4,
    "verifactu": 6,
    "website": 5,
    "whatsapp_inbox": 22,
}

#: The closed lists (``enum`` of text) of the assistant's writes with a value the models of their app give no label,
#: by app: their card says that value as sent. Only ever lower, as above.
UNLABELLED_LISTS = {
    "invoice": 4,
    "kitchen": 1,
    "printing": 1,
    "sale": 3,
    "tax": 5,
    "website": 4,
    "whatsapp_inbox": 2,
}


def unnamed(op: Operation) -> tuple[list[str], list[str]]:
    """``op``'s references no mark names and its closed lists with a value its app gives no label, at any depth."""
    references: list[str] = []
    lists: list[str] = []
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})
    entity = op.name.split(".")[1]

    def walk(name: str, prop: dict, path: str, depth: int) -> None:
        prop = assistant._resolved(prop, defs)
        if depth > 8:
            return
        if prop.get("format") == "uuid" and assistant.refers_of(prop) is None and not is_attempt_key(prop):
            references.append(path)
        choices = [value for value in prop.get("enum", []) if isinstance(value, str) and value]
        if choices and not all(assistant._choice_label(op.app_label, entity, name, value) for value in choices):
            lists.append(path)
        if isinstance(prop.get("items"), dict):
            walk(name, prop["items"], f"{path}[]", depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner, inner_prop, f"{path}.{inner}", depth + 1)

    for name, prop in schema.get("properties", {}).items():
        walk(name, prop, name, 0)
    return references, lists


def by_app(operations) -> tuple[dict[str, int], dict[str, int]]:
    references: dict[str, int] = {}
    lists: dict[str, int] = {}
    for op in operations:
        found_references, found_lists = unnamed(op)
        if found_references:
            references[op.app_label] = references.get(op.app_label, 0) + len(found_references)
        if found_lists:
            lists[op.app_label] = lists.get(op.app_label, 0) + len(found_lists)
    return dict(sorted(references.items())), dict(sorted(lists.items()))


def writes() -> list[Operation]:
    return [op for _, op in sorted(registry.items()) if op.kind == "command" and assistant.is_tool(op)]


def test_every_reference_and_closed_list_of_a_write_is_named_but_the_known_ones():
    """A new reference without its mark, or a new list without its labels, fails here; a fixed one lowers its number."""
    references, lists = by_app(writes())
    assert references == UNNAMED_REFERENCES
    assert lists == UNLABELLED_LISTS


class UnnamedIn(Schema):
    member_id: UUID
    person: str = Field(
        json_schema_extra={"refers": {"read": "base.person.detail", "by": "person", "name": "name"}},
    )
    mode: Literal["kiosk", "frobnicated"]
    source: Literal["counter", "phone"]


UNNAMED = Operation(
    name="appointment.appointment.unnamed",
    kind="command",
    permission="appointment.add_own_appointment",
    input=UnnamedIn,
    output=UnnamedIn,
    expose_api=False,
    ai={"description": "A write with a reference nobody marks and a list nobody labels."},
    fn=lambda ctx, data: data,
)


def test_the_ratchet_counts_a_reference_nobody_marks_and_a_list_nobody_labels():
    assert unnamed(UNNAMED) == (["member_id"], ["mode"])
    assert by_app([UNNAMED, UNNAMED]) == ({"appointment": 2}, {"appointment": 2})


# ── A datum the screen knows by its name, titled by its app (FIX-HUB-BASE-ASSISTANT-DANGER-CARD-CALLS-THE-RECORD-BY-ITS-FIELD-NAME) ──

#: What the card of a dangerous write calls a datum it knows by its name (``assistant-card.ts`` ``FIELDS``, base's
#: catalogue) when its app gives it no title of its own, in Spanish.
KNOWN = json.loads((Path(settings.BASE_DIR) / "base/frontend/locale/es.json").read_text())["base"]["assistant"]["card"][
    "fields"
]

#: Every datum the screen knows by its name that a write's schema titles itself, and what its card calls it in
#: Spanish: the title its app wrote, never the generic word for its name («Registro: 5 (Terraza)»).
TITLED_IN_SPANISH = {
    "attendance.record.close_for_terminated:id": "Persona",
    "base.api_key.revoke:id": "Clave de API",
    "base.device.remove:id": "Dispositivo",
    "base.device.rename:id": "Dispositivo",
    "base.failed_event.discard:id": "Evento caído",
    "base.failed_event.retry:id": "Evento caído",
    "base.import.undo:id": "Importación",
    "base.support.report:description": "¿Qué pasó?",
    **{f"table.session.{action}:id": "Cuenta" for action in (
        "close", "delete", "link_order", "merge", "park", "restore", "set_guests", "split", "transfer",
    )},
    **{f"table.table.{action}:id": "Mesa" for action in ("delete", "move", "update")},
    **{f"table.zone.{action}:id": "Zona" for action in ("delete", "update")},
}


def card_title(field: dict) -> str:
    """What the card calls ``field``, as ``assistant-card.ts`` ``fieldLines`` does: by the title its app wrote, else by
    the screen's word for a datum it knows, else by the label the server gives it."""
    return field["label"] if field.get("titled") else KNOWN.get(field["name"], field["label"])


def test_every_datum_the_screen_knows_that_a_write_titles_is_called_by_its_title(monkeypatch):
    """Every write the assistant may run: a datum the screen knows by its name («Registro» for ``id``) that its app
    titles («Cuenta») is called by that title in Spanish; every other one keeps the screen's word — none goes by its
    name as sent («Id»)."""
    monkeypatch.setattr(assistant, "_reference", lambda value, prop, words: "5 (Terraza)")
    titles: dict[str, str] = {}
    for op in writes():
        props = op.input.model_json_schema().get("properties", {})
        arguments = {name: TABLE for name in props if name in KNOWN}
        for field in assistant.card(op, arguments, "es")["fields"]:
            if card_title(field) != KNOWN[field["name"]]:
                titles[f"{op.name}:{field['name']}"] = card_title(field)
    assert titles == TITLED_IN_SPANISH
    assert not {title for title in titles.values() if title.lower() in {"id", "ids"} or "_" in title}


def test_every_dangerous_write_of_the_platform_titles_the_record_it_names():
    """The record a dangerous write of the platform acts on is called as its screen calls it, in the person's language
    («Dispositivo: Barra», «Evento caído: …»), never «Registro»: its schema titles it, and a catalog says that title in
    Spanish. One that does not comes in here (FIX-HUB-BASE-ASSISTANT-DANGER-CARD-CALLS-THE-RECORD-BY-ITS-FIELD-NAME)."""
    untitled = []
    for op in writes():
        if op.app_label != "base" or assistant.risk(op) != "high":
            continue
        props = op.input.model_json_schema().get("properties", {})
        with translation.override("es"):
            untitled += [
                f"{op.name}:{name}"
                for name in ("id", "ids")
                if name in props and assistant._own_title(name, props[name].get("title")) is None
            ]
    assert untitled == []


def test_no_preview_titles_a_datum_the_screen_knows_by_its_name():
    """What a dangerous write will do (BASE-F98) is said as what it sends: today no read a preview names titles a datum
    the screen knows (Employees' PIN removal says the person's «Nombre» and «Correo electrónico», as pydantic titles
    them); one that does is called by its title, and comes in here."""
    titled = []
    for op in writes():
        declared = assistant.preview_of(op)
        if declared is None:
            continue
        read = registry[declared["operation"]]
        out = assistant._output_schema(read).get("properties", {})
        with translation.override("es"):
            titled += [
                f"{op.name} › {read.name}:{name}"
                for name in declared["fields"]
                if name in KNOWN and assistant._own_title(name, out[name].get("title")) is not None
            ]
    assert titled == []


# ── The mark, checked at start (base.E009) ────────────────────────────────────────────────────────────────────────────


def marking(refers: object, *, name: str = "demo.item.assign") -> Operation:
    class MarkedIn(Schema):
        person: str = Field(json_schema_extra={"refers": refers})

    return Operation(
        name=name,
        kind="command",
        permission="demo.manage",
        input=MarkedIn,
        output=MarkedIn,
        expose_api=False,
        ai={"description": "Gives a demo item to a person."},
        fn=lambda ctx, data: data,
    )


def reference_errors() -> list:
    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E009"]


def test_the_marks_of_every_app_are_sound():
    assert reference_errors() == []


@pytest.mark.parametrize(
    ("write", "why"),
    [
        (marking("base.person.detail"), "is not a read, by and name"),
        (marking({"read": "base.person.nothing", "by": "person", "name": "name"}), "names no operation base.person.nothing"),
        (marking({"read": "base.person.pin_remove", "by": "person", "name": "name"}), "not a read"),
        (marking({"read": "base.person.detail", "by": "who", "name": "name"}), "takes no who"),
        (marking({"read": "base.person.detail", "by": "person", "name": "full_name"}), "gives no full_name"),
        (marking({"read": "base.person.detail", "by": "person", "name": ["name", "nick"]}), "gives no nick"),
        (marking({"read": "base.person.detail", "by": "person", "name": []}), "is not a read, by and name"),
        (
            marking({"read": "appointment.appointment.get", "by": "id", "name": "number"}),
            "of appointment, which demo does not require",
        ),
    ],
)
def test_a_mark_is_checked_at_start(monkeypatch, write, why):
    """Like a preview (base.E005): a mark that names no read, a datum its read does not take or does not give, or an
    app the write's own does not require, is said at start."""
    monkeypatch.setitem(registry, write.name, write)
    [error] = reference_errors()
    assert write.name in error.msg and why in error.msg


# ── What a dangerous write will do (BASE-F98): its preview says each datum in words too ───────────────────────────────


class WhenPreviewOut(Schema):
    name: str
    since: dt.datetime = Field(title="Since")


@pytest.mark.django_db
def test_a_preview_says_a_moment_as_the_person_reads_it_too(monkeypatch):
    """«What will happen» of a dangerous card (BASE-F98) says its data by the same rule as what the write sends: a
    moment its read answers in ISO reaches the card as the person's language writes it, at the business's hour."""
    from base.tests.test_assistant import count_preview, declaring

    read = count_preview({"name": "Item 7", "since": "2026-11-02T09:00:00Z"}, output=WhenPreviewOut)
    write = declaring({"operation": read.name, "fields": ["name", "since"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.preview(ctx({*ADMIN, "demo.view", "demo.manage"}), write, {"id": "7"})
    assert failure is None
    assert [(field["name"], field["value"]) for field in fields] == [("name", "Item 7"), ("since", "2 nov 2026, 10:00")]


# ── An attempt key: never on the card, always in the write (FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-ATTEMPT-KEYS) ───────────

#: A key of the caller's attempt (idempotency), as a model sends it: born once, the same on every retry, so a retry
#: never charges, sends or prints twice. Nobody can judge it: «Clave del intento: charge-0192f5a0-retry-7».
ATTEMPT = "charge-0192f5a0-retry-7"


class KeyedLineIn(Schema):
    text: str
    client_line_id: str = Field(json_schema_extra={"attempt_key": True})


class KeyedIn(Schema):
    note: str
    idempotency_key: str | None = Field(None, json_schema_extra={"attempt_key": True})
    line: KeyedLineIn | None = None
    lines: list[KeyedLineIn] = []


def keyed(fn=lambda ctx, data: data) -> Operation:
    return Operation(
        name="demo.item.keyed",
        kind="command",
        permission="demo.manage",
        input=KeyedIn,
        output=KeyedIn,
        expose_api=False,
        ai={"description": "A write with the key of its attempt."},
        fn=fn,
    )


KEYED_ARGUMENTS = {
    "note": "Mesa 4",
    "idempotency_key": ATTEMPT,
    "line": {"text": "Café", "client_line_id": f"{ATTEMPT}-1"},
    "lines": [{"text": "Té", "client_line_id": f"{ATTEMPT}-2"}],
}


@pytest.mark.parametrize("language", ["es", "en"])
def test_an_attempt_key_its_schema_marks_never_reaches_the_card_at_any_depth(language):
    """Its line is left out, inside an object and in each item of a list too (which still says how many it carries),
    and an empty one leaves no empty line: the person reads what the write does, not the key that makes it safe."""
    card = assistant.card(keyed(), KEYED_ARGUMENTS, language)
    assert values(card) == {"note": "Mesa 4", "line": {"text": "Café"}, "lines": [{"text": "Té"}]}
    assert ATTEMPT not in json.dumps(card, ensure_ascii=False)
    assert values(assistant.card(keyed(), {"note": "Mesa 4", "idempotency_key": None}, language)) == {"note": "Mesa 4"}


class KeyedPreviewOut(Schema):
    name: str
    idempotency_key: str = Field(json_schema_extra={"attempt_key": True})


@pytest.mark.django_db
def test_an_attempt_key_never_reaches_a_preview_either(monkeypatch):
    """«What will happen» of a dangerous card (BASE-F98) says its data by the same rule: a key its read answers is not
    there, even when its app names it among the preview's data."""
    from base.tests.test_assistant import count_preview, declaring

    read = count_preview({"name": "Item 7", "idempotency_key": ATTEMPT}, output=KeyedPreviewOut)
    write = declaring({"operation": read.name, "fields": ["name", "idempotency_key"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.preview(ctx({*ADMIN, "demo.view", "demo.manage"}), write, {"id": "7"})
    assert failure is None
    assert [(field["name"], field["value"]) for field in fields] == [("name", "Item 7")]


@pytest.mark.django_db
def test_the_yes_runs_the_write_with_its_attempt_keys_as_sent(monkeypatch):
    """The card leaves the keys out; the write the yes runs gets every one of them whole, at any depth."""
    received = []
    write = keyed(lambda ctx, data: received.append(data.model_dump()) or data)
    monkeypatch.setitem(registry, write.name, write)
    asked = turn(call(write.name, KEYED_ARGUMENTS))["confirm"]
    assert ATTEMPT not in json.dumps(asked, ensure_ascii=False)
    plan = turn(call(write.name, KEYED_ARGUMENTS), decision={"call_id": "c1", "accepted": True})
    assert plan["executed"][0]["outcome"] == "ok"
    assert received == [KEYED_ARGUMENTS]


@pytest.mark.django_db
def test_a_line_the_assistant_adds_twice_with_its_key_is_one_line():
    """A real write: Demo's line, its card without its key; the yes adds it, and the same line again — a retry with
    the same key — answers the line already there instead of adding another."""
    from base.tests.test_services_assistant import run

    item = run("demo.item.create", name="Mesa 4")
    line = {"id": item["id"], "text": "Café", "qty": "1", "client_line_id": "0192f5a0-0000-7000-8000-000000000001"}
    asked = turn(call("demo.item.add_line", line))["confirm"]
    assert values(asked) == {"text": "Café", "qty": "1"}
    for _ in range(2):
        plan = turn(call("demo.item.add_line", line), decision={"call_id": "c1", "accepted": True})
        assert plan["executed"][0]["outcome"] == "ok"
    lines = run("demo.item.detail", id=item["id"])["lines"]
    assert [(row["text"], row["client_line_id"]) for row in lines] == [("Café", line["client_line_id"])]


# ── The ratchet: attempt keys nobody marks, by app ────────────────────────────────────────────────────────────────────

#: How an attempt key is named in this repo: ``idempotency_key`` (Sales, Payments), ``job_key`` (Printing),
#: ``submit_key`` and ``client_message_id`` (WhatsApp inbox), ``client_line_id`` (Demo), or any name that says
#: idempotency or attempt key. Only a text: ``attempt`` (Printing, which hand-out printed) is a count, and
#: ``tax_category_key`` or ``regime_key`` name a record of a list.
ATTEMPT_KEY_NAME = re.compile(r"idempoten|attempt_key|^(?:job|submit)_key$|^client_\w+_id$")

#: The attempt keys of the assistant's writes no ``attempt_key`` mark declares, by app: their card shows them, or
#: leaves them out only as an id it cannot name. Only ever lower: an app that marks its own lowers its number here,
#: and none comes in.
UNMARKED_ATTEMPT_KEYS = {
    "whatsapp_inbox": 4,
}


def is_attempt_key(prop: dict) -> bool:
    return prop.get("attempt_key") is True


def unmarked_attempt_keys(op: Operation) -> list[str]:
    """``op``'s data that look like an attempt key by their name (``ATTEMPT_KEY_NAME``, a text) and no mark declares
    so, at any depth."""
    found: list[str] = []
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})

    def walk(name: str, prop: dict, path: str, depth: int) -> None:
        prop = assistant._resolved(prop, defs)
        if depth > 8:
            return
        if prop.get("type") == "string" and ATTEMPT_KEY_NAME.search(name) and not is_attempt_key(prop):
            found.append(path)
        if isinstance(prop.get("items"), dict):
            walk(name, prop["items"], f"{path}[]", depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner, inner_prop, f"{path}.{inner}", depth + 1)

    for name, prop in schema.get("properties", {}).items():
        walk(name, prop, name, 0)
    return found


def attempt_keys_by_app(operations) -> dict[str, int]:
    counted: dict[str, int] = {}
    for op in operations:
        if found := unmarked_attempt_keys(op):
            counted[op.app_label] = counted.get(op.app_label, 0) + len(found)
    return dict(sorted(counted.items()))


def test_every_attempt_key_of_a_write_is_marked_but_the_known_ones():
    """A new attempt key without its mark fails here; an app that marks its own lowers its number."""
    assert attempt_keys_by_app(writes()) == UNMARKED_ATTEMPT_KEYS


class UnmarkedKeysIn(Schema):
    idempotency_key: str
    lines: list[KeyedLineIn] = []
    visits: list[VisitIn] = []
    client_visit_id: UUID | None = None
    marked_key: str = Field(json_schema_extra={"attempt_key": True})
    job_key: str = Field(json_schema_extra={"attempt_key": True})
    attempt: int = 1
    tax_category_key: str = ""
    session_token: str = ""


def test_the_ratchet_counts_an_attempt_key_nobody_marks_and_nothing_else():
    """Its name gives it away at any depth, an id one too; a marked one, a count of attempts or the key of a record of
    a list are not counted."""
    op = dataclasses.replace(keyed(), input=UnmarkedKeysIn, output=UnmarkedKeysIn)
    assert unmarked_attempt_keys(op) == ["idempotency_key", "client_visit_id"]
    assert attempt_keys_by_app([op, op]) == {"demo": 4}


def misplaced_marks(op: Operation) -> list[str]:
    """``op``'s data marked ``attempt_key`` that are no text, at any depth."""
    found: list[str] = []
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})

    def walk(prop: dict, path: str, depth: int) -> None:
        prop = assistant._resolved(prop, defs)
        if depth > 8:
            return
        if is_attempt_key(prop) and prop.get("type") != "string":
            found.append(path)
        if isinstance(prop.get("items"), dict):
            walk(prop["items"], f"{path}[]", depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner_prop, f"{path}.{inner}", depth + 1)

    for name, prop in schema.get("properties", {}).items():
        walk(prop, name, 0)
    return found


class MisplacedIn(Schema):
    amount_cents: int = Field(json_schema_extra={"attempt_key": True})
    line: KeyedLineIn
    visit: VisitIn = Field(json_schema_extra={"attempt_key": True})


def test_an_attempt_key_is_marked_only_on_a_text():
    """The mark leaves its datum out of the card: on anything but a text (an amount, an object) it would hide what the
    person confirms. Every operation of every app, at any depth."""
    misplaced = dataclasses.replace(keyed(), input=MisplacedIn, output=MisplacedIn)
    assert misplaced_marks(misplaced) == ["amount_cents", "visit"]
    assert [f"{name}:{path}" for name, op in sorted(registry.items()) for path in misplaced_marks(op)] == []


# ── An amount, known by the mark of its schema (FIX-HUB-BASE-ASSISTANT-MONEY-KNOWN-ONLY-BY-DESCRIPTION-WORDS) ─────────

#: The mark of an amount: a whole number in the minor unit of its currency (``json_schema_extra={"money": True}``).
MONEY = {"money": True}


class PricedLineIn(Schema):
    text: str
    unit_price: int = Field(description="The price of one unit, in minor units of the cart's currency.", json_schema_extra=MONEY)


class PricedIn(Schema):
    # The words of hub#361 and hub#359: neither says «in cents».
    price: int = Field(description="The price, in minor units of the business's currency.", json_schema_extra=MONEY)
    hourly_rate: int | None = Field(None, description="Hourly rate in whole cents.", json_schema_extra=MONEY)
    quantity: int = Field(1, description="How many units.")
    line: PricedLineIn | None = None
    lines: list[PricedLineIn] = []


def priced(input: type[Schema] = PricedIn) -> Operation:
    return Operation(
        name="demo.item.priced",
        kind="command",
        permission="demo.manage",
        input=input,
        output=input,
        expose_api=False,
        ai={"description": "A write with amounts."},
        fn=lambda ctx, data: data,
    )


PRICED_ARGUMENTS = {
    "price": 1500,
    "hourly_rate": 1250,
    "quantity": 2,
    "line": {"text": "Café", "unit_price": 150},
    "lines": [{"text": "Té", "unit_price": 1200}],
}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "country", "one", "twelve"),
    [("es", "ES", "1,50\xa0€", "12,00\xa0€"), ("en", "ES", "€1.50", "€12.00"), ("es", "PL", "1,50\xa0PLN", "12,00\xa0PLN")],
    ids=["es", "en", "a business in zlotys"],
)
def test_an_amount_its_schema_marks_is_money_whatever_its_words_at_any_depth(language, country, one, twelve):
    """hub#361 and hub#359: a price «in minor units…» and a rate «in whole cents» reached the card as a bare figure
    («Precio: 1500»): the card knew an amount only by the words «in cents». Now by its schema's mark: on top, money the
    screen paints in the business's currency; inside an object or a list, said in it as the Hub writes money. A whole
    number that is no amount stays as sent."""
    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": country})
    card = assistant.card(priced(), PRICED_ARGUMENTS, language, ctx=ctx(language=language))
    shown = {field["name"]: (field["kind"], field["value"]) for field in card["fields"]}
    assert shown == {
        "price": ("money", 1500),
        "hourly_rate": ("money", 1250),
        "quantity": ("text", 2),
        "line": ("object", {"text": "Café", "unit_price": one}),
        "lines": ("list", [{"text": "Té", "unit_price": twelve}]),
    }


class WordsOnlyIn(Schema):
    price: int = Field(description="Price in cents.")
    total_cents: int = 0


def test_words_alone_make_no_amount_its_mark_does():
    """One way to say an amount, the mark: the words of a description are the model's, and rewriting them changes
    nothing of the card. Every amount the assistant shows or fills carries its mark (the ratchet below)."""
    card = assistant.card(priced(WordsOnlyIn), {"price": 1500, "total_cents": 4200}, "es")
    assert [(field["name"], field["kind"]) for field in card["fields"]] == [("price", "text"), ("total_cents", "text")]


class DueOut(Schema):
    due: int = Field(description="What is left to pay.", json_schema_extra=MONEY)
    note: str = ""


class InvoicedPreviewOut(Schema):
    totals: DueOut
    currency: str = ""


@pytest.mark.django_db
def test_an_amount_inside_a_datum_of_a_preview_is_said_in_the_currency_its_read_answers(monkeypatch):
    """As the amounts on top of «What will happen» (BASE-F98): an invoice keeps the currency it was issued in."""
    from base.tests.test_assistant import count_preview, declaring

    Hub.objects.update_or_create(slug="a", defaults={"name": "Bar A", "country": "ES"})
    read = count_preview({"totals": {"due": 1200, "note": "R1"}, "currency": "USD"}, output=InvoicedPreviewOut)
    write = declaring({"operation": read.name, "fields": ["totals"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.preview(ctx({*ADMIN, "demo.view", "demo.manage"}, language="en"), write, {"id": "7"})
    assert failure is None
    assert [(field["name"], field["kind"], field["value"]) for field in fields] == [
        ("totals", "object", {"due": "$12.00", "note": "R1"})
    ]


def test_the_model_is_told_an_amount_by_its_mark_whatever_its_description_says():
    """The tool the model fills carries the mark of each amount, at any depth, and its instructions say what the mark
    means: the minor unit of the business's currency. Words like «in cents» are not what tells it."""
    parameters = assistant.tool_spec(priced())["parameters"]
    defs = parameters["$defs"]
    assert assistant._resolved(parameters["properties"]["price"], defs)["money"] is True
    assert assistant._resolved(parameters["properties"]["hourly_rate"], defs)["money"] is True
    assert defs["PricedLineIn"]["properties"]["unit_price"]["money"] is True
    assert "money" not in assistant._resolved(parameters["properties"]["quantity"], defs)
    text = assistant.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={})
    assert '`"money": true`' in text and "17.00 EUR → 1700" in text
    assert "«in cents»" not in text


# ── The ratchet: amounts nobody marks, by app ─────────────────────────────────────────────────────────────────────────

#: How an amount says itself in this repo's schemas: a whole number named ``…_cents``, or whose description speaks of
#: cents or of the minor unit (``in cents``, ``in whole cents``, ``in minor units``, «céntimos»). Not a percentage
#: («Percent off in basis points»), a count, nor a text whose name says cents.
AMOUNT_WORDS = re.compile(r"\bcents?\b|\bminor units?\b|\bcéntimos?\b", re.IGNORECASE)

#: The amounts the assistant shows or fills that no ``money`` mark declares, by app: the card paints them as a bare
#: figure and the model is not told their unit. Only ever lower: an app that marks its own lowers its number here, and
#: none comes in.
UNMARKED_AMOUNTS: dict[str, int] = {}


def is_marked_amount(prop: dict) -> bool:
    return prop.get("money") is True


def looks_like_an_amount(name: str, prop: dict) -> bool:
    return prop.get("type") == "integer" and (
        name.endswith("_cents") or bool(AMOUNT_WORDS.search(str(prop.get("description", ""))))
    )


def data_of(schema: dict, names: list[str] | None = None) -> list[tuple[str, str, dict]]:
    """Each datum of ``schema`` (only ``names`` on top, when given), at any depth: its name, its path and its schema."""
    defs = schema.get("$defs", {})
    found: list[tuple[str, str, dict]] = []

    def walk(name: str, prop: dict, path: str, depth: int) -> None:
        prop = assistant._resolved(prop, defs)
        if depth > 8:
            return
        found.append((name, path, prop))
        if isinstance(prop.get("items"), dict):
            walk(name, prop["items"], f"{path}[]", depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner, inner_prop, f"{path}.{inner}", depth + 1)

    for name, prop in schema.get("properties", {}).items():
        if names is None or name in names:
            walk(name, prop, name, 0)
    return found


def assistant_data(op: Operation) -> list[tuple[str, str, dict]]:
    """What the assistant shows or fills of the tool ``op``: its input (the model's parameters, a write's card) and,
    for a write with a preview, the data of its read's answer the card shows («What will happen»)."""
    found = data_of(op.input.model_json_schema())
    declared = assistant.preview_of(op)
    read = registry.get(declared["operation"]) if isinstance(declared, dict) else None
    if read is not None:
        found += [(name, f"preview:{path}", prop) for name, path, prop in data_of(read.output.model_json_schema(), declared["fields"])]
    return found


def tools() -> list[Operation]:
    return [op for _, op in sorted(registry.items()) if assistant.is_tool(op)]


def unmarked_amounts(op: Operation) -> list[str]:
    """``op``'s data that look like an amount (``looks_like_an_amount``) and no mark declares so, at any depth."""
    return [path for name, path, prop in assistant_data(op) if looks_like_an_amount(name, prop) and not is_marked_amount(prop)]


def amounts_by_app(operations) -> dict[str, int]:
    counted: dict[str, int] = {}
    for op in operations:
        if found := unmarked_amounts(op):
            counted[op.app_label] = counted.get(op.app_label, 0) + len(found)
    return dict(sorted(counted.items()))


def test_every_amount_the_assistant_shows_or_fills_is_marked_but_the_known_ones():
    """A new amount without its mark — or one whose mark is lost while its words say cents — fails here; an app that
    marks its own lowers its number."""
    assert amounts_by_app(tools()) == UNMARKED_AMOUNTS


class UnmarkedPriceLineIn(Schema):
    text: str
    unit_price: int = Field(description="The price of one unit, in minor units.")


class UnmarkedAmountsIn(Schema):
    price: int = Field(description="The price, in minor units of the business's currency.")
    hourly_rate: int | None = Field(None, description="Hourly rate in whole cents.")
    total_cents: int = 0
    lines: list[UnmarkedPriceLineIn] = []
    marked: int = Field(0, description="Price in cents.", json_schema_extra=MONEY)
    discount_percent_bp: int = Field(0, description="Percent off in basis points (1050 = 10.50 %).")
    quantity: int = Field(1, description="How many units.")
    note_cents: str = Field("", description="A note, in cents as written.")


def test_the_ratchet_counts_an_amount_nobody_marks_and_nothing_else():
    """The words of hub#361 («in minor units») and hub#359 («in whole cents») give an amount away, a name in
    ``_cents`` too, at any depth; a marked one, a percentage, a count or a text are not counted."""
    op = priced(UnmarkedAmountsIn)
    assert unmarked_amounts(op) == ["price", "hourly_rate", "total_cents", "lines[].unit_price"]
    assert amounts_by_app([op, op]) == {"demo": 8}


def test_no_amount_the_card_painted_as_money_stops_being_one():
    """What the card painted as money by its words before (a whole number named ``_cents`` or described «in cents»)
    carries the mark now, every one of them: nothing that was money stops being so."""
    def by_words(name: str, prop: dict) -> bool:
        return prop.get("type") == "integer" and (name.endswith("_cents") or "in cents" in str(prop.get("description", "")).lower())

    painted = {(op.name, path) for op in tools() for name, path, prop in assistant_data(op) if by_words(name, prop)}
    marked = {(op.name, path) for op in tools() for _, path, prop in assistant_data(op) if is_marked_amount(prop)}
    assert len(painted) > 50
    assert sorted(painted - marked) == []


def misplaced_money(op: Operation) -> list[str]:
    """``op``'s data marked ``money`` that are no whole number, at any depth, in what it takes and what it answers."""
    return [
        f"{side}:{path}"
        for side, schema in (("in", op.input.model_json_schema()), ("out", op.output.model_json_schema()))
        for _, path, prop in data_of(schema)
        if is_marked_amount(prop) and prop.get("type") != "integer"
    ]


class MisplacedMoneyIn(Schema):
    name: str = Field(json_schema_extra=MONEY)
    ratio: float = Field(json_schema_extra=MONEY)
    line: PricedLineIn = Field(json_schema_extra=MONEY)
    price: int = Field(json_schema_extra=MONEY)


def test_an_amount_is_marked_only_on_a_whole_number():
    """An amount goes in the minor unit of its currency, a whole number: the mark on a text, a fraction or an object
    would paint as money what is none. Every operation of every app, at any depth."""
    assert misplaced_money(priced(MisplacedMoneyIn)) == ["in:name", "in:ratio", "in:line", "out:name", "out:ratio", "out:line"]
    assert [f"{name}:{path}" for name, op in sorted(registry.items()) for path in misplaced_money(op)] == []
