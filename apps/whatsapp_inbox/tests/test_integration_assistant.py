"""The assistant's confirmation card names each datum of a write of the WhatsApp inbox by a name of the app's own
(FIX-HUB-WHATSAPP_INBOX-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title
pydantic makes up from the field («Assignee», «Business Id»), nor by a word another app's catalog happens to lend.
The card is base's (``base.assistant.card``); the names are whatsapp_inbox's: the titles of its schemas and the
``verbose_name`` of its models, with their Spanish in its catalog, as its screens (the inbox, the conversation, the
templates, the quick replies and the channel's settings) say them."""

import gettext
import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

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
