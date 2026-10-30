"""FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-RAW-VALUES (BASE-F97, step 2): the card of a write the assistant wants to run said
each datum as the model sent it — «Starts at: 2026-11-02T10:00:00+01:00», «Booked through: whatsapp», «Professional:
<uuid>» — where the person reads a day and a time, a channel and a person. Its schema says what each datum is, at any
depth: a moment (``format: date-time``, ``date``, ``time``) is said as the person's language writes it, in the
business's zone; a value of a closed list (``enum``) by the label its app's models give it; a record named by its id
(``format: uuid``, or a datum its schema marks ``refers``) by the read that mark names, run as the person — otherwise
it is left out, never shown by its id.
"""

import datetime as dt
import json
import re
from typing import Literal
from uuid import UUID

import pytest
from django.core import checks
from django.utils import timezone
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
#: them out. Only ever lower: an app that marks its own lowers its number here, and none comes in.
UNNAMED_REFERENCES = {
    "appointment": 34,
    "cash_register": 6,
    "combo": 25,
    "customer": 22,
    "demo": 4,
    "inventory": 15,
    "invoice": 12,
    "kitchen": 23,
    "modifier": 14,
    "online_booking": 7,
    "payment": 9,
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
        if prop.get("format") == "uuid" and assistant.refers_of(prop) is None:
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
