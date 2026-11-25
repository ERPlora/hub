"""The words the book names a record by (a read by id's ``label``): as the assistant's card says a day and a time
(base/assistant/cards.py: CLDR's medium day and short time, as the screens' formatters), in the caller's language:
«Ana García · 15 oct 2026 · 21:00».
"""

import datetime as dt

from babel.dates import format_date, format_time
from live.context import OperationContext

from apps.customer.queries.contact import sees_contact
from apps.reservation.models import Reservation, WaitlistEntry
from base.business import babel_locale


def _said_day(day: dt.date, language: str) -> str:
    return format_date(day, "medium", locale=babel_locale(language))


def _said_time(at: dt.time, language: str) -> str:
    return format_time(at.replace(tzinfo=None), "short", locale=babel_locale(language))


def _said_hours(start: dt.time, end: dt.time, language: str) -> str:
    return f"{_said_time(start, language)}–{_said_time(end, language)}"


def _named(*parts: str) -> str:
    return " · ".join(part for part in parts if part)


def _who(ctx: OperationContext, row: Reservation | WaitlistEntry) -> str:
    """The guest as the dialogs say her: her name, else her phone to whoever sees it; nothing once erased."""
    return row.guest_name or (row.guest_phone if sees_contact(ctx) else "")
