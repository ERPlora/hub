"""The assistant's card for a write of verifactu (FIX-HUB-VERIFACTU-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the VeriFactu screens give it, never by the title pydantic makes
up from the field («Invoice Id», «Issuer Nif», «Month»). The card is base's (``base.assistant.card``); the names
are verifactu's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog.

And which writes are tools at all (FIX-HUB-VERIFACTU-CERTIFICATE-PASSWORD-ASKED-IN-THE-CHAT): a write that takes a
secret (the certificate and its password, the signed authorisation and the copy of an identity document) is «Not an
assistant tool» — said in a chat it has already reached the model and the history, and its card would paint it in
clear. The person gives it in «Configuración», as before."""

import json
from typing import get_args

import pytest
from django.utils import translation
from django.utils.text import capfirst
from live.operations import get, registry
from pydantic import BaseModel, SecretBytes, SecretStr

from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import ctx_for
from base import assistant
from base.tests.test_assistant import named_by_the_screen


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
        "verifactu.chain.recover_manual",
        "verifactu.record.create",
    } <= {op.name for op in writes}
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_invoice_of_a_record_as_the_records_do():
    """The invoice a record is sealed for, by its id or its number: the number as every other write and the records
    name it («Número de factura»), never a bare «Número»."""
    create = get("verifactu.record.create")
    for language in ("es", "en"):
        with translation.override(language):
            invoice_number = capfirst(str(Record._meta.get_field("invoice_number").verbose_name))
        card = assistant.card(create, {"invoice_id": "x", "number": "F-1"}, language)
        assert labels(card) == [{"es": "Factura", "en": "Invoice"}[language], invoice_number]
    assert invoice_number == "Invoice number"


def test_the_card_names_the_month_asked_of_the_aeat():
    query = get("verifactu.aeat.query")
    arguments = {"year": 2026, "month": 10}
    assert labels(assistant.card(query, arguments, "es")) == ["Año", "Mes"]
    assert labels(assistant.card(query, arguments, "en")) == ["Year", "Month"]


def _types(annotation) -> list:
    """``annotation`` and every type inside it (``X | None``, ``list[X]``, ``dict[str, X]``)."""
    return [annotation, *(inner for arg in get_args(annotation) for inner in _types(arg))]


def secret_data(model: type[BaseModel], prefix: str = "", seen: frozenset = frozenset()) -> list[str]:
    """The data of ``model`` that are a secret (``SecretStr``, ``SecretBytes``), in the schemas nested in it too."""
    found: list[str] = []
    for name, field in model.model_fields.items():
        for kind in _types(field.annotation):
            if not isinstance(kind, type):
                continue
            if issubclass(kind, (SecretStr, SecretBytes)) and prefix + name not in found:
                found.append(prefix + name)
            elif issubclass(kind, BaseModel) and kind not in seen:
                found += secret_data(kind, f"{prefix}{name}.", seen | {model})
    return found


#: The writes of verifactu that take a secret, with its data: by name.
SECRET_WRITES = {
    op.name: data
    for op in registry.values()
    if op.app_label == "verifactu" and op.kind == "command" and (data := secret_data(op.input))
}


def test_no_write_of_verifactu_that_takes_a_secret_is_an_assistant_tool():
    """A secret said in a chat has already reached the model and the history, and the write's card paints it in clear
    (as ChatGPT's actions, Zapier or Make ask for credentials: in their form, never in the chat; hub#370 for flow's
    secrets). The next write of verifactu with a secret falls here too."""
    # Positive control: the certificate (the .p12 and its password) and the authorisation (the signed model, the copy
    # of the identity document) are secrets the screen asks for.
    assert SECRET_WRITES["verifactu.certificate.upload"] == ["p12_base64", "password"]
    assert "id_copy_base64" in SECRET_WRITES["verifactu.representation.submit"]
    assert sorted(name for name in SECRET_WRITES if assistant.is_tool(get(name))) == []


def test_the_certificate_and_its_password_are_never_asked_for_in_a_chat():
    upload = get("verifactu.certificate.upload")
    assert assistant.description(upload).startswith("Not an assistant tool")
    assert not assistant.is_tool(upload)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("role", ["hub_owner", "hub_admin"])
def test_not_even_who_may_configure_verifactu_is_offered_them(role):
    """What the assistant hands the model: verifactu's other tools, none of its writes with a secret."""
    tools = assistant.catalog(ctx_for(role))
    assert {"verifactu.aeat.query", "verifactu.config.update"} <= set(tools)  # positive control: verifactu is on
    assert sorted(set(SECRET_WRITES) & set(tools)) == []


def test_a_secret_inside_a_nested_schema_is_seen_too():
    """The guard above reads the schemas nested in a write's input as well: a secret one level down still counts."""

    class Holder(BaseModel):
        name: str
        password: SecretStr

    class Upload(BaseModel):
        label: str
        holder: Holder | None = None
        others: list[Holder] = []

    assert secret_data(Upload) == ["holder.password", "others.password"]


@pytest.mark.django_db
def test_a_turn_that_still_names_the_certificate_upload_builds_no_card_and_runs_nothing():
    """The way the chat really takes (``base.assistant.turn``, BASE-G118): a model that calls the write by its name
    anyway, password included, is refused as «not available»; no card is built (before the fix, the card came back
    with «hunter2» in clear), so the password is painted nowhere the person sees, and the receipt names what was
    refused without running it."""
    turn = get("base.assistant.turn")
    name = assistant.tool_name("verifactu.certificate.upload")
    arguments = json.dumps({"p12_base64": "MIIFAKEP12", "password": "hunter2"})
    asked = {"role": "user", "content": "sube mi certificado, la contraseña es hunter2"}
    called = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": name, "arguments": arguments}}],
    }
    data = turn.input.model_validate(
        {
            "messages": [asked, called],
            "pending": [{"call_id": "c1", "name": name, "arguments": arguments}],
        }
    )
    plan = turn(ctx_for("hub_owner", language="es"), data).model_dump(mode="json")
    assert plan["confirm"] is None  # before the fix: its card, the password in clear among its fields
    refused = plan["executed"][0]
    assert (refused["outcome"], refused["code"], refused["name"]) == ("refused", "not_available", "verifactu.certificate.upload")
    # Only the history the model wrote itself still carries the password: nothing the turn builds does.
    assert "hunter2" not in json.dumps({key: value for key, value in plan.items() if key != "messages"})
