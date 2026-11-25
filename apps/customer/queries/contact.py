"""What a read of Customers looks into, by whether the caller sees the customers' email and phone (BASE-F119).

Whoever does not see them cannot find a card by them either: a search, or a card named by its phone or email, would
tell whose they are."""

from django.db.models import Q, QuerySet
from live.context import OperationContext

from base.sensitive import VIEW_CUSTOMER_CONTACT


def sees_contact(ctx: OperationContext) -> bool:
    return ctx.has(VIEW_CUSTOMER_CONTACT)


def holds(ctx: OperationContext, term: str, through: str = "") -> Q:
    """The cards whose name, tax id or company holds ``term`` (already normalized), and their email or phone for
    whoever sees them; ``through`` a relation to a card («customer__»), the rows joined to such a card."""
    column = "search_text" if sees_contact(ctx) else "search_text_without_contact"
    return Q(**{f"{through}{column}__contains": term})


def searched(ctx: OperationContext, cards: QuerySet, term: str) -> QuerySet:
    return cards.filter(holds(ctx, term))
