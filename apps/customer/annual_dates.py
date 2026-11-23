"""A birthday or an anniversary of the card: ``YYYY-MM-DD``, or ``--MM-DD`` when the year is not known (as vCard writes
a birthday without its year: ``--03-14`` is the 14th of March).

The column stays a ``date``, so the code of before keeps reading and writing it while a deploy migrates or after a
rollback. A day without its year is kept in ``YEARLESS``, as Apple's Contacts keep one, and ``AnnualDateField`` turns
it back into ``--MM-DD`` on every read."""

import re
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

#: A leap year, so the 29th of February fits, that no customer was born in.
YEARLESS = 1604

_DAY = re.compile(r"(\d{4}|-)-(\d{2})-(\d{2})")


def annual_date(value: object) -> str | None:
    """``value`` (a text as the card keeps it, or a ``date``) as the card keeps it; none is ``None``. ``ValueError`` if
    it is no day: a text in another form or a day that does not exist (``--02-30``)."""
    if isinstance(value, date):
        return f"--{value:%m-%d}" if value.year == YEARLESS else value.isoformat()
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    day = _DAY.fullmatch(value.strip()) if isinstance(value, str) else None
    if day is None:
        raise ValueError(f"{value!r} is no day")
    date(YEARLESS if day[1] == "-" else int(day[1]), int(day[2]), int(day[3]))
    return day[0]


def stored_day(text: str | None) -> date | None:
    """The ``date`` the column keeps for ``text`` (``annual_date``'s form)."""
    if text is None:
        return None
    year, month, day = text.removeprefix("-").split("-")
    return date(int(year) if year else YEARLESS, int(month), int(day))


class AnnualDateField(models.DateField):
    """A ``date`` column whose value on the model is the text of ``annual_date``."""

    def from_db_value(self, value, expression, connection):
        return annual_date(value)

    def to_python(self, value):
        try:
            return annual_date(value)
        except ValueError:
            raise ValidationError(
                self.error_messages["invalid_date"], code="invalid_date", params={"value": value}
            ) from None

    def get_prep_value(self, value):
        return stored_day(self.to_python(value))

    def value_to_string(self, obj):
        return self.value_from_object(obj) or ""

    def formfield(self, **kwargs):
        return models.Field.formfield(self, **{"form_class": forms.CharField, "max_length": 10, **kwargs})
