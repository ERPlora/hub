"""The assistant's confirmation card names each datum of a write of the WhatsApp inbox by a name of the app's own
(FIX-HUB-WHATSAPP_INBOX-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title
pydantic makes up from the field («Assignee», «Business Id»), nor by a word another app's catalog happens to lend.
The card is base's (``base.assistant.card``); the names are whatsapp_inbox's: the titles of its schemas and the
``verbose_name`` of its models, with their Spanish in its catalog, as its screens (the inbox, the conversation, the
templates, the quick replies and the channel's settings) say them."""

import gettext
import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get, registry

from apps.whatsapp_inbox.tests.conftest import B, ctx_for
from apps.whatsapp_inbox.tests.test_template_header_file import PDF, upload
from apps.whatsapp_inbox.tests.test_template_header_file import hub_files  # noqa: F401 - fixture
from base import assistant
from base.tests.test_assistant import named_by_the_screen

APP = Path(apps.get_app_config("whatsapp_inbox").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["whatsapp_inbox"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["whatsapp_inbox"]

#: The writes of the WhatsApp inbox the assistant calls, by name.
TOOLS = sorted(
    name
    for name, op in registry.items()
    if op.app_label == "whatsapp_inbox" and op.kind == "command" and assistant.is_tool(op)
)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def named_by_whatsapp_inbox(op, name: str, title: str | None) -> bool:
    """Whether whatsapp_inbox itself names the datum ``name`` of ``op``: by its schema's own title, by the
    ``verbose_name`` of one of its models, or by its own catalog. A title pydantic made up that another app's catalog
    happens to translate is not a name of the WhatsApp inbox: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("whatsapp_inbox", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_whatsapp_inbox_reaches_a_spanish_card_by_its_technical_name():
    """Every write of whatsapp_inbox the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up. By where the name comes from, not by the word."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 10  # positive control: the registry has whatsapp_inbox's writes (not the platform's own)
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_whatsapp_inbox(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_the_assignee_as_the_conversation_screen():
    """By their name or by their id, the same person: «Assigned to», as the conversation's header says it."""
    assign = get("whatsapp_inbox.conversation.assign")
    for arguments in ({"assignee": "Ana"}, {"assignee_id": 7}):
        assert labels(assistant.card(assign, arguments, "es")) == [SCREENS["conversation"]["assignedTo"]]
        assert labels(assistant.card(assign, arguments, "en")) == [SCREENS_EN["conversation"]["assignedTo"]]
    unassign = assistant.card(assign, {"unassign": True}, "es")
    assert labels(unassign) == [SCREENS["conversation"]["unassign"]]


def test_the_card_names_the_customer_card_actions_as_the_conversation_screen():
    link = get("whatsapp_inbox.conversation.link_customer")
    conversation, conversation_en = SCREENS["conversation"], SCREENS_EN["conversation"]
    arguments = {"create": True, "unlink": True}
    assert labels(assistant.card(link, arguments, "es")) == [conversation["createCard"], conversation["unlink"]]
    assert labels(assistant.card(link, arguments, "en")) == [conversation_en["createCard"], conversation_en["unlink"]]


def test_the_card_names_a_template_as_the_composer():
    """To the inbox's customer or from an automation, the same word: «Template», as the composer's button."""
    template = {"name": "cita_recordatorio", "language": "es"}
    for name in ("whatsapp_inbox.message.send", "whatsapp_inbox.message.notify"):
        assert labels(assistant.card(get(name), {"template": template}, "es")) == [SCREENS["composer"]["template"]]
        assert labels(assistant.card(get(name), {"template": template}, "en")) == [SCREENS_EN["composer"]["template"]]


# ── A real card: the header's file by its name, the attempt key never (FIX-HUB-WHATSAPP-INBOX-ATTEMPT-KEYS-UNMARKED) ──

#: What a card never carries: an id.
AN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)

#: An attempt key as a model may send it: a new UUID, or a text the write refuses but the card must not show either.
KEYS = ("0192f5a0-0000-7000-8000-0000000000a1", "reintento-1", "")


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def sending(sample_id, key: str) -> dict:
    """«Send the menu template to +34 600 111 222 with this PDF», as the model asks for it."""
    template = {"name": "carta_del_dia", "language": "es", "header_sample": str(sample_id)}
    return {"to": "+34600111222", "template": template, "client_message_id": key}


@pytest.mark.django_db
@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_card_of_a_template_names_its_headers_file_and_never_its_message_key(language, key):
    """WHATSAPP_INBOX-F33: whoever answers reads which file goes in the header, by the name it was chosen with, and
    never the key that keeps a retry from sending twice — not even empty."""
    kept = upload(PDF, "DOCUMENT", "carta.pdf")
    who = ctx_for("hub_employee", language=language)

    card = assistant.card(get("whatsapp_inbox.message.send"), sending(kept.id, key), language, ctx=who)

    template = {"name": "carta_del_dia", "language": "es", "header_sample": "carta.pdf"}
    assert values(card) == {"to": "+34600111222", "template": template}
    assert not AN_ID.search(json.dumps(card, ensure_ascii=False))


@pytest.mark.django_db
@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("name", ["whatsapp_inbox.template.create", "whatsapp_inbox.template.update"])
def test_the_card_of_a_template_to_review_names_its_headers_file_and_never_its_save_key(name, key):
    """WHATSAPP_INBOX-F29, F30: the file Meta reviews the template with, by its name; the key of the save, never."""
    kept = upload(PDF, "DOCUMENT", "carta.pdf")
    arguments = {"header_format": "DOCUMENT", "header_sample": str(kept.id), "body": "Hola", "submit_key": key}

    shown = values(assistant.card(get(name), arguments, "es", ctx=ctx_for(language="es")))

    assert shown["header_sample"] == "carta.pdf"
    assert "submit_key" not in shown


@pytest.mark.django_db
def test_a_file_of_another_business_is_never_named_nor_shown_by_its_id():
    """Phase 1 shares the tables: ``b``'s file, named in a write of ``a``, is left out of the card."""
    theirs = upload(PDF, "DOCUMENT", "de-b.pdf", ctx=ctx_for(scope=B))

    card = assistant.card(get("whatsapp_inbox.message.send"), sending(theirs.id, KEYS[0]), "es", ctx=ctx_for("hub_employee"))

    assert values(card)["template"] == {"name": "carta_del_dia", "language": "es"}
    assert not AN_ID.search(json.dumps(card, ensure_ascii=False))


@pytest.mark.parametrize("key", KEYS)
def test_an_automations_card_never_shows_the_message_key(key):
    """FLOW-F31: an automation's card, with nobody at hand to read the file as, leaves out both."""
    template = {"name": "carta_del_dia", "header_sample": KEYS[0]}
    arguments = {"phone": "+34600111222", "template": template, "client_message_id": key}

    shown = values(assistant.card(get("whatsapp_inbox.message.notify"), arguments, "es"))

    assert shown == {"phone": "+34600111222", "template": {"name": "carta_del_dia"}}
