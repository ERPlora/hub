"""Live queries of the WhatsApp inbox and the events that re-run them after the COMMIT.

The inbox is live (WHATSAPP_INBOX-F03): a message arriving, sent or read, an assignment, a status, a
card joined or the channel's state re-run what shows them. A customer card renamed, merged, deleted or erased
re-runs the lists that paint its name. The exact-number lookup (for other apps) and the team (a picker)
are asked once, not followed.
"""

from live.live_registry import live

from apps.whatsapp_inbox import events as E

INBOX = [
    E.MESSAGE_RECEIVED,
    E.MESSAGE_SENT,
    E.CONVERSATION_READ,
    E.ASSIGNED,
    E.STATUS_CHANGED,
    E.CUSTOMER_LINKED,
    E.ERASED,
]
#: A card's name is painted in the inbox.
CARD = [E.CUSTOMER_UPDATED, E.CUSTOMER_MERGED, E.CUSTOMER_DELETED, E.CUSTOMER_ERASED]

live("whatsapp_inbox.conversation.list", on=[*INBOX, *CARD])
live("whatsapp_inbox.conversation.detail", on=[*INBOX, *CARD, E.CHANNEL_SYNCED])
live(
    "whatsapp_inbox.conversation.summary",
    on=[
        E.MESSAGE_RECEIVED,
        E.MESSAGE_SENT,
        E.CONVERSATION_READ,
        E.STATUS_CHANGED,
        E.ERASED,
        E.CHANNEL_SYNCED,
    ],
)
live(
    "whatsapp_inbox.message.list",
    on=[E.MESSAGE_RECEIVED, E.MESSAGE_SENT, E.MESSAGE_STATUS_CHANGED, E.ERASED],
)
live("whatsapp_inbox.note.list", on=[E.NOTE_ADDED, E.NOTE_DELETED, E.ERASED])
live(
    "whatsapp_inbox.template.list",
    on=[E.CHANNEL_SYNCED, E.TEMPLATE_CREATED, E.TEMPLATE_UPDATED, E.TEMPLATE_DELETED],
)
live("whatsapp_inbox.channel.get", on=[E.CHANNEL_SYNCED])
