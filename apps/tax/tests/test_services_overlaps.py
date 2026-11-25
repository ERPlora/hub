"""Two active root rules of one country, region and category never apply on the same day, also when two people save
at the same instant."""

import threading
from datetime import date
from decimal import Decimal

from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import atomic

from apps.tax.models import TaxCategory, TaxRule
from apps.tax.schemas.rules import RuleBulkIn, RuleEndIn, RuleOut, RuleRefIn
from apps.tax.services.overlaps import _overlapping

from base.tenancy.tests.concurrency import in_a_thread

from .conftest import HUB_DB, HUB_DB_COMMITTED, QUIET, category, create_rule, outbox, refused, run

# Overlaps: two active root rules of one slot are never in force the same day


def overlap(**fields):
    error = refused(Conflict, lambda: create_rule(**fields))
    assert (error.status, error.code) == (409, "tax.rule_overlaps")
    assert list(error.fields) == ["valid_from"]
    return error


@HUB_DB
def test_the_case_of_the_issue_is_refused(no_seed):
    # «PT · general 23 %» with no end, and «PT · general 25 % from 2027-01-01» on top of it.
    category()
    create_rule(country_code="PT", rate_pct="23")
    OutboxEvent.objects.all().delete()
    error = overlap(country_code="PT", rate_pct="25", valid_from="2027-01-01")
    assert str(error.message).startswith(
        "It overlaps another active rule of this country, region and category"
    )
    assert TaxRule.objects.count() == 1 and outbox() == []


@HUB_DB
def test_inside_or_starting_the_same_day_is_an_overlap(no_seed):
    category()
    create_rule(valid_from="2026-01-01", valid_to="2026-12-31")
    overlap(valid_from="2026-03-01", valid_to="2026-03-31")
    overlap(valid_from="2026-01-01", valid_to="2026-01-01")
    overlap(valid_to="2026-01-01")  # since always, up to its first day
    overlap(valid_from="2026-12-31")  # from its last day on


@HUB_DB
def test_contiguous_ranges_are_the_way_to_change_a_rate(no_seed):
    category()
    create_rule(valid_to="2026-12-31")
    create_rule(rate_pct="22", valid_from="2027-01-01")
    assert TaxRule.objects.count() == 2


@HUB_DB
def test_other_slots_are_no_overlap(no_seed):
    category(), category("restaurant.food")
    root = create_rule()
    create_rule(tax_category_key="restaurant.food", rate_pct="10")
    create_rule(region_code="ES-CN", rate_pct="7", tax_type="igic")
    create_rule(country_code="PT", rate_pct="23")
    create_rule(
        rate_pct="5.2", parent_id=root.id, tax_type="surcharge"
    )  # a component shares the slot
    assert TaxRule.objects.count() == 5


@HUB_DB
def test_a_deactivated_rule_does_not_count(no_seed):
    generic = category()
    TaxRule.objects.create(
        category=generic, country_code="ES", rate_pct=Decimal("18"), is_active=False
    )
    # Its days do not count for an overlap. Another first day: the very same one is the deactivated
    # rule's natural key (review point 6, test_a_twin_of_a_deactivated_rule_is_refused_on_its_first_day).
    create_rule(valid_from="2020-01-01")
    assert TaxRule.objects.filter(is_active=True).count() == 1
    assert _overlapping(TaxRule.objects.get(is_active=True)) is None


# Two people saving at the same instant: the second waits for the first, then is refused


def _in_thread(target):
    """``target`` in its own thread and session of the business at work; its outcome in the list once it ends."""
    outcome = [None]
    thread = in_a_thread(target, outcome)
    thread.start()
    return thread, outcome


def _race(first_write, second_write):
    """Run ``first_write`` in a transaction that stays open, then ``second_write`` in another session.

    Returns whether the second one was still waiting while the first was open, and its outcome.
    """
    first_saved, release = threading.Event(), threading.Event()

    def first():
        with atomic():
            first_write()
            first_saved.set()
            release.wait(5)

    holder, held = _in_thread(first)
    assert first_saved.wait(5), held
    second, outcome = _in_thread(second_write)
    second.join(QUIET)
    waited = second.is_alive()
    release.set()
    holder.join(5)
    second.join(5)
    assert not (holder.is_alive() or second.is_alive())
    assert not isinstance(held[0], Exception), held
    return waited, outcome


def _overlap_refused(waited, outcome):
    assert waited  # it waits for the first one, it does not run its check blind
    assert isinstance(outcome[0], Conflict) and outcome[0].code == "tax.rule_overlaps", outcome


@HUB_DB_COMMITTED
def test_two_overlapping_rules_saved_at_once_keep_one(plan_with_room):
    TaxCategory.objects.create(key="product.race", name="Race")
    rule = {"country_code": "FR", "tax_category_key": "product.race"}

    waited, outcome = _race(
        lambda: create_rule(**rule, rate_pct="20"),
        lambda: create_rule(**rule, rate_pct="25", valid_from="2027-01-01"),
    )

    _overlap_refused(waited, outcome)
    assert list(
        TaxRule.objects.filter(category__key="product.race").values_list(
            "rate_pct", flat=True
        )
    ) == [Decimal("20.00")]


@HUB_DB_COMMITTED
def test_two_rules_that_do_not_overlap_saved_at_once_are_both_kept(plan_with_room):
    TaxCategory.objects.create(key="product.race", name="Race")
    rule = {"country_code": "FR", "tax_category_key": "product.race"}

    _waited, outcome = _race(
        lambda: create_rule(**rule, rate_pct="20", valid_to="2026-12-31"),
        lambda: create_rule(**rule, rate_pct="25", valid_from="2027-01-01"),
    )

    assert isinstance(outcome[0], RuleOut)
    assert TaxRule.objects.filter(category__key="product.race").count() == 2


@HUB_DB_COMMITTED
def test_bringing_back_a_rule_while_an_overlapping_one_is_saved_keeps_one(plan_with_room):
    race = TaxCategory.objects.create(key="product.race", name="Race")
    old = TaxRule.objects.create(category=race, country_code="FR", rate_pct=Decimal("18"), is_active=False)

    waited, outcome = _race(
        lambda: run("tax.rule.activate", RuleRefIn(id=old.id)),
        lambda: create_rule(country_code="FR", tax_category_key="product.race", rate_pct="25", valid_from="2027-01-01"),
    )

    _overlap_refused(waited, outcome)
    assert list(TaxRule.objects.filter(category=race, is_active=True).values_list("pk", flat=True)) == [old.pk]


@HUB_DB_COMMITTED
def test_moving_an_end_while_an_overlapping_rule_is_saved_keeps_them_apart(plan_with_room):
    race = TaxCategory.objects.create(key="product.race", name="Race")
    old = TaxRule.objects.create(category=race, country_code="FR", rate_pct=Decimal("20"), valid_to=date(2026, 12, 31))

    waited, outcome = _race(
        lambda: run("tax.rule.end", RuleEndIn(id=old.id, valid_to="2027-06-30")),
        lambda: create_rule(country_code="FR", tax_category_key="product.race", rate_pct="25", valid_from="2027-01-01"),
    )

    _overlap_refused(waited, outcome)
    assert TaxRule.objects.filter(category=race).count() == 1


@HUB_DB_COMMITTED
def test_a_batch_and_an_overlapping_rule_saved_at_once_keep_one(plan_with_room):
    TaxCategory.objects.create(key="product.race", name="Race")
    batch = RuleBulkIn(rules=[{"country_code": "FR", "tax_category_key": "product.race", "rate_pct": "20"}])

    waited, outcome = _race(
        lambda: run("tax.rule.bulk_create", batch),
        lambda: create_rule(country_code="FR", tax_category_key="product.race", rate_pct="25", valid_from="2027-01-01"),
    )

    _overlap_refused(waited, outcome)
    assert list(TaxRule.objects.filter(category__key="product.race").values_list("rate_pct", flat=True)) == [
        Decimal("20.00")
    ]
