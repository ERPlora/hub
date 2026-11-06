"""FIX-HUB-WHATSAPP_INBOX-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#571): the card of a write of the WhatsApp inbox
says which conversation, customer card, message, note or template it acts on by its name, read as whoever asks, never
by its id, and leaves it out when that person may not read it or it is not there. A conversation goes by what the
inbox calls it, a message and a note by their text, a template by its name and its language, as its sheet says
«¿Borrar esta plantilla?»; the customer card is Customers', which the inbox requires, by its own read.
"""

import dataclasses

import pytest
from live.context import OperationContext, Scope
from live.assistant import NAMED
from live.errors import NotFound, PermissionDenied
from live.operations import get
from pydantic import ValidationError

from apps.whatsapp_inbox.models import Conversation, Message, Note, Template
from apps.whatsapp_inbox.tests.conftest import NOW, A, card, connect, ctx_for, receive, run, template
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

#: The writes on a conversation, each with what else the model sends: the conversation by its id.
ON_A_CONVERSATION = [
    ("whatsapp_inbox.conversation.assign", {"unassign": True}),
    ("whatsapp_inbox.conversation.erase", {}),
    ("whatsapp_inbox.conversation.flag", {}),
    ("whatsapp_inbox.conversation.link_customer", {"unlink": True}),
    ("whatsapp_inbox.conversation.mark_read", {}),
    ("whatsapp_inbox.conversation.set_status", {"status": "closed"}),
    ("whatsapp_inbox.note.add", {"text": "Call her back"}),
    ("whatsapp_inbox.message.send", {"text": "Hola Ana"}),
]

#: The writes on a template of the business, as Settings › WhatsApp lists it.
ON_A_TEMPLATE = ["whatsapp_inbox.template.delete", "whatsapp_inbox.template.retry", "whatsapp_inbox.template.update"]


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card_ = assistant.card(get(write), arguments, language, ctx or ctx_for(language=language))
    return {field["name"]: field for field in card_["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def read(name: str, data: dict, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data))


def without(permission: str, scope: Scope = A) -> OperationContext:
    """An admin of ``scope`` without ``permission``: a combination no role has."""
    return dataclasses.replace(ctx_for(scope=scope), permissions=frozenset(ctx_for().permissions) - {permission})


def a_conversation(wa_id: str = "wamid.1", **fields) -> Conversation:
    """A customer's first message makes her conversation, as erplora.com hands it in (her profile is «Ana»)."""
    return Conversation.objects.get(pk=receive(wa_id, **fields).conversation_id)


def a_note(text: str = "Prefers mornings") -> Note:
    added = run("whatsapp_inbox.note.add", {"id": str(a_conversation().id), "text": text})
    return Note.objects.get(pk=added.id)


def a_template(name: str = "recordatorio", language: str = "es") -> Template:
    """A template of the business, as erplora.com's photo of Meta's list brings it."""
    connect(templates=[template(name, language=language)])
    return Template.objects.get(name=name, language=language)


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


# ── A conversation ────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Conversation"), ("es", "Conversación")])
@pytest.mark.parametrize(("write", "extra"), ON_A_CONVERSATION)
def test_a_write_on_a_conversation_says_whose_it_is_as_the_inbox_calls_it(write, extra, language, title):
    """The case the issue names: assigning, closing, erasing, noting or answering a conversation."""
    conversation = a_conversation()
    field = fields_of(write, {"id": str(conversation.id), **extra}, language)["id"]
    assert (field["value"], field["label"]) == ("Ana", title)


@pytest.mark.django_db
def test_a_conversation_joined_to_a_card_goes_by_the_cards_name():
    """As the inbox lists it: the card's name before the WhatsApp profile's."""
    conversation = a_conversation()
    ana = card("Ana López")
    run("whatsapp_inbox.conversation.link_customer", {"id": str(conversation.id), "customer_id": str(ana.id)})
    said = shown("whatsapp_inbox.conversation.set_status", {"id": str(conversation.id), "status": "open"})
    assert said["id"] == "Ana López"


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Customer"), ("es", "Cliente")])
def test_joining_a_card_says_the_customer_by_its_name(language, title):
    conversation, ana = a_conversation(), card("Ana López")
    said = fields_of(
        "whatsapp_inbox.conversation.link_customer", {"id": str(conversation.id), "customer_id": str(ana.id)}, language
    )
    assert (said["customer_id"]["value"], said["customer_id"]["label"]) == ("Ana López", title)
    assert said["id"]["value"] == "Ana"


# ── A message and a note, by their text ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Message"), ("es", "Mensaje")])
def test_retrying_a_message_says_it_by_its_text(language, title):
    message = Message.objects.get(pk=receive("wamid.1", text="Hola, ¿tenéis hora mañana?").id)
    field = fields_of("whatsapp_inbox.message.retry", {"id": str(message.id)}, language)["id"]
    assert (field["value"], field["label"]) == ("Hola, ¿tenéis hora mañana?", title)


@pytest.mark.django_db
def test_a_message_without_text_goes_by_its_caption_else_by_its_file_name():
    """As the inbox's list says one: its caption, else its file name."""
    media = {"url": "https://erplora.com/m/1", "mime_type": "application/pdf", "filename": "carta.pdf"}
    captioned = receive("wamid.c", type="document", text="", media={**media, "caption": "La carta de hoy"})
    bare = receive("wamid.b", type="document", text="", media=media)
    retry = "whatsapp_inbox.message.retry"
    assert shown(retry, {"id": str(captioned.id)})["id"] == "La carta de hoy"
    assert shown(retry, {"id": str(bare.id)})["id"] == "carta.pdf"


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Note"), ("es", "Nota")])
def test_deleting_a_note_says_it_by_its_text(language, title):
    note = a_note("Prefers mornings")
    field = fields_of("whatsapp_inbox.note.delete", {"id": str(note.id)}, language)["id"]
    assert (field["value"], field["label"]) == ("Prefers mornings", title)


# ── A template, by its name and its language ──────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Template"), ("es", "Plantilla")])
@pytest.mark.parametrize("write", ON_A_TEMPLATE)
def test_a_write_on_a_template_says_its_name_and_its_language_as_its_sheet_does(write, language, title):
    """«recordatorio (es)»: the same name may be in several languages."""
    kept = a_template("recordatorio", "es")
    field = fields_of(write, {"id": str(kept.id)}, language)["id"]
    assert (field["value"], field["label"]) == ("recordatorio (es)", title)


@pytest.mark.django_db
def test_a_template_deleted_here_that_meta_still_has_is_named_to_retry_its_deletion():
    """Settings still lists it, «Deleting…», and «Retry» hands its deletion to Meta again."""
    kept = a_template()
    run("whatsapp_inbox.template.delete", {"id": str(kept.id)})
    kept.refresh_from_db()
    assert kept.delete_state == Template.DeleteState.PENDING  # positive control: deleted here, not at Meta yet
    assert shown("whatsapp_inbox.template.retry", {"id": str(kept.id)})["id"] == "recordatorio (es)"


@pytest.mark.parametrize("write", ["whatsapp_inbox.template.create", "whatsapp_inbox.template.update"])
def test_the_buttons_of_a_template_go_by_how_many_never_by_their_codes(write):
    """A button is a line of two data (its type and its text), so the card says how many go, as it does every such
    list, and never «QUICK_REPLY»: why the type of a button, which no field of the models names, may stay without its
    label in base/tests/test_assistant_card_values.py (hub#571)."""
    buttons = [{"type": "QUICK_REPLY", "text": "Sí"}, {"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "+34910000000"}]
    field = fields_of(write, {"body": "Hola", "buttons": buttons}, "es", ctx=None)["buttons"]
    assert (field["kind"], NAMED in field) == ("list", False)


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("needed", "write", "datum"),
    [
        ("whatsapp_inbox.view", "whatsapp_inbox.conversation.set_status", "id"),
        ("whatsapp_inbox.view", "whatsapp_inbox.message.retry", "id"),
        ("whatsapp_inbox.view", "whatsapp_inbox.note.delete", "id"),
        ("whatsapp_inbox.reply", "whatsapp_inbox.template.delete", "id"),
        ("customer.view", "whatsapp_inbox.conversation.link_customer", "customer_id"),
    ],
)
def test_what_the_person_may_not_read_is_left_out_never_said_by_its_id(needed, write, datum):
    conversation = a_conversation()
    target = {
        "whatsapp_inbox.conversation.set_status": lambda: conversation,
        "whatsapp_inbox.message.retry": lambda: Message.objects.filter(conversation=conversation).get(),
        "whatsapp_inbox.note.delete": lambda: a_note(),
        "whatsapp_inbox.template.delete": lambda: a_template(),
        "whatsapp_inbox.conversation.link_customer": lambda: card("Ana López"),
    }[write]()
    arguments = {datum: str(target.id), **({"status": "open"} if write.endswith("set_status") else {})}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without(needed))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("write", "datum"),
    [
        ("whatsapp_inbox.conversation.erase", "id"),
        ("whatsapp_inbox.message.send", "id"),
        ("whatsapp_inbox.conversation.link_customer", "customer_id"),
        ("whatsapp_inbox.message.retry", "id"),
        ("whatsapp_inbox.note.delete", "id"),
        ("whatsapp_inbox.template.update", "id"),
    ],
)
def test_what_does_not_exist_is_left_out(write, datum):
    said = shown(write, {datum: A_MISSING_ID})
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_an_erased_conversation_and_what_it_held_are_left_out():
    """Erasing keeps the conversation's row without the customer's data: no screen shows it any more."""
    conversation = a_conversation()
    message = Message.objects.filter(conversation=conversation).get()
    Conversation.objects.filter(pk=conversation.pk).update(erased_at=NOW)
    assert shown("whatsapp_inbox.conversation.erase", {"id": str(conversation.id)}) == {}
    assert shown("whatsapp_inbox.message.retry", {"id": str(message.id)}) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    conversation = a_conversation()
    said = {
        field["name"]: field["value"]
        for field in assistant.card(get("whatsapp_inbox.note.add"), {"id": str(conversation.id), "text": "Hi"}, "en")[
            "fields"
        ]
    }
    assert said == {"text": "Hi"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        conversation = Conversation.objects.get(pk=receive(scope=in_a.scope).conversation_id)
        note = Note.objects.create(conversation=conversation, text="Prefers mornings")
        kept = Template.objects.create(host=hub_a.slug, name="recordatorio", language="es", body="Hola")
        writes = [
            ("whatsapp_inbox.conversation.set_status", conversation, {"status": "open"}),
            ("whatsapp_inbox.note.delete", note, {}),
            ("whatsapp_inbox.template.delete", kept, {}),
        ]
        for write, record, extra in writes:  # positive control
            assert "id" in shown(write, {"id": str(record.id), **extra}, ctx=in_a), write
    with use_hub(hub_b):
        for write, record, extra in writes:
            assert "id" not in shown(write, {"id": str(record.id), **extra}, ctx=in_b), write


# ── The reads that name them ──────────────────────────────────────────────────────────────────────────────────────────

READS = ["whatsapp_inbox.note.get", "whatsapp_inbox.template.get"]


@pytest.mark.django_db
def test_the_reads_answer_what_names_what_they_read():
    note, kept = a_note("Prefers mornings"), a_template("recordatorio", "en")
    assert read("whatsapp_inbox.note.get", {"id": str(note.id)}).text == "Prefers mornings"
    named = read("whatsapp_inbox.template.get", {"id": str(kept.id)})
    assert (named.name, named.language, named.label) == ("recordatorio", "en", "recordatorio (en)")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "needed"),
    [("whatsapp_inbox.note.get", "whatsapp_inbox.view"), ("whatsapp_inbox.template.get", "whatsapp_inbox.reply")],
)
def test_the_reads_need_the_right_to_see_what_they_read(name, needed):
    with pytest.raises(PermissionDenied):
        read(name, {"id": A_MISSING_ID}, without(needed))


@pytest.mark.django_db
@pytest.mark.parametrize("name", READS)
def test_the_reads_say_not_found_for_what_is_not_there(name):
    with pytest.raises(NotFound):
        read(name, {"id": A_MISSING_ID})


@pytest.mark.django_db
def test_a_template_of_another_business_or_gone_for_good_is_not_found():
    """Phase 1 shares the table: only the business's own, and not one Meta deleted too."""
    theirs = Template.objects.create(host="b", name="recordatorio", language="es", body="Hola")
    gone = a_template("aviso")
    Template.objects.filter(pk=gone.pk).update(deleted_at=NOW)
    for row in (theirs, gone):
        with pytest.raises(NotFound):
            read("whatsapp_inbox.template.get", {"id": str(row.id)})


@pytest.mark.parametrize("name", READS)
def test_the_reads_refuse_no_id(name):
    with pytest.raises(ValidationError):
        get(name).input.model_validate({})


@pytest.mark.parametrize("name", READS)
def test_the_reads_are_no_tool_of_the_assistant(name):
    """The model finds them in their lists; only the card reads them."""
    assert not assistant.is_tool(get(name))
