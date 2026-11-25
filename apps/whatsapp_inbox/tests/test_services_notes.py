"""The internal notes of a conversation (WHATSAPP_INBOX-F36): who wrote them and who may delete them."""

import pytest
from live.errors import NotFound, PermissionDenied

from apps.whatsapp_inbox.models import Note
from apps.whatsapp_inbox.tests.conftest import HUB_DB, NOW, ctx_for, events, receive, run

pytestmark = HUB_DB


# ── WHATSAPP_INBOX-F36 Internal notes ───────────────────────────────────────────────────────────


def test_a_note_keeps_its_author_and_only_they_or_a_manager_delete_it(make_user):
    receive("wamid.1")
    luis = make_user("luis", first_name="Luis")
    marta = make_user("marta", first_name="Marta")
    note = run(
        "whatsapp_inbox.note.add",
        {"conversation": "Ana", "text": " Llamar mañana "},
        ctx_for("hub_employee", actor=luis),
    )
    assert (note.text, note.author_id, note.author_name, note.created_at) == (
        "Llamar mañana",
        luis.person.id,
        "Luis",
        NOW,
    )
    with pytest.raises(PermissionDenied):
        run(
            "whatsapp_inbox.note.delete",
            {"id": str(note.id)},
            ctx_for("hub_employee", actor=marta),
        )
    assert (
        run(
            "whatsapp_inbox.note.delete",
            {"id": str(note.id)},
            ctx_for("hub_employee", actor=luis),
        ).id
        == note.id
    )
    again = run(
        "whatsapp_inbox.note.add",
        {"conversation": "Ana", "text": "Otra"},
        ctx_for("hub_employee", actor=luis),
    )
    run("whatsapp_inbox.note.delete", {"id": str(again.id)}, ctx_for("hub_manager"))
    assert Note.objects.count() == 0
    with pytest.raises(NotFound):
        run("whatsapp_inbox.note.delete", {"id": str(again.id)})
    assert len(events("whatsapp_inbox.note.added")) == 2
    assert len(events("whatsapp_inbox.note.deleted")) == 2
