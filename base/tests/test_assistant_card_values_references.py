"""How the card of a write the assistant wants to run says each datum (BASE-F97, step 2): never as the model sent it
(«Starts at: 2026-11-02T10:00:00+01:00», «Booked through: whatsapp», «Professional: <uuid>») but as the person reads a
day and a time, a channel and a person. Its schema says what each datum is, at any depth: a moment (``format:
date-time``, ``date``, ``time``) is said as the person's language writes it, in the business's zone; a value of a
closed list (``enum``) by the label its app's models give it; a record named by its id (``format: uuid``, or a datum
its schema marks ``refers``) by the read that mark names, run as the person — otherwise it is left out, never shown by
its id.
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
from django.utils import timezone, translation
from live import assistant as shared
from live.context import OperationContext, Scope
from live.assistant import CHOICES_OF, NAMED, OWN_WORDS, REFERS, choices_of
from live.operations import Operation, get, registry
from ninja import Field, Schema

from base import access, assistant
from base.models import Hub, Membership
from base.models.access import TrustedDevice
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.card_values import ADMIN, VisitIn, ctx, is_attempt_key, reference_errors, values, writes
from base.tests.test_record_details import api_key, device as a_device, failed_event, load, signed_in
from base.tests.test_services_assistant import call, turn

__all__ = ["in_business_a"]

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


# ── A moment and a value of a closed list, as the person reads them ───────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize(
    ("language", "start", "source"),
    [("es", "2 nov 2026, 10:00", "Mostrador"), ("en", "Nov 2, 2026, 10:00 AM", "Front desk")],
)
def test_a_booking_says_when_and_through_what_as_the_person_reads_them(language, start, source):
    card = assistant.cards.card(get("appointment.appointment.create"), BOOKING, language)
    assert (values(card)["start"], values(card)["source"]) == (start, source)
    assert not AN_ISO_MOMENT.search(json.dumps(card, ensure_ascii=False))


@pytest.mark.parametrize(
    ("language", "expected"),
    [("es", ("2 nov 2026", "21:30", "En el local")), ("en", ("Nov 2, 2026", "9:30 PM", "In person"))],
)
def test_a_table_booking_says_its_day_its_time_and_through_what(language, expected):
    shown = values(assistant.cards.card(get("reservation.reservation.create"), TABLE_BOOKING, language))
    assert (shown["date"], shown["time"], shown["source"]) == expected


@HUB_DB
@pytest.mark.parametrize(
    ("language", "expected"), [("es", ("14 de marzo", "1 jun 2015")), ("en", ("March 14", "Jun 1, 2015"))]
)
def test_a_day_without_its_year_is_said_by_its_day_and_its_month(language, expected):
    """A birthday is often known without its year (``--03-14``, as vCard writes it): the card says the day and the
    month, and a day with its year as any other."""
    days = {"customer": "Lucía", "birthday": "--03-14", "anniversary": "2015-06-01"}
    shown = values(assistant.cards.card(get("customer.customer.update"), days, language))
    assert (shown["birthday"], shown["anniversary"]) == expected


@HUB_DB
def test_a_moment_with_its_offset_is_said_in_the_businesss_zone_and_a_wall_clock_one_as_it_is():
    """Outside a hub, the deployment's zone (Europe/Madrid). An instant of another zone is said at the business's hour;
    the wall-clock time the model sent (the app books it at the business's hour) as it is, summer or winter."""
    op = get("appointment.appointment.create")
    def start(sent: str) -> str:
        return values(assistant.cards.card(op, {**BOOKING, "start": sent}, "es"))["start"]

    assert start("2026-11-02T09:00:00Z") == "2 nov 2026, 10:00"
    assert start("2026-07-02T08:00:00Z") == "2 jul 2026, 10:00"
    assert start("2026-11-02 10:00") == "2 nov 2026, 10:00"


@HUB_DB
def test_a_moment_is_said_in_the_zone_of_the_business_the_person_works_in():
    """In the person's hub, the business's own zone (Settings › Business), the clock every app reads."""
    hub, _ = Hub.objects.update_or_create(slug=A.key, defaults={"name": "Bar A", "timezone": "Atlantic/Canary"})
    with use_hub(hub):
        card = assistant.cards.card(get("appointment.appointment.create"), BOOKING, "es", ctx=ctx())
    assert values(card)["start"] == "2 nov 2026, 9:00"


@HUB_DB
def test_what_is_no_moment_no_value_of_its_list_or_no_id_is_shown_as_sent():
    """The write refuses it with its reason; the card makes nothing up, nor hides it."""
    arguments = {**BOOKING, "start": "mañana a las 10", "source": "carrier pigeon"}
    shown = values(assistant.cards.card(get("appointment.appointment.create"), arguments, "es"))
    assert (shown["start"], shown["source"]) == ("mañana a las 10", "carrier pigeon")
    # A reference no mark names, with no id in it (Citas names its professional by its mark: hub#514).
    visit = {"staff_id": "Ana", "start": "2026-11-02T10:00:00+01:00", "source": "phone"}
    assert values(assistant.cards.card(VISITS, {"first": visit}, "es"))["first"]["staff_id"] == "Ana"


# ── A record named by its id ──────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_record_named_by_its_id_never_reaches_the_card_by_it(language):
    for name, arguments in [("appointment.appointment.create", BOOKING), ("reservation.reservation.create", TABLE_BOOKING)]:
        assert not AN_ID.search(json.dumps(assistant.cards.card(get(name), arguments, language))), name
    shown = values(assistant.cards.card(get("appointment.appointment.create"), BOOKING, language))
    assert "customer_id" not in shown and "staff_id" not in shown
    assert shown["customer"] == "Ana López"
    # Its service left out (nobody at hand reads it): the screen counts it among the more, never by its id (hub#835).
    assert shown["services"] == [{}]


@pytest.mark.parametrize("write", ["appointment.appointment.create", "appointment.appointment.update"])
@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("blank", ["   ", "\t", "\u00a0"], ids=["spaces", "tab", "no-break space"])
def test_a_service_whose_name_comes_blank_is_counted_never_said_in_blank(write, language, blank):
    """hub#879: a model that sends a booking's service by a blank name (``{"service": "   "}``) and the card said
    «Servicios:» with nothing after it. Blanks name nothing, as an empty name does: the list reaches the screen unnamed,
    which says «Servicios: 1 elemento»; a real name is still said, and beside its record the record names the line."""
    op = get(write)

    def services(sent: list) -> tuple:
        shown = list_field(assistant.cards.card(op, {"services": sent}, language), "services")
        return shown["value"], shown.get(NAMED, False)

    assert services([{"service": "Tinte"}]) == ([{"service": "Tinte"}], True)
    assert services([{"service": blank}]) == ([{"service": blank}], False)
    assert services([{"service": blank, "service_id": None}])[1] is False
    assert services([{"service": "Tinte"}, {"service": blank}])[1] is False
    assert services([{"service_id": SERVICE, "service": blank}]) == ([{}], True)


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


@HUB_DB
def test_inside_an_object_or_a_list_a_moment_and_a_value_are_said_and_an_id_left_out():
    visit = {"staff_id": MEMBER, "start": "2026-11-02T10:00:00+01:00", "source": "phone"}
    card = assistant.cards.card(VISITS, {"first": visit, "then": [visit], "staff_ids": [MEMBER, MEMBER]}, "es")
    said = {"start": "2 nov 2026, 10:00", "source": "Teléfono"}
    # A list of ids still says how many: each one is there, by no id.
    assert values(card) == {"first": said, "then": [said], "staff_ids": [None, None]}
    assert [field["kind"] for field in card["fields"]] == ["object", "list", "list"]


@HUB_DB
def test_a_record_its_schema_marks_is_named_by_the_read_of_its_app_as_the_person(make_user):
    """Base's own: «Remove the PIN» named the person by the id the model sent («Persona: saas:3»)."""
    make_user("saas:3", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Eva", last_name="Gil")
    card = assistant.cards.card(get("base.person.pin_remove"), {"person": "saas:3"}, "es", ctx=ctx())
    assert values(card) == {"person": "Eva Gil"}
    assert [field["label"] for field in card["fields"]] == ["Persona"]


@HUB_DB
def test_a_record_the_person_may_not_read_or_that_is_not_there_is_left_out_never_by_its_id(make_user):
    make_user("saas:3", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Eva", last_name="Gil")
    op = get("base.person.pin_remove")
    assert values(assistant.cards.card(op, {"person": "saas:3"}, "es", ctx=ctx({"base.view_home"}))) == {}
    assert values(assistant.cards.card(op, {"person": "saas:0"}, "es", ctx=ctx())) == {}
    # Without the person at hand (an automation's card) the read is not run for anybody.
    assert values(assistant.cards.card(op, {"person": "saas:3"}, "es")) == {}


@pytest.mark.parametrize(("language", "label"), [("es", "Terracota"), ("en", "Terracotta")])
def test_a_palette_is_said_by_the_name_my_profile_gives_it(language, label):
    card = assistant.cards.card(get("base.profile.preferences_set"), {"palette": "terracotta"}, language)
    assert values(card) == {"palette": label}


@HUB_DB
def test_every_record_a_write_of_base_names_by_its_id_is_named_on_its_card(client, hub_a):
    """«Revoke» an API key, remove or rename a device, resend or discard a failed event, undo a load or load again what
    did not go in: the card says which, by the name its screen gives it (base's own reads by id), never by the id."""
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
        shown = {name: values(assistant.cards.card(get(name), arguments, "es", ctx=owner)) for name, arguments, _ in writes}
    assert shown == {name: expected for name, _, expected in writes}


@HUB_DB
def test_a_device_nobody_named_is_said_by_what_it_is_as_the_devices_list_says_it(hub_a):
    """Settings › Devices shows «Unnamed device» and, under it, what it is («Chrome · macOS»): the card, the latter."""
    with use_hub(hub_a):
        device = TrustedDevice.objects.create(
            token_digest=access.token_digest("unnamed"), agent="Chrome · macOS", last_entry_at=timezone.now()
        )
        owner = OperationContext(scope=Scope("host", hub_a.slug), actor="saas:1", permissions=ADMIN, language="es")
        assert values(assistant.cards.card(get("base.device.remove"), {"id": str(device.pk)}, "es", ctx=owner)) == {
            "id": "Chrome · macOS"
        }


@HUB_DB
def test_a_device_with_no_name_nor_a_browser_it_knows_is_left_out(hub_a):
    """Devices shows it only as «Unnamed device», which says nothing of which: the card leaves it out, never its id."""
    with use_hub(hub_a):
        device = TrustedDevice.objects.create(token_digest=access.token_digest("bare"), last_entry_at=timezone.now())
        owner = OperationContext(scope=Scope("host", hub_a.slug), actor="saas:1", permissions=ADMIN, language="es")
        assert values(assistant.cards.card(get("base.device.remove"), {"id": str(device.pk)}, "es", ctx=owner)) == {}


@HUB_DB
def test_the_card_a_turn_shows_names_the_person_and_says_the_moment(make_user):
    make_user("saas:3", host=A.key, role=Membership.Role.EMPLOYEE, first_name="Eva", last_name="Gil")
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


@HUB_DB
def test_no_write_lets_an_id_or_an_iso_moment_reach_its_card():
    """Every write the assistant may run: what its schema declares an id or a moment never reaches its card as sent."""
    checked = []
    for name, op in sorted(registry.items()):
        if op.kind != "command" or not assistant.tools.is_tool(op):
            continue
        schema = op.input.model_json_schema()
        arguments = ids_and_moments(schema, schema.get("$defs", {}))
        if arguments:
            checked.append(name)
            text = json.dumps(assistant.cards.card(op, arguments, "es"), ensure_ascii=False)
            assert not AN_ID.search(text), name
            assert not AN_ISO_MOMENT.search(text), name
    # Not an empty sweep: a booking, a table booking and a work schedule (times in a list) are among them.
    assert {"appointment.appointment.create", "reservation.reservation.create", "staff.schedule.create"} <= set(checked)


# ── A list the screen says by its items: only one the server said in words (``NAMED``) ──────────────────────────────


def list_field(card: dict, name: str) -> dict:
    return next(field for field in card["fields"] if field["name"] == name)


@HUB_DB
@pytest.mark.parametrize(
    ("language", "expected"),
    [("es", ["Crear una tarea", "Crear un cliente"]), ("en", ["Create a task", "Create a customer"])],
)
def test_the_permissions_of_a_grant_are_named_item_by_item(language, expected):
    """hub#504: who confirms a grant reads what each permission lets the automation do, as the History names it."""
    card = assistant.cards.card(
        get("flow.flow.grant"),
        {"operations": ["task.task.create", "customer.customer.create"]},
        language,
        ctx=ctx({"*"}, language=language),
    )
    shown = list_field(card, "operations")
    assert (shown["kind"], shown["value"], shown.get(NAMED)) == ("list", expected, True)


@HUB_DB
@pytest.mark.parametrize(("language", "expected"), [("es", ["Ventas / TPV", "Facturación"]), ("en", ["Sales & POS", "Invoicing"])])
def test_the_apps_of_a_blueprint_are_named_item_by_item(language, expected):
    """hub#504: who confirms a template reads which apps it loads, by their name, never by their id."""
    card = assistant.cards.card(
        get("base.blueprint.import"), {"apps": ["sale", "invoice"]}, language, ctx=ctx({"*"}, language=language)
    )
    shown = list_field(card, "apps")
    assert (shown["kind"], shown["value"], shown.get(NAMED)) == ("list", expected, True)


@HUB_DB
def test_a_list_with_a_value_nobody_can_name_says_the_rest_and_counts_it():
    """A stale permission or app is left out, never shown by its code: the screen says the rest and counts it among the more."""
    grant = assistant.cards.card(
        get("flow.flow.grant"), {"operations": ["task.task.create", "ghost.thing.missing"]}, "es", ctx=ctx({"*"})
    )
    blueprint = assistant.cards.card(get("base.blueprint.import"), {"apps": ["sale", "ghost"]}, "es", ctx=ctx({"*"}))
    assert list_field(grant, "operations")["value"] == ["Crear una tarea", None]
    assert list_field(blueprint, "apps")["value"] == ["Ventas / TPV", None]
    assert list_field(grant, "operations")[NAMED] is True
    assert list_field(blueprint, "apps")[NAMED] is True


def text_lists() -> dict[str, list[str]]:
    """Each list of texts of the assistant's writes no schema says anything of (no record, moment, closed list or the
    person's own words): the write and its datum."""
    found: dict[str, list[str]] = {}
    for op in writes():
        schema = op.input.model_json_schema()
        defs = schema.get("$defs", {})
        for name, prop in schema.get("properties", {}).items():
            prop = shared.resolved(prop, defs)
            if prop.get("type") != "array":
                continue
            items = shared.resolved(prop.get("items", {}), defs)
            if items.get("type") == "string" and not {"enum", "format", REFERS, OWN_WORDS} & {*prop.keys(), *items.keys()}:
                found.setdefault(op.name, []).append(name)
    return found


@HUB_DB
def test_no_list_of_texts_sent_as_they_are_is_named():
    """Every one of them, codes or texts no schema marks as the person's own words: as sent, so never said item by item
    as if the server had named it. A list the server says in words is (positive controls: a series of visits, said as
    moments; the options of a select field, the person's own words, hub#2288)."""
    found = text_lists()
    assert "flow.draft.propose" in found
    named = [
        f"{write}:{name}"
        for write, names in found.items()
        for name in names
        if NAMED in list_field(assistant.cards.card(get(write), {name: ["sale.sale.create", "vip"]}, "es"), name)
    ]
    assert named == []
    starts = ["2026-11-02T10:00:00+01:00", "2026-11-09T10:00:00+01:00"]
    visits = list_field(assistant.cards.card(get("appointment.appointment.bulk_create"), {"starts": starts}, "es"), "starts")
    assert (visits["value"], visits.get(NAMED)) == (["2 nov 2026, 10:00", "9 nov 2026, 10:00"], True)
    field = assistant.cards.card(get("customer.field.create"), {"options": ["Terraza", "Dentro"]}, "es")
    options = list_field(field, "options")
    assert (options["value"], options.get(NAMED)) == (["Terraza", "Dentro"], True)


# ── The ratchet: references nobody marks and lists nobody labels, by app ──────────────────────────────────────────────

#: The references (``format: uuid``) of the assistant's writes no ``refers`` mark names, by app: their card leaves
#: them out. An attempt key (``attempt_key``) is no reference. Only ever lower: an app that marks its own lowers its
#: number here, and none comes in.
UNNAMED_REFERENCES = {
    "invoice": 1,
}

#: The closed lists (``enum`` of text) of the assistant's writes with a value the models give no label — of their app,
#: or those their ``choices_of`` mark names —, by app: their card says that value as sent. Only ever lower, as above.
UNLABELLED_LISTS = {
    # The type of a template's button (template.create and .update): it lives in the JSON of its buttons, and no field
    # of the models names its values to point a mark at. The card says the buttons by how many go, never by their codes
    # (a line of two data: test_the_buttons_of_a_template_go_by_how_many_never_by_their_codes, hub#571).
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
        prop = shared.resolved(prop, defs)
        if depth > 8:
            return
        if prop.get("format") == "uuid" and shared.refers_of(prop) is None and not is_attempt_key(prop):
            references.append(path)
        choices = [value for value in prop.get("enum", []) if isinstance(value, str) and value]
        app_label, field_name = choices_of(op.app_label, name, prop)
        if choices and not all(shared.choice_label(app_label, entity, field_name, value) for value in choices):
            lists.append(path)
        if isinstance(prop.get("items"), dict):
            # A list's mark names the values of its items, as it does on the card.
            mark = {CHOICES_OF: prop[CHOICES_OF]} if CHOICES_OF in prop else {}
            walk(name, {**mark, **prop["items"]}, f"{path}[]", depth + 1)
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
    served: Literal["dine_in", "takeaway"] = Field(json_schema_extra={"choices_of": "kitchen.order_type"})
    served_badly: Literal["dine_in", "teleport"] = Field(json_schema_extra={"choices_of": "kitchen.order_type"})
    each_served: list[Literal["dine_in", "takeaway"]] = Field(json_schema_extra={"choices_of": "kitchen.order_type"})


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
    assert unnamed(UNNAMED) == (["member_id"], ["mode", "served_badly"])
    assert by_app([UNNAMED, UNNAMED]) == ({"appointment": 2}, {"appointment": 4})


class MarkedIn(Schema):
    how: Literal["counter", "phone"] | None = Field(None, json_schema_extra={CHOICES_OF: "source"})
    ways: list[Literal["counter", "phone"]] = Field([], json_schema_extra={CHOICES_OF: "source"})
    odd: Literal["counter", "frobnicated"] = Field("counter", json_schema_extra={CHOICES_OF: "source"})
    elsewhere: Literal["counter", "phone"] = Field("counter", json_schema_extra={CHOICES_OF: "demo.source"})


MARKED = dataclasses.replace(UNNAMED, name="appointment.appointment.marked", input=MarkedIn, output=MarkedIn)


def test_the_ratchet_reads_a_closed_list_by_the_field_its_mark_names_as_the_card_does():
    """hub#708: a marked datum is no unnamed list when that field names every value, by itself or through a list; a value
    the field does not name, or a field another app does not have, still counts."""
    assert unnamed(MARKED)[1] == ["odd", "elsewhere"]


# ── A datum the screen knows by its name, titled by its app ───────────────────────────────────────────────────────────

#: What the card of a dangerous write calls a datum it knows by its name (``FIELDS`` of the shared assistant's
#: ``card.ts`` and its catalogue, @erplora/ui) when its app gives it no title of its own, in Spanish.
KNOWN = json.loads(
    (Path(settings.BASE_DIR) / "packages/ui/src/components/Assistant/locales/es.json").read_text()
)["assistant"]["card"]["fields"]

#: Every datum the screen knows by its name that a write's schema titles itself, and what its card calls it in
#: Spanish: the title its app wrote, never the generic word for its name («Registro: 5 (Terraza)»).
TITLED_IN_SPANISH = {
    **{f"appointment.appointment.{action}:id": "Cita" for action in (
        "cancel", "charge", "complete", "confirm", "delete", "mark_no_show", "reschedule", "start", "update",
    )},
    "appointment.appointment.bulk_delete:ids": "Citas",
    "appointment.blocked_time.delete:id": "Bloqueo",
    **{f"appointment.recurring.{action}:id": "Cita periódica" for action in (
        "activate", "deactivate", "delete", "materialize", "update",
    )},
    "attendance.record.close_for_terminated:id": "Persona",
    "base.api_key.revoke:id": "Clave de API",
    "base.device.remove:id": "Dispositivo",
    "base.device.rename:id": "Dispositivo",
    "base.failed_event.discard:id": "Evento caído",
    "base.failed_event.retry:id": "Evento caído",
    "base.import.undo:id": "Importación",
    "base.support.report:description": "¿Qué pasó?",
    **{f"combo.combo.{action}:id": "Menú" for action in ("delete", "set_active", "set_image", "update")},
    **{f"combo.group.{action}:id": "Plato" for action in ("delete", "update")},
    "combo.group.reorder:id": "Menú",
    **{f"combo.option.{action}:id": "Elección" for action in ("delete", "update")},
    **{f"customer.customer.{action}:id": "Cliente" for action in (
        "delete", "erase", "merge", "set_groups", "set_tags", "update",
    )},
    **{f"customer.field.{action}:id": "Campo personalizado" for action in ("delete", "update")},
    **{f"customer.group.{action}:id": "Grupo" for action in ("delete", "update")},
    **{f"customer.tag.{action}:id": "Etiqueta" for action in ("delete", "update")},
    **{f"demo.item.{action}:id": "Elemento" for action in ("add_line", "delete", "update")},
    **{f"flow.flow.{action}:id": "Automatización" for action in (
        "delete", "duplicate", "grant", "run", "set_enabled", "update",
    )},
    "flow.question.answer:id": "Pregunta",
    "flow.run.retry:id": "Ejecución",
    **{f"inventory.category.{action}:id": "Categoría" for action in ("delete", "update")},
    **{f"inventory.product.{action}:id": "Producto" for action in (
        "delete", "print_label", "set_image", "set_sold_out", "update",
    )},
    **{f"modifier.group.{action}:id": "Grupo" for action in ("delete", "update")},
    "modifier.link.detach:id": "Se aplica a",
    **{f"modifier.option.{action}:id": "Opción" for action in ("delete", "update")},
    **{
        f"online_booking.booking.{action}:id": "Reserva"
        for action in ("cancel", "complete", "confirm", "delete", "no_show")
    },
    "online_order.qr_code.regenerate:id": "Mesa",
    **{f"payment.method.{action}:id": "Método" for action in ("activate", "deactivate", "update")},
    **{f"payment.payment.{action}:id": "Pago" for action in ("approve", "cancel", "mark_completed", "mark_sent")},
    **{f"pricing.price_item.{action}:id": "Precio" for action in ("remove", "update")},
    **{f"pricing.price_list.{action}:id": "Tarifa" for action in ("activate", "deactivate", "set_default", "update")},
    **{f"pricing.rule.{action}:id": "Regla de descuento" for action in ("activate", "deactivate", "update")},
    "reservation.blocked_date.delete:id": "Fecha bloqueada",
    **{f"reservation.reservation.{action}:id": "Reserva" for action in (
        "cancel", "complete", "confirm", "delete", "no_show", "seat", "update",
    )},
    "reservation.time_slot.delete:id": "Franja",
    **{f"reservation.waitlist.{action}:id": "Entrada de la lista de espera" for action in (
        "convert", "delete", "update",
    )},
    **{f"sale.department.{action}:id": "Sección" for action in ("delete", "update")},
    **{f"sale.quick_note.{action}:id": "Nota rápida" for action in ("delete", "update")},
    **{f"schedule.override.{action}:id": "Cambio temporal" for action in ("delete", "update")},
    **{f"schedule.special_day.{action}:id": "Día especial" for action in ("delete", "update")},
    **{f"service.assignment.{action}:id": "Profesional del servicio" for action in ("remove", "update")},
    **{f"service.category.{action}:id": "Categoría" for action in ("delete", "update")},
    **{f"service.grant.{action}:id": "Bono vendido" for action in ("adjust", "link", "redeem", "void")},
    **{f"service.package.{action}:id": "Paquete" for action in ("delete", "update")},
    **{f"service.service.{action}:id": "Servicio" for action in ("archive", "restore", "set_image", "update")},
    "service.session.release:id": "Sesión del bono",
    **{f"service.session.{action}:ids": "Sesiones del bono" for action in ("return", "settle")},
    **{f"staff.member.{action}:id": "Miembro del personal" for action in ("deactivate", "terminate", "update")},
    "staff.role.update:id": "Rol",
    **{f"staff.schedule.{action}:id": "Horario" for action in ("delete", "set_active", "update")},
    **{f"staff.time_off.{action}:id": "Ausencia" for action in ("approve", "cancel", "reject")},
    **{f"table.session.{action}:id": "Cuenta" for action in (
        "close", "delete", "link_order", "merge", "park", "restore", "set_guests", "split", "transfer",
    )},
    **{f"table.table.{action}:id": "Mesa" for action in ("delete", "move", "update")},
    **{f"table.zone.{action}:id": "Zona" for action in ("delete", "update")},
    **{f"task.project.{action}:id": "Proyecto" for action in ("delete", "update")},
    **{f"task.task.{action}:id": "Tarea" for action in ("assign", "complete", "delete", "set_status", "update")},
    **{f"tax.rule.{action}:id": "Regla" for action in ("activate", "deactivate", "end")},
    **{f"tip.tip.{action}:id": "Propina" for action in ("update", "void")},
    **{f"whatsapp_inbox.conversation.{action}:id": "Conversación" for action in (
        "assign", "erase", "flag", "link_customer", "mark_read", "set_status",
    )},
    "whatsapp_inbox.message.retry:id": "Mensaje",
    "whatsapp_inbox.message.send:id": "Conversación",
    "whatsapp_inbox.note.add:id": "Conversación",
    "whatsapp_inbox.note.delete:id": "Nota",
    **{f"whatsapp_inbox.template.{action}:id": "Plantilla" for action in ("delete", "retry", "update")},
}


def card_title(field: dict) -> str:
    """What the card calls ``field``, as ``fieldLines`` of the shared assistant's ``card.ts`` does: by the title its app wrote, else by
    the screen's word for a datum it knows, else by the label the server gives it."""
    return field["label"] if field.get("titled") else KNOWN.get(field["name"], field["label"])


def test_every_datum_the_screen_knows_that_a_write_titles_is_called_by_its_title(monkeypatch):
    """Every write the assistant may run: a datum the screen knows by its name («Registro» for ``id``) that its app
    titles («Cuenta») is called by that title in Spanish; every other one keeps the screen's word — none goes by its
    name as sent («Id»)."""
    monkeypatch.setattr(assistant.cards, "_reference", lambda value, prop, words: "5 (Terraza)")
    titles: dict[str, str] = {}
    for op in writes():
        props = op.input.model_json_schema().get("properties", {})
        arguments = {name: TABLE for name in props if name in KNOWN}
        for field in assistant.cards.card(op, arguments, "es")["fields"]:
            if card_title(field) != KNOWN[field["name"]]:
                titles[f"{op.name}:{field['name']}"] = card_title(field)
    assert titles == TITLED_IN_SPANISH
    assert not {title for title in titles.values() if title.lower() in {"id", "ids"} or "_" in title}


def test_every_dangerous_write_of_the_platform_flow_and_reservation_titles_the_record_it_names():
    """The record a dangerous write of the platform, Automations or Reservations acts on is called as its screen calls
    it, in the person's language («Dispositivo: Barra», «Automatización: Bienvenida», «Reserva: Ana…»), never
    «Registro»: its schema titles it, and a catalog says that title in Spanish. One that does not comes in here
    (hub#428, hub#499 and hub#549)."""
    untitled = []
    checked = []
    for op in writes():
        if op.app_label not in {"base", "flow", "reservation"} or shared.risk(op) != "high":
            continue
        checked.append(op.name)
        props = op.input.model_json_schema().get("properties", {})
        with translation.override("es"):
            untitled += [
                f"{op.name}:{name}"
                for name in ("id", "ids")
                if name in props and shared.own_title(name, props[name].get("title")) is None
            ]
    assert {
        "reservation.reservation.delete",
        "reservation.reservation.no_show",
        "reservation.reservation.cancel",
        "reservation.time_slot.delete",
        "reservation.blocked_date.delete",
        "reservation.waitlist.delete",
    } <= set(checked)
    assert untitled == []


def test_no_preview_titles_a_datum_the_screen_knows_by_its_name():
    """What a dangerous write will do (BASE-F98) is said as what it sends: today no read a preview names titles a datum
    the screen knows (Employees' PIN removal says the person's «Nombre» and «Correo electrónico», as pydantic titles
    them); one that does is called by its title, and comes in here."""
    titled = []
    for op in writes():
        declared = shared.preview_of(op)
        if declared is None:
            continue
        read = registry[declared["operation"]]
        out = shared.output_schema(read).get("properties", {})
        with translation.override("es"):
            titled += [
                f"{op.name} › {read.name}:{name}"
                for name in declared["fields"]
                if name in KNOWN and shared.own_title(name, out[name].get("title")) is not None
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


@HUB_DB
def test_a_preview_says_a_moment_as_the_person_reads_it_too(monkeypatch):
    """«What will happen» of a dangerous card (BASE-F98) says its data by the same rule as what the write sends: a
    moment its read answers in ISO reaches the card as the person's language writes it, at the business's hour."""
    from base.tests.test_assistant_previews import count_preview, declaring

    read = count_preview({"name": "Item 7", "since": "2026-11-02T09:00:00Z"}, output=WhenPreviewOut)
    write = declaring({"operation": read.name, "fields": ["name", "since"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.cards.preview(ctx({*ADMIN, "demo.view", "demo.manage"}), write, {"id": "7"})
    assert failure is None
    assert [(field["name"], field["value"]) for field in fields] == [("name", "Item 7"), ("since", "2 nov 2026, 10:00")]
