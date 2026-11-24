"""The documents and photos attached in the assistant's chat are kept in Files with ``base.file.upload``, its card and
the person's yes, as «Upload file» keeps them: the model names each file it was attached and the Hub gives the upload
that very file, never what the model writes."""

import base64
import json

import pytest
from django.core.files.storage import storages
from live import assistant as shared
from live.operations import get

from base.models import Hub, Membership
from base.schemas.assistant import AN_ATTACHED_FILE
from base.storage import hub_prefix
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.assistant_context import asked, turn
from base.tests.test_services_data import person

__all__ = ["in_business_a"]

pytestmark = HUB_DB

FOLDER = "Facturas de proveedores"
DELIVERY = b"%PDF-1.7\n" + b"albaran" * 16
INVOICE = b"\xff\xd8\xff\xe0" + b"factura" * 16


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode()


@pytest.fixture(autouse=True)
def store(settings):
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
    return storages["hub_files"]


@pytest.fixture
def owner():
    context = person(Membership.Role.OWNER)
    get("base.file.create_folder")(context, get("base.file.create_folder").input(parent="", name=FOLDER))
    return context


def attaching() -> dict:
    pdf = {"type": "input_file", "filename": "albaran.pdf", "mime_type": "application/pdf", "data": b64(DELIVERY)}
    photo = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(INVOICE)}"}, "filename": "factura.jpg"}
    return {"role": "user", "content": [{"type": "text", "text": "te paso dos papeles del proveedor"}, pdf, photo]}


def keep(name: str, call_id: str) -> dict:
    arguments = {"folder": FOLDER, "name": name, "content_base64": name}
    return {"call_id": call_id, "name": shared.tool_name("base.file.upload"), "arguments": json.dumps(arguments)}


def kept(store, name: str) -> bytes:
    with store.open(f"{hub_prefix(Hub.objects.get(slug=A.key).id)}/files/{FOLDER}/{name}") as file:
        return file.read()


def conversation(*calls) -> list[dict]:
    # The files come in a message before the last one: the panel sends the whole conversation with each question.
    return [
        attaching(),
        {"role": "assistant", "content": "Ya los tengo. ¿Qué hago con ellos?"},
        {"role": "user", "content": f"guárdalos en la carpeta «{FOLDER}»"},
        asked(*calls),
    ]


def test_the_files_attached_earlier_are_kept_in_the_folder_with_each_card_and_the_persons_yes(owner, store):
    calls = [keep("albaran.pdf", "c1"), keep("factura.jpg", "c2")]
    messages = conversation(*calls)
    pending = calls
    ran = []
    for name in ("albaran.pdf", "factura.jpg"):
        drawn = turn(owner, messages, pending)
        card = drawn["confirm"]
        assert card["operation"] == "base.file.upload"
        # The card names the file the person attached, never its bytes.
        assert [field["value"] for field in card["fields"] if field["name"] == "content_base64"] == [name]
        yes = {"call_id": drawn["pending"][0]["call_id"], "accepted": True, "typed": card["confirm_word"]}
        done = turn(owner, messages, drawn["pending"], decision=yes)
        ran += [(row["name"], row["outcome"]) for row in done["executed"]]
        pending = done["pending"]

    assert ran == [("base.file.upload", "ok"), ("base.file.upload", "ok")]
    assert (kept(store, "albaran.pdf"), kept(store, "factura.jpg")) == (DELIVERY, INVOICE)


def test_the_model_hears_the_name_of_each_file_it_reads_and_still_reads_it(owner):
    sent = turn(owner, conversation()[:3], [])["messages"][0]["content"]

    said = [part["text"] for part in sent if part["type"] == "text"]
    assert any("«albaran.pdf»" in text for text in said)
    assert any("«factura.jpg»" in text for text in said)
    # erplora.com still gets each file whole, to read it; a photo as it takes one, without the name beside it.
    assert [part["type"] for part in sent if part["type"] != "text"] == ["input_file", "image_url"]
    assert [sorted(part) for part in sent if part["type"] == "image_url"] == [["image_url", "type"]]


def test_a_file_no_longer_attached_is_not_kept_and_the_model_hears_why(owner, store):
    # After the page reloads, the panel keeps an attachment by its name alone.
    reloaded = {"role": "user", "content": [{"type": "text", "text": "[Attached: albaran.pdf]"}]}
    call = keep("albaran.pdf", "c1")

    plan = turn(owner, [reloaded, asked(call)], [call])

    assert plan["confirm"] is None
    assert json.loads(plan["append"][0]["content"])["error"]["code"] == "base.assistant_attachment_missing"
    assert not store.exists(f"{hub_prefix(Hub.objects.get(slug=A.key).id)}/files/{FOLDER}/albaran.pdf")


def test_the_upload_takes_an_attached_file_by_its_name():
    field = get("base.file.upload").input.model_fields["content_base64"]

    assert field.json_schema_extra == AN_ATTACHED_FILE
