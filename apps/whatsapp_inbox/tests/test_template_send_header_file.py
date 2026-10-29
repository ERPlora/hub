"""WHATSAPP_INBOX-F33, F28 · Sending a template whose header is a photo, a video or a document.

As WATI, respond.io, Twilio and WhatsApp Manager do, sending such a template asks for the header's file: one made here
comes with its own (``Template.header_sample``), which may be changed; one made in WhatsApp Manager asks for it. The
file is one of the business's kept files (``whatsapp_inbox.template_sample.upload``), of the header's kind; the message
names it (``Message.header_sample``) and its hand-over to erplora.com (door 5, after the COMMIT, the file read from the
store with no connection held) carries it in base64, so erplora.com uploads it to the number and sends the template
with it. A retry carries the same file with the same key. An automation sends what it can fill alone: a template with
its own file, never one that asks for it. Meta not answering is said as Meta's (gh:hub#2731).
"""

import base64
import datetime as dt
import json

import httpx
import pytest
import respx
from live.errors import InvalidPayload

from apps.whatsapp_inbox.models import Message, Template, TemplateSample
from apps.whatsapp_inbox.tests.conftest import NOW, B, connect, ctx_for, receive, run, template
from apps.whatsapp_inbox.tests.test_services import SEND, conv, send, stored
from apps.whatsapp_inbox.tests.test_services import delivered  # noqa: F401 - fixture
from apps.whatsapp_inbox.tests.test_template_header_file import JPEG, MP4, OTHER_JPEG, approved_with_photo, upload
from apps.whatsapp_inbox.tests.test_template_header_file import hub_files  # noqa: F401 - fixture

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("hub_files")]

MANAGER_PHOTO = "promo_foto"


def answering(status: int = 200, body: dict | None = None):
    return respx.post(SEND).mock(return_value=httpx.Response(status, json=body or {"wa_message_id": "wamid.OUT"}))


def door_5(route) -> dict:
    return json.loads(route.calls.last.request.content)


def a_conversation():
    """A customer who wrote three days ago: only a template reaches her."""
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(days=3)).isoformat())
    return conv()


def with_photo(delivered) -> Template:
    """A template made here with a photo header, approved by Meta, and a conversation to send it to."""
    row = approved_with_photo(delivered)
    a_conversation()
    return row


def from_manager():
    """A photo template made in WhatsApp Manager (no file of its own here), and a conversation."""
    connect(templates=[template(MANAGER_PHOTO, header_format="IMAGE", body="¡Hola {{1}}!", variables=1)])
    return a_conversation()


def sending(row: Template, **fields) -> dict:
    return {"name": row.name, "variables": ["Ana", "viernes"], **fields}


# ── A template made here: its own file ──────────────────────────────────────────────────────────


@respx.mock
def test_a_photo_template_made_here_goes_with_its_own_photo(delivered):
    row = with_photo(delivered)
    route = answering()

    out = delivered(lambda: send({"id": str(conv().id), "template": sending(row)}))

    sent = door_5(route)["template"]
    assert (sent["name"], sent["variables"], sent["header_format"]) == (row.name, ["Ana", "viernes"], "IMAGE")
    assert sent["header_sample"]["name"] == "carta.jpg"
    assert base64.b64decode(sent["header_sample"]["content_base64"]) == JPEG
    assert (out.kind, out.media_filename, out.media_mime_type) == ("template", "carta.jpg", "image/jpeg")
    assert stored(out).header_sample_id == row.header_sample_id
    assert stored(out).status == Message.Status.SENT


@respx.mock
def test_another_photo_chosen_when_sending_goes_instead(delivered):
    row = with_photo(delivered)
    other = upload(OTHER_JPEG, name="carta-otono.jpg")
    route = answering()

    out = delivered(lambda: send({"id": str(conv().id), "template": sending(row, header_sample=str(other.id))}))

    assert base64.b64decode(door_5(route)["template"]["header_sample"]["content_base64"]) == OTHER_JPEG
    assert stored(out).header_sample_id == other.id
    assert Template.objects.get(pk=row.pk).header_sample_id == row.header_sample_id, "the template keeps its own"


@respx.mock
def test_a_retry_carries_the_same_file_with_the_same_key(delivered):
    row = with_photo(delivered)
    route = respx.post(SEND).mock(side_effect=httpx.ConnectError("down"))
    out = delivered(lambda: send({"id": str(conv().id), "template": sending(row)}))
    assert stored(out).status == Message.Status.SENDING
    first_key = route.calls.last.request.headers["Idempotency-Key"]

    route.mock(side_effect=None, return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
    delivered(lambda: run("whatsapp_inbox.message.retry", {"id": str(out.id)}))

    assert route.calls.last.request.headers["Idempotency-Key"] == first_key
    assert base64.b64decode(door_5(route)["template"]["header_sample"]["content_base64"]) == JPEG
    assert stored(out).status == Message.Status.SENT


# ── One made in WhatsApp Manager: it asks for the file ──────────────────────────────────────────


def test_a_photo_template_from_whatsapp_manager_is_offered_to_send_asking_for_its_file():
    from_manager()

    [row] = run("whatsapp_inbox.template.list", {"fillable": True}).rows
    assert (row.name, row.editable, row.header_format, row.header_sample) == (MANAGER_PHOTO, False, "IMAGE", None)
    assert run("whatsapp_inbox.template.list", {"sendable": True}).rows == [], "an automation cannot choose its file"


@respx.mock
def test_a_photo_template_from_whatsapp_manager_goes_with_the_file_chosen(delivered):
    c = from_manager()
    chosen = upload(name="foto.jpg")
    route = answering()

    out = delivered(
        lambda: send(
            {"id": str(c.id), "template": {"name": MANAGER_PHOTO, "variables": ["Ana"], "header_sample": str(chosen.id)}}
        )
    )

    assert door_5(route)["template"]["header_sample"]["name"] == "foto.jpg"
    assert out.media_filename == "foto.jpg"


def test_without_its_file_it_does_not_leave():
    c = from_manager()

    with pytest.raises(InvalidPayload) as refused:
        send({"id": str(c.id), "template": {"name": MANAGER_PHOTO, "variables": ["Ana"]}})

    assert "file" in refused.value.fields["header_sample"]
    assert not Message.objects.filter(direction=Message.Direction.OUTBOUND).exists()


@pytest.mark.parametrize("sample", ["another_kind", "another_business"])
def test_the_file_is_of_its_kind_and_of_its_business(sample):
    c = from_manager()
    chosen = {
        "another_kind": lambda: upload(MP4, "VIDEO", name="visita.mp4"),
        "another_business": lambda: upload(ctx=ctx_for(scope=B)),
    }[sample]()

    with pytest.raises(InvalidPayload) as refused:
        send({"id": str(c.id), "template": {"name": MANAGER_PHOTO, "variables": ["Ana"], "header_sample": str(chosen.id)}})

    assert "file" in refused.value.fields["header_sample"]


def test_a_template_without_a_file_header_takes_no_file():
    connect(templates=[template("recordatorio")])
    c = a_conversation()

    with pytest.raises(InvalidPayload) as refused:
        send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["Ana", "viernes"], "header_sample": str(upload().id)}})

    assert "header_sample" in refused.value.fields


# ── What reaches erplora.com, and what does not ─────────────────────────────────────────────────


@respx.mock
def test_a_file_gone_from_the_store_fails_the_message_saying_so(delivered, hub_files):
    row = with_photo(delivered)
    hub_files.delete(TemplateSample.objects.get(pk=row.header_sample_id).key)
    route = answering()

    out = delivered(lambda: send({"id": str(conv().id), "template": sending(row)}))

    assert route.call_count == 0
    message = stored(out)
    assert (message.status, message.error_code) == (Message.Status.FAILED, "whatsapp_inbox.header_sample_missing")
    [listed] = [m for m in run("whatsapp_inbox.message.list", {"id": str(conv().id)}).rows if m.id == out.id]
    assert "file" in listed.error_message


@respx.mock
def test_the_store_not_answering_leaves_it_to_be_handed_again(delivered, hub_files, monkeypatch):
    row = with_photo(delivered)
    route = answering()

    def not_answering(*args, **kwargs):
        raise OSError("the store did not answer")

    monkeypatch.setattr(hub_files, "open", not_answering)
    out = delivered(lambda: send({"id": str(conv().id), "template": sending(row)}))

    assert route.call_count == 0
    assert stored(out).status == Message.Status.SENDING


@respx.mock
def test_meta_not_taking_the_file_is_said_as_metas_never_erploras(delivered):
    row = with_photo(delivered)
    answering(503, {"error": {"code": "whatsapp.meta_unreachable", "message": "Meta did not take the header's file."}})

    out = delivered(lambda: send({"id": str(conv().id), "template": sending(row)}))

    message = stored(out)
    assert (message.status, message.error_code) == (Message.Status.SENDING, "whatsapp_inbox.meta_unreachable")
    [listed] = [m for m in run("whatsapp_inbox.message.list", {"id": str(conv().id)}).rows if m.id == out.id]
    assert "Meta" in listed.error_message and "erplora" not in listed.error_message.lower()


@respx.mock
def test_a_message_never_carries_another_business_file(delivered):
    """Phase 1 shares the tables: a message of ``a`` naming ``b``'s file (never written by the operations) is not
    handed over with it."""
    row = with_photo(delivered)
    route = respx.post(SEND).mock(side_effect=httpx.ConnectError("down"))
    out = delivered(lambda: send({"id": str(conv().id), "template": sending(row)}))
    foreign = upload(OTHER_JPEG, name="de-b.jpg", ctx=ctx_for(scope=B))
    Message.objects.filter(pk=out.id).update(header_sample_id=foreign.id)
    calls = route.call_count

    route.mock(side_effect=None, return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
    delivered(lambda: run("whatsapp_inbox.message.retry", {"id": str(out.id)}))

    assert route.call_count == calls
    assert stored(out).error_code == "whatsapp_inbox.header_sample_missing"


# ── An automation (notify) ──────────────────────────────────────────────────────────────────────


@respx.mock
def test_an_automation_sends_a_template_made_here_with_its_own_photo(delivered):
    row = with_photo(delivered)
    route = answering()

    delivered(
        lambda: run("whatsapp_inbox.message.notify", {"phone": conv().phone, "template": sending(row)})
    )

    assert base64.b64decode(door_5(route)["template"]["header_sample"]["content_base64"]) == JPEG


def test_an_automation_cannot_send_one_that_asks_for_its_file():
    c = from_manager()

    with pytest.raises(InvalidPayload) as refused:
        run("whatsapp_inbox.message.notify", {"phone": c.phone, "template": {"name": MANAGER_PHOTO, "variables": ["Ana"]}})

    assert "header_sample" in refused.value.fields


# ── Meta's list keeps a template made here as it was (F28) ──────────────────────────────────────


@respx.mock
def test_metas_list_keeps_a_photo_template_made_here_editable_and_sendable_with_its_file(delivered):
    """Its row matched by name and language: never a new one that lost its file (the e2e's leftover row came from
    deleting the Hub's rows by hand while erplora.com kept its copy)."""
    row = approved_with_photo(delivered)

    connect(version=2, templates=[template(row.name, language=row.language, header_format="IMAGE", body=row.body)])

    [listed] = run("whatsapp_inbox.template.list", {}).rows
    assert (listed.id, listed.editable, listed.sendable) == (row.id, True, True)
    assert listed.header_sample.id == row.header_sample_id
