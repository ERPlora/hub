"""The bell's notice of a plan with an unpaid invoice (``base.bell.counters``, key ``base.payment_pending``).

erplora.com's photo of the business says ``past_due`` while its invoice waits inside the 7 days of grace, and
``suspends_on`` is the instant erplora.com suspends it. Whoever runs the business sees one notice with that deadline and
a button to the business's unpaid invoices on erplora.com; nobody else does. The Hub never asks erplora.com and never
counts the 7 days itself: without ``suspends_on`` the notice has no date.
"""

import datetime as dt
import logging

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import override
from live.context import OperationContext, Scope
from live.operations import get

from base.models import Membership
from base.permissions import access_for
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from control.models.hubs import Hub

pytestmark = [pytest.mark.django_db(databases=hubs.HUB_DATABASES)]

NOW = dt.datetime(2026, 3, 15, 12, 0, tzinfo=dt.UTC)
KEY = "base.payment_pending"


@pytest.fixture(autouse=True)
def the_clock(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)


def photo(hub, **state) -> None:
    Hub.objects.filter(pk=hub.pk).update(state=state, timezone="Europe/Madrid")


def bell_of(hub, role="hub_owner", language="en") -> dict:
    user, _ = get_user_model().objects.get_or_create(username=f"saas:bell-{role}-{hub.slug}")
    scope = Scope("host", hub.slug)
    op = get("base.bell.counters")
    with use_hub(hub), override(language):
        Membership.objects.get_or_create(user=user, host=hub.slug, defaults={"role": role})
        ctx = OperationContext(scope=scope, actor=user, permissions=access_for(user, scope), language=language)
        return op(ctx, op.input()).model_dump(mode="json")


def payment_rows(hub, **kwargs) -> list[dict]:
    return [row for row in bell_of(hub, **kwargs)["counters"] if row["key"] == KEY]


def billing_of(hub) -> str:
    return f"{settings.SAAS_URL.rstrip('/')}/dashboard/billing/invoices?business={hub.id}&status=open"


def test_a_payment_pending_is_one_notice_with_its_deadline_and_a_button_to_the_invoices(hub_a):
    photo(hub_a, status="past_due", suspends_on="2026-03-18T10:30:00+00:00")

    assert payment_rows(hub_a) == [
        {
            "key": KEY,
            "app": "base",
            "count": 1,
            "route": billing_of(hub_a),
            "label": "Unpaid invoice",
            "icon": "ion:card-outline",
            "severity": "danger",
            "title": "Your ERPlora plan has an unpaid invoice",
            "body": "Pay it on erplora.com: if it is not paid by March 18, 2026, the business is suspended. "
            "Nothing is deleted.",
            "action_label": "Pay on erplora.com",
            "due": "2026-03-18T10:30:00Z",
        }
    ]


def test_the_deadline_is_the_day_on_the_business_s_clock(hub_a):
    photo(hub_a, status="past_due", suspends_on="2026-03-17T23:30:00+00:00")

    assert "by March 18, 2026," in payment_rows(hub_a)[0]["body"]


def test_it_is_said_in_the_person_s_language(hub_a):
    photo(hub_a, status="past_due", suspends_on="2026-03-18T10:30:00+00:00")

    [row] = payment_rows(hub_a, language="es")
    assert (row["label"], row["title"], row["action_label"]) == (
        "Factura sin pagar",
        "Tu plan de ERPlora tiene una factura sin pagar",
        "Pagar en erplora.com",
    )
    assert row["body"] == (
        "Págala en erplora.com: si no se paga antes del 18 de marzo de 2026, el negocio se suspende. No se borra nada."
    )


def test_past_its_deadline_and_not_yet_suspended_it_says_the_deadline_went_by(hub_a):
    photo(hub_a, status="past_due", suspends_on="2026-03-15T11:59:00+00:00")

    [row] = payment_rows(hub_a)
    assert row["due"] == "2026-03-15T11:59:00Z"
    assert row["body"] == (
        "Pay it on erplora.com: its deadline was March 15, 2026 and the business may be suspended at any moment. "
        "Nothing is deleted."
    )
    [row] = payment_rows(hub_a, language="es")
    assert row["body"] == (
        "Págala en erplora.com: su plazo terminó el 15 de marzo de 2026 y el negocio se puede suspender en cualquier "
        "momento. No se borra nada."
    )


def test_without_a_deadline_in_the_photo_the_notice_has_no_date_and_none_is_counted(hub_a):
    photo(hub_a, status="past_due")

    [row] = payment_rows(hub_a)
    assert row["due"] is None
    assert row["body"] == "Pay it on erplora.com: if it is not paid soon, the business is suspended. Nothing is deleted."
    [row] = payment_rows(hub_a, language="es")
    assert row["body"] == "Págala en erplora.com: si no se paga pronto, el negocio se suspende. No se borra nada."


@pytest.mark.parametrize("deadline", ["next week", 1773836400, "2026-03-18T10:30:00"], ids=["text", "number", "naive"])
def test_a_deadline_that_is_no_instant_is_told_as_none(hub_a, deadline, caplog):
    photo(hub_a, status="past_due", suspends_on=deadline)

    with caplog.at_level(logging.WARNING, logger="base.unpaid_plan"):
        [row] = payment_rows(hub_a)
    assert row["due"] is None
    assert "soon" in row["body"]
    assert "base.unpaid_plan_bad_deadline" in caplog.text


@pytest.mark.parametrize(
    "state",
    [{"status": "active"}, {"status": "active", "suspends_on": "2026-03-18T10:30:00+00:00"}, {}],
    ids=["paid", "paid with a stale deadline", "no photo"],
)
def test_with_nothing_pending_there_is_no_notice(hub_a, state):
    photo(hub_a, **state)

    assert payment_rows(hub_a) == []


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_only_who_runs_the_business_sees_it(hub_a, role):
    photo(hub_a, status="past_due", suspends_on="2026-03-18T10:30:00+00:00")

    assert payment_rows(hub_a, role=role) == []


def test_a_business_sees_only_its_own_payment(hub_a, hub_b):
    photo(hub_b, status="past_due", suspends_on="2026-03-18T10:30:00+00:00")

    assert payment_rows(hub_a) == []
    assert [row["route"] for row in payment_rows(hub_b)] == [billing_of(hub_b)]


@pytest.fixture
def apps_ask(monkeypatch):
    """What the apps on ask of the bell's clock (``base.home.bell_counters.bell_refresh_every``), fixed for the test."""

    def ask(seconds):
        monkeypatch.setattr("base.home.bell_counters.bell_refresh_every", lambda ctx, configs: seconds)

    return ask


@pytest.mark.parametrize(
    ("deadline", "every"),
    [
        ("2026-03-15T12:10:00+00:00", 600),
        ("2026-03-15T12:00:05+00:00", 30),
        ("2026-03-18T10:30:00+00:00", 86400),
    ],
    ids=["at the deadline", "never sooner than half a minute", "never later than a day"],
)
def test_the_bell_reads_itself_again_when_the_deadline_comes(hub_a, apps_ask, deadline, every):
    apps_ask(None)
    photo(hub_a, status="past_due", suspends_on=deadline)

    assert bell_of(hub_a)["refresh_every"] == every


@pytest.mark.parametrize(("asked", "every"), [(300, 300), (900, 600)], ids=["an app asks sooner", "an app asks later"])
def test_the_sooner_of_the_deadline_and_what_an_app_asks_wins(hub_a, apps_ask, asked, every):
    apps_ask(asked)
    photo(hub_a, status="past_due", suspends_on="2026-03-15T12:10:00+00:00")

    assert bell_of(hub_a)["refresh_every"] == every


@pytest.mark.parametrize("asked", [None, 300], ids=["no app asks", "an app asks"])
@pytest.mark.parametrize(
    "state",
    [
        {"status": "past_due", "suspends_on": "2026-03-15T11:00:00+00:00"},
        {"status": "past_due"},
        {"status": "active", "suspends_on": "2026-03-15T12:10:00+00:00"},
    ],
    ids=["deadline gone by", "no deadline", "paid"],
)
def test_with_no_deadline_ahead_the_bell_reads_itself_again_only_as_the_apps_ask(hub_a, apps_ask, state, asked):
    apps_ask(asked)
    photo(hub_a, **state)

    assert bell_of(hub_a)["refresh_every"] == asked


def test_who_does_not_run_the_business_gets_no_reading_for_its_deadline(hub_a, apps_ask):
    apps_ask(None)
    photo(hub_a, status="past_due", suspends_on="2026-03-15T12:10:00+00:00")

    assert bell_of(hub_a, role="hub_employee")["refresh_every"] is None
