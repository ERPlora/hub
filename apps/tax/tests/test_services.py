"""Write operations of the tax app: one transaction each, with its event in the outbox.

The cases are those of the current product's batteries: overlapping rules refused (taxes#66),
concurrently too (taxes#69); no rate on a class that charges no tax and coherent components
(taxes#9, #59); a closed jurisdiction (taxes#41); end, deactivate and reactivate (taxes#52).
"""

import json
import threading
import uuid
from datetime import date, timedelta
from decimal import Decimal

import psycopg
import pytest
from django.db import connection, transaction
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.tax import events
from apps.tax.models import TaxAlias, TaxCategory, TaxRule
from apps.tax.schemas import (
    AliasIn,
    AliasOut,
    CategoryIn,
    CategoryOut,
    RuleBulkIn,
    RuleBulkOut,
    RuleEndIn,
    RuleIn,
    RuleOut,
    RuleRefIn,
)

from .conftest import A, B, ctx_for

WAIT = 1.0
QUIET = 0.3


def run(name, data, role="hub_admin", scope=A):
    return get(name)(ctx_for(role, scope), data)


def outbox():
    return list(OutboxEvent.objects.values_list("name", "scope_key", "payload"))


def category(key="product.generic", name=None, **fields):
    return TaxCategory.objects.create(key=key, name=name or key, **fields)


def create_rule(role="hub_admin", scope=A, **fields):
    data = {
        "country_code": "ES",
        "tax_category_key": "product.generic",
        "rate_pct": "21",
        **fields,
    }
    return run("tax.rule.create", RuleIn(**data), role, scope)


def refused(error, make):
    with pytest.raises(error) as excinfo:
        make()
    return excinfo.value


# Declarations: the assistant sees every write, and how risky it is


@pytest.mark.parametrize(
    ("name", "input", "output", "expose_api", "risk"),
    [
        ("tax.category.create", CategoryIn, CategoryOut, False, "normal"),
        ("tax.alias.create", AliasIn, AliasOut, False, "normal"),
        # A rule decides what is charged and declared: fiscal, so high.
        ("tax.rule.create", RuleIn, RuleOut, False, "high"),
        ("tax.rule.bulk_create", RuleBulkIn, RuleBulkOut, False, "high"),
        ("tax.rule.end", RuleEndIn, RuleOut, True, "high"),
        ("tax.rule.deactivate", RuleRefIn, RuleOut, False, "high"),
        ("tax.rule.activate", RuleRefIn, RuleOut, True, "high"),
    ],
)
def test_declarations(name, input, output, expose_api, risk):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "command",
        "tax.manage",
        input,
        output,
        expose_api,
    )
    assert (
        op.ai["description"].strip()
        and op.ai["risk"] == risk
        and set(op.ai) == {"description", "risk"}
    )


# tax.category.create (TAX-F02)


@pytest.mark.django_db
def test_create_an_own_category(no_seed):
    created = run(
        "tax.category.create",
        CategoryIn(key="product.books", name="Libros", description="Papel"),
    )
    books = TaxCategory.objects.get()
    assert created.model_dump() == {
        "id": books.id,
        "key": "product.books",
        "name": "Libros",
        "description": "Papel",
        "display_name": "Libros",
        "display_description": "Papel",
        "is_system": False,
        "is_active": True,
    }
    assert outbox() == [
        (events.CATEGORY_CREATED, "a", {"id": str(books.id), "key": "product.books"})
    ]


@pytest.mark.django_db
def test_a_category_may_be_marked_as_system(no_seed):
    assert (
        run(
            "tax.category.create", CategoryIn(key="product.x", name="X", is_system=True)
        ).is_system
        is True
    )


@pytest.mark.django_db
def test_a_repeated_key_is_refused_on_its_field(no_seed):
    category("product.books")
    error = refused(
        Conflict,
        lambda: run(
            "tax.category.create", CategoryIn(key="product.books", name="Other")
        ),
    )
    assert (error.status, error.code) == (409, "tax.category_exists")
    assert error.fields == {"key": "There is already a tax category with that key."}
    assert TaxCategory.objects.count() == 1 and outbox() == []


# tax.alias.create (TAX-F14)


@pytest.mark.django_db
def test_create_an_alias_naming_the_category_by_voice(no_seed):
    food = category("restaurant.food", "Restaurant — food", is_system=True)
    created = run(
        "tax.alias.create",
        AliasIn(alias="  Comida  Casera ", tax_category_key="Restauración — comida"),
    )
    alias = TaxAlias.objects.get()
    assert (alias.alias, alias.category, alias.source, alias.is_active) == (
        "comida casera",
        food,
        "learned",
        True,
    )
    assert (created.alias, created.tax_category_key, created.source) == (
        "comida casera",
        "restaurant.food",
        "learned",
    )
    assert outbox() == [
        (
            events.ALIAS_CREATED,
            "a",
            {
                "id": str(alias.id),
                "alias": "comida casera",
                "tax_category_key": "restaurant.food",
            },
        )
    ]


@pytest.mark.django_db
def test_a_repeated_alias_is_refused_on_its_field(no_seed):
    food = category("restaurant.food")
    TaxAlias.objects.create(alias="beer", category=food)
    error = refused(
        Conflict,
        lambda: run(
            "tax.alias.create",
            AliasIn(alias="BEER", tax_category_key="restaurant.food"),
        ),
    )
    assert (error.code, error.fields) == (
        "tax.alias_exists",
        {"alias": "That alias already exists."},
    )
    assert outbox() == []


@pytest.mark.django_db
def test_an_alias_of_an_unknown_category_is_refused_on_its_field(no_seed):
    error = refused(
        InvalidPayload,
        lambda: run(
            "tax.alias.create", AliasIn(alias="beer", tax_category_key="nothing")
        ),
    )
    assert (error.status, error.code) == (422, "invalid_field")
    assert error.fields == {"tax_category_key": "This tax category does not exist."}
    assert not TaxAlias.objects.exists()


# tax.rule.create (TAX-F04, F05, F06, F11)


@pytest.mark.django_db
def test_create_a_root_rule(no_seed):
    generic = category()
    created = create_rule(valid_from="2026-01-01")
    rule = TaxRule.objects.get()
    assert (rule.category, rule.country_code, rule.region_code, rule.rate_pct) == (
        generic,
        "ES",
        "",
        Decimal("21.00"),
    )
    assert (
        created.id,
        created.tax_category_key,
        created.valid_from,
        created.is_active,
    ) == (
        rule.id,
        "product.generic",
        date(2026, 1, 1),
        True,
    )
    assert outbox() == [
        (
            events.RULE_CREATED,
            "a",
            {
                "id": str(rule.id),
                "country_code": "ES",
                "region_code": None,
                "tax_category_key": "product.generic",
                "rate_pct": "21.00",
            },
        )
    ]
    assert OutboxEvent.objects.get().actor == "tester"


@pytest.mark.django_db
def test_the_category_of_a_rule_is_found_by_name_or_alias(no_seed):
    food = category("restaurant.food", "Restaurant — food", is_system=True)
    TaxAlias.objects.create(alias="meal", category=food)
    create_rule(
        tax_category_key="Restauración — comida", rate_pct="10", valid_to="2025-12-31"
    )
    create_rule(tax_category_key="meal", rate_pct="10", valid_from="2026-01-01")
    assert (
        list(TaxRule.objects.values_list("category__key", flat=True))
        == ["restaurant.food"] * 2
    )


@pytest.mark.django_db
def test_a_rule_of_an_unknown_category_is_refused_on_its_field(no_seed):
    error = refused(
        InvalidPayload, lambda: create_rule(tax_category_key="nothing.here")
    )
    assert error.fields == {"tax_category_key": "This tax category does not exist."}
    assert not TaxRule.objects.exists() and outbox() == []


@pytest.mark.django_db
def test_an_exempt_rule_keeps_its_cause_and_another_class_drops_it(no_seed):
    category("service.health"), category()
    exempt = create_rule(
        tax_category_key="service.health",
        rate_pct="0",
        operation_class="exempt",
        exempt_reason="e1",
        regime_key="01",
    )
    assert (exempt.operation_class, exempt.exempt_reason, exempt.regime_key) == (
        "exempt",
        "E1",
        "01",
    )
    subject = create_rule(country_code="PT", exempt_reason="E1")
    assert (
        subject.exempt_reason is None
    )  # a cause only means something on an exempt rule


@pytest.mark.django_db
def test_a_regional_rule_with_its_tax_family(no_seed):
    category()
    canary = create_rule(region_code="ES-CN", rate_pct="7", tax_type="igic")
    assert (canary.region_code, canary.tax_type) == ("ES-CN", "igic")


# Components (taxes#9, #59)


@pytest.mark.django_db
def test_a_component_hangs_from_a_coherent_root(no_seed):
    category()
    root = create_rule()
    surcharge = create_rule(
        rate_pct="5.2",
        tax_type="surcharge",
        parent_id=root.id,
        component_label="Recargo de equivalencia",
    )
    assert (surcharge.parent_id, surcharge.component_label) == (
        root.id,
        "Recargo de equivalencia",
    )


@pytest.mark.django_db
def test_an_incoherent_component_is_refused(no_seed):
    generic, food = category(), category("restaurant.food")
    root = TaxRule.objects.create(
        category=generic, country_code="ES", rate_pct=Decimal("21")
    )
    component = TaxRule.objects.create(
        category=generic, country_code="ES", rate_pct=Decimal("1"), parent=root
    )
    exempt_root = TaxRule.objects.create(
        category=food,
        country_code="ES",
        rate_pct=Decimal("0"),
        operation_class="exempt",
    )
    OutboxEvent.objects.all().delete()
    cases = [
        {"parent_id": uuid.uuid7()},  # no such rule
        {"parent_id": component.id},  # a component of a component
        {"parent_id": root.id, "country_code": "PT"},  # another country
        {"parent_id": root.id, "region_code": "ES-CN"},  # another region
        {
            "parent_id": root.id,
            "tax_category_key": "restaurant.food",
        },  # another category
        # A rate under a root that charges no tax would add a quota to a tax-free operation.
        {
            "parent_id": exempt_root.id,
            "tax_category_key": "restaurant.food",
            "rate_pct": "5.2",
        },
    ]
    for case in cases:
        error = refused(Conflict, lambda case=case: create_rule(**case))
        assert (error.status, error.code) == (409, "tax.rule_incoherent"), case
        assert list(error.fields) == ["parent_id"]
    assert TaxRule.objects.count() == 3 and outbox() == []
    # At 0 % under the tax-free root it is legitimate.
    create_rule(
        parent_id=exempt_root.id, tax_category_key="restaurant.food", rate_pct="0"
    )


# Overlaps (taxes#66): two active root rules of one slot are never in force the same day


def overlap(**fields):
    error = refused(Conflict, lambda: create_rule(**fields))
    assert (error.status, error.code) == (409, "tax.rule_overlaps")
    assert list(error.fields) == ["valid_from"]
    return error


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_inside_or_starting_the_same_day_is_an_overlap(no_seed):
    category()
    create_rule(valid_from="2026-01-01", valid_to="2026-12-31")
    overlap(valid_from="2026-03-01", valid_to="2026-03-31")
    overlap(valid_from="2026-01-01", valid_to="2026-01-01")
    overlap(valid_to="2026-01-01")  # since always, up to its first day
    overlap(valid_from="2026-12-31")  # from its last day on


@pytest.mark.django_db
def test_contiguous_ranges_are_the_way_to_change_a_rate(no_seed):
    category()
    create_rule(valid_to="2026-12-31")
    create_rule(rate_pct="22", valid_from="2027-01-01")
    assert TaxRule.objects.count() == 2


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_a_deactivated_rule_does_not_count(no_seed):
    generic = category()
    TaxRule.objects.create(
        category=generic, country_code="ES", rate_pct=Decimal("18"), is_active=False
    )
    # Its days do not count for an overlap. Another first day: the very same one is the deactivated
    # rule's natural key (review point 6, test_a_twin_of_a_deactivated_rule_is_refused_on_its_first_day).
    create_rule(valid_from="2020-01-01")
    assert TaxRule.objects.filter(is_active=True).count() == 1


# tax.rule.bulk_create (TAX-F12): every check of a single rule, all or none


@pytest.mark.django_db
def test_bulk_creates_every_rule(no_seed):
    for key in ("product.generic", "product.reduced", "product.super_reduced"):
        category(key)
    rows = [
        {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"},
        {"country_code": "es", "tax_category_key": "product.reduced", "rate_pct": "10"},
        {
            "country_code": "ES",
            "tax_category_key": "product.super_reduced",
            "rate_pct": "4",
        },
    ]
    created = run("tax.rule.bulk_create", RuleBulkIn(rules=rows))
    assert [(r.tax_category_key, r.rate_pct) for r in created.rules] == [
        ("product.generic", Decimal("21.00")),
        ("product.reduced", Decimal("10.00")),
        ("product.super_reduced", Decimal("4.00")),
    ]
    assert [name for name, _scope, _payload in outbox()] == [events.RULE_CREATED] * 3


@pytest.mark.django_db
def test_bulk_with_an_unknown_category_saves_nothing(no_seed):
    category()
    rows = [
        {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"},
        {"country_code": "ES", "tax_category_key": "nothing.here", "rate_pct": "10"},
    ]
    error = refused(
        InvalidPayload, lambda: run("tax.rule.bulk_create", RuleBulkIn(rules=rows))
    )
    assert error.fields == {
        "rules.1.tax_category_key": "This tax category does not exist."
    }
    assert not TaxRule.objects.exists() and outbox() == []


@pytest.mark.django_db
def test_bulk_overlapping_an_existing_rule_or_itself_saves_nothing(no_seed):
    category(), category("restaurant.food")
    create_rule(country_code="PT", rate_pct="23")
    OutboxEvent.objects.all().delete()
    rows = [
        {"country_code": "ES", "tax_category_key": "restaurant.food", "rate_pct": "10"},
        {
            "country_code": "PT",
            "tax_category_key": "product.generic",
            "rate_pct": "25",
            "valid_from": "2027-01-01",
        },
        {
            "country_code": "ES",
            "tax_category_key": "restaurant.food",
            "rate_pct": "12",
            "valid_from": "2030-01-01",
        },
    ]
    error = refused(
        Conflict, lambda: run("tax.rule.bulk_create", RuleBulkIn(rules=rows))
    )
    assert (error.code, sorted(error.fields)) == (
        "tax.rule_overlaps",
        ["rules.1.valid_from", "rules.2.valid_from"],
    )
    assert TaxRule.objects.count() == 1 and outbox() == []


# tax.rule.end (TAX-F07)


@pytest.mark.django_db
def test_end_a_rule_and_schedule_the_next_rate(no_seed):
    category()
    current = create_rule(valid_from="2012-09-01")
    OutboxEvent.objects.all().delete()
    ended = run("tax.rule.end", RuleEndIn(id=current.id, valid_to="2026-12-31"))
    assert ended.valid_to == date(2026, 12, 31)
    assert outbox() == [
        (events.RULE_ENDED, "a", {"id": str(current.id), "valid_to": "2026-12-31"})
    ]
    create_rule(
        rate_pct="22", valid_from="2027-01-01"
    )  # the day after: contiguous, allowed


@pytest.mark.django_db
def test_end_a_rule_named_by_its_slot(no_seed):
    category("restaurant.food", "Restaurant — food", is_system=True)
    current = create_rule(tax_category_key="restaurant.food", rate_pct="10")
    data = RuleEndIn(
        country_code="ES",
        tax_category_key="Restauración — comida",
        valid_to="2030-12-31",
    )
    assert run("tax.rule.end", data).id == current.id


@pytest.mark.django_db
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_the_same_end_again_changes_nothing(no_seed):
    category()
    rule = create_rule(valid_to="2026-12-31")
    OutboxEvent.objects.all().delete()
    assert run(
        "tax.rule.end", RuleEndIn(id=rule.id, valid_to="2026-12-31")
    ).valid_to == date(2026, 12, 31)
    assert outbox() == []


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_deactivate_and_bring_back(no_seed):
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
        (events.RULE_DEACTIVATED, "a", {"id": str(root.id)}),
        (events.RULE_ACTIVATED, "a", {"id": str(root.id)}),
    ]


@pytest.mark.django_db
def test_named_by_voice_deactivate_takes_the_rule_in_force_and_activate_the_latest_deactivated(
    no_seed,
):
    category("restaurant.food", "Restaurant — food", is_system=True)
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_a_missing_rule_is_not_found(no_seed):
    for name in ("tax.rule.deactivate", "tax.rule.activate"):
        refused(NotFound, lambda name=name: run(name, RuleRefIn(id=uuid.uuid7())))


@pytest.mark.django_db
def test_bringing_back_a_rule_that_now_overlaps_is_refused(no_seed):
    category()
    old = create_rule(rate_pct="18")
    run("tax.rule.deactivate", RuleRefIn(id=old.id))
    create_rule(rate_pct="21", valid_from="2020-01-01")
    error = refused(Conflict, lambda: run("tax.rule.activate", RuleRefIn(id=old.id)))
    assert error.code == "tax.rule_overlaps"
    assert TaxRule.objects.get(pk=old.id).is_active is False


# Permissions


@pytest.mark.django_db
def test_an_employee_cannot_write(no_seed):
    category()
    rule = create_rule()
    OutboxEvent.objects.all().delete()
    attempts = [
        ("tax.category.create", CategoryIn(key="product.x", name="X")),
        ("tax.alias.create", AliasIn(alias="x", tax_category_key="product.generic")),
        (
            "tax.rule.create",
            RuleIn(
                country_code="PT", tax_category_key="product.generic", rate_pct="23"
            ),
        ),
        (
            "tax.rule.bulk_create",
            RuleBulkIn(
                rules=[
                    {
                        "country_code": "PT",
                        "tax_category_key": "product.generic",
                        "rate_pct": "23",
                    }
                ]
            ),
        ),
        ("tax.rule.end", RuleEndIn(id=rule.id, valid_to="2030-01-01")),
        ("tax.rule.deactivate", RuleRefIn(id=rule.id)),
        ("tax.rule.activate", RuleRefIn(id=rule.id)),
    ]
    for name, data in attempts:
        refused(
            PermissionDenied,
            lambda name=name, data=data: run(name, data, role="hub_employee"),
        )
    assert (
        TaxCategory.objects.count(),
        TaxRule.objects.count(),
        TaxAlias.objects.count(),
    ) == (1, 1, 0)
    assert TaxRule.objects.get().is_active and outbox() == []


# Two people saving at the same instant (taxes#69): the second waits for the first, then is refused


def _in_thread(target):
    outcome = {}

    def body():
        try:
            outcome["result"] = target()
        except Exception as error:  # the outcome is asserted by the test
            outcome["error"] = error
        finally:
            connection.close()

    thread = threading.Thread(target=body)
    thread.start()
    return thread, outcome


@pytest.mark.django_db(transaction=True)
def test_two_overlapping_rules_saved_at_once_keep_one():
    TaxCategory.objects.create(key="product.race", name="Race")
    rule = {"country_code": "FR", "tax_category_key": "product.race"}
    first_saved, release = threading.Event(), threading.Event()

    def first():
        with transaction.atomic():  # stays open, holding what it wrote, until released
            created = create_rule(**rule, rate_pct="20")
            first_saved.set()
            release.wait(5)
        return created

    holder, held = _in_thread(first)
    assert first_saved.wait(5)
    second, outcome = _in_thread(
        lambda: create_rule(**rule, rate_pct="25", valid_from="2027-01-01")
    )
    second.join(QUIET)
    assert (
        second.is_alive()
    )  # it waits for the first one, it does not run its check blind
    release.set()
    holder.join(5)
    second.join(5)

    assert "result" in held
    assert (
        isinstance(outcome.get("error"), Conflict)
        and outcome["error"].code == "tax.rule_overlaps"
    )
    assert list(
        TaxRule.objects.filter(category__key="product.race").values_list(
            "rate_pct", flat=True
        )
    ) == [Decimal("20.00")]


@pytest.mark.django_db(transaction=True)
def test_two_rules_that_do_not_overlap_saved_at_once_are_both_kept():
    TaxCategory.objects.create(key="product.race", name="Race")
    rule = {"country_code": "FR", "tax_category_key": "product.race"}
    first_saved, release = threading.Event(), threading.Event()

    def first():
        with transaction.atomic():
            create_rule(**rule, rate_pct="20", valid_to="2026-12-31")
            first_saved.set()
            release.wait(5)

    holder, _held = _in_thread(first)
    assert first_saved.wait(5)
    second, outcome = _in_thread(
        lambda: create_rule(**rule, rate_pct="25", valid_from="2027-01-01")
    )
    release.set()
    holder.join(5)
    second.join(5)
    assert "result" in outcome
    assert TaxRule.objects.filter(category__key="product.race").count() == 2


# Notifications: after the COMMIT, on the channel of the command's scope only


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@pytest.mark.django_db(transaction=True)
def test_a_rule_saved_in_b_notifies_the_channel_of_b_only(listen):
    TaxCategory.objects.create(key="product.notify", name="Notify")
    on_a, on_b = listen(A), listen(B)

    create_rule(country_code="FR", tax_category_key="product.notify", scope=B)

    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.RULE_CREATED]})
    ]
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_refused_rule_notifies_nobody(listen):
    TaxCategory.objects.create(key="product.notify", name="Notify")
    create_rule(country_code="FR", tax_category_key="product.notify", scope=B)
    on_b = listen(B)

    with pytest.raises(Conflict):
        create_rule(
            country_code="FR", tax_category_key="product.notify", rate_pct="25", scope=B
        )

    assert received(on_b, timeout=QUIET) == []


@pytest.mark.django_db
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


def _race(first_write, second_write):
    """Run ``first_write`` in a transaction that stays open, then ``second_write`` in another session.

    Returns whether the second one was still waiting while the first was open, and its outcome.
    """
    first_saved, release = threading.Event(), threading.Event()

    def first():
        with transaction.atomic():
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
    assert "error" not in held, held
    return waited, outcome


def _overlap_refused(waited, outcome):
    assert waited  # it waits for the first one, it does not run its check blind
    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "tax.rule_overlaps", outcome


@pytest.mark.django_db(transaction=True)
def test_bringing_back_a_rule_while_an_overlapping_one_is_saved_keeps_one():
    race = TaxCategory.objects.create(key="product.race", name="Race")
    old = TaxRule.objects.create(category=race, country_code="FR", rate_pct=Decimal("18"), is_active=False)

    waited, outcome = _race(
        lambda: run("tax.rule.activate", RuleRefIn(id=old.id)),
        lambda: create_rule(country_code="FR", tax_category_key="product.race", rate_pct="25", valid_from="2027-01-01"),
    )

    _overlap_refused(waited, outcome)
    assert list(TaxRule.objects.filter(category=race, is_active=True).values_list("pk", flat=True)) == [old.pk]


@pytest.mark.django_db(transaction=True)
def test_moving_an_end_while_an_overlapping_rule_is_saved_keeps_them_apart():
    race = TaxCategory.objects.create(key="product.race", name="Race")
    old = TaxRule.objects.create(category=race, country_code="FR", rate_pct=Decimal("20"), valid_to=date(2026, 12, 31))

    waited, outcome = _race(
        lambda: run("tax.rule.end", RuleEndIn(id=old.id, valid_to="2027-06-30")),
        lambda: create_rule(country_code="FR", tax_category_key="product.race", rate_pct="25", valid_from="2027-01-01"),
    )

    _overlap_refused(waited, outcome)
    assert TaxRule.objects.filter(category=race).count() == 1


@pytest.mark.django_db(transaction=True)
def test_a_batch_and_an_overlapping_rule_saved_at_once_keep_one():
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


@pytest.mark.django_db
def test_a_twin_of_a_deactivated_rule_is_refused_on_its_first_day(no_seed):
    # Review (the current product's natural key): the deactivated rule keeps its key; bring it back
    # or start the new one another day.
    category()
    old = create_rule(valid_from="2026-01-01")
    run("tax.rule.deactivate", RuleRefIn(id=old.id))
    OutboxEvent.objects.all().delete()
    error = refused(Conflict, lambda: create_rule(rate_pct="22", valid_from="2026-01-01"))
    assert (error.status, error.code) == (409, "tax.rule_exists")
    assert error.fields == {
        "valid_from": "There is already a rule of this country, region and category from that day, perhaps "
        "deactivated: reactivate it or start this one another day."
    }
    assert TaxRule.objects.count() == 1 and outbox() == []
    create_rule(rate_pct="22", valid_from="2026-01-02")  # another first day is another rule


@pytest.mark.django_db
def test_a_batch_with_a_twin_saves_nothing(no_seed):
    category()
    TaxRule.objects.create(
        category=TaxCategory.objects.get(), country_code="PT", rate_pct=Decimal("23"), is_active=False
    )
    rows = [{"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"},
            {"country_code": "PT", "tax_category_key": "product.generic", "rate_pct": "23"}]  # fmt: skip
    error = refused(Conflict, lambda: run("tax.rule.bulk_create", RuleBulkIn(rules=rows)))
    assert (error.code, list(error.fields)) == ("tax.rule_exists", ["rules.1.valid_from"])
    assert TaxRule.objects.count() == 1


@pytest.mark.django_db
def test_a_batch_with_twin_rows_is_refused_as_an_overlap_not_a_crash(no_seed):
    # Two identical rows (or a row identical to an active rule) overlap: refused with its field,
    # never a database error on the natural key.
    category()
    create_rule(country_code="PT", rate_pct="23")
    rows = [{"country_code": "PT", "tax_category_key": "product.generic", "rate_pct": "23"},
            {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"},
            {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"}]  # fmt: skip
    error = refused(Conflict, lambda: run("tax.rule.bulk_create", RuleBulkIn(rules=rows)))
    assert (error.code, sorted(error.fields)) == ("tax.rule_overlaps", ["rules.0.valid_from", "rules.2.valid_from"])
    assert TaxRule.objects.count() == 1
