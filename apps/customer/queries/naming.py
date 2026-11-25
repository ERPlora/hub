"""The cards a customer named in words is, instead of her id: what ``find_customer`` reads for every app.

What is exactly her email, her phone or her name names her first. When nothing is, the words name the cards the
Customers list finds with them (``contact.searched``, CUSTOMER-F02), so «Lucía» or «Lucia Fernandez» is «Lucía
Fernández QA», as a person says it. Only whoever sees the customers' contact details finds a card by them."""

from uuid import UUID

from django.db.models import QuerySet
from live.context import OperationContext

from apps.customer.models import Customer
from apps.customer.phones import candidates
from apps.customer.search import normalize, search_term
from base import listing

from . import contact

#: The cards a refusal names when several fit, as Staff names its members.
MAX_NAMED = 5


def matching(ctx: OperationContext, reference: str, country: str) -> list[tuple[UUID, str]]:
    """The live cards ``reference`` names, as ``(id, name)`` by name, at most ``MAX_NAMED + 1``; a phone is read in
    ``country``."""
    cards = Customer.objects.live().order_by("name", "id")
    text = reference.strip()
    found = _exactly(ctx, cards, text, country)
    if found:
        return found
    term = search_term(text)
    if not term:
        return []
    return list(contact.searched(ctx, cards, term).values_list("id", "name")[: MAX_NAMED + 1])


def names(found: list[tuple[UUID, str]], language: str) -> str:
    """The names a refusal says of ``found``, the first ``MAX_NAMED``, joined as a screen in ``language`` joins them."""
    return listing.joined((name for _, name in found[:MAX_NAMED]), language)


def _exactly(ctx: OperationContext, cards: QuerySet, text: str, country: str) -> list[tuple[UUID, str]]:
    if "@" in text and contact.sees_contact(ctx):
        return list(cards.filter(email__iexact=text).values_list("id", "name")[: MAX_NAMED + 1])
    numbers = candidates(text, country) if contact.sees_contact(ctx) else []
    if numbers:
        return list(cards.filter(phone__in=numbers).values_list("id", "name")[: MAX_NAMED + 1])
    wanted = normalize(text)
    found = cards.filter(search_text__startswith=wanted).values_list("id", "name")
    return [(card_id, name) for card_id, name in found if normalize(name) == wanted][: MAX_NAMED + 1]
