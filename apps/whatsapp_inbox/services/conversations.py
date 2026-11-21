"""The team's work on a conversation: read it (WHATSAPP_INBOX-F05), assign it (F07), change its status
(F35), flag it «Needs attention» (F20) and join it to a customer card (F37)."""

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, PermissionDenied
from live.operations import get, operation
from live.outbox import record_event

from apps.customer.models import Customer
from apps.customer.queries import find_customer
from apps.whatsapp_inbox import events
from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.queries.agents import team
from apps.whatsapp_inbox.queries.conversations import conversation_out, find_conversation
from apps.whatsapp_inbox.queries.reads import actor_id, person_name
from apps.whatsapp_inbox.schemas import (
    AssignIn,
    ConversationOut,
    ConversationRefIn,
    FlaggedOut,
    LinkCustomerIn,
    SetStatusIn,
)
from base.models import HubUser
from base.services.sessions import acting_hub_user

from .writes import _save

ALREADY_ASSIGNED = _("This conversation is already with %(name)s.")
ONLY_YOURSELF = _("You may only assign conversations to yourself.")
NOBODY_CALLED = _("Nobody in this business is called “%(reference)s”.")
SEVERAL_CALLED = _("Several people match “%(reference)s”: choose one from the list.")
NOT_IN_BUSINESS = _("That person does not work in this business.")
NOT_A_PERSON = _("Only a person can be assigned a conversation.")


@operation(
    "whatsapp_inbox.conversation.mark_read",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="whatsapp_inbox.view",
    input=ConversationRefIn,
    output=ConversationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "mark Nuria's chat as read",
                "clear the unread count of Jorge's conversation",
                "I've seen Elena's WhatsApp, mark it read",
            ),
            "es": (
                "da por leído el chat de Nuria",
                "pon a cero los no leídos de la conversación de Jorge",
                "ya he visto el WhatsApp de Elena, quítale el sin leer",
            ),
        },
        "description": "Marks a WhatsApp conversation as read: its unread counter goes back to zero.",
        "risk": "normal",
    },
)
def mark_read(ctx: OperationContext, data: ConversationRefIn) -> dict:
    conversation = find_conversation(ctx, data.id, data.conversation, lock=True)
    if conversation.unread_count:
        conversation.unread_count = 0
        _save(conversation, "unread_count")
        record_event(ctx, events.CONVERSATION_READ, {"id": str(conversation.id)})
    return conversation_out(conversation)


def _assignee(ctx: OperationContext, data: AssignIn) -> HubUser | None:
    """The person ``data`` names (a person of this business's database with access to it), or ``None`` to unassign."""
    if data.unassign:
        return None
    people = team(ctx)
    if data.assignee_id is not None:
        person = people.filter(pk=data.assignee_id).first()
        if person is None:
            raise InvalidPayload(
                str(NOT_IN_BUSINESS), fields={"assignee": str(NOT_IN_BUSINESS)}
            )
        return person
    reference = (data.assignee or "").strip()
    if reference.lower() == "me":
        # Whoever takes it is a person of the business's database: made if their session came before it.
        me = acting_hub_user(ctx)
        if me is None:
            raise InvalidPayload(
                str(NOT_A_PERSON), fields={"assignee": str(NOT_A_PERSON)}
            )
        person = people.filter(pk=me.pk).first()
        if person is None:
            raise InvalidPayload(
                str(NOT_IN_BUSINESS), fields={"assignee": str(NOT_IN_BUSINESS)}
            )
        return person
    # The full name, the first name (its first word), the username or the email.
    matches = list(
        people.filter(
            Q(username__iexact=reference)
            | Q(email__iexact=reference)
            | Q(name__iexact=reference)
            | Q(name__istartswith=f"{reference} ")
        )
        .order_by("id")[:2]
    )
    if not matches:
        message = str(NOBODY_CALLED % {"reference": reference})
        raise InvalidPayload(message, fields={"assignee": message})
    if len(matches) > 1:
        message = str(SEVERAL_CALLED % {"reference": reference})
        raise InvalidPayload(message, fields={"assignee": message})
    return matches[0]


@operation(
    "whatsapp_inbox.conversation.assign",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="whatsapp_inbox.reply",
    input=AssignIn,
    output=ConversationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "assign Nuria's conversation to Jorge",
                "I'll take the conversation with Elena",
                "unassign Raúl's WhatsApp",
            ),
            "es": (
                "asigna la conversación de Nuria a Jorge",
                "me quedo yo con la conversación de Elena",
                "quita la asignación del WhatsApp de Raúl",
            ),
        },
        "description": "Assigns a WhatsApp conversation to a person of the team («assign Ana's conversation to "
        "Luis», «take it»: assignee me), or to nobody. Only managers assign somebody else or take it from "
        "somebody; «only if unassigned» never takes it from anybody.",
        "risk": "normal",
    },
)
def assign(ctx: OperationContext, data: AssignIn) -> dict:
    conversation = find_conversation(ctx, data.id, data.conversation, lock=True)
    person = _assignee(ctx, data)
    me = actor_id(ctx)
    target = person.pk if person is not None else None
    taken = (
        conversation.assigned_to_id is not None
        and conversation.assigned_to_id != target
    )
    if not ctx.has("whatsapp_inbox.assign"):
        # Without the permission one only takes a free conversation, or lets one's own go.
        if conversation.assigned_to_id not in (None, me):
            raise Conflict(
                str(ALREADY_ASSIGNED % {"name": person_name(conversation.assigned_to)}),
                code="whatsapp_inbox.already_assigned",
            )
        if target not in (None, me):
            raise PermissionDenied(str(ONLY_YOURSELF))
    elif data.only_if_unassigned and taken:
        raise Conflict(
            str(ALREADY_ASSIGNED % {"name": person_name(conversation.assigned_to)}),
            code="whatsapp_inbox.already_assigned",
        )
    if conversation.assigned_to_id != target:
        conversation.assigned_to = person
        _save(conversation, "assigned_to")
        record_event(
            ctx,
            events.ASSIGNED,
            {"id": str(conversation.id), "assigned_to_id": None if target is None else str(target)},
        )
    return conversation_out(conversation)


@operation(
    "whatsapp_inbox.conversation.set_status",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="whatsapp_inbox.reply",
    input=SetStatusIn,
    output=ConversationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "change the status of Nuria's conversation to closed",
                "set Jorge's chat to pending",
                "reopen the WhatsApp conversation with Elena",
            ),
            "es": (
                "cambia a cerrada la conversación de Nuria",
                "deja pendiente el chat de Jorge",
                "vuelve a abrir la conversación de Elena",
            ),
        },
        "description": "Marks a WhatsApp conversation open, pending (waiting for the customer) or closed (done); "
        "a new message from the customer opens it again.",
        "risk": "high",
    },
)
def set_status(ctx: OperationContext, data: SetStatusIn) -> dict:
    conversation = find_conversation(ctx, data.id, data.conversation, lock=True)
    if conversation.status != data.status:
        conversation.status = data.status
        conversation.needs_attention = False
        _save(conversation, "status", "needs_attention")
        record_event(
            ctx,
            events.STATUS_CHANGED,
            {"id": str(conversation.id), "status": data.status},
        )
    return conversation_out(conversation)


@operation(
    "whatsapp_inbox.conversation.flag",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="whatsapp_inbox.reply",
    input=ConversationRefIn,
    output=FlaggedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "flag Nuria's chat as needing attention",
                "the bot didn't understand Jorge: flag the conversation",
                "a person needs to look at Elena's WhatsApp",
            ),
            "es": (
                "pon en atención la conversación de Jorge",
                "la respuesta automática no entendió a Nuria, que la mire una persona",
                "señala el chat de Elena: necesita a alguien del negocio",
            ),
        },
        "description": "Marks an open WhatsApp conversation «Needs attention»: an automatic answer could not answer "
        "the customer, so she waits for a person even after its apology; somebody of the business answering, or "
        "changing its status, takes it away. A pending or closed conversation is left as it is.",
        "risk": "normal",
    },
)
def flag(ctx: OperationContext, data: ConversationRefIn) -> dict:
    conversation = find_conversation(ctx, data.id, data.conversation, lock=True)
    if conversation.status != Conversation.Status.OPEN:
        return {"id": conversation.id, "flagged": False}
    if not conversation.needs_attention:
        conversation.needs_attention = True
        _save(conversation, "needs_attention")
        record_event(ctx, events.FLAGGED, {"id": str(conversation.id)})
    return {"id": conversation.id, "flagged": True}


@operation(
    "whatsapp_inbox.conversation.link_customer",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="whatsapp_inbox.reply",
    input=LinkCustomerIn,
    output=ConversationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "link Nuria's WhatsApp to her customer card",
                "put Elena's WhatsApp chat on her customer card",
                "unlink the customer from Jorge's conversation",
            ),
            "es": (
                "une el WhatsApp de Nuria a su ficha de cliente",
                "haz la ficha de cliente desde esta conversación",
                "quita la ficha de cliente de la conversación de Jorge",
            ),
        },
        "description": "Joins a WhatsApp conversation to a customer card (by id or by the card's exact name, phone "
        "or email), creates the card from the WhatsApp name and number, or takes the card off.",
        "risk": "normal",
    },
)
def link_customer(ctx: OperationContext, data: LinkCustomerIn) -> dict:
    # The card chosen before the conversation (``_locked_cards_of``): one the Hub admin deletes is waited for and gone.
    chosen = None
    if not (data.unlink or data.create):
        chosen = find_customer(ctx, data.customer_id, data.customer, lock=True)
    conversation = find_conversation(ctx, data.id, data.conversation, lock=True)
    if data.unlink:
        card = None
    elif data.create:
        create = get("customer.customer.create")
        made = create(
            ctx,
            create.input.model_validate(
                {
                    "name": conversation.contact_name or conversation.phone,
                    "phone": conversation.phone,
                    "source": "whatsapp",
                }
            ),
        )
        card = Customer.objects.get(pk=made.id)
    else:
        card = chosen
    if conversation.customer_id != (card.id if card else None):
        conversation.customer = card
        _save(conversation, "customer")
        record_event(
            ctx,
            events.CUSTOMER_LINKED,
            {"id": str(conversation.id), "customer_id": str(card.id) if card else None},
        )
    return conversation_out(conversation)
