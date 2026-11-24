"""A card's consent: the one in force is the last fact per purpose and channel, and the history keeps every fact,
newest first (``consent_ledger.pg``)."""

from datetime import timedelta

from apps.customer.models import Consent
from apps.customer.schemas.consent import ConsentHistoryIn, ConsentStateIn

from .conftest import HUB_DB, NOW, card, run


pytestmark = HUB_DB


def test_the_consent_state_is_the_last_fact_per_purpose_and_channel():
    ana = card("Ana")
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="granted",
        occurred_at=NOW - timedelta(days=2),
    )
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="withdrawn",
        occurred_at=NOW - timedelta(days=1),
    )
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="granted",
        occurred_at=NOW,
        recorded_by="clara",
    )
    Consent.objects.create(
        customer=ana, channel="sms", state="withdrawn", occurred_at=NOW
    )
    Consent.objects.create(
        customer=ana,
        purpose="surveys",
        channel="email",
        state="granted",
        occurred_at=NOW,
    )
    state = run("customer.consent.state", ConsentStateIn(customer_id=ana.id))
    assert state.customer_id == ana.id
    assert [
        (row.purpose, row.channel, row.state, row.recorded_by) for row in state.rows
    ] == [
        ("marketing", "email", "granted", "clara"),
        ("marketing", "sms", "withdrawn", ""),
        ("surveys", "email", "granted", ""),
    ]


def test_the_consent_history_keeps_every_fact_newest_first():
    ana = card("Ana")
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="granted",
        notice_text="Yes to offers",
        occurred_at=NOW - timedelta(days=1),
    )
    Consent.objects.create(
        customer=ana,
        channel="email",
        state="withdrawn",
        reason="Too many",
        occurred_at=NOW,
    )
    page = run("customer.consent.history", ConsentHistoryIn(customer_id=ana.id))
    assert [(row.state, row.notice_text, row.reason) for row in page.rows] == [
        ("withdrawn", "", "Too many"),
        ("granted", "Yes to offers", ""),
    ]
    assert (
        run(
            "customer.consent.history",
            ConsentHistoryIn(customer_id=ana.id, search="offers"),
        ).total
        == 1
    )
