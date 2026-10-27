"""The assistant's card for a write of printing (FIX-HUB-PRINTING-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Printing screens give it, never by the title pydantic makes
up from the field («Job Id», «Attempt», «Source Ref»). The card is base's (``base.assistant.card``); the names are
printing's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

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


def test_the_card_names_a_job_of_the_queue_as_the_queue_does():
    """The job by the queue's word («trabajo») and its document's number, as retrying or cancelling one names it."""
    retry = get("printing.job.retry")
    arguments = {"job_id": "x", "reference": "T-000123"}
    job, job_en = SCREENS["jobs"]["entity"]["one"].capitalize(), SCREENS_EN["jobs"]["entity"]["one"].capitalize()
    assert labels(assistant.card(retry, arguments, "es")) == [job, "Referencia"]
    assert labels(assistant.card(retry, arguments, "en")) == [job_en, "Reference"]


def test_the_card_names_what_a_device_reports_about_a_job():
    """A device confirms a job it printed, or says why it could not: the job, the device, the hand-out and the
    error."""
    arguments = {"job_id": "x", "device": "Caja", "attempt": 1, "error": "Sin papel"}
    fail = get("printing.job.fail")
    assert labels(assistant.card(fail, arguments, "es")) == [
        "Trabajo",
        SCREENS["devices"]["modal"]["name"],
        "Intento",
        "Error de impresión",
    ]
    assert labels(assistant.card(fail, arguments, "en")) == [
        "Job",
        SCREENS_EN["devices"]["modal"]["name"],
        "Attempt",
        "Print error",
    ]
    complete = get("printing.job.complete")
    assert labels(assistant.card(complete, {"attempt": 2}, "es")) == ["Intento"]


def test_the_card_names_a_device_as_the_devices_screen_does():
    retire = get("printing.device.retire")
    device, device_en = SCREENS["devices"]["entity"]["one"], SCREENS_EN["devices"]["entity"]["one"]
    assert labels(assistant.card(retire, {"device_id": "x"}, "es")) == [device.capitalize()]
    assert labels(assistant.card(retire, {"device_id": "x"}, "en")) == [device_en.capitalize()]


def test_the_card_names_the_money_the_print_at_checkout_and_the_document_of_a_new_job():
    arguments = {"currency": "EUR", "automatic": True, "source_ref": "T-000123"}
    create = get("printing.job.create")
    assert labels(assistant.card(create, arguments, "es")) == [
        "Moneda",
        "Impresión automática al cobrar",
        "Referencia",
    ]
    assert labels(assistant.card(create, arguments, "en")) == ["Currency", "Automatic print at checkout", "Reference"]
