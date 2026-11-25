"""Consent to be contacted: each grant and withdrawal is a fact (CUSTOMER-F14, F15)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import InvalidPayload, NotFound

from apps.customer import events
from apps.customer.models import Activity, Consent
from apps.customer.schemas.cards import CustomerPatchIn
from apps.customer.schemas.consent import ConsentGrantIn, ConsentWithdrawIn

from .conftest import HUB_DB, NOW, card, clear_outbox, invalid, outbox, run

pytestmark = HUB_DB


# customer.consent.grant / withdraw (CUSTOMER-F14, F15; consent_ledger.pg)


@pytest.mark.parametrize(
    ("channel", "address"),
    [
        ("email", "ana@example.com"),
        ("whatsapp", "+34600111222"),
        ("sms", "+34600111222"),
        ("postal", "Calle Mayor 1, 28001 Madrid, ES"),
    ],
)
def test_a_grant_is_a_fact_for_the_cards_address_on_that_channel(channel, address):
    ana = card(
        "Ana",
        email="ana@example.com",
        phone="+34600111222",
        address="Calle Mayor 1",
        postal_code="28001",
        city="Madrid",
        country="ES",
    )
    fact = run(
        "customer.consent.grant",
        ConsentGrantIn(
            customer_id=ana.id,
            channel=channel,
            notice_text="I want offers.",
            notice_version="v1",
        ),
        "hub_employee",
        actor="clara",
    )
    assert (
        fact.state,
        fact.channel,
        fact.contact_point,
        fact.recorded_by,
        fact.purpose,
        fact.source,
    ) == (
        "granted",
        channel,
        address,
        "clara",
        "marketing",
        "counter",
    )
    assert fact.notice_text == "I want offers."
    entry = Activity.objects.get()
    assert (entry.kind, entry.text, entry.related_id) == (
        "consent_granted",
        "I want offers.",
        str(fact.id),
    )
    assert outbox() == [
        (
            events.CONSENT_GRANTED,
            {"id": str(fact.id), "customer_id": str(ana.id), "channel": channel},
        )
    ]


def test_grant_withdraw_and_grant_again_leave_three_facts_and_the_last_one_rules():
    ana = card("Ana", email="ana@example.com")
    yesterday = timezone.now() - timedelta(days=1)
    run(
        "customer.consent.grant",
        ConsentGrantIn(
            customer_id=ana.id,
            channel="email",
            notice_text="Yes",
            occurred_at=yesterday,
        ),
    )
    withdrawn = run(
        "customer.consent.withdraw",
        ConsentWithdrawIn(customer_id=ana.id, channel="email", reason="Too many"),
    )
    assert (withdrawn.state, withdrawn.reason, withdrawn.notice_text) == (
        "withdrawn",
        "Too many",
        "",
    )
    # The address is the card's at that moment, never one the caller sends (WORKBOOK F14).
    run("customer.customer.update", CustomerPatchIn(id=ana.id, email="new@example.com"))
    clear_outbox()
    run(
        "customer.consent.grant",
        ConsentGrantIn(customer_id=ana.id, channel="email", notice_text="Yes again"),
    )
    assert list(ana.consents.values_list("state", "contact_point")) == [
        ("granted", "new@example.com"),
        ("withdrawn", "ana@example.com"),
        ("granted", "ana@example.com"),
    ]
    assert [name for name, _ in outbox()] == [events.CONSENT_GRANTED]
    assert list(ana.activity.values_list("kind", flat=True)) == [
        "consent_granted",
        "consent_withdrawn",
        "consent_granted",
    ]


def test_a_consent_said_in_the_future_or_for_a_card_that_is_gone_is_refused():
    ana = card("Ana")
    with pytest.raises(InvalidPayload) as excinfo:
        run(
            "customer.consent.grant",
            ConsentGrantIn(
                customer_id=ana.id,
                channel="sms",
                notice_text="Yes",
                occurred_at=timezone.now() + timedelta(days=1),
            ),
        )
    assert invalid(excinfo.value) == (
        422,
        "customer.date_in_future",
        {"occurred_at": "This date is in the future."},
    )
    with pytest.raises(NotFound):
        run(
            "customer.consent.withdraw",
            ConsentWithdrawIn(
                customer_id=card("Gone", deleted_at=NOW).id, channel="sms"
            ),
        )
    assert not Consent.objects.exists()
