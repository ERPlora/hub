"""Models of the WhatsApp inbox: the channel's state, conversations, their messages and notes, and the
copy of the templates Meta approved (WORKBOOK «Para quien lo mantiene → Modelo»).

Each business has these tables in its own database; only the live notifications are per scope. A conversation is live
while ``erased_at`` is empty; erased (WHATSAPP_INBOX-F10, F11) it keeps no personal data and frees its number. Who a
conversation is with, who sent a message from the Hub and who wrote a note hang from the person in the business's own
database (``base.HubUser``), never from control's user: the columns ``*_hub_user_id`` are new, the old ones wait empty
for a later deploy to drop them (``migrations/0010_hub_users``).

One module per responsibility, each imported here so that Django registers its models, in this order.
"""

from . import (
    channel as channel,
    conversations as conversations,
    templates as templates,
)
