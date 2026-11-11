"""Services with the platform's assistant (flow service-business-currency): every amount a write of Services takes
is money for the assistant — the card the person confirms paints it in the business's currency (``kind == "money"``)
and the assistant's instructions tell the AI to send it in the minor unit of that currency (17 € → 1700, ¥17 → 17).
An amount is a ``Cents`` field of the schemas (bounded by ``MAX_CENTS``); a write that is a tool of the assistant with
such a field must hand it to the card as money, or the AI could send 65 for «65 €».

And by its name (FIX-HUB-SERVICE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, every datum a write
of Services sends reaches the card by the name the Services screens give it, never by the title pydantic makes up from
the field («Absorbed Id», «Tax Category Key», «Items»). The card is base's (``base.assistant.card``); the names are
service's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import dataclasses
import datetime as dt
import gettext
import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import formats, timezone, translation
from live.context import OperationContext, Scope
from live.errors import AppInactive, Conflict, PermissionDenied
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import INTERNAL, get, registry
from pydantic import ValidationError

from apps.customer.models import Customer
from apps.service.models import Assignment, Grant, Package
from apps.service.schemas import MAX_CENTS
from base import assistant
from base.business import business_zone
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID, list_field, unnamed

from .conftest import ctx_for, make_category, make_customer, make_grant, make_member, make_package, make_redemption, make_service

APP = Path(apps.get_app_config("service").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["service"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["service"]

#: The writes of Services the assistant calls, by name.
TOOLS = sorted(name for name, op in registry.items() if op.app_label == "service" and op.kind == "command" and assistant.is_tool(op))


def money_fields(name: str) -> list[str]:
    """The fields of the input of ``name`` that are an amount (``Cents``: at most ``MAX_CENTS``)."""
    schema = assistant._schema(get(name))
    defs = schema.get("$defs", {})
    return [field for field, prop in schema.get("properties", {}).items() if assistant._resolved(prop, defs).get("maximum") == MAX_CENTS]


def test_the_writes_with_an_amount_are_found():
    """The detector is not empty: a service's price and a voucher's closed price are among them."""
    found = {(name, field) for name in TOOLS for field in money_fields(name)}
    assert {("service.service.create", "price"), ("service.package.create", "fixed_price")} <= found


@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("name", TOOLS)
def test_every_amount_of_a_write_reaches_the_card_as_money(name, language):
    fields = money_fields(name)
    card = assistant.card(get(name), {field: 1500 for field in fields}, language)
    assert {field["name"]: field["kind"] for field in card["fields"]} == dict.fromkeys(fields, "money")


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def named_by_service(op, name: str, title: str | None) -> bool:
    """Whether service itself names the datum ``name`` of ``op``: by its schema's own title, by the ``verbose_name`` of
    one of its models, or by its own catalog. A title pydantic made up that another app's catalog happens to translate
    («Reference» → «Referencia», from Printing's) is not a name of Services: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("service", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_service_reaches_a_spanish_card_by_its_technical_name():
    """Every write of service the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up. By where the name comes from, not by the word: «Color» is said the same
    in both languages and is its model's."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 23  # positive control: the registry has service's writes (not the platform's own)
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_service(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_the_duplicate_customer_whose_vouchers_move():
    """Customers merges a duplicate card into the one that stays: the duplicate as its merge screen calls it."""
    reassign = get("service.grant.reassign")
    assert labels(assistant.card(reassign, {"absorbed_id": "x"}, "es")) == ["Ficha duplicada"]
    assert labels(assistant.card(reassign, {"absorbed_id": "x"}, "en")) == ["Duplicate customer"]


def test_the_card_names_the_tax_category_of_a_service_as_its_form():
    for name in ("service.service.create", "service.service.update"):
        arguments = {"tax_category_key": "general"}
        assert labels(assistant.card(get(name), arguments, "es")) == [SCREENS["services"]["form"]["tax"]]
        assert labels(assistant.card(get(name), arguments, "en")) == [SCREENS_EN["services"]["form"]["tax"]]
    settings = get("service.settings.update")
    arguments = {"default_tax_category_key": "general"}
    assert labels(assistant.card(settings, arguments, "es")) == [SCREENS["settings"]["defaultTax"]]
    assert labels(assistant.card(settings, arguments, "en")) == [SCREENS_EN["settings"]["defaultTax"]]


def test_the_card_names_the_services_a_package_includes_as_its_form():
    create = get("service.package.create")
    arguments = {"items": [{"service": "Corte"}]}
    assert labels(assistant.card(create, arguments, "es")) == [SCREENS["packages"]["form"]["lines"]]
    assert labels(assistant.card(create, arguments, "en")) == [SCREENS_EN["packages"]["form"]["lines"]]


def test_the_card_titles_the_refund_or_void_that_gives_sessions_back_by_services_own_words():
    """Sales gives back the sessions spent in a sale it refunds or voids: the card titles that document by what it is,
    with service's own words, not with the «Referencia» another app's catalog lends to pydantic's «Reference» (the
    card that names a real refund under it: test_a_write_of_services_names_the_sale_the_lines_the_appointment_…)."""
    reference = assistant._schema(get("service.session.return"))["properties"]["reference"]
    assert named_by_service(get("service.session.return"), "reference", reference.get("title"))
    with translation.override("es"):
        assert translation.gettext(reference["title"]) == "Devolución o anulación"
        assert translation.gettext("Reference") == "Referencia"  # the lent word the guardrail must not take for one
    with translation.override("en"):
        assert translation.gettext(reference["title"]) == "Refund or void"


# ── The records a write names by their id (hub#676) ──────────────────────────────────────────────────────────────────

#: What each write of Services names by its id, and which record that is.
NAMED = {
    "service.assignment.assign": {"service_id": "service", "member_id": "member"},
    "service.assignment.remove": {"id": "assignment"},
    "service.assignment.update": {"id": "assignment"},
    "service.category.create": {"parent_id": "parent"},
    "service.category.delete": {"id": "category"},
    "service.category.update": {"id": "category", "parent_id": "parent"},
    "service.grant.adjust": {"id": "grant"},
    "service.grant.create": {"package_id": "package", "customer_id": "customer"},
    "service.grant.redeem": {"id": "grant", "service_id": "service", "member_id": "member"},
    "service.grant.void": {"id": "grant"},
    "service.package.delete": {"id": "package"},
    "service.package.update": {"id": "package"},
    "service.service.archive": {"id": "service"},
    "service.service.create": {"category_id": "category"},
    "service.service.restore": {"id": "service"},
    "service.service.set_image": {"id": "service"},
    "service.service.update": {"id": "service", "category_id": "category"},
    "service.session.hold": {"grant_id": "grant", "service_id": "service"},
    "service.session.release": {"id": "session"},
    "service.session.settle": {"customer_id": "customer"},
}
#: The sessions a write names at once, by their ids.
OVER_SESSIONS = ("service.session.return", "service.session.settle")
#: What a write of Services names by its id that is Sales' or Appointments', which Services does not require: the sale,
#: the line of a sale, the appointment, the line of an open check and the refund or the void that gives sessions back.
#: Services' own read names each by the read of its app, as whoever asks (``service.record.get``, hub#756).
TILL = {
    "service.grant.create": {"sale_id": "sale", "sale_line_id": "sale_line"},
    "service.grant.redeem": {"sale_id": "sale", "appointment_id": "appointment"},
    "service.session.hold": {"order_line_id": "check_line"},
    "service.session.return": {"reference": "refund"},
    "service.session.settle": {"sale_id": "sale"},
}
TILL_TITLES = {
    "es": {
        "appointment": "Cita",
        "check_line": "Línea de la cuenta",
        "refund": "Devolución o anulación",
        "sale": "Venta",
        "sale_line": "Línea de venta",
    },
    "en": {
        "appointment": "Appointment",
        "check_line": "Check line",
        "refund": "Refund or void",
        "sale": "Sale",
        "sale_line": "Sale line",
    },
}
#: The read of another app ``service.record.get`` names each record of ``TILL`` by.
BEHIND_OF = {
    "sale": "sale.sale.get",
    "sale_line": "sale.record.get",
    "check_line": "sale.record.get",
    "refund": "sale.record.get",
    "appointment": "appointment.appointment.get",
}
BEHIND = tuple(sorted(set(BEHIND_OF.values())))
TITLES = {
    "es": {
        "assignment": "Profesional del servicio",
        "category": "Categoría",
        "customer": "Cliente",
        "grant": "Bono vendido",
        "member": "Profesional",
        "package": "Paquete",
        "parent": "Categoría padre",
        "service": "Servicio",
        "session": "Sesión del bono",
    },
    "en": {
        "assignment": "Professional of a service",
        "category": "Category",
        "customer": "Customer",
        "grant": "Voucher sold",
        "member": "Professional",
        "package": "Package",
        "parent": "Parent category",
        "service": "Service",
        "session": "Voucher session",
    },
}
#: When the voucher of ``a_salon`` was sold (midday: the same day in any zone of Europe).
SOLD_ON = dt.datetime(2026, 10, 3, 12, tzinfo=dt.UTC)
SOLD_ON_SAID = {"es": "3 oct 2026", "en": "Oct 3, 2026"}
#: The roles a business gives that run Services' writes.
ROLES = ("hub_employee", "hub_manager", "hub_admin", "hub_owner")


def references(op) -> set[str]:
    """The data of ``op``'s input its schema declares an id of (``format: uuid``)."""
    schema = op.input.model_json_schema()
    props = schema.get("properties", {})
    return {name for name, prop in props.items() if assistant._resolved(prop, schema.get("$defs", {})).get("format") == "uuid"}


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def no_id(card: dict) -> bool:
    return not AN_ID.search(json.dumps(card, ensure_ascii=False))


def person(hub, role: str = "hub_admin", language: str = "es", without: frozenset = frozenset()) -> OperationContext:
    """Whoever asks in ``hub`` with ``role``, in ``language``, lacking the permissions ``without``."""
    return OperationContext(
        scope=Scope("host", hub.slug),
        actor="tester",
        permissions=permissions_for_role(all_live_app_configs(), role) - without,
        language=language,
    )


def sold(package, customer, on: dt.datetime = SOLD_ON):
    grant = make_grant(package, customer)
    Grant.objects.filter(pk=grant.pk).update(granted_at=on)
    return grant


def a_salon() -> dict:
    """What the Services screens of a hair salon show: «Corte» in «Peluquería», done by Ana López, and «Bono 5 cortes»
    sold to Lucía Pérez on 3 October, with a session held for a «Corte»."""
    category = make_category("Peluquería")
    parent = make_category("Belleza")
    service = make_service("Corte", category=category)
    member = make_member("Ana", "López")
    customer = make_customer("Lucía Pérez")
    package = make_package("Bono 5 cortes", services=[service], sessions=5)
    grant = sold(package, customer)
    session = make_redemption(grant, service)
    assignment = Assignment.objects.create(service=service, member=member)
    return {
        "service": service.id,
        "category": category.id,
        "parent": parent.id,
        "package": package.id,
        "member": member.id,
        "customer": customer.id,
        "grant": grant.id,
        "session": session.id,
        "assignment": assignment.id,
    }


def said(language: str = "es") -> dict:
    """How the card names each record of ``a_salon``."""
    return {
        "service": "Corte",
        "category": "Peluquería",
        "parent": "Belleza",
        "package": "Bono 5 cortes",
        "member": "Ana López",
        "customer": "Lucía Pérez",
        "grant": f"Bono 5 cortes · Lucía Pérez · {SOLD_ON_SAID[language]}",
        "session": "Bono 5 cortes · Lucía Pérez · Corte",
        "assignment": "Corte · Ana López",
    }


def run(ctx: OperationContext, name: str, data: dict):
    op = get(name)
    return op(ctx, op.input.model_validate(data))


def a_till(hub, salon: dict) -> dict:
    """What Sales and Appointments show of ``a_salon``'s day, made by their own operations: an open check with a «Tinte»
    line, a sale of a «Tinte» part of which was refunded, a second sale that was voided, and Lucía Pérez's «Corte» with
    Ana López a week from today at 10:00 (inside the time ahead Appointments books)."""
    from apps.schedule.models import ScheduleSettings, WeekDay

    owner = person(hub, "hub_owner")
    dye = run(owner, "service.service.create", {"name": "Tinte", "price": 3000, "tax_category_key": "service.generic"})
    # By card: cash would ask for an open cash session.
    card = next(row for row in run(owner, "sale.payment_method.list", {}).rows if row.type == "card")
    check = run(owner, "sale.order.open", {"service_lines": [{"service_id": str(dye.id)}]})

    def charged(key: str):
        lines = [{"service_id": str(dye.id)}]
        return run(owner, "sale.sale.complete", {"idempotency_key": key, "service_lines": lines, "payments": [{"method_id": str(card.id)}]})

    sale, voided = charged("till-756-0001"), charged("till-756-0002")
    refund = run(
        owner,
        "sale.sale.refund",
        {"sale_id": str(sale.id), "reason": "Mal color", "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 500}]},
    )
    run(owner, "sale.sale.void", {"sale_id": str(voided.id), "reason": "Cobrada dos veces"})
    # Open every hour: the appointment is booked whatever the business's opening hours.
    WeekDay.objects.all().delete()
    ScheduleSettings.objects.all().delete()
    day = booked_on()
    booked = run(
        owner,
        "appointment.appointment.create",
        {
            "customer_id": str(salon["customer"]),
            "services": [{"service_id": str(salon["service"])}],
            "staff_id": str(salon["member"]),
            "start": f"{day.isoformat()}T10:00:00",
        },
    )
    return {
        "sale": sale.id,
        "number": sale.number,
        "sale_line": sale.lines[0].id,
        "appointment": booked.id,
        "day": day,
        "check_line": check.lines[0].id,
        "refund": refund.refund_id,
        "voided": voided.id,
        "voided_number": voided.number,
    }


def booked_on() -> dt.date:
    """The day of the appointment of ``a_till``: a week from today, at the business's hour."""
    return timezone.localtime(timezone.now(), business_zone()).date() + dt.timedelta(days=7)


def as_appointments_says(day: dt.date, language: str) -> str:
    """``day`` with its weekday first, as Appointments says the day of an appointment («martes, 2 de marzo de 2027»)."""
    with translation.override(language):
        return f"{formats.date_format(day, 'l')}, {formats.date_format(day, 'DATE_FORMAT')}"


def said_at_the_till(till: dict, language: str = "es") -> dict:
    """How the card names each record of ``a_till``: the sale by its number, the lines by what they charge, the
    appointment as Appointments' cards say it and the refund by the sale it gives back."""
    refund = {"es": "Devolución de la venta {}", "en": "Refund of sale {}"}[language]
    return {
        "sale": till["number"],
        "sale_line": "Tinte",
        "appointment": f"Lucía Pérez · {as_appointments_says(till["day"], language)} · 10:00 · Ana López",
        "check_line": "Tinte",
        "refund": refund.format(till["number"]),
    }


def till_cards(till: dict, ctx: OperationContext | None, language: str = "es") -> dict:
    """The card of each write of ``TILL`` naming every record of Sales or Appointments it names by its id."""
    return {
        write: assistant.card(get(write), {datum: str(till[kind]) for datum, kind in data.items()}, language, ctx)
        for write, data in TILL.items()
    }


def named_at_the_till(till: dict, language: str = "es") -> dict:
    names = said_at_the_till(till, language)
    return {write: {datum: names[kind] for datum, kind in data.items()} for write, data in TILL.items()}


def cards(salon: dict, ctx: OperationContext | None, language: str = "es") -> dict:
    """The card of each write of ``NAMED`` naming every record it names by its id, as ``ctx``'s person would confirm it."""
    return {
        write: assistant.card(get(write), {datum: str(salon[kind]) for datum, kind in data.items()}, language, ctx)
        for write, data in NAMED.items()
    }


def named_as_the_screens(language: str = "es") -> dict:
    names = said(language)
    return {write: {datum: names[kind] for datum, kind in data.items()} for write, data in NAMED.items()}


def left_out_of_every_card() -> dict:
    return dict.fromkeys(NAMED, {})


def test_every_record_a_write_of_services_names_by_its_id_is_listed_here():
    """Positive control of the tests below: a new reference of a write of Services comes in here, with its name."""
    writes = [get(name) for name in TOOLS]
    till = {(write, datum) for write, data in TILL.items() for datum in data}
    assert {
        op.name: found for op in writes if (found := {datum for datum in references(op) if (op.name, datum) not in till})
    } == {write: set(data) for write, data in NAMED.items()}
    assert {(op.name, datum) for op in writes for datum in references(op)} >= till


def test_no_write_of_services_leaves_a_record_unnamed():
    """The sale, the appointment and the lines are of apps Services does not require, and the reference of a return is
    what gives it back: all of them are named too (hub#756). ``base``'s ratchet counts none of Services."""
    assert {f"{name}:{path}" for name in TOOLS for path in unnamed(get(name))[0]} == set()


# ── What Sales and Appointments name, by their own reads (hub#756) ─────────────────────────────────────────────────


def titled(card: dict) -> dict:
    """Each datum of ``card`` by its title and the name it says."""
    return {field["name"]: (field["label"], field["value"]) for field in card["fields"]}


def assert_left_out(shown: dict) -> None:
    """Every card of ``TILL`` leaves out what Sales and Appointments name, and none of them says it by its id."""
    assert {write: values(card) for write, card in shown.items()} == dict.fromkeys(TILL, {})
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_write_of_services_names_the_sale_the_lines_the_appointment_and_the_refund_as_their_screens_do(
    language, hub_a, no_fallback
):
    """«Véndele el bono de la venta de esta mañana», «gasta la sesión en la cita de Lucía»: the card says which sale (by
    its number), which line (by what it charges), which appointment (as Appointments' cards say it) and which refund
    gives the sessions back (by its sale), each under the title its screens give it («Venta», never «Id»), never by an
    id."""
    with use_hub(hub_a):
        till = a_till(hub_a, a_salon())
        shown = till_cards(till, person(hub_a, language=language), language)
    names, titles = said_at_the_till(till, language), TILL_TITLES[language]
    assert {write: titled(card) for write, card in shown.items()} == {
        write: {datum: (titles[kind], names[kind]) for datum, kind in data.items()} for write, data in TILL.items()
    }
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(("language", "said"), [("es", "Anulación de la venta {}"), ("en", "Void of sale {}")])
def test_the_sessions_a_void_gives_back_name_the_sale_voided(language, said, hub_a, no_fallback):
    """SERVICE-F27: Sales gives back the sessions of a sale it voids with the sale itself as the document."""
    with use_hub(hub_a):
        till = a_till(hub_a, a_salon())
        card = assistant.card(
            get("service.session.return"), {"reference": str(till["voided"])}, language, person(hub_a, language=language)
        )
    assert values(card) == {"reference": said.format(till["voided_number"])}


@pytest.fixture(params=["off", "absent"])
def turn_off_sales_and_appointments(request, monkeypatch):
    """What turns Sales and Appointments, which Services does not require, off in the business or uninstalls them."""

    def off(ctx, data):
        raise AppInactive("Off.")

    def turn_off():
        for read in BEHIND:
            if request.param == "absent":
                monkeypatch.delitem(registry, read)
            else:
                monkeypatch.setitem(registry, read, dataclasses.replace(registry[read], fn=off))

    return turn_off


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_without_sales_and_appointments_the_card_leaves_them_out_never_by_their_id(
    hub_a, no_fallback, turn_off_sales_and_appointments
):
    with use_hub(hub_a):
        till = a_till(hub_a, a_salon())
        named = till_cards(till, person(hub_a))
        turn_off_sales_and_appointments()
        shown = till_cards(till, person(hub_a))
    assert {write: values(card) for write, card in named.items()} == named_at_the_till(till)  # positive control
    assert_left_out(shown)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_who_may_not_see_sales_nor_appointments_reads_none_of_them_on_the_card(hub_a, no_fallback):
    """The reads of Sales and Appointments run as whoever asks: without their rights, Services names nothing of theirs."""
    hidden = frozenset({"sale.view_sale", "appointment.view_appointment", "appointment.view_own_appointment"})
    ctx = person(hub_a, without=hidden)
    # Positive control: Services' own read is theirs to run; only what it asks of the others is not.
    assert ctx.has(get("service.record.get").permission)
    with use_hub(hub_a):
        shown = till_cards(a_till(hub_a, a_salon()), ctx)
    assert_left_out(shown)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_an_employee_reads_the_sale_and_the_lines_but_not_an_appointment_of_someone_else(hub_a, no_fallback):
    """An employee sees her own appointments only (Appointments' rule): another's is left out, never by its id."""
    with use_hub(hub_a):
        till = a_till(hub_a, a_salon())
        shown = till_cards(till, person(hub_a, "hub_employee"))
    expected = named_at_the_till(till)
    expected["service.grant.redeem"].pop("appointment_id")
    assert {write: values(card) for write, card in shown.items() if write in expected} == expected
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_nobody_behind_the_request_reads_nothing_of_sales_nor_appointments(hub_a, no_fallback):
    with use_hub(hub_a):
        shown = till_cards(a_till(hub_a, a_salon()), None)
    assert_left_out(shown)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_sale_or_an_appointment_that_is_not_there_is_left_out_never_by_its_id(hub_a, no_fallback):
    gone = {kind: uuid.uuid7() for kind in TILL_TITLES["es"]}
    with use_hub(hub_a):
        shown = till_cards(gone, person(hub_a))
    assert_left_out(shown)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_sale_or_an_appointment_of_hub_b_is_never_named_on_a_card_of_hub_a(hub_a, hub_b, no_fallback):
    with use_hub(hub_b):
        theirs = a_till(hub_b, a_salon())
        named_in_b = till_cards(theirs, person(hub_b))
    with use_hub(hub_a):
        shown = till_cards(theirs, person(hub_a))
    assert {write: values(card) for write, card in named_in_b.items()} == named_at_the_till(theirs)  # positive control
    assert_left_out(shown)


# ── The read that names them ─────────────────────────────────────────────────────────────────────────────────────────


def test_the_read_that_names_them_is_no_tool_and_takes_one_record():
    read = get("service.record.get")
    assert (read.kind, read.ai, read.expose_api) == ("query", INTERNAL, False)
    for data in ({}, {"sale_id": str(uuid.uuid7()), "appointment_id": str(uuid.uuid7())}, {"nothing": "x"}):
        with pytest.raises(ValidationError):
            read.input.model_validate(data)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(("language", "said"), [("es", "Anulación de la venta {}"), ("en", "Void of sale {}")])
def test_the_read_that_names_them_answers_in_the_readers_language(language, said, hub_a, no_fallback):
    """Whatever language is active where it is asked from (a request in the other one, a nested call)."""
    other = {"es": "en", "en": "es"}[language]
    read = get("service.record.get")
    with use_hub(hub_a):
        till = a_till(hub_a, a_salon())
        with translation.override(other):
            named = read(person(hub_a, language=language), read.input.model_validate({"reference": str(till["voided"])}))
    assert named.name == said.format(till["voided_number"])


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_the_read_that_names_them_needs_the_right_to_see_the_vouchers(hub_a, no_fallback):
    read = get("service.record.get")
    with use_hub(hub_a), pytest.raises(PermissionDenied):
        read(person(hub_a, without=frozenset({read.permission})), read.input.model_validate({"sale_id": str(uuid.uuid7())}))


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(
    ("datum", "code"),
    [
        ("sale_id", "service.sales_unavailable"),
        ("sale_line_id", "service.sales_unavailable"),
        ("order_line_id", "service.sales_unavailable"),
        ("reference", "service.sales_unavailable"),
        ("appointment_id", "service.appointments_unavailable"),
    ],
)
def test_without_their_app_the_read_says_it_is_unavailable(datum, code, hub_a, no_fallback, monkeypatch):
    for name in BEHIND:
        monkeypatch.delitem(registry, name)
    read = get("service.record.get")
    with use_hub(hub_a), pytest.raises(Conflict) as caught:
        read(person(hub_a), read.input.model_validate({datum: str(uuid.uuid7())}))
    assert caught.value.code == code


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_write_of_services_names_each_record_as_its_screens_do(language, hub_a, no_fallback):
    """«Anula ese bono», «quítale ese servicio a Ana»: the card says which service, category, package, professional,
    customer, voucher or session by its name, in the person's language, never by its id."""
    with use_hub(hub_a):
        shown = cards(a_salon(), person(hub_a, language=language), language)
    assert {write: values(card) for write, card in shown.items()} == named_as_the_screens(language)
    assert [write for write, card in shown.items() if not no_id(card)] == []


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_each_record_is_titled_as_the_screens_title_it(language, hub_a, no_fallback):
    """«Servicio: Corte», «Bono vendido: Bono 5 cortes · …», never «Id: Corte»: the mark alone would name it under its
    field."""
    with use_hub(hub_a):
        shown = cards(a_salon(), person(hub_a, language=language), language)
    assert {write: {field["name"]: field["label"] for field in card["fields"]} for write, card in shown.items()} == {
        write: {datum: TITLES[language][kind] for datum, kind in data.items()} for write, data in NAMED.items()
    }


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_records_inside_a_list_are_named_too(language, hub_a, no_fallback):
    """The services of a new package and the category of each service of a bulk create, at any depth."""
    with use_hub(hub_a):
        salon = a_salon()
        ctx = person(hub_a, language=language)
        package = assistant.card(
            get("service.package.create"), {"items": [{"service_id": str(salon["service"]), "sessions": 5}]}, language, ctx
        )
        bulk = assistant.card(
            get("service.service.bulk_create"),
            {"services": [{"name": "Tinte", "category_id": str(salon["category"])}]},
            language,
            ctx,
        )
    assert list_field(package, "items")["value"][0]["service_id"] == "Corte"
    assert list_field(bulk, "services")["value"][0]["category_id"] == "Peluquería"
    assert no_id(package) and no_id(bulk)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
@pytest.mark.parametrize("write", OVER_SESSIONS)
def test_a_write_over_several_sessions_names_each_and_says_how_many(write, language, hub_a, no_fallback):
    """The dangerous writes over the sessions of a sale: whoever types the number sees which they are."""
    with use_hub(hub_a):
        salon = a_salon()
        second_service = make_service("Peinado")
        grant = Grant.objects.get(pk=salon["grant"])
        second = make_redemption(grant, second_service)
        card = assistant.card(
            get(write), {"ids": [str(salon["session"]), str(second.id)]}, language, person(hub_a, language=language)
        )
    field = list_field(card, "ids")
    assert field["value"] == ["Bono 5 cortes · Lucía Pérez · Corte", "Bono 5 cortes · Lucía Pérez · Peinado"]
    assert field["label"] == {"es": "Sesiones del bono", "en": "Voucher sessions"}[language]
    assert card["count"] == 2
    assert no_id(card)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_nobody_behind_the_request_reads_no_record_of_services(hub_a, no_fallback):
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    with use_hub(hub_a):
        shown = cards(a_salon(), None)
    assert {write: values(card) for write, card in shown.items()} == left_out_of_every_card()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_who_may_not_see_them_reads_none_of_them_on_the_card(hub_a, no_fallback):
    """Whoever may run the writes but see nothing (a key that only writes, say) gets every record left out, never its
    id."""
    writes_only = OperationContext(
        scope=Scope("host", hub_a.slug),
        actor="key",
        permissions=frozenset(get(write).permission for write in NAMED),
        language="es",
    )
    # Positive control: running a write gives away none of the reads its card names a record by.
    assert not {
        "customer.view",
        "service.view_category",
        "service.view_package",
        "service.view_package_balance",
        "service.view_service",
        "staff.view",
    } & writes_only.permissions
    with use_hub(hub_a):
        shown = cards(a_salon(), writes_only)
    assert {write: values(card) for write, card in shown.items()} == left_out_of_every_card()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_that_is_not_there_is_left_out_never_by_its_id(hub_a, no_fallback):
    gone = {kind: uuid.uuid7() for kind in TITLES["es"]}
    with use_hub(hub_a):
        shown = cards(gone, person(hub_a))
    assert {write: values(card) for write, card in shown.items()} == left_out_of_every_card()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_of_hub_b_is_never_named_on_a_card_of_hub_a(hub_a, hub_b, no_fallback):
    """The read runs in the hub the person asks in: hub B's voucher or session is nobody in hub A."""
    with use_hub(hub_b):
        theirs = a_salon()
        named_in_b = cards(theirs, person(hub_b))
    with use_hub(hub_a):
        shown = cards(theirs, person(hub_a))
    assert {write: values(card) for write, card in shown.items()} == left_out_of_every_card()
    assert all(no_id(card) for card in shown.values())
    # Positive control: in hub B the same cards name them.
    assert {write: values(card) for write, card in named_in_b.items()} == named_as_the_screens()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_two_equal_vouchers_of_a_customer_are_told_apart_by_the_day_they_were_sold(hub_a, no_fallback):
    with use_hub(hub_a):
        salon = a_salon()
        package, customer = Package.objects.get(pk=salon["package"]), Customer.objects.get(pk=salon["customer"])
        later = sold(package, customer, on=dt.datetime(2026, 10, 20, 12, tzinfo=dt.UTC))
        admin = person(hub_a)
        void = get("service.grant.void")
        said_of = [values(assistant.card(void, {"id": str(grant)}, "es", admin))["id"] for grant in (salon["grant"], later.id)]
    assert said_of == ["Bono 5 cortes · Lucía Pérez · 3 oct 2026", "Bono 5 cortes · Lucía Pérez · 20 oct 2026"]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_who_may_not_see_customers_reads_the_voucher_without_its_owner(hub_a, no_fallback):
    """The voucher's name is Services'; the customer's, Customers': the card says no more than the person may read."""
    with use_hub(hub_a):
        salon = a_salon()
        ctx = person(hub_a, without=frozenset({"customer.view"}))
        grant = values(assistant.card(get("service.grant.void"), {"id": str(salon["grant"])}, "es", ctx))["id"]
        session = values(assistant.card(get("service.session.release"), {"id": str(salon["session"])}, "es", ctx))["id"]
    assert grant == "Bono 5 cortes · 3 oct 2026"
    assert session == "Bono 5 cortes · Corte"


def test_whoever_may_run_a_write_reads_the_record_its_card_names():
    """The read runs as the person: a role that may run a write and not read what its card names would get a card with
    nothing to recognise, just in the common case. Every role a business gives, every write that names a record."""
    unread: list[tuple[str, str, str]] = []
    checked = 0
    named: dict[str, dict] = {}
    for listed in (NAMED, {write: {"ids": "session"} for write in OVER_SESSIONS}, TILL):
        for write, data in listed.items():
            named[write] = {**named.get(write, {}), **data}
    for role in ROLES:
        mine = ctx_for(role)
        for name, data in named.items():
            op = get(name)
            if not mine.has(op.permission):
                continue
            schema = op.input.model_json_schema()
            defs = schema.get("$defs", {})
            for datum, kind in data.items():
                checked += 1
                prop = assistant._resolved(schema["properties"][datum], defs)
                marked = assistant.refers_of(assistant._resolved(prop["items"], defs) if "items" in prop else prop)
                reads = [marked["read"]] if marked else []
                # What Sales or Appointments name, by the read of theirs that Services' own read asks.
                reads += [BEHIND_OF[kind]] if kind in BEHIND_OF else []
                if marked is None or not all(mine.has(registry[read].permission) for read in reads):
                    unread.append((role, name, datum))
    # Positive control: the owner and the admin run them all, the manager and the employee what their roles give them
    # (the four roles that spend a session say who did it): 91, plus the settle's ``customer_id`` beside its ``ids`` for
    # each of the four, plus the sale, its lines, the appointment and the refund of the five writes of the till: 6 for
    # the employee, who gives back no session, and 7 for each of the other three (hub#756).
    assert checked == 91 + 4 + 27
    assert unread == []
