"""Reactions to Customers (events.py): a card made, merged (WHATSAPP_INBOX-F12), deleted or
erased (F11) takes, moves, lets go or erases the conversations of its number."""

from django.db.models import Q
from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.customer.models import Customer
from apps.customer.services.writes import lock_customers
from apps.whatsapp_inbox import events
from apps.whatsapp_inbox.models.conversations import Conversation
from apps.whatsapp_inbox.queries.reads import live_conversations
from apps.whatsapp_inbox.schemas.customer_reactions import CustomerEventIn, MergedEventIn, ReactionOut

from .erasing import _erase
from .writes import RECEIVE, _link_by_phone, _locked_cards_of, _only_card_of, _save


@operation(
    "whatsapp_inbox.conversation.claim_for_customer",
    kind="command",
    permission=RECEIVE,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "System only (customer.customer.created/updated/restored): joins the conversations of "
        "the card's number that have no live card to it, when no other live card has that number.",
        "risk": "normal",
    },
)
def claim_for_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    # The card before its number's conversations (``_locked_cards_of``); one the Hub admin deleted claims nothing.
    if not lock_customers([data.id]):
        return {"count": 0}
    card = Customer.objects.live().filter(pk=data.id).first()
    if card is None or not card.phone or _only_card_of(card.phone) != card.id:
        return {"count": 0}
    rows = list(
        live_conversations()
        .select_for_update(of=("self",))
        .filter(
            Q(customer__isnull=True) | Q(customer__deleted_at__isnull=False),
            phone=card.phone,
        )
    )
    for conversation in rows:
        conversation.customer = card
        _save(conversation, "customer")
        record_event(
            ctx,
            events.CUSTOMER_LINKED,
            {"id": str(conversation.id), "customer_id": str(card.id)},
        )
    return {"count": len(rows)}


@operation(
    "whatsapp_inbox.conversation.move_customer",
    kind="command",
    permission=RECEIVE,
    input=MergedEventIn,
    output=ReactionOut,
    ai={
        "description": "System only (customer.customer.merged): the conversations of the absorbed card follow the "
        "card that stays.",
        "risk": "normal",
    },
)
def move_customer(ctx: OperationContext, data: MergedEventIn) -> dict:
    # The card that stays before the conversations that move to it; one the Hub admin deleted takes nothing.
    if data.id == data.absorbed_id or not lock_customers([data.id]):
        return {"count": 0}
    rows = list(
        Conversation.objects.select_for_update().filter(customer_id=data.absorbed_id)
    )
    for conversation in rows:
        conversation.customer_id = data.id
        _save(conversation, "customer")
        record_event(
            ctx,
            events.CUSTOMER_LINKED,
            {"id": str(conversation.id), "customer_id": str(data.id)},
        )
    return {"count": len(rows)}


@operation(
    "whatsapp_inbox.conversation.release_customer",
    kind="command",
    permission=RECEIVE,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "System only (customer.customer.deleted): the conversations of the deleted card are left "
        "without it, and another live card of their number, if there is exactly one, claims them.",
        "risk": "normal",
    },
)
def release_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    phones = live_conversations().filter(customer_id=data.id).values_list("phone", flat=True)
    claims = _locked_cards_of(sorted(set(phones)))
    rows = list(live_conversations().select_for_update().filter(customer_id=data.id))
    for conversation in rows:
        conversation.customer = None
        _save(conversation, "customer")
        record_event(
            ctx,
            events.CUSTOMER_LINKED,
            {"id": str(conversation.id), "customer_id": None},
        )
        _link_by_phone(ctx, conversation, claims.get(conversation.phone))
    return {"count": len(rows)}


@operation(
    "whatsapp_inbox.conversation.erase_for_customer",
    kind="command",
    permission=RECEIVE,
    input=CustomerEventIn,
    output=ReactionOut,
    ai={
        "description": "System only (customer.customer.erased): erases every conversation of the erased card, as "
        "erasing a number does, here and at erplora.com.",
        "risk": "high",
    },
)
def erase_for_customer(ctx: OperationContext, data: CustomerEventIn) -> dict:
    rows = list(live_conversations().select_for_update().filter(customer_id=data.id))
    for conversation in rows:
        _erase(ctx, conversation)
    return {"count": len(rows)}
