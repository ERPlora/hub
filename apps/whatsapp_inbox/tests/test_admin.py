"""Django admin of the WhatsApp inbox (round 12, PLAN §17): the staff's CRUD on hubs.erplora.com/admin.

Messages are read only, received and sent alike: they are what WhatsApp carried, and a message is
corrected by erasing the conversation's data, never by editing it. Deleting stays for the staff.
"""

import re

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.whatsapp_inbox.admin import (
    ChannelAdmin,
    ConversationAdmin,
    MessageAdmin,
    MessageInline,
    NoteAdmin,
    TemplateAdmin,
)
from apps.whatsapp_inbox.models import Channel, Conversation, Message, Note, Template
from apps.whatsapp_inbox.tests.conftest import NOW, receive


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_model_is_registered():
    assert isinstance(admin.site._registry[Channel], ChannelAdmin)
    assert isinstance(admin.site._registry[Conversation], ConversationAdmin)
    assert isinstance(admin.site._registry[Message], MessageAdmin)
    assert isinstance(admin.site._registry[Note], NoteAdmin)
    assert isinstance(admin.site._registry[Template], TemplateAdmin)
    assert MessageInline in admin.site._registry[Conversation].inlines


def test_full_crud_except_messages_which_are_read_only(superuser):
    request = request_by(superuser)
    for model in (Channel, Conversation, Note, Template):
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request)
        assert model_admin.has_add_permission(request)
        assert model_admin.has_change_permission(request)
        assert model_admin.has_delete_permission(request)
    messages = admin.site._registry[Message]
    assert messages.has_view_permission(request)
    assert not messages.has_add_permission(request)
    assert not messages.has_change_permission(request)
    assert messages.has_delete_permission(request)
    inline = MessageInline(Conversation, admin.site)
    assert not inline.has_add_permission(request, None)
    assert not inline.has_change_permission(request)


@pytest.mark.django_db
def test_the_pages_render(client, superuser):
    receive("wamid.1")
    conversation = Conversation.objects.get()
    message = Message.objects.get()
    note = Note.objects.create(conversation=conversation, text="Llamar", created_at=NOW)
    template = Template.objects.create(host="a", name="recordatorio", language="es")
    channel = Channel.objects.create()
    client.force_login(superuser)
    host = {"HTTP_HOST": "hubs.localhost"}
    for path in (
        "/admin/whatsapp_inbox/conversation/",
        f"/admin/whatsapp_inbox/conversation/{conversation.pk}/change/",
        "/admin/whatsapp_inbox/message/",
        f"/admin/whatsapp_inbox/message/{message.pk}/change/",
        f"/admin/whatsapp_inbox/note/{note.pk}/change/",
        f"/admin/whatsapp_inbox/template/{template.pk}/change/",
        f"/admin/whatsapp_inbox/channel/{channel.pk}/change/",
    ):
        assert client.get(path, **host).status_code == 200, path


def test_the_channels_say_whose_business_they_are():
    # One row per business (phase 1: its host): the staff tells them apart by it.
    channels = admin.site._registry[Channel]
    assert channels.list_display[0] == "host"
    assert "host" in channels.search_fields
    assert "host" in channels.readonly_fields


def test_the_templates_say_whose_business_they_are():
    # Each business's templates are its own (phase 1: its host); the staff tells them apart by it.
    templates = admin.site._registry[Template]
    assert templates.list_display[0] == "host"
    assert "host" in templates.list_filter
    assert "host" in templates.search_fields
    assert "host" in templates.readonly_fields


@pytest.mark.django_db
def test_the_admin_in_spanish_says_the_inboxs_own_words(client, superuser):
    """The messages' list filters by «origen» (who sent it) and by «procedencia» (live or its history), two filters
    with two names; a template says when it was «Sincronizada el» and «Borrada el», and the channel «Sincronizado el»:
    the inbox's words, not the «origen» and «eliminado el» of Clientes nor the «recibido el» of Facturación, loaded
    before it with the same English (hub#570)."""
    receive("wamid.1")
    template = Template.objects.create(host="a", name="recordatorio", language="es", synced_at=NOW, deleted_at=NOW)
    channel = Channel.objects.create(synced_at=NOW)
    client.force_login(superuser)

    def page(path: str) -> str:
        response = client.get(path, HTTP_HOST="hubs.localhost", HTTP_ACCEPT_LANGUAGE="es")
        assert response.status_code == 200, path
        return response.content.decode()

    messages = page("/admin/whatsapp_inbox/message/")
    assert '<details data-filter-title="dirección"' in messages  # the page is in Spanish
    assert messages.count('<details data-filter-title="origen"') == 1  # who sent it
    assert '<details data-filter-title="procedencia"' in messages  # live or its history
    templates = page("/admin/whatsapp_inbox/template/")
    header = re.search(r'class="sortable column-synced_at">\s*<div class="text"><a [^>]*>([^<]*)</a>', templates)
    assert header and header.group(1) == "Sincronizada el"
    shown = page(f"/admin/whatsapp_inbox/template/{template.pk}/change/")
    assert 'for="id_synced_at">Sincronizada el:</label>' in shown
    assert "<label>Borrada el:</label>" in shown
    assert 'for="id_synced_at">Sincronizado el:</label>' in page(f"/admin/whatsapp_inbox/channel/{channel.pk}/change/")
    for said in (messages, templates, shown):
        assert "liminado el" not in said
        assert "ecibido el" not in said
