"""A birthday or an anniversary of the card: ``YYYY-MM-DD``, or ``--MM-DD`` when the year is not known. The column stays a
``date`` (the code of before keeps reading and writing it while a deploy migrates), and a day without its year is kept
in 1604, as Apple's Contacts keep one: a leap year, so the 29th of February fits, that no customer was born in."""

from datetime import date

import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import DateField
from django.db.models.functions import Cast

from apps.customer.annual_dates import annual_date, stored_day
from apps.customer.models import Customer

from .conftest import HUB_DB


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("--03-14", "--03-14"),
        (" 1990-03-14 ", "1990-03-14"),
        (date(1990, 3, 14), "1990-03-14"),
        (date(1604, 2, 29), "--02-29"),
        ("", None),
        (None, None),
    ],
)
def test_a_day_reads_as_the_card_keeps_it(value, text):
    assert annual_date(value) == text


@pytest.mark.parametrize("value", ["--02-30", "1990-02-31", "03-14", "14/03", "0000-03-14", 314])
def test_a_day_that_does_not_exist_is_no_day(value):
    with pytest.raises(ValueError):
        annual_date(value)


def test_a_day_without_its_year_is_stored_in_1604():
    assert [stored_day(text) for text in ("--03-14", "--02-29", "1990-03-14", None)] == [
        date(1604, 3, 14),
        date(1604, 2, 29),
        date(1990, 3, 14),
        None,
    ]


@HUB_DB
def test_the_card_keeps_a_date_and_reads_back_the_day_as_written():
    lucia = Customer.objects.create(name="Lucía", birthday="--03-14", anniversary="2015-06-01")
    stored = Customer.objects.filter(pk=lucia.pk).values_list(
        Cast("birthday", DateField()), Cast("anniversary", DateField())
    )
    assert stored.get() == (date(1604, 3, 14), date(2015, 6, 1))
    lucia.refresh_from_db()
    assert (lucia.birthday, lucia.anniversary) == ("--03-14", "2015-06-01")
    assert Customer.objects.filter(birthday="--03-14").values_list("birthday", flat=True).get() == "--03-14"


@HUB_DB
def test_a_day_that_does_not_exist_is_refused_by_the_model():
    with pytest.raises(ValidationError) as refused:
        Customer(name="Lucía", birthday="--02-30").full_clean()
    assert list(refused.value.error_dict) == ["birthday"]


def test_the_admin_edits_the_day_as_text():
    field = Customer._meta.get_field("birthday").formfield()
    assert (type(field), field.max_length, field.required) == (forms.CharField, 10, False)
