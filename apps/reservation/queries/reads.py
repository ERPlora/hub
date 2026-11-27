"""What the book's reads share: a blocked date's row, a page of a list, and finding a guest as a person says her."""

import datetime as dt
import re

from django.db.models import Q
from live.context import OperationContext

from apps.customer.queries.contact import sees_contact
from apps.reservation.models import BlockedDate
from base.text_search import contains_text

MAX_CANDIDATES = 5
DIGITS = re.compile(r"\D")


def blocked_out(block: BlockedDate) -> dict:
    return {
        "id": block.pk,
        "date": block.date,
        "reason": block.reason,
        "is_full_day": block.is_full_day,
        "blocked_from": block.blocked_from,
        "blocked_until": block.blocked_until,
    }


def _page(queryset, params, row) -> dict:
    total = queryset.count()
    window = queryset[params.offset : params.offset + params.limit]
    return {
        "rows": [row(item) for item in window],
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


def _phone_matches(said: str) -> Q:
    """Part of the guest's phone, as typed or by its digits alone (spaces, dashes, a prefix)."""
    text = said.strip()
    match = contains_text(text, "guest_phone")
    digits = DIGITS.sub("", text)
    if len(digits) >= 3:
        match |= contains_text(digits, "guest_phone")
    return match


def _guest_matches(ctx: OperationContext, said: str) -> Q:
    """The guest by part of the name and, for whoever sees the customers' contact details, of the email or the phone
    (however typed: spaces, prefix): a search by them would tell whose they are."""
    text = said.strip()
    named = contains_text(text, "guest_name")
    return (named | contains_text(text, "guest_email") | _phone_matches(text)) if sees_contact(ctx) else named


def _when(day: dt.date, at: dt.time) -> str:
    return f"{day:%Y-%m-%d} {at:%H:%M}"
