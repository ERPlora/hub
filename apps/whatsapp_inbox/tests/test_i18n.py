"""Every visible text of the WhatsApp inbox has its Spanish translation, compiled and current."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils.functional import Promise
from django.utils.translation import gettext as gettext_
from django.utils.translation import override

from apps.whatsapp_inbox import queries, schemas, services
from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template
from apps.whatsapp_inbox.tests.conftest import receive
from base.tests.po import (
    catalogue_key,
    compiled_differences,
    config_texts,
    model_texts,
    module_texts,
    operation_titles,
    po_entries,
    untranslated,
)

LOCALE = (
    Path(apps.get_app_config("whatsapp_inbox").path) / "locale" / "es" / "LC_MESSAGES"
)


def visible_texts() -> set[str]:
    """The catalogue key of every lazy text the app shows (menu, store, admin, choices, errors) — its English, with
    its context in front for a ``pgettext_lazy`` — and the titles of its schemas."""
    config = apps.get_app_config("whatsapp_inbox")
    lazies = [
        *config_texts(config),
        # The Home's bell and the device's notices (WHATSAPP_INBOX-F09).
        *(counter.label for counter in config.bell),
        *(text for notice in config.notices for text in (*notice.title, *notice.body) if isinstance(text, Promise)),
        *module_texts(schemas, queries, services),
    ]
    lazies += model_texts((Channel, Conversation, Message, Note, Template))
    for choices in (
        Channel.Status,
        Conversation.Status,
        Message.Direction,
        Message.Origin,
        Message.Source,
        Message.Status,
        Template.Category,
        Template.Status,
        Template.HeaderFormat,
        Template.SubmitState,
        Template.DeleteState,
    ):
        lazies += list(choices.labels)
    with override("en"):
        return {catalogue_key(text) for text in lazies} | operation_titles("whatsapp_inbox")


def test_every_entry_has_a_spanish_translation():
    assert untranslated(LOCALE / "django.po") == []


def test_every_visible_text_is_in_the_catalog():
    """By its whole key, context included: a text that goes back to ``_()`` while its entry keeps the context, or whose
    context has a typo, is missing from the catalogue — on screen it says another app's Spanish (hub#639)."""
    texts = visible_texts()
    assert len(texts) > 200  # positive control: the collection found the app's texts...
    assert len({key for key in texts if "\x04" in key}) >= 37  # ...and kept the context of its pgettext_lazy ones
    assert texts - set(po_entries(LOCALE / "django.po")) == set()


def test_the_compiled_catalog_is_current():
    assert compiled_differences(LOCALE) == {}


def test_the_card_says_each_title_with_whatsapp_inboxs_own_spanish():
    """A title the inbox shares with an app installed before it («Phone», «Template») is said with that app's
    Spanish, so the inbox's own entry would be dead text: they have to say the same."""
    with (LOCALE / "django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    titles = operation_titles("whatsapp_inbox")
    assert {"Assigned to", "Template", "WhatsApp Business account"} <= titles
    with override("es"):
        assert {title: gettext_(title) for title in titles} == {title: own.gettext(title) for title in titles}


def test_spanish_texts():
    with override("es"):
        assert (
            str(apps.get_app_config("whatsapp_inbox").verbose_name)
            == "Bandeja de WhatsApp"
        )
        assert str(Conversation.Status.PENDING.label) == "Pendiente"
        assert str(Message.Status.READ.label) == "Leído"
        assert str(Template.Status.DELETED.label) == "Borrada en WhatsApp Manager"
        assert str(services.WINDOW_CLOSED) == (
            "Han pasado más de 24 horas desde el último mensaje del cliente: WhatsApp solo deja escribirle "
            "con una plantilla aprobada."
        )
        assert str(queries.RECONNECT_NEEDED) == "El permiso de WhatsApp para tu número caducó: vuelve a conectarlo."


def test_spanish_says_the_inboxs_own_words_not_an_earlier_apps():
    """The labels the inbox shares in English with an app loaded before it come out in Spanish with its own words
    (hub#570): where a message came from (live or its history) is its «procedencia», since «origen» already names who
    sent it, not Clientes' «origen»; a template is «borrada el» and «sincronizada el» like it is «entregada el», not
    Clientes' «eliminado el» nor Facturación's «recibido el»; the channel is «sincronizado el»."""
    labels = {
        "Message.origin": Message._meta.get_field("origin").verbose_name,
        "Message.source": Message._meta.get_field("source").verbose_name,
        "Template.submit_at": Template._meta.get_field("submit_at").verbose_name,
        "Template.deleted_at": Template._meta.get_field("deleted_at").verbose_name,
        "Template.synced_at": Template._meta.get_field("synced_at").verbose_name,
        "Channel.synced_at": Channel._meta.get_field("synced_at").verbose_name,
    }
    with override("es"):
        assert {name: str(label) for name, label in labels.items()} == {
            "Message.origin": "origen",
            "Message.source": "procedencia",
            "Template.submit_at": "entregada el",
            "Template.deleted_at": "borrada el",
            "Template.synced_at": "sincronizada el",
            "Channel.synced_at": "sincronizado el",
        }


@pytest.mark.django_db
def test_an_error_follows_the_language_of_the_request(client, make_user):
    receive("wamid.1")
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = client.post(
        "/api/whatsapp_inbox/messages/send",
        json.dumps({"conversation": "Zoe", "text": "Hola", "client_message_id": "0199e000-0000-7000-8000-0000000000be"}),
        content_type="application/json",
        HTTP_HOST="a.localhost",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    assert response.status_code == 404
    assert (
        response.json()["error"]["message"]
        == "Ninguna conversación coincide con «Zoe»."
    )
