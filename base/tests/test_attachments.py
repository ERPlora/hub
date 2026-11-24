"""The files the person attaches in the assistant's chat that a tool takes whole (a copy of a business,
``.blueprint.zip``): the model hears only their names, and the Hub gives the tool the file the person attached."""

import json

from live.operations import Operation, get, registry
from ninja import Schema
from pydantic import Field

from base.assistant import attachments
from base.schemas.assistant import AN_ATTACHED_FILE
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.test_services_assistant import asked, call, turn

__all__ = ["in_business_a"]

ZIP = "UEsDBBQAAAAIAA=="
PDF = "JVBERi0xLjcK"
COPY = {"type": "input_file", "filename": "bar-pepe.blueprint.zip", "mime_type": "application/zip", "data": ZIP}
MENU = {"type": "input_file", "filename": "carta.pdf", "mime_type": "application/pdf", "data": PDF}
IMPORT = get("base.blueprint.import")


def said(*parts):
    return {"role": "user", "content": [{"type": "text", "text": "cárgame esta copia"}, *parts]}


def test_the_model_hears_the_name_of_a_file_for_a_tool_never_its_bytes():
    messages = [said(COPY, MENU)]

    sent = attachments.for_gateway(messages)

    text, copy, menu = sent[0]["content"]
    assert text == {"type": "text", "text": "cárgame esta copia"}
    assert copy["type"] == "text"
    assert "«bar-pepe.blueprint.zip»" in copy["text"]
    assert ZIP not in json.dumps(sent)
    # What erplora.com reads still goes to it whole, and the conversation the person keeps is not touched.
    assert menu == MENU
    assert messages == [said(COPY, MENU)]


def test_a_message_of_words_alone_goes_as_it_is():
    words = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¿Qué necesitas?"}]

    assert attachments.for_gateway(words) == words


def test_the_files_of_the_conversation_are_the_persons_by_name_the_last_one_named_so_counting():
    newer = {**COPY, "data": "UEsFBgAA"}
    messages = [
        said(COPY, MENU),
        {"role": "assistant", "content": [{"type": "input_file", "filename": "otro.zip", "data": ZIP}]},
        {"role": "user", "content": [newer, "not a part", {"type": "input_file", "filename": "", "data": ZIP}]},
    ]

    assert attachments.attached(messages) == {"bar-pepe.blueprint.zip": "UEsFBgAA", "carta.pdf": PDF}


def test_a_datum_marked_as_an_attached_file_takes_the_file_of_that_name():
    given, refused = attachments.with_files(IMPORT, {"file_base64": "bar-pepe.blueprint.zip"}, {"bar-pepe.blueprint.zip": ZIP}, "es")

    assert (given, refused) == ({"file_base64": ZIP}, None)


def test_a_file_that_is_not_in_the_conversation_runs_nothing_and_the_model_hears_why():
    given, refused = attachments.with_files(IMPORT, {"file_base64": "bar-pepe.blueprint.zip"}, {"carta.pdf": PDF}, "es")

    assert given is None
    # Said as an app says its refusals: in the person's language, for the model and for the write's receipt.
    assert (refused.outcome, refused.code) == ("error", "base.assistant_attachment_missing")
    error = json.loads(refused.content)["error"]
    assert error["code"] == "base.assistant_attachment_missing"
    assert "«bar-pepe.blueprint.zip»" in error["message"]
    in_english = attachments.with_files(IMPORT, {"file_base64": "bar-pepe.blueprint.zip"}, {}, "en")[1]
    assert json.loads(in_english.content)["error"]["message"] != error["message"]


class _Upload(Schema):
    name: str = ""
    content: str = Field("", json_schema_extra=AN_ATTACHED_FILE)


def test_only_the_marked_data_take_a_file_and_one_not_given_stays_empty():
    class Upload:
        input = _Upload

    assert attachments.with_files(Upload, {"name": "carta.pdf"}, {"carta.pdf": PDF}, "es") == ({"name": "carta.pdf"}, None)
    assert attachments.with_files(Upload, {"name": "x", "content": "carta.pdf"}, {"carta.pdf": PDF}, "es") == (
        {"name": "x", "content": PDF},
        None,
    )
    # A template of the catalogue names no file.
    assert attachments.with_files(IMPORT, {"template": "bar.es"}, {}, "es") == ({"template": "bar.es"}, None)


def test_the_copy_of_a_business_is_taken_as_an_attached_file():
    assert IMPORT.input.model_fields["file_base64"].json_schema_extra == AN_ATTACHED_FILE
    assert get("base.blueprint.inspect").input.model_fields["file_base64"].json_schema_extra == AN_ATTACHED_FILE


class _AttachIn(Schema):
    id: str = Field(min_length=1)
    content: str = Field("", json_schema_extra=AN_ATTACHED_FILE)


class _AttachPreviewIn(Schema):
    content: str = ""


class _AttachPreviewOut(Schema):
    size: int = Field(title="Size")


ATTACH_PREVIEW = Operation(
    name="demo.item.attach_preview",
    kind="query",
    permission="demo.view",
    input=_AttachPreviewIn,
    output=_AttachPreviewOut,
    expose_api=False,
    ai={"description": "What attaching a file to a demo item would do."},
    fn=lambda ctx, data: {"size": len(data.content)},
)
ATTACH = Operation(
    name="demo.item.attach",
    kind="command",
    permission="demo.manage",
    input=_AttachIn,
    output=_AttachPreviewOut,
    expose_api=False,
    ai={"description": "Attaches a file to a demo item.", "preview": {"operation": ATTACH_PREVIEW.name, "fields": ["size"]}},
    fn=lambda ctx, data: {"size": len(data.content)},
)


@HUB_DB
def test_what_a_write_will_do_is_read_with_the_file_its_card_names(monkeypatch):
    monkeypatch.setitem(registry, ATTACH.name, ATTACH)
    monkeypatch.setitem(registry, ATTACH_PREVIEW.name, ATTACH_PREVIEW)
    pending = call(ATTACH.name, {"id": "7", "content": "carta.pdf"})

    plan = turn(pending, messages=[said(MENU), asked(pending)])

    card = plan["confirm"]
    assert [field["value"] for field in card["fields"] if field["name"] == "content"] == ["carta.pdf"]
    assert [field["value"] for field in card["preview"]] == [len(PDF)]
