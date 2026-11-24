"""A card's health data (CUSTOMER-F32): for the screen only, nothing without its permission, the last health
decision with its data, never in the card, the list or the export, and its permission in the consent reads."""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import NotFound
from live.operations import INTERNAL, get

from apps.customer.models import Consent, Customer, HealthRecord
from apps.customer.schemas.cards import CustomerListIn
from apps.customer.schemas.consent import ConsentHistoryIn, ConsentStateIn
from apps.customer.schemas.exports import CustomerExportIn
from apps.customer.schemas.fields import CustomerRefIn
from apps.customer.schemas.health import HealthDetailIn, HealthOut

from .conftest import HUB_DB, run


pytestmark = HUB_DB


def test_the_health_query_is_for_the_screen_only():
    op = get("customer.health.detail")
    assert (op.kind, op.permission, op.input, op.output) == (
        "query",
        "customer.view",
        HealthDetailIn,
        HealthOut,
    )
    assert (op.ai, op.expose_api) == (INTERNAL, False)


def test_without_permission_the_health_block_holds_nothing():
    ana = Customer.objects.create(name="Ana")
    block = run(
        "customer.health.detail", HealthDetailIn(customer_id=ana.id), "hub_employee"
    )
    assert (
        block.customer_id,
        block.consent,
        block.consent_at,
        block.allergies,
        block.sensitivity_test_on,
        block.sensitivity_test_result,
        block.updated_at,
    ) == (ana.id, "none", None, "", None, "", None)


def test_the_health_block_is_the_last_health_decision_and_its_data():
    ana = Customer.objects.create(name="Ana")
    said = timezone.now() - timedelta(days=1)
    Consent.objects.create(
        customer=ana,
        purpose="health",
        channel="",
        state="granted",
        notice_text="I let this business keep my allergies.",
        recorded_by="clara",
        occurred_at=said,
    )
    # A marketing decision is not a health permission.
    Consent.objects.create(
        customer=ana, purpose="marketing", channel="email", state="withdrawn"
    )
    HealthRecord.objects.create(
        customer=ana,
        allergies="PPD",
        sensitivity_test_on=timezone.localdate(),
        sensitivity_test_result="negative",
        updated_by="clara",
    )
    block = run("customer.health.detail", HealthDetailIn(customer="Ana"))
    assert (
        block.consent,
        block.consent_at,
        block.consent_by,
        block.notice_text,
        block.allergies,
        block.sensitivity_test_on,
        block.sensitivity_test_result,
        block.updated_by,
    ) == (
        "granted",
        said,
        "clara",
        "I let this business keep my allergies.",
        "PPD",
        timezone.localdate(),
        "negative",
        "clara",
    )


def test_the_health_data_stays_out_of_the_card_the_list_and_the_export():
    ana = Customer.objects.create(name="Ana")
    HealthRecord.objects.create(customer=ana, allergies="PPD-allergy-marker")
    detail = run("customer.customer.detail", CustomerRefIn(id=ana.id))
    page = run("customer.customer.list", CustomerListIn(search="PPD-allergy-marker"))
    export = run("customer.customer.export", CustomerExportIn())
    assert "PPD-allergy-marker" not in detail.model_dump_json()
    assert page.total == 0
    assert "PPD-allergy-marker" not in export.csv


def test_the_health_block_of_a_card_that_is_gone_is_not_found():
    ana = Customer.objects.create(name="Ana", deleted_at=timezone.now())
    with pytest.raises(NotFound):
        run("customer.health.detail", HealthDetailIn(customer_id=ana.id))


def test_the_consent_history_and_state_carry_the_health_permission_without_channel():
    ana = Customer.objects.create(name="Ana")
    Consent.objects.create(
        customer=ana, purpose="health", channel="", state="granted", notice_text="Yes."
    )
    history = run("customer.consent.history", ConsentHistoryIn(customer_id=ana.id))
    state = run("customer.consent.state", ConsentStateIn(customer_id=ana.id))
    assert [(row.purpose, row.channel) for row in history.rows] == [("health", "")]
    assert [(row.purpose, row.channel, row.state) for row in state.rows] == [
        ("health", "", "granted")
    ]
