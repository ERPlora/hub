"""Events of the WhatsApp inbox (``whatsapp_inbox.<entity>.<fact>``) and its reactions to Customers.

services.py records them in the outbox, in the command's transaction; live.py names the ones that
re-run each live query. They carry ids only, never a number or a text.

Reactions (WORKBOOK «A qué reacciona»): a card created or corrected claims the unlinked conversations
of its number (F04), a merged card hands its conversations to the one that stays (F12), a deleted card
lets them go (another live card of the number may claim them) and an erased card erases them (F11), each through an operation of this app run as the system, in its own
transaction. The outbox relay (phase 2, in the worker) hands each delivered event to ``react``; the
operations are idempotent, so a repeated delivery changes nothing.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

MESSAGE_RECEIVED = "whatsapp_inbox.message.received"
MESSAGE_SENT = "whatsapp_inbox.message.sent"
MESSAGE_STATUS_CHANGED = "whatsapp_inbox.message.status_changed"
CONVERSATION_READ = "whatsapp_inbox.conversation.read"
ASSIGNED = "whatsapp_inbox.conversation.assigned"
STATUS_CHANGED = "whatsapp_inbox.conversation.status_changed"
CUSTOMER_LINKED = "whatsapp_inbox.conversation.customer_linked"
ERASED = "whatsapp_inbox.conversation.erased"
NOTE_ADDED = "whatsapp_inbox.note.added"
NOTE_DELETED = "whatsapp_inbox.note.deleted"
CHANNEL_SYNCED = "whatsapp_inbox.channel.synced"
#: erplora.com's answer when the business connects (door 11) or disconnects (door 12) its number from Settings.
CHANNEL_CONNECTED = "whatsapp_inbox.channel.connected"
CHANNEL_DISCONNECTED = "whatsapp_inbox.channel.disconnected"
TEMPLATE_CREATED = "whatsapp_inbox.template.created"
TEMPLATE_UPDATED = "whatsapp_inbox.template.updated"
TEMPLATE_DELETED = "whatsapp_inbox.template.deleted"
#: The file of a template's header with a photo, a video or a document, kept in the hub's store (F29).
TEMPLATE_SAMPLE_UPLOADED = "whatsapp_inbox.template_sample.uploaded"

ALL = [
    MESSAGE_RECEIVED,
    MESSAGE_SENT,
    MESSAGE_STATUS_CHANGED,
    CONVERSATION_READ,
    ASSIGNED,
    STATUS_CHANGED,
    CUSTOMER_LINKED,
    ERASED,
    NOTE_ADDED,
    NOTE_DELETED,
    CHANNEL_SYNCED,
    CHANNEL_CONNECTED,
    CHANNEL_DISCONNECTED,
    TEMPLATE_CREATED,
    TEMPLATE_UPDATED,
    TEMPLATE_DELETED,
    TEMPLATE_SAMPLE_UPLOADED,
]

#: What changes whether a conversation waits for an answer (WHATSAPP_INBOX-F09; the bell's count): a message arrives
#: (the customer's, or the echo of one sent from the business's phone), one is sent from the Hub, its status changes or
#: it is erased. Never a read, an assignment, a note nor a card joined.
AWAITING_REPLY_EVENTS = [MESSAGE_RECEIVED, MESSAGE_SENT, STATUS_CHANGED, ERASED]
#: What may leave a customer waiting anew (the device's notices): a message of hers, or a conversation opened again.
NOTICE_EVENTS = [MESSAGE_RECEIVED, STATUS_CHANGED]

# The Customers app's events (its WORKBOOK fixes their payload: ``{"id"}``, merged adds ``absorbed_id``).
CUSTOMER_CREATED = "customer.customer.created"
CUSTOMER_UPDATED = "customer.customer.updated"
CUSTOMER_MERGED = "customer.customer.merged"
CUSTOMER_DELETED = "customer.customer.deleted"
CUSTOMER_ERASED = "customer.customer.erased"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    CUSTOMER_CREATED: "whatsapp_inbox.conversation.claim_for_customer",
    CUSTOMER_UPDATED: "whatsapp_inbox.conversation.claim_for_customer",
    CUSTOMER_MERGED: "whatsapp_inbox.conversation.move_customer",
    CUSTOMER_DELETED: "whatsapp_inbox.conversation.release_customer",
    CUSTOMER_ERASED: "whatsapp_inbox.conversation.erase_for_customer",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
