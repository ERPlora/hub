"""Models of the cash register app: what the database itself refuses, and the helpers the models carry."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cash_register.models import (
    Count,
    Movement,
    Register,
    Session,
    SessionCounter,
    Settings,
    session_number,
)

pytestmark = pytest.mark.django_db


def refused(make):
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


def a_session(**more) -> Session:
    values = {
        "number": "S-261014-0001",
        "business_day": dt.date(2026, 10, 14),
        "sequence": 1,
        "opening_balance": 10000,
    }
    return Session.objects.create(**(values | more))


def closed(**more) -> Session:
    values = {
        "status": Session.Status.CLOSED,
        "closed_at": timezone.now(),
        "expected_balance": 10000,
        "closing_balance": 9950,
        "difference": -50,
    }
    return a_session(**(values | more))


def test_the_session_number_is_the_business_day_and_a_counter_of_at_least_four_digits():
    day = dt.date(2026, 10, 4)
    assert session_number(day, 7) == "S-261004-0007"
    assert session_number(day, 10000) == "S-261004-10000"


def test_a_session_number_is_unique():
    closed()
    refused(lambda: a_session())


def test_only_one_session_is_open_at_a_time():
    a_session()
    refused(lambda: a_session(number="S-261014-0002", sequence=2))


def test_closed_sessions_do_not_compete_for_the_open_slot():
    closed()
    closed(number="S-261014-0002", sequence=2)
    a_session(number="S-261014-0003", sequence=3)
    assert Session.objects.filter(status="open").count() == 1


def test_amounts_of_a_session_are_never_negative():
    refused(lambda: a_session(opening_balance=-1))
    refused(lambda: closed(closing_balance=-1, difference=-10001))
    # The expected may go below zero (a cash refund, or a cash-out the settings allow): it is not.
    closed(expected_balance=-100, closing_balance=0, difference=100)


def test_an_open_session_has_no_close_and_a_closed_one_has_its_expected():
    refused(lambda: a_session(closed_at=timezone.now()))
    refused(lambda: a_session(expected_balance=100))
    refused(lambda: closed(closed_at=None))
    refused(lambda: closed(expected_balance=None))


def test_the_difference_is_counted_minus_expected():
    refused(lambda: closed(difference=50))
    # Closed by itself (auto-close): nobody counted, so no difference either.
    closed(closing_balance=None, difference=None, auto_closed=True)


def test_one_counter_row_per_business_day():
    SessionCounter.objects.create(day=dt.date(2026, 10, 14))
    refused(lambda: SessionCounter.objects.create(day=dt.date(2026, 10, 14)))


def test_a_register_name_is_unique_whatever_the_case():
    Register.objects.create(name="Bar")
    refused(lambda: Register.objects.create(name="bar"))
    refused(lambda: Register.objects.create(name=""))


def test_settings_are_one_row():
    Settings.objects.create()
    refused(lambda: Settings.objects.create())


def test_the_factory_settings():
    settings = Settings()
    assert settings.enable_cash_register is True
    assert settings.require_opening_balance is False
    assert settings.require_closing_balance is True
    assert settings.allow_negative_balance is False
    assert settings.require_blind_count is False
    assert settings.auto_close_enabled is False
    assert settings.auto_close_time == dt.time(4, 0)


def test_a_new_row_without_an_hour_closes_at_four():
    settings = Settings.objects.create()
    settings.refresh_from_db()
    assert settings.auto_close_time == dt.time(4, 0)


@pytest.mark.parametrize(
    "instant",
    ["2026-10-25T03:59:55+00:00", "2026-10-25T04:00:05+00:00", "2026-10-25T12:00:00+00:00"],
)
def test_the_auto_close_default_raises_no_check_warning_at_any_hour(monkeypatch, instant):
    # Django warns fields.W161 when a fixed time default falls within 10 s of the current UTC time.
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime.fromisoformat(instant))
    assert Settings._meta.get_field("auto_close_time").check() == []


def test_the_auto_close_time_is_a_whole_hour():
    refused(lambda: Settings.objects.create(auto_close_time=dt.time(4, 30)))


def test_a_manual_movement_belongs_to_a_session_and_moves_money():
    session = a_session()
    Movement.objects.create(session=session, type="in", amount=500)
    refused(lambda: Movement.objects.create(type="out", amount=500))
    refused(lambda: Movement.objects.create(session=session, type="out", amount=0))
    refused(lambda: Movement.objects.create(session=session, type="in", amount=-5))


def test_the_sign_comes_from_the_type():
    assert Movement(type="in", amount=500).signed_amount == 500
    assert Movement(type="sale", amount=500).signed_amount == 500
    assert Movement(type="out", amount=500).signed_amount == -500
    assert Movement(type="refund", amount=500).signed_amount == -500
    assert Movement(type="void", amount=500).signed_amount == -500


def test_a_count_belongs_to_a_session_and_is_never_negative():
    session = a_session()
    Count.objects.create(session=session, type="closing", total=0)
    refused(lambda: Count.objects.create(session=session, type="closing", total=-1))
