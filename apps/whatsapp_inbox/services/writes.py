"""What more than one write of the WhatsApp inbox shares: the system's own permission, saving a row, a
hand-over after the COMMIT, and a number's conversation and customer card."""

from uuid import UUID

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import atomic
from live.outbox import record_event

from apps.customer.models import Customer
from apps.customer.services.writes import lock_customers
from apps.whatsapp_inbox import events
from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.queries.reads import live_conversations
from base import outbound

#: Only the system context (``*``) holds it: the doors erplora.com calls, the reactions, the deliveries.
RECEIVE = "whatsapp_inbox.receive"

NOT_A_NUMBER = _("This is not a phone number.")


def _save(instance, *fields: str) -> None:
    instance.save(
        update_fields=[
            *fields,
            *(["updated_at"] if hasattr(instance, "updated_at") else []),
        ]
    )


def _after_commit(ctx: OperationContext, job, *args) -> None:
    """Run ``job(scope, *args)`` once this command's transaction committed (never after a rollback): outside it, with
    no lock, in a thread of the process's own (``base.outbound``) and in this command's database, so that the
    request, the worker's relay or its tick that committed never waits for erplora.com. A job lost on the way (the
    process stopped) is found again by ``delivery.resume``: each one claims its row first."""
    outbound.after_commit(job, ctx.scope, *args)


def _conversation_for(phone: str, contact_name: str = "") -> Conversation:
    """The live conversation of ``phone``, locked; created when there is none.

    Two transactions that create it at once meet at the unique index: the second waits for the first
    and then takes its row.
    """
    rows = live_conversations().select_for_update()
    found = rows.filter(phone=phone).first()
    if found is not None:
        return found
    try:
        with atomic():
            return Conversation.objects.create(phone=phone, contact_name=contact_name)
    except IntegrityError:
        return rows.get(phone=phone)


def _live_card_id(conversation: Conversation) -> UUID | None:
    """The conversation's card if it is still live; a deleted, merged or erased card counts as none."""
    if conversation.customer_id is None:
        return None
    return (
        conversation.customer_id
        if Customer.objects.live().filter(pk=conversation.customer_id).exists()
        else None
    )


def _only_card_of(phone: str) -> UUID | None:
    """The one live card with ``phone``; ``None`` when there is none or several."""
    ids = (
        list(
            Customer.objects.live().filter(phone=phone).values_list("id", flat=True)[:2]
        )
        if phone
        else []
    )
    return ids[0] if len(ids) == 1 else None


def _locked_cards_of(phones) -> dict[str, UUID]:
    """The one live card of each number of ``phones`` (none for a number with none or several), locked in id order
    before the conversations they join.

    Customers' writes and the Hub admin's «Delete» of a card lock the card before what points at it (the deletion
    then leaves its conversations without it): a deletion under way is waited for and its card is no longer there
    to join; one that comes after waits for the join and then leaves the conversation without the card. Each card
    is read again once locked: the write it waited for may have changed its number or taken it out of use.
    """
    wanted = {phone: _only_card_of(phone) for phone in phones if phone}
    lock_customers([card_id for card_id in wanted.values() if card_id is not None])
    return {
        phone: card_id
        for phone, card_id in wanted.items()
        if card_id is not None and _only_card_of(phone) == card_id
    }


def _link_by_phone(ctx: OperationContext, conversation: Conversation, card_id: UUID | None) -> None:
    """Join a conversation without a live card to ``card_id``, the one live card of its number, locked before the
    conversation (``_locked_cards_of``; WHATSAPP_INBOX-F04)."""
    if card_id is None or _live_card_id(conversation) is not None or card_id == conversation.customer_id:
        return
    conversation.customer_id = card_id
    _save(conversation, "customer")
    record_event(
        ctx,
        events.CUSTOMER_LINKED,
        {"id": str(conversation.id), "customer_id": str(card_id)},
    )
