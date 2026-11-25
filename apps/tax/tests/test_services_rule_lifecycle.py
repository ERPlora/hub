"""What happens to a tax rule that exists: its end (TAX-F07), and deactivating and bringing it back (TAX-F08)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from live.errors import Conflict, NotFound
from live.models import OutboxEvent
from live.operations import get

from apps.tax import events
from apps.tax.models import TaxAlias, TaxCategory, TaxRule
from apps.tax.schemas.rules import RuleEndIn, RuleRefIn
from apps.tax.services.rule_lifecycle import activate_rule, deactivate_rule, end_rule

from .conftest import HUB_DB, A, category, create_rule, outbox, refused, run

# tax.rule.end (TAX-F07)


@HUB_DB
def test_end_a_rule_and_schedule_the_next_rate(no_seed):
    assert get("tax.rule.end") is end_rule
    category()
    current = create_rule(valid_from="2012-09-01")
    OutboxEvent.objects.all().delete()
    ended = run("tax.rule.end", RuleEndIn(id=current.id, valid_to="2026-12-31"))
    assert ended.valid_to == date(2026, 12, 31)
    assert outbox() == [
        (events.RULE_ENDED, A.key, {"id": str(current.id), "valid_to": "2026-12-31"})
    ]
    create_rule(
        rate_pct="22", valid_from="2027-01-01"
    )  # the day after: contiguous, allowed


@HUB_DB
def test_end_a_rule_named_by_its_slot(no_seed):
    category("restaurant.food", "Restaurant — food", system=True)
    current = create_rule(tax_category_key="restaurant.food", rate_pct="10")
    data = RuleEndIn(
        country_code="ES",
        tax_category_key="Restauración — comida",
        valid_to="2030-12-31",
    )
    assert run("tax.rule.end", data).id == current.id


@HUB_DB
def test_an_end_before_the_start_is_refused(no_seed):
    category()
    rule = create_rule(valid_from="2026-06-01")
    error = refused(
        Conflict,
        lambda: run("tax.rule.end", RuleEndIn(id=rule.id, valid_to="2026-05-31")),
    )
    assert (error.code, error.fields) == (
        "tax.rule_end_invalid",
        {"valid_to": "That rule cannot end before the day it starts."},
    )
    # Its first day is a valid last day: a one-day rule.
    assert run(
        "tax.rule.end", RuleEndIn(id=rule.id, valid_to="2026-06-01")
    ).valid_to == date(2026, 6, 1)


@HUB_DB
def test_an_end_that_runs_into_the_next_rule_is_refused(no_seed):
    category()
    old = create_rule(valid_to="2026-12-31")
    create_rule(rate_pct="22", valid_from="2027-01-01")
    error = refused(
        Conflict,
        lambda: run("tax.rule.end", RuleEndIn(id=old.id, valid_to="2027-01-01")),
    )
    assert (error.code, list(error.fields)) == ("tax.rule_overlaps", ["valid_to"])
    assert TaxRule.objects.get(pk=old.id).valid_to == date(2026, 12, 31)


@HUB_DB
def test_the_same_end_again_changes_nothing(no_seed):
    category()
    rule = create_rule(valid_to="2026-12-31")
    OutboxEvent.objects.all().delete()
    assert run(
        "tax.rule.end", RuleEndIn(id=rule.id, valid_to="2026-12-31")
    ).valid_to == date(2026, 12, 31)
    assert outbox() == []


@HUB_DB
def test_ending_a_missing_rule(no_seed):
    error = refused(
        NotFound,
        lambda: run("tax.rule.end", RuleEndIn(id=uuid.uuid7(), valid_to="2026-12-31")),
    )
    assert str(error.message) == "This tax rule no longer exists."
    refused(
        NotFound,
        lambda: run(
            "tax.rule.end",
            RuleEndIn(country_code="ES", tax_category_key="x", valid_to="2026-12-31"),
        ),
    )


# tax.rule.deactivate and tax.rule.activate (TAX-F08)


@HUB_DB
def test_deactivate_and_bring_back(no_seed):
    assert get("tax.rule.deactivate") is deactivate_rule and get("tax.rule.activate") is activate_rule
    category()
    root = create_rule()
    surcharge = create_rule(rate_pct="5.2", parent_id=root.id, tax_type="surcharge")
    OutboxEvent.objects.all().delete()

    off = run("tax.rule.deactivate", RuleRefIn(id=root.id))
    assert off.is_active is False
    # Nothing else moves: its rate, its dates and its components stay as they were.
    assert TaxRule.objects.get(pk=surcharge.id).is_active is True
    on = run("tax.rule.activate", RuleRefIn(id=root.id))
    assert (on.is_active, on.rate_pct, on.valid_from) == (True, Decimal("21.00"), None)
    assert outbox() == [
        (events.RULE_DEACTIVATED, A.key, {"id": str(root.id)}),
        (events.RULE_ACTIVATED, A.key, {"id": str(root.id)}),
    ]


@HUB_DB
def test_named_by_voice_deactivate_takes_the_rule_in_force_and_activate_the_latest_deactivated(
    no_seed,
):
    category("restaurant.food", "Restaurant — food", system=True)
    today = timezone.localdate()
    current = create_rule(
        tax_category_key="restaurant.food",
        rate_pct="10",
        valid_to=today + timedelta(days=30),
    )
    create_rule(
        tax_category_key="restaurant.food",
        rate_pct="12",
        valid_from=today + timedelta(days=31),
    )
    by_slot = RuleRefIn(country_code="ES", tax_category_key="comida")
    TaxAlias.objects.create(
        alias="comida", category=TaxCategory.objects.get(key="restaurant.food")
    )
    assert run("tax.rule.deactivate", by_slot).id == current.id
    assert run("tax.rule.activate", by_slot).id == current.id


@HUB_DB
def test_twice_is_refused(no_seed):
    category()
    rule = create_rule()
    error = refused(Conflict, lambda: run("tax.rule.activate", RuleRefIn(id=rule.id)))
    assert (error.code, str(error.message)) == (
        "tax.rule_already_active",
        "That rule is already active.",
    )
    run("tax.rule.deactivate", RuleRefIn(id=rule.id))
    error = refused(Conflict, lambda: run("tax.rule.deactivate", RuleRefIn(id=rule.id)))
    assert (error.code, str(error.message)) == (
        "tax.rule_already_inactive",
        "That rule is already deactivated.",
    )


@HUB_DB
def test_a_missing_rule_is_not_found(no_seed):
    for name in ("tax.rule.deactivate", "tax.rule.activate"):
        refused(NotFound, lambda name=name: run(name, RuleRefIn(id=uuid.uuid7())))


@HUB_DB
def test_bringing_back_a_rule_that_now_overlaps_is_refused(no_seed):
    category()
    old = create_rule(rate_pct="18")
    run("tax.rule.deactivate", RuleRefIn(id=old.id))
    create_rule(rate_pct="21", valid_from="2020-01-01")
    error = refused(Conflict, lambda: run("tax.rule.activate", RuleRefIn(id=old.id)))
    assert error.code == "tax.rule_overlaps"
    assert TaxRule.objects.get(pk=old.id).is_active is False


@HUB_DB
def test_reactivating_by_slot_brings_the_most_recently_deactivated(no_seed):
    # Review: it used to bring the one with the newest start (R2, a future rate), not the one the
    # owner just deactivated by mistake (R1, today's) — the WORKBOOK and the ai text say «the last one».
    category()
    today = timezone.localdate()
    r1 = create_rule(rate_pct="21", valid_to=today + timedelta(days=30))
    r2 = create_rule(rate_pct="22", valid_from=today + timedelta(days=31))
    run("tax.rule.deactivate", RuleRefIn(id=r2.id))
    TaxRule.objects.filter(pk=r2.id).update(updated_at=timezone.now() - timedelta(days=30))
    run("tax.rule.deactivate", RuleRefIn(id=r1.id))

    back = run("tax.rule.activate", RuleRefIn(country_code="ES", tax_category_key="product.generic"))

    assert back.id == r1.id
    assert TaxRule.objects.get(pk=r2.id).is_active is False
