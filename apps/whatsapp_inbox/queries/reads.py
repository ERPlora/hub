"""What the inbox's reads share, and services/ too: a number as a conversation's key, a person's name, the
caller, a message's preview, the live conversations and how a list pages."""

from uuid import UUID

from django.db.models import QuerySet
from live.context import OperationContext

from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries import business_country
from apps.whatsapp_inbox.models import Conversation
from apps.whatsapp_inbox.schemas.fields import PageIn
from base.models import HubUser
from base.queries.people import hub_user_of


def e164(raw: str, ctx: OperationContext, *, from_whatsapp: bool = False) -> str:
    """``raw`` as the conversation's key (E.164). WhatsApp's bare digits are international; a number a
    person typed is one of the business's country unless it says its own, as Customers reads a card's phone
    (in a Spanish business ``600222333`` is Spain's, never +60's; hub#527).

    Raises ``InvalidPhone`` when it is no number.
    """
    text = (raw or "").strip()
    if from_whatsapp and text.isdigit() and not text.startswith("0"):
        text = f"+{text}"
    number = to_e164(text, business_country(ctx))
    if not number:
        raise InvalidPhone(raw)
    return number


def person_name(person: HubUser | None) -> str:
    """A person's name as the inbox shows it: their full name, else their username."""
    if person is None:
        return ""
    return (person.name or person.username).strip()


def actor_id(ctx: OperationContext) -> UUID | None:
    """The calling person's id in the business's database (``base.HubUser``), read only; ``None`` for the system, an
    API key, a test's string actor or a person it does not know yet (whom nothing is assigned to)."""
    person = hub_user_of(ctx)
    return None if person is None else person.pk


def preview(body: str, filename: str = "", caption: str = "") -> str:
    """The start of a message as the inbox list shows it: its text, else its caption or file name.

    A message with none of them (a photo, a location) leaves it empty: the inbox names it by its type
    (``last_message_kind``), in the reader's language.
    """
    return (body or caption or filename or "").strip()[:160]


def live_conversations() -> QuerySet:
    return Conversation.objects.filter(erased_at__isnull=True)


def page(rows: QuerySet, params: PageIn, convert=None) -> dict:
    """One page of ``rows`` (already ordered with the id as the tie-break) and how many there are."""
    found = list(rows[params.offset : params.offset + params.limit])
    return {
        "rows": [convert(row) for row in found] if convert else found,
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
