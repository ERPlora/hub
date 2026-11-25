"""A card's health data, kept only with the customer's explicit permission (CUSTOMER-F32)."""

from datetime import date, timedelta

import pytest
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import INTERNAL, get

from apps.customer import events
from apps.customer.models import Activity, Consent, HealthRecord
from apps.customer.schemas.erasing import EraseIn
from apps.customer.schemas.health import HealthGrantIn, HealthIn, HealthOut, HealthWithdrawIn
from apps.customer.schemas.merging import MergeIn
from apps.customer.services.health import HEALTH_TEST_DATE_MISSING
from apps.customer.services.writes import DATE_IN_FUTURE

from .conftest import HUB_DB, HEALTH_WORDS, card, clear_outbox, grant_health, invalid, outbox, run

pytestmark = HUB_DB


@pytest.mark.parametrize(
    ("name", "input"),
    [
        ("customer.health.grant", HealthGrantIn),
        ("customer.health.withdraw", HealthWithdrawIn),
        ("customer.health.update", HealthIn),
    ],
)
def test_health_declarations_keep_the_data_away_from_the_assistant_and_the_api_keys(
    name, input
):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output) == (
        "command",
        "customer.manage",
        input,
        HealthOut,
    )
    assert (op.ai, op.expose_api) == (INTERNAL, False)


def test_health_data_is_refused_until_the_permission_is_recorded():
    ana = card("Ana")
    with pytest.raises(Conflict) as refused:
        run(
            "customer.health.update",
            HealthIn(customer_id=ana.id, allergies="PPD"),
            "hub_employee",
        )
    assert (refused.value.status, refused.value.code) == (
        409,
        "customer.health_consent_required",
    )
    assert (HealthRecord.objects.count(), outbox()) == (0, [])


def test_the_permission_is_a_health_fact_with_its_words_and_then_the_data_is_kept():
    ana = card("Ana", phone="+34600111222", email="ana@example.com")
    block = grant_health(ana)
    fact = Consent.objects.get()
    assert (
        fact.purpose,
        fact.channel,
        fact.state,
        fact.contact_point,
        fact.notice_text,
        fact.notice_version,
        fact.recorded_by,
    ) == ("health", "", "granted", "", HEALTH_WORDS, "v1", "clara")
    assert (block.consent, block.consent_by, block.notice_text, block.allergies) == (
        "granted",
        "clara",
        HEALTH_WORDS,
        "",
    )
    granted = Activity.objects.get()
    assert (granted.kind, granted.text, granted.related_id) == (
        "health_consent_granted",
        HEALTH_WORDS,
        str(fact.id),
    )
    assert outbox() == [
        (
            events.HEALTH_CONSENT_GRANTED,
            {"id": str(fact.id), "customer_id": str(ana.id)},
        )
    ]
    clear_outbox()
    tested = timezone.localdate() - timedelta(days=2)
    block = run(
        "customer.health.update",
        HealthIn(
            customer="Ana",
            allergies="PPD (hair dye)",
            sensitivity_test_on=tested,
            sensitivity_test_result="negative",
        ),
        "hub_employee",
        actor="clara",
    )
    record = HealthRecord.objects.get()
    assert (
        record.customer_id,
        record.allergies,
        record.sensitivity_test_on,
        record.sensitivity_test_result,
        record.updated_by,
    ) == (ana.id, "PPD (hair dye)", tested, "negative", "clara")
    assert (
        block.allergies,
        block.sensitivity_test_on,
        block.sensitivity_test_result,
    ) == (
        "PPD (hair dye)",
        tested,
        "negative",
    )
    # The timeline says it changed, never what: the health data lives only in its block.
    updated = Activity.objects.get(kind="health_updated")
    assert (updated.text, updated.data, updated.related_id) == ("", {}, str(record.id))
    assert outbox() == [
        (events.HEALTH_UPDATED, {"id": str(record.id), "customer_id": str(ana.id)})
    ]
    clear_outbox()
    # Saving the same data again changes nothing and tells nobody.
    run(
        "customer.health.update",
        HealthIn(
            customer_id=ana.id,
            allergies="PPD (hair dye)",
            sensitivity_test_on=tested,
            sensitivity_test_result="negative",
        ),
    )
    assert (outbox(), Activity.objects.filter(kind="health_updated").count()) == ([], 1)


def test_withdrawing_the_permission_erases_the_health_data_at_once():
    ana = card("Ana")
    grant_health(ana)
    run("customer.health.update", HealthIn(customer_id=ana.id, allergies="Latex"))
    clear_outbox()
    block = run(
        "customer.health.withdraw",
        HealthWithdrawIn(customer_id=ana.id, reason="Asked at the counter"),
        "hub_employee",
        actor="clara",
    )
    assert (block.consent, block.allergies, HealthRecord.objects.count()) == (
        "withdrawn",
        "",
        0,
    )
    fact = Consent.objects.get(state="withdrawn")
    assert (fact.purpose, fact.channel, fact.reason, fact.recorded_by) == (
        "health",
        "",
        "Asked at the counter",
        "clara",
    )
    assert Activity.objects.filter(kind="health_consent_withdrawn").count() == 1
    assert outbox() == [
        (
            events.HEALTH_CONSENT_WITHDRAWN,
            {"id": str(fact.id), "customer_id": str(ana.id)},
        )
    ]
    with pytest.raises(Conflict):
        run("customer.health.update", HealthIn(customer_id=ana.id, allergies="Latex"))


def test_a_test_in_the_future_or_a_result_without_its_date_saves_nothing():
    ana = card("Ana")
    grant_health(ana)
    clear_outbox()
    for data, message in (
        (
            {"sensitivity_test_on": timezone.localdate() + timedelta(days=1)},
            DATE_IN_FUTURE,
        ),
        ({"sensitivity_test_result": "positive"}, HEALTH_TEST_DATE_MISSING),
    ):
        with pytest.raises(InvalidPayload) as refused:
            run("customer.health.update", HealthIn(customer_id=ana.id, **data))
        assert invalid(refused.value)[0] == 422
        assert refused.value.fields == {"sensitivity_test_on": message}
    assert (HealthRecord.objects.count(), outbox()) == (0, [])


def test_a_test_is_in_the_future_only_past_the_businesss_midnight(night_elsewhere):
    ana = card("Ana")
    grant_health(ana)
    with pytest.raises(InvalidPayload) as refused:
        run("customer.health.update", HealthIn(customer_id=ana.id, sensitivity_test_on=date(2026, 11, 3)))
    assert refused.value.code == "customer.date_in_future"
    record = run("customer.health.update", HealthIn(customer_id=ana.id, sensitivity_test_on=date(2026, 11, 2)))
    assert record.sensitivity_test_on == date(2026, 11, 2)


def test_health_on_a_card_that_is_gone_or_by_who_does_not_manage_cards_is_refused():
    ana = card("Ana", deleted_at=timezone.now())
    for name, data in (
        (
            "customer.health.grant",
            HealthGrantIn(customer_id=ana.id, notice_text=HEALTH_WORDS),
        ),
        ("customer.health.withdraw", HealthWithdrawIn(customer_id=ana.id)),
        ("customer.health.update", HealthIn(customer_id=ana.id, allergies="PPD")),
    ):
        with pytest.raises(NotFound):
            run(name, data)
    bea = card("Bea")
    with pytest.raises(PermissionDenied):
        run(
            "customer.health.grant",
            HealthGrantIn(customer_id=bea.id, notice_text=HEALTH_WORDS),
            "hub_guest",
        )
    assert (Consent.objects.count(), outbox()) == (0, [])


def test_erasing_a_card_erases_its_health_data():
    ana = card("Ana")
    grant_health(ana)
    run("customer.health.update", HealthIn(customer_id=ana.id, allergies="PPD"))
    run("customer.customer.erase", EraseIn(id=ana.id))
    assert HealthRecord.objects.count() == 0
    assert Consent.objects.filter(customer=ana, purpose="health").exists()


def test_a_merge_brings_the_duplicates_health_data_while_the_permission_holds():
    survivor, absorbed = card("Ana"), card("Ana G.")
    grant_health(absorbed)
    run(
        "customer.health.update",
        HealthIn(
            customer_id=absorbed.id,
            allergies="PPD",
            sensitivity_test_on=timezone.localdate(),
            sensitivity_test_result="negative",
        ),
    )
    run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))
    record = HealthRecord.objects.get()
    assert (record.customer_id, record.allergies) == (survivor.id, "PPD")
    # The survivor's own data stays; only its empty fields are filled.
    other = card("Ana García")
    grant_health(other)
    run("customer.health.update", HealthIn(customer_id=other.id, allergies="Latex"))
    run("customer.customer.merge", MergeIn(id=other.id, absorbed_id=survivor.id))
    kept = HealthRecord.objects.get()
    assert (
        kept.customer_id,
        kept.allergies,
        kept.sensitivity_test_on,
        kept.sensitivity_test_result,
    ) == (other.id, "Latex", timezone.localdate(), "negative")


def test_a_merge_fills_the_survivors_empty_allergies_with_the_duplicates():
    survivor, absorbed = card("Ana"), card("Ana G.")
    for one in (survivor, absorbed):
        grant_health(one)
    today = timezone.localdate()
    run(
        "customer.health.update",
        HealthIn(
            customer_id=survivor.id,
            sensitivity_test_on=today,
            sensitivity_test_result="negative",
        ),
    )
    run("customer.health.update", HealthIn(customer_id=absorbed.id, allergies="PPD"))
    run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))
    kept = HealthRecord.objects.get()
    assert (kept.customer_id, kept.allergies, kept.sensitivity_test_on) == (
        survivor.id,
        "PPD",
        today,
    )


def test_a_merge_drops_the_health_data_when_the_last_decision_withdrew_the_permission():
    survivor, absorbed = card("Ana"), card("Ana G.")
    grant_health(absorbed)
    run("customer.health.update", HealthIn(customer_id=absorbed.id, allergies="PPD"))
    # The survivor said no after the duplicate said yes: the last decision rules.
    grant_health(survivor)
    run("customer.health.withdraw", HealthWithdrawIn(customer_id=survivor.id))
    run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))
    assert HealthRecord.objects.count() == 0
