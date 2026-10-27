"""The assistant's card for a write of verifactu (FIX-HUB-VERIFACTU-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the VeriFactu screens give it, never by the title pydantic makes
up from the field («Id Copy Base64», «P12 Base64», «Month»). The card is base's (``base.assistant.card``); the names
are verifactu's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

LOCALE = Path(apps.get_app_config("verifactu").path) / "frontend/locale"
SCREENS = json.loads((LOCALE / "es.json").read_text())["verifactu"]
SCREENS_EN = json.loads((LOCALE / "en.json").read_text())["verifactu"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def verifactu_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "verifactu" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_verifactu_reaches_a_spanish_card_by_its_technical_name():
    """Every write of verifactu the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = verifactu_writes()
    # Positive control: the registry has verifactu's writes, those that send the data this fix names among them.
    assert {
        "verifactu.aeat.query",
        "verifactu.certificate.upload",
        "verifactu.representation.submit",
    } <= {op.name for op in writes}
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_signed_authorisation_as_its_form_does():
    """The authorisation of the AEAT (Anexo I of Convenio 17): who signs and each document, as «Firmar el
    otorgamiento» asks for them."""
    submit = get("verifactu.representation.submit")
    arguments = {
        "signer_tax_id": "X1234567L",
        "signer_name": "Ana Pérez",
        "signer_document_type": "nie",
        "signed_model_base64": "x",
        "id_copy_base64": "x",
        "signature_sample_base64": "x",
        "representation_proof_base64": "x",
    }
    for language, screens in (("es", SCREENS), ("en", SCREENS_EN)):
        grant = screens["grant"]
        assert labels(assistant.card(submit, arguments, language)) == [
            grant["signerNif"],
            grant["signerName"],
            grant["documentType"],
            grant["doc"]["signed_model"],
            grant["doc"]["id_copy"],
            grant["doc"]["signature_sample"],
            grant["doc"]["representation_proof"],
        ]


def test_the_card_names_the_certificate_as_its_screen_does():
    upload = get("verifactu.certificate.upload")
    assert labels(assistant.card(upload, {"p12_base64": "x"}, "es")) == [SCREENS["config"]["certTitle"]]
    assert labels(assistant.card(upload, {"p12_base64": "x"}, "en")) == [SCREENS_EN["config"]["certTitle"]]


def test_the_card_names_the_month_asked_of_the_aeat():
    query = get("verifactu.aeat.query")
    arguments = {"year": 2026, "month": 10}
    assert labels(assistant.card(query, arguments, "es")) == ["Año", "Mes"]
    assert labels(assistant.card(query, arguments, "en")) == ["Year", "Month"]
