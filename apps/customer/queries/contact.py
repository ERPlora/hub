"""What a read of Customers looks into, by whether the caller sees the customers' email and phone (BASE-F119).

Whoever does not see them cannot find a card by them either: a search, or a card named by its phone or email, would
tell whose they are."""

from django.db.models import QuerySet
from live.context import OperationContext

from base.sensitive import VIEW_CUSTOMER_CONTACT


def sees_contact(ctx: OperationContext) -> bool:
    return ctx.has(VIEW_CUSTOMER_CONTACT)


def searched(ctx: OperationContext, cards: QuerySet, term: str) -> QuerySet:
    """The ``cards`` whose name, tax id or company holds ``term`` (already normalized), and their email or phone for
    whoever sees them."""
    column = "search_text" if sees_contact(ctx) else "search_text_without_contact"
    return cards.filter(**{f"{column}__contains": term})
