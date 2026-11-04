"""Services with the platform's assistant (flow service-business-currency): every amount a write of Services takes
is money for the assistant — the card the person confirms paints it in the business's currency (``kind == "money"``)
and the assistant's instructions tell the AI to send it in the minor unit of that currency (17 € → 1700, ¥17 → 17).
An amount is a ``Cents`` field of the schemas (bounded by ``MAX_CENTS``); a write that is a tool of the assistant with
such a field must hand it to the card as money, or the AI could send 65 for «65 €».

And by its name (FIX-HUB-SERVICE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, every datum a write
of Services sends reaches the card by the name the Services screens give it, never by the title pydantic makes up from
the field («Absorbed Id», «Tax Category Key», «Items»). The card is base's (``base.assistant.card``); the names are
service's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import datetime as dt
import gettext
import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import translation
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get, registry

from apps.customer.models import Customer
from apps.service.models import Assignment, Grant, Package
from apps.service.schemas import MAX_CENTS
from base import assistant
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


def test_the_card_names_the_refund_or_void_that_gives_sessions_back():
    """Sales gives back the sessions spent in a sale it refunds or voids: the card names that document by what it is,
    with service's own words, not with the «Referencia» another app's catalog lends to pydantic's «Reference»."""
    give_back = get("service.session.return")
    assert labels(assistant.card(give_back, {"reference": "x"}, "es")) == ["Devolución o anulación"]
    assert labels(assistant.card(give_back, {"reference": "x"}, "en")) == ["Refund or void"]
    with translation.override("es"):
        assert translation.gettext("Reference") == "Referencia"  # the lent word the guardrail must not take for one


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
    "service.grant.redeem": {"id": "grant", "service_id": "service"},
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
#: What no read of Services may name: the sale, the appointment and the line of an order are of apps it does not require,
#: and the reference of a return is the refund or the void of a sale. Their card leaves them out (hub#756).
LEFT_OUT = {
    "service.grant.create:sale_id",
    "service.grant.redeem:appointment_id",
    "service.grant.redeem:sale_id",
    "service.session.hold:order_line_id",
    "service.session.return:reference",
    "service.session.settle:sale_id",
}
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
    known = {tuple(known.split(":")) for known in LEFT_OUT}
    assert {
        op.name: found for op in writes if (found := {datum for datum in references(op) if (op.name, datum) not in known})
    } == {write: set(data) for write, data in NAMED.items()}


def test_the_only_records_a_write_of_services_leaves_unnamed_are_the_six_of_the_ratchet():
    """The sale, the appointment and the line of an order are of apps Services does not require, and the reference of a
    return is what gives it back: nothing else. This is what ``base``'s ratchet counts, by name."""
    assert {f"{name}:{path}" for name in TOOLS for path in unnamed(get(name))[0]} == LEFT_OUT


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_the_card_of_a_write_paints_none_of_the_six_nor_an_id(hub_a, no_fallback):
    """The reference of a return, the sale of a voucher: left out, never by its id, whoever asks."""
    with use_hub(hub_a):
        salon = a_salon()
        admin = person(hub_a)
        arguments: dict[str, dict] = {}
        for known in LEFT_OUT:
            write, datum = known.split(":")
            arguments.setdefault(write, {})[datum] = str(salon["grant"])
        shown = {write: assistant.card(get(write), data, "es", admin) for write, data in arguments.items()}
    assert {write: values(card) for write, card in shown.items()} == dict.fromkeys(arguments, {})
    assert all(no_id(card) for card in shown.values())


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
    for role in ROLES:
        mine = ctx_for(role)
        for name, data in {**NAMED, **{write: {"ids": "session"} for write in OVER_SESSIONS}}.items():
            op = get(name)
            if not mine.has(op.permission):
                continue
            schema = op.input.model_json_schema()
            defs = schema.get("$defs", {})
            for datum in data:
                checked += 1
                prop = assistant._resolved(schema["properties"][datum], defs)
                marked = assistant.refers_of(assistant._resolved(prop["items"], defs) if "items" in prop else prop)
                if marked is None or not mine.has(registry[marked["read"]].permission):
                    unread.append((role, name, datum))
    # Positive control: the owner and the admin run them all, the manager and the employee what their roles give them
    # (the settle's ``customer_id`` is replaced by its ``ids`` here).
    assert checked == 87
    assert unread == []
