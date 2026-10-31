"""The assistant's card for a write of printing (FIX-HUB-PRINTING-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Printing screens give it, never by the title pydantic makes
up from the field («Job Id», «Attempt», «Source Ref»). The card is base's (``base.assistant.card``); the names are
printing's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.operations import get, registry

from apps.printing.documents import DOCUMENT_TYPES
from apps.printing.models import PrintDevice, PrintJob
from apps.printing.tests.conftest import A, RECEIPT, ctx_for, run
from base import assistant
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID

FRONTEND = Path(apps.get_app_config("printing").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["printing"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["printing"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def printing_writes() -> list:
    return [
        op for op in registry.values() if op.app_label == "printing" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_printing_reaches_a_spanish_card_by_its_technical_name():
    """Every write of printing the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = printing_writes()
    assert len(writes) > 10  # positive control: the registry has printing's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def a_job() -> str:
    """The id of a receipt in the queue: a job's id is on a card only when it names one (since the card names it)."""
    return str(run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}).job.id)


@pytest.mark.django_db
def test_the_card_names_a_job_of_the_queue_as_the_queue_does():
    """The job by the queue's word («trabajo») and its document's number, as retrying or cancelling one names it."""
    retry = get("printing.job.retry")
    arguments = {"job_id": a_job(), "reference": "T-000123"}
    job, job_en = SCREENS["jobs"]["entity"]["one"].capitalize(), SCREENS_EN["jobs"]["entity"]["one"].capitalize()
    assert labels(assistant.card(retry, arguments, "es", ctx_for(language="es"))) == [job, "Referencia"]
    assert labels(assistant.card(retry, arguments, "en", ctx_for())) == [job_en, "Reference"]


@pytest.mark.django_db
def test_the_card_names_what_a_device_reports_about_a_job():
    """A device confirms a job it printed, or says why it could not: the job, the device, the hand-out and the
    error."""
    arguments = {"job_id": a_job(), "device": "Caja", "attempt": 1, "error": "Sin papel"}
    fail = get("printing.job.fail")
    assert labels(assistant.card(fail, arguments, "es", ctx_for(language="es"))) == [
        "Trabajo",
        SCREENS["devices"]["modal"]["name"],
        "Intento",
        "Error de impresión",
    ]
    assert labels(assistant.card(fail, arguments, "en", ctx_for())) == [
        "Job",
        SCREENS_EN["devices"]["modal"]["name"],
        "Attempt",
        "Print error",
    ]
    complete = get("printing.job.complete")
    assert labels(assistant.card(complete, {"attempt": 2}, "es")) == ["Intento"]


@pytest.mark.django_db
def test_the_card_names_a_device_as_the_devices_screen_does():
    retire = get("printing.device.retire")
    counter = {"device_id": str(PrintDevice.objects.create(name="Mostrador", key=PrintDevice.key_of("counter")).id)}
    device, device_en = SCREENS["devices"]["entity"]["one"], SCREENS_EN["devices"]["entity"]["one"]
    assert labels(assistant.card(retire, counter, "es", ctx_for(language="es"))) == [device.capitalize()]
    assert labels(assistant.card(retire, counter, "en", ctx_for())) == [device_en.capitalize()]


def test_the_card_names_the_money_the_print_at_checkout_and_the_document_of_a_new_job():
    arguments = {"currency": "EUR", "automatic": True, "source_ref": "T-000123"}
    create = get("printing.job.create")
    assert labels(assistant.card(create, arguments, "es")) == [
        "Moneda",
        "Impresión automática al cobrar",
        "Referencia",
    ]
    assert labels(assistant.card(create, arguments, "en")) == ["Currency", "Automatic print at checkout", "Reference"]


def test_the_card_says_a_printer_is_active_as_the_printers_screen_does():
    """«Activa», the Printers screen's word for a printer that takes jobs, never auth's «Activo» for the same English
    (FIX-HUB-PRINTING-ES-TEXTS-SHADOWED-BY-AN-EARLIER-APP)."""
    for name in ("printing.printer.create", "printing.printer.update"):
        op = get(name)
        arguments = dict.fromkeys(op.input.model_json_schema()["properties"], "x")
        said = {field["name"]: field["label"] for field in assistant.card(op, arguments, "es")["fields"]}
        assert said["is_active"] == SCREENS["printers"]["columns"]["active"] == "Activa", name


# ── The record a write names by its id, by its name (FIX-HUB-PRINTING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's half
# is hub#416) ──
# Since hub#416 the card leaves out an id its schema does not mark: «reintenta el ticket T-000123», «retira la tablet del
# mostrador» or «prueba la impresora de la caja» said no job, no device and no printer, and a new job said its document
# as the model sent it («kitchen_order»). Now each record is named as the Printing screens show it: a printer and a
# device by their names, a job as the queue titles it («Recibo T-000123»), and a document by the queue's word for it.
# Read as whoever asks, in the hub they ask in: never by the id, and left out when nobody, or somebody who may not see
# the printers, is behind the request.

#: Every record a write of printing names by its id: the data that name one (an id or a list of ids), by write.
NAMED = {
    "printing.device.register": ("printers",),
    "printing.device.retire": ("device_id",),
    "printing.device.update": ("device_id", "printers"),
    "printing.job.cancel": ("job_id",),
    "printing.job.claim": ("printers",),
    "printing.job.complete": ("job_id",),
    "printing.job.fail": ("job_id",),
    "printing.job.retry": ("job_id",),
    "printing.printer.test": ("printer_id",),
    "printing.printer.update": ("printer_id",),
}
#: The roles a business gives (``apps.py``'s ``role_permissions``; the owner and the admin hold every permission).
ROLES = ("hub_employee", "hub_manager", "hub_admin", "hub_owner")


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def no_id(card: dict) -> bool:
    return not AN_ID.search(json.dumps(card, ensure_ascii=False))


def references(op) -> set[str]:
    """The data of ``op``'s input its schema declares an id, or a list of ids, of (``format: uuid``)."""
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})

    def an_id(prop: dict) -> bool:
        prop = assistant._resolved(prop, defs)
        return prop.get("format") == "uuid" or (isinstance(prop.get("items"), dict) and an_id(prop["items"]))

    return {name for name, prop in schema.get("properties", {}).items() if an_id(prop)}


def a_business(ctx: OperationContext | None = None) -> dict:
    """What a salon's Printing screens show: the printers «Caja» and «Cocina», the device «Tablet del mostrador» that
    reaches both, and the receipt T-000123 in the queue."""
    till = run("printing.printer.create", {"name": "Caja", "kind": "network", "address": "10.0.0.1", "usage": "receipt"}, ctx)
    kitchen = run(
        "printing.printer.create", {"name": "Cocina", "kind": "network", "address": "10.0.0.2", "usage": "kitchen"}, ctx
    )
    counter = PrintDevice.objects.create(name="Tablet del mostrador", key=PrintDevice.key_of("counter"))
    counter.printers.add(till.id, kitchen.id)
    job = run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx).job
    return {"printer_id": till.id, "printers": [till.id, kitchen.id], "device_id": counter.id, "job_id": job.id}


def arguments(business: dict, data: tuple[str, ...]) -> dict:
    return {datum: [str(one) for one in business[datum]] if datum == "printers" else str(business[datum]) for datum in data}


def cards(business: dict, ctx, language: str = "es") -> dict:
    """The card of each write of ``NAMED`` naming every record it names by its id, as ``ctx``'s person would confirm it."""
    return {write: assistant.card(get(write), arguments(business, data), language, ctx) for write, data in NAMED.items()}


#: How the card names each record of ``a_business``, as the Printing screens show it, by language.
SAID = {
    "es": {"printer_id": "Caja", "printers": ["Caja", "Cocina"], "device_id": "Tablet del mostrador", "job_id": "Recibo T-000123"},
    "en": {"printer_id": "Caja", "printers": ["Caja", "Cocina"], "device_id": "Tablet del mostrador", "job_id": "Receipt T-000123"},
}


def named_as_the_screens(language: str = "es") -> dict:
    return {write: {datum: SAID[language][datum] for datum in data} for write, data in NAMED.items()}


def left_out() -> dict:
    """Each record left out: a single one is no datum of the card, a list still says how many it carries."""
    return {write: {"printers": [None, None]} if "printers" in data else {} for write, data in NAMED.items()}


def test_every_record_a_write_of_printing_names_by_its_id_is_listed_here():
    """Positive control of the tests below: a new reference of a write of printing comes in here, with its name."""
    assert {op.name: references(op) for op in printing_writes() if references(op)} == {
        write: set(data) for write, data in NAMED.items()
    }


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_write_of_printing_names_each_record_as_the_printing_screens_do(language):
    """«Reintenta el ticket T-000123», «retira la tablet del mostrador», «prueba la impresora de la caja»: the card says
    which job, device or printer as the Printing screens show them, never by its id."""
    said = cards(a_business(), ctx_for(language=language), language)
    assert {write: values(card) for write, card in said.items()} == named_as_the_screens(language)
    assert [write for write, card in said.items() if not no_id(card)] == []


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "test_page", "drawer"), [("es", "Hoja de prueba Caja", "Abrir el cajón"), ("en", "Test page Caja", "Open the drawer")])
def test_a_job_is_named_by_its_document_as_the_queue_titles_it(language, test_page, drawer):
    """A test page by the printer it tests; a job with no number (a drawer opening at checkout) by what it is."""
    till = run("printing.printer.create", {"name": "Caja", "kind": "network", "address": "10.0.0.1", "usage": "receipt"})
    page = run("printing.printer.test", {"printer_id": str(till.id)})
    opening = PrintJob.objects.create(job_key="drawer-1", kind=PrintJob.Kind.DRAWER, usage="receipt", printer_id=till.id)
    retry = get("printing.job.retry")
    named = [values(assistant.card(retry, {"job_id": str(job)}, language, ctx_for(language=language))) for job in (page.id, opening.id)]
    assert named == [{"job_id": test_page}, {"job_id": drawer}]


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_document_of_a_new_job_is_said_by_the_queues_word_for_it(language):
    """«Imprime la comanda de cocina»: the card says «Comanda de cocina», as the queue does, never «kitchen_order»."""
    screens = SCREENS if language == "es" else SCREENS_EN
    create = get("printing.job.create")
    said = {kind: values(assistant.card(create, {"document_type": kind}, language))["document_type"] for kind in DOCUMENT_TYPES}
    assert said == {kind: screens["documents"][kind] for kind in DOCUMENT_TYPES}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record_of_printing():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    said = cards(a_business(), None)
    assert {write: values(card) for write, card in said.items()} == left_out()
    assert all(no_id(card) for card in said.values())


@pytest.mark.django_db
def test_who_may_not_see_the_printers_reads_none_of_them_on_the_card():
    """Whoever asks without «view printers» (a key that only prints and handles the queue, say) gets every record left
    out, never its id."""
    business = a_business()
    printer_only = OperationContext(
        scope=A, actor="tester", permissions=frozenset({"printing.print", "printing.manage_jobs"}), language="es"
    )
    said = cards(business, printer_only)
    assert {write: values(card) for write, card in said.items()} == left_out()
    assert all(no_id(card) for card in said.values())


@pytest.mark.django_db
def test_a_record_that_is_not_there_is_left_out_never_by_its_id():
    gone = {"printer_id": uuid.uuid7(), "printers": [uuid.uuid7(), uuid.uuid7()], "device_id": uuid.uuid7(), "job_id": uuid.uuid7()}
    said = cards(gone, ctx_for(language="es"))
    assert {write: values(card) for write, card in said.items()} == left_out()
    assert all(no_id(card) for card in said.values())


@pytest.mark.django_db
def test_a_retired_device_is_no_device_to_name():
    """Retired, it prints nothing and the devices screen no longer lists it: a card does not name it either."""
    business = a_business()
    run("printing.device.retire", {"device_id": str(business["device_id"])})
    card = assistant.card(get("printing.device.update"), arguments(business, ("device_id",)), "es", ctx_for(language="es"))
    assert values(card) == {} and no_id(card)


@pytest.fixture
def no_fallback(monkeypatch):
    """As production: without ``use_hub`` a hub's model fails, nothing falls back on the shared database."""
    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_of_hub_b_is_never_named_on_a_card_of_hub_a(hub_a, hub_b, no_fallback):
    """The read runs in the hub the person asks in: hub B's printer, device or job is nobody in hub A."""
    in_b = ctx_for(scope=Scope("host", hub_b.slug), language="es")
    with use_hub(hub_b):
        theirs = a_business(in_b)
        named_in_b = cards(theirs, in_b)
    in_a = ctx_for(scope=Scope("host", hub_a.slug), language="es")
    with use_hub(hub_a):
        said = cards(theirs, in_a)
    assert {write: values(card) for write, card in said.items()} == left_out()
    assert all(no_id(card) for card in said.values())
    # Positive control: in hub B the same cards name them.
    assert {write: values(card) for write, card in named_in_b.items()} == named_as_the_screens()


def test_whoever_may_run_a_write_reads_the_record_its_card_names():
    """The read runs as the person: a role that may run a write and not read what its card names would get a card with
    nothing to recognise, just in the common case. Every role a business gives, every write that names a record."""
    unread: list[tuple[str, str, str]] = []
    checked = 0
    for role in ROLES:
        mine = ctx_for(role)
        for name, data in NAMED.items():
            op = get(name)
            if not mine.has(op.permission):
                continue
            schema = op.input.model_json_schema()
            for datum in data:
                prop = assistant._resolved(schema["properties"][datum], schema.get("$defs", {}))
                marked = assistant.refers_of(assistant._resolved(prop.get("items", prop), schema.get("$defs", {})))
                checked += 1
                if marked is None or not mine.has(registry[marked["read"]].permission):
                    unread.append((role, name, datum))
    # Positive control: the employee runs the writes of «print» (4 records), the manager all but the queue's retry and
    # cancel (9), the admin and the owner every one (11).
    assert checked == 4 + 9 + 11 + 11
    assert unread == []
